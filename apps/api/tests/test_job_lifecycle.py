import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from secmate_api import jobs
from secmate_api.run_store import RunStore
from secmate_api.run_store import RunStoreError, digest


def accepted(tmp_path, kind="GENERATION"):
    source = tmp_path / "source"
    session = jobs.prepare(tmp_path / "active-run.lock", "chatmate-run-probe", kind, source)
    payload = {"run_id": session.run_id, "status": "QUEUED"}
    intent = session.intent(payload)
    RunStore(source).save(payload, job_intent=intent)
    session.acknowledge(intent)
    return session


def test_real_worker_gate_and_completion_for_harmless_probe(tmp_path):
    session = accepted(tmp_path)
    process = session.launch([sys.executable, "-c", "print('durable probe')"], stdout=jobs.subprocess.PIPE,
                             stderr=jobs.subprocess.PIPE, text=True)
    output, error = process.communicate(timeout=30)
    assert process.returncode == 0, error
    assert "durable probe" in output
    assert session.ledger.get(session.job_id)["worker_completion"] is True
    session.finish()


def test_gate_with_pinned_worker_interpreter_and_controller_heartbeat(tmp_path):
    worker_python = Path(__file__).resolve().parents[3] / "services" / "deepteam-worker" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not worker_python.exists():
        pytest.skip("Pinned worker environment is not installed")
    session = accepted(tmp_path)
    # Real API interpreter -> Python 3.11 worker. Stay alive through a controller
    # lease renewal to exercise both authorization and cross-process heartbeats.
    try:
        process = session.launch([str(worker_python), "-c", "import time; time.sleep(6); print('cross-version probe')"],
                                 stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
        output, error = process.communicate(timeout=30)
        assert process.returncode == 0, error
        assert "cross-version probe" in output
        assert session.state()["worker_completion"] is True
    finally:
        session.finish()


def publish(session, status=None):
    kind = session.state()["kind"]
    payload = {"run_id": session.run_id, "status": status or ("AWAITING_SELECTION" if kind == "GENERATION" else "COMPLETED")}
    if kind == "CRITIC":
        payload["critic_status"] = status or "COMPLETED"
    intent = session.intent(payload)
    RunStore(Path(session.value["source_root"])).save(payload, job_intent=intent)
    session.acknowledge(intent)


def test_all_job_kinds_share_one_atomic_worker_slot(tmp_path):
    ledger = jobs.JobLedger(tmp_path / "worker.lock")

    def claim(kind):
        try:
            return ledger.prepare("run-" + kind, kind, tmp_path / kind)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(claim, sorted(jobs.KINDS)))
    assert sum(value is not None for value in values) == 1
    assert len(ledger.active()) == 1


def test_expired_lease_never_authorizes_another_attempt(tmp_path):
    session = accepted(tmp_path)
    session.ledger.update(session.job_id, session.token, lease_until=0, lease_monotonic_until=0)
    with pytest.raises(FileExistsError):
        jobs.prepare(session.ledger.lock_path, "different-run", "CRITIC", tmp_path / "other")


def test_invalid_transitions_and_stale_tokens_fail_closed(tmp_path):
    session = accepted(tmp_path)
    with pytest.raises(RunStoreError, match="transition"):
        session.ledger.update(session.job_id, session.token, state="RUNNING")
    old = session.state()
    adopted = session.ledger._adopt(old, "UNCERTAIN", "test-fencing")
    assert adopted["token"] > session.token
    with pytest.raises(RunStoreError, match="fencing"):
        session.ledger.update(session.job_id, session.token, lease_until=time.time() + 30)
    with pytest.raises(RunStoreError):
        session.intent({"run_id": session.run_id, "status": "FAILED"})


def test_controller_singleton_rejects_a_second_controller(tmp_path):
    with jobs.ControllerGuard(tmp_path):
        with pytest.raises(RunStoreError, match="Another API"):
            with jobs.ControllerGuard(tmp_path):
                pytest.fail("Second controller must not enter")


def test_cancelled_queued_job_never_spawns(tmp_path, monkeypatch):
    session = accepted(tmp_path)
    session.ledger.update(session.job_id, session.token, cancel_requested=True)
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Must not dispatch"))
    with pytest.raises(RunStoreError, match="cancelled"):
        session.launch([sys.executable, "-c", "print('not executed')"])


def test_completion_files_and_marker_cannot_be_forged_without_journal_seal(tmp_path):
    session = accepted(tmp_path)
    output = tmp_path / "published" / "result.json"
    code = "import sys; from pathlib import Path; Path(sys.argv[sys.argv.index('--output')+1]).write_text('{\"trusted\":true}')"
    process = session.launch([sys.executable, "-c", code, "--output", str(output)], stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    process.communicate(timeout=30)
    assert json.loads(output.read_text()) == {"trusted": True}
    result = session.directory / "results" / "result.json"
    result.write_text('{"forged":true}')
    marker_path = session.directory / "completion.json"
    marker = json.loads(marker_path.read_text())
    import hashlib
    marker["files"]["result.json"] = hashlib.sha256(result.read_bytes()).hexdigest()
    marker_path.write_text(json.dumps(marker))
    with pytest.raises(RunStoreError, match="changed after sealing"):
        session.completion()


def test_worker_reads_sealed_input_even_if_file_changes_during_execution(tmp_path):
    session = accepted(tmp_path)
    original = tmp_path / "input.json"
    original.write_text('{"original":true}')
    output = tmp_path / "published" / "result.json"
    code = "import sys; from pathlib import Path; p=Path(sys.argv[sys.argv.index('--input')+1]); p.write_text('{\"altered\":true}'); data=sys.modules['__main__'].read_frozen(p); Path(sys.argv[sys.argv.index('--output')+1]).write_bytes(data)"
    process = session.launch([sys.executable, "-c", code, "--input", str(original), "--output", str(output)],
                             stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    _, error = process.communicate(timeout=30)
    assert process.returncode == 0, error
    assert json.loads(output.read_text()) == {"original": True}


@pytest.mark.parametrize("kind", sorted(jobs.KINDS))
def test_verified_completion_recovery_never_calls_popen(tmp_path, monkeypatch, kind):
    session = accepted(tmp_path, kind)
    process = session.launch([sys.executable, "-c", "print('completed once')"], stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    process.communicate(timeout=30)
    session.finish()  # no API publication: unresolved, but sealed completion exists
    monkeypatch.setattr(jobs, "_epoch", "new-controller-epoch")
    session.ledger.reconcile()
    restored = session.ledger.get(session.job_id)
    assert restored["state"] == "RESULT_READY"
    recovered = jobs.JobSession(session.ledger, restored)
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Recovery must not infer"))
    proxy = recovered.launch([sys.executable, "-c", "must not execute"])
    assert proxy.communicate(timeout=1) == ("", "")
    publish(recovered)
    assert recovered.finish()
    assert recovered.ledger.get(recovered.job_id)["state"] == "SUCCEEDED"


def test_publication_ack_failure_is_reconciled_without_inference(tmp_path, monkeypatch):
    session = accepted(tmp_path)
    payload = {"run_id": session.run_id, "status": "FAILED"}
    intent = session.intent(payload)
    RunStore(Path(session.value["source_root"])).save(payload, job_intent=intent)
    monkeypatch.setattr(session, "acknowledge", lambda intent: (_ for _ in ()).throw(RunStoreError("Injected lost acknowledgment")))
    with pytest.raises(RunStoreError, match="lost acknowledgment"):
        session.acknowledge(intent)
    monkeypatch.setattr(jobs, "_epoch", "next-controller")
    session.ledger.reconcile()
    assert session.ledger.get(session.job_id)["state"] == "FAILED"


def test_unsealed_started_attempt_stays_uncertain_until_explicit_ack(tmp_path):
    session = accepted(tmp_path)
    process = session.launch([sys.executable, "-c", "import time; time.sleep(30)"], stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    session.ledger.update(session.job_id, session.token, state="RECONCILING", authorized=False)
    process.communicate(timeout=10)
    publish(session, "FAILED")
    assert not session.finish()
    assert session.ledger.get(session.job_id)["state"] == "UNCERTAIN"
    with pytest.raises(FileExistsError):
        jobs.prepare(session.ledger.lock_path, "next-run", "JUDGE", tmp_path / "next")
    with pytest.raises(RunStoreError, match="acknowledgment"):
        session.ledger.resolve_uncertain(session.job_id, False)
    resolved = session.ledger.resolve_uncertain(session.job_id, True)
    assert resolved["state"] == "FAILED"


def test_request_cache_conflicts_and_does_not_store_response_bodies(tmp_path):
    cache = jobs.RequestCache(tmp_path / "worker.lock")
    assert cache.reserve("request-key", digest({"safe": True})) is None
    assert cache.reserve("request-key", digest({"safe": True}))["state"] == "PROCESSING"
    with pytest.raises(RunStoreError):
        cache.reserve("request-key", digest({"safe": False}))
    with cache.ledger.connection() as connection:
        assert "response_body" not in [row[1] for row in connection.execute("PRAGMA table_info(requests)")]


def test_http_create_idempotency_returns_one_committed_run(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from secmate_api import main, chatmate_runs as chat, deepteam_runs as deep
    from secmate_api.config import Settings
    root = tmp_path / "chat"
    lock = tmp_path / "worker.lock"
    python = tmp_path / "python.exe"
    python.touch()
    monkeypatch.setattr(chat, "CHATMATE_RUN_ROOT", root)
    monkeypatch.setattr(chat, "RUN_LOCK", lock)
    monkeypatch.setattr(deep, "RUN_LOCK", lock)
    monkeypatch.setattr(chat, "WORKER_PYTHON", python)
    monkeypatch.setattr(chat, "_runs", {})
    monkeypatch.setattr(chat, "_processes", {})
    monkeypatch.setattr(main, "get_settings", lambda: Settings("fake", "fake", 45))
    calls = []

    class Idle:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def start(self):
            pass

    monkeypatch.setattr(chat.threading, "Thread", Idle)
    client = TestClient(main.app)
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "same-request-key"}
    body = {"attack_profile_id": "prompt-injection-v1", "max_total_tokens": 50000, "authorization_attested": True}
    first = client.post("/api/v1/chatmate-runs", headers=headers, json=body)
    second = client.post("/api/v1/chatmate-runs", headers=headers, json=body)
    assert first.status_code == second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    assert len(calls) == 1
    conflict = client.post("/api/v1/chatmate-runs", headers=headers, json={**body, "max_total_tokens": 100000})
    assert conflict.status_code == 409
    assert client.post("/api/v1/chatmate-runs", headers={"Idempotency-Key": "same-request-key"}, json=body).status_code == 403
    assert client.post("/api/v1/chatmate-runs", headers={**headers, "Origin": "https://untrusted.example"}, json=body).status_code == 403
    assert client.post("/api/v1/chatmate-runs", headers=headers, json={**body, "authorization_attested": False}).status_code == 422
    fresh = {**headers, "Idempotency-Key": "unauthorized-first-key"}
    assert client.post("/api/v1/chatmate-runs", headers={"Idempotency-Key": fresh["Idempotency-Key"]}, json=body).status_code == 403
    request_key = digest(["POST", "/api/v1/chatmate-runs", fresh["Idempotency-Key"]])
    with jobs.JobLedger(lock).connection() as connection:
        assert connection.execute("SELECT 1 FROM requests WHERE request_key=?", (request_key,)).fetchone() is None


def test_request_outbox_replays_a_committed_action_after_lost_ack(tmp_path):
    cache = jobs.RequestCache(tmp_path / "worker.lock")
    assert cache.reserve("key", digest({}), 200) is None
    token = jobs._request.set({"key": "key"})
    try:
        payload = {"run_id": "chatmate-run-proof", "status": "AWAITING_RESPONSE"}
        jobs.persist(RunStore(tmp_path / "source"), tmp_path / "worker.lock", payload)
    finally:
        jobs._request.reset(token)
    entry = cache.reserve("key", digest({}))
    replay, status = cache.replay(entry, {"chatmate": tmp_path / "source"})
    assert replay == payload and status == 200


def test_request_outbox_replays_action_attached_to_existing_job(tmp_path):
    lock = tmp_path / "worker.lock"
    source = tmp_path / "source"
    cache = jobs.RequestCache(lock)
    assert cache.reserve("cancel-key", digest(None), 202, action="/run/cancellation") is None
    session = jobs.prepare(lock, "chatmate-run-proof", "GENERATION", source)
    accepted_payload = {"run_id": session.run_id, "status": "QUEUED"}
    accepted_intent = session.intent(accepted_payload)
    RunStore(source).save(accepted_payload, job_intent=accepted_intent)
    session.acknowledge(accepted_intent)
    token = jobs._request.set({"key": "cancel-key"})
    current = jobs._current.set(session)
    try:
        payload = {"run_id": session.run_id, "status": "CANCEL_REQUESTED"}
        jobs.persist(RunStore(source), lock, payload)
    finally:
        jobs._current.reset(current)
        jobs._request.reset(token)
    entry = cache.reserve("cancel-key", digest(None), action="/run/cancellation")
    replay, status = cache.replay(entry, {"chatmate": source})
    assert replay == payload and status == 202


def test_unresolved_request_without_a_commit_is_not_reexecuted(tmp_path):
    cache = jobs.RequestCache(tmp_path / "worker.lock")
    cache.reserve("key", digest({}))
    pending = cache.reserve("key", digest({}))
    assert cache.replay(pending, {"chatmate": tmp_path / "source"}) == (None, 409)


def test_future_job_schema_is_rejected(tmp_path):
    import sqlite3
    ledger = jobs.JobLedger(tmp_path / "worker.lock")
    ledger.active()
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RunStoreError, match="schema"):
        ledger.active()
