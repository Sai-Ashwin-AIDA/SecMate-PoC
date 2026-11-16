"""Checkpoint fault regressions: real outer runtime, isolated data, no inference."""
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from secmate_api import jobs, main, chatmate_runs as chat, chatmate_critic as critic, deepteam_runs as deep
from secmate_api.config import Settings
from secmate_api.run_store import RunStore, RunStoreError, digest
from test_job_lifecycle import accepted


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    lock = tmp_path / "worker.lock"
    monkeypatch.setattr(chat, "CHATMATE_RUN_ROOT", tmp_path / "chat")
    monkeypatch.setattr(deep, "RUN_ROOT", tmp_path / "synthetic")
    for module in (chat, deep):
        monkeypatch.setattr(module, "RUN_LOCK", lock)
        monkeypatch.setattr(module, "_runs", {})
        monkeypatch.setattr(module, "_processes", {})
    monkeypatch.setattr(main, "get_settings", lambda: Settings("offline", "offline", 45))
    return lock


def test_missing_mapped_artifact_never_reads_existing_projection(tmp_path):
    session = accepted(tmp_path)
    output = tmp_path / "published" / "result.json"
    output.parent.mkdir()
    output.write_text('{"stale":true}')
    process = session.launch([sys.executable, "-c", "pass", "--output", str(output)],
                             stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    process.communicate(timeout=30)
    token = jobs._current.set(session)
    try:
        with pytest.raises(RunStoreError, match="absent"):
            deep._read_json(output)
    finally:
        jobs._current.reset(token)
        session.finish()


def test_projected_mutation_does_not_replace_verified_bytes(tmp_path):
    session = accepted(tmp_path)
    output = tmp_path / "published" / "result.json"
    code = "import sys; from pathlib import Path; Path(sys.argv[sys.argv.index('--output')+1]).write_text('{\"trusted\":true}')"
    process = session.launch([sys.executable, "-c", code, "--output", str(output)],
                             stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    process.communicate(timeout=30)
    output.write_text('{"substituted":true}')
    assert json.loads(session.projected_bytes(output)) == {"trusted": True}
    session.finish()


@pytest.mark.parametrize("kind", ["GENERATION", "SYNTHETIC"])
def test_lock_write_failure_aborts_unaccepted_job(isolated, monkeypatch, kind):
    original = jobs.os.write
    monkeypatch.setattr(jobs.os, "write", lambda *args: (_ for _ in ()).throw(OSError("Injected disk full")))
    with pytest.raises(OSError, match="disk full"):
        (chat._claim_worker_lock if kind == "GENERATION" else deep._claim_run_lock)("run-write-failure")
    assert not isolated.exists()
    assert jobs.JobLedger(isolated).active() == []
    monkeypatch.setattr(jobs.os, "write", original)
    session = jobs.prepare(isolated, "next-run", kind, chat.CHATMATE_RUN_ROOT)
    jobs.claim_projection(session)
    assert session.finish()


def test_reused_launcher_pid_does_not_prove_worker_exit(monkeypatch):
    job = {"machine": jobs.machine_identity(), "pid": 100, "identity": "old-launcher",
           "worker_pid": 101, "worker_identity": "live-worker"}
    monkeypatch.setattr(jobs, "process_absent", lambda pid: False)
    monkeypatch.setattr(jobs, "process_identity", lambda pid: "new-launcher" if pid == 100 else "live-worker")
    assert not jobs.original_worker_exited(job)


@pytest.mark.parametrize("module,kind", [(chat, "GENERATION"), (deep, "SYNTHETIC")])
def test_late_reaper_cannot_release_a_new_attempt(isolated, module, kind):
    root = chat.CHATMATE_RUN_ROOT if module is chat else deep.RUN_ROOT
    run_id = "chatmate-run-reaper" if module is chat else "api-run-reaper"
    old = jobs.prepare(isolated, run_id, kind, root)
    assert old.finish()
    new = jobs.prepare(isolated, run_id, kind, root)
    jobs.claim_projection(new)
    current_process = object()
    module._processes[run_id] = current_process
    module._release_after_process_exit(run_id, SimpleNamespace(wait=lambda: 0), old)
    assert new.state()["state"] == "PREPARED"
    assert module._processes[run_id] is current_process
    assert json.loads(isolated.read_text())["job_id"] == new.job_id
    new.finish()


def test_finish_waits_for_contained_descendant(tmp_path):
    session = accepted(tmp_path)
    output = tmp_path / "published" / "child.json"
    code = ("import sys,subprocess,json; from pathlib import Path; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            "Path(sys.argv[sys.argv.index('--output')+1]).write_text(json.dumps({'pid':p.pid}))")
    process = session.launch([sys.executable, "-c", code, "--output", str(output)],
                             stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    process.communicate(timeout=30)
    child = json.loads(output.read_text())["pid"]
    assert not jobs.process_absent(child)
    session.finish()
    assert jobs.process_absent(child)


@pytest.mark.parametrize("phase", ["before_launch", "before_authorize"])
def test_shutdown_retains_guard_until_dispatch_quiesces(isolated, monkeypatch, phase):
    entered, release = threading.Event(), threading.Event()
    errors = []
    original_authorize = jobs.JobSession.authorize

    def paused_authorize(session):
        entered.set()
        assert release.wait(20)
        return original_authorize(session)

    if phase == "before_authorize":
        monkeypatch.setattr(jobs.JobSession, "authorize", paused_authorize)
    with jobs.ControllerGuard(isolated.parent):
        session = jobs.prepare(isolated, "chatmate-run-shutdown", "GENERATION", chat.CHATMATE_RUN_ROOT)
        intent = session.intent({"run_id": session.run_id, "status": "QUEUED"})
        RunStore(chat.CHATMATE_RUN_ROOT).save({"run_id": session.run_id, "status": "QUEUED"}, job_intent=intent)
        session.acknowledge(intent)
        coordinator = jobs.Coordinator(isolated)
        coordinator.start()

        def work():
            try:
                if phase == "before_launch":
                    entered.set()
                    assert release.wait(20)
                process = session.launch([sys.executable, "-c", "print('must not authorize after stop')"],
                                         stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
                process.communicate(timeout=20)
            except RunStoreError as error:
                errors.append(str(error))
            finally:
                session.finish()

        coordinator.submit(work, ())
        assert entered.wait(10)
        closing = threading.Thread(target=coordinator.close)
        closing.start()
        assert coordinator.stop.wait(10)
        try:
            assert str(isolated.resolve()) in jobs._controllers
            with pytest.raises(RunStoreError, match="Another API"):
                with jobs.ControllerGuard(isolated.parent):
                    pytest.fail("Guard must remain held")
        finally:
            release.set()
            closing.join(30)
        assert not closing.is_alive()
        assert not coordinator.thread.is_alive()
        assert errors
        assert not session.ledger.get(session.job_id)["execution_started"]


def test_diagnostics_and_job_admission_are_mutually_exclusive(isolated, monkeypatch):
    with jobs.diagnostic_slot(isolated):
        with pytest.raises(FileExistsError, match="Diagnostic"):
            jobs.prepare(isolated, "run", "GENERATION", chat.CHATMATE_RUN_ROOT)
        with pytest.raises(FileExistsError):
            with jobs.diagnostic_slot(isolated):
                pytest.fail("Only one diagnostic may infer")
    session = jobs.prepare(isolated, "run", "GENERATION", chat.CHATMATE_RUN_ROOT)
    monkeypatch.setattr(main, "clients", lambda: pytest.fail("No HTTP while job owns the slot"))
    client = TestClient(main.app)
    assert client.post("/api/v1/model-profiles/groq-qwen-attacker/test").status_code == 409
    assert client.post("/api/v1/model-workflows/adaptive-handoff/test").status_code == 409
    session.finish()


def test_job_operations_validate_and_preserve_unresolved_ownership(isolated):
    client = TestClient(main.app)
    headers = {"X-SecMate-Local-Run": "confirmed"}
    assert client.post("/api/v1/jobs/missing/cancel", headers=headers).status_code == 404
    assert client.post("/api/v1/jobs/missing/resolve", headers=headers, json={"acknowledge_uncertain_completion": True}).status_code == 404
    session = jobs.prepare(isolated, "run-uncertain", "GENERATION", chat.CHATMATE_RUN_ROOT)
    session.ledger._adopt(session.state(), "UNCERTAIN", "PID_NOT_RECORDED")
    path = f"/api/v1/jobs/{session.job_id}/resolve"
    assert client.post(path, headers=headers, json=[]).status_code == 422
    assert client.post(path, headers=headers, content="{invalid",).status_code == 422
    for acknowledgment in (False, 1, "true", True):
        response = client.post(path, headers=headers, json={"acknowledge_uncertain_completion": acknowledgment})
        assert response.status_code == 409
    assert session.ledger.get(session.job_id)["state"] == "UNCERTAIN"


def test_committed_request_mapping_tamper_is_rejected(tmp_path):
    cache = jobs.RequestCache(tmp_path / "lock")
    root = tmp_path / "runs"
    for key, run in (("key-one", "chatmate-run-one"), ("key-two", "chatmate-run-two")):
        cache.reserve(key, digest({}), 200, action="/selection")
        token = jobs._request.set({"key": key})
        try:
            jobs.persist(RunStore(root), cache.ledger.lock_path, {"run_id": run, "status": "AWAITING_RESPONSE"})
        finally:
            jobs._request.reset(token)
        cache.complete(key, 200)
    with cache.ledger.connection() as connection:
        connection.execute("UPDATE requests SET run_id='chatmate-run-two' WHERE request_key='key-one'")
    entry = cache.reserve("key-one", digest({}), 200, action="/selection")
    assert cache.replay(entry, {"chatmate": root}) == (None, 409)


def test_full_raw_submission_identity_and_validation_before_replay(isolated, monkeypatch):
    monkeypatch.setattr(main, "submit_chatmate_response", lambda *args: pytest.fail("A conflicting or invalid retry must not execute"))
    from test_chatmate_runs import _record
    record = _record("AWAITING_RESPONSE")
    path = f"/api/v1/chatmate-runs/{record.run_id}/response"
    body = {"candidate_id": record.selected_candidate_id, "candidate_sha256": record.selected_candidate_sha256,
            "outcome": "RESPONSE", "response_text": "operator-one@example.test", "prompt_submitted_unchanged": True,
            "observation_captured_verbatim": True, "judge_data_collection_attested": True}
    key = "full-input-identity"
    cache = jobs.RequestCache(isolated)
    cache.reserve(digest(["POST", path, key]), digest(body), 202, action=path)
    client = TestClient(main.app)
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": key}
    assert client.post(path, headers=headers, json={**body, "response_text": "operator-two@example.test"}).status_code == 409
    assert client.post(path, headers=headers, json={**body, "response_text": "x" * 20001}).status_code == 422


def test_concurrent_duplicate_reservation_has_one_owner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    cache = jobs.RequestCache(tmp_path / "lock")
    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(lambda _: cache.reserve("same", digest({}), action="/action"), range(8)))
    assert sum(entry is None for entry in entries) == 1


def test_selection_lost_ack_replays_200_and_deleted_run_returns_410(isolated, monkeypatch):
    from test_chatmate_runs import _record
    record = _record()
    chat._runs[record.run_id] = record
    chat._persist(record)
    path = f"/api/v1/chatmate-runs/{record.run_id}/selection"
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "selection-lost-ack"}
    body = {"candidate_id": record.candidate_batch.candidates[0].candidate_id}
    monkeypatch.setattr(jobs.RequestCache, "complete", lambda *args: (_ for _ in ()).throw(RunStoreError("lost ack")))
    client = TestClient(main.app)
    first = client.post(path, headers=headers, json=body)
    second = client.post(path, headers=headers, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    chat.delete_chatmate_run(record.run_id)
    assert client.post(path, headers=headers, json=body).status_code == 410


def test_synthetic_optional_body_and_cancellation_idempotency(isolated, monkeypatch):
    from test_deepteam_runs import _run_record
    calls = []

    def create(*args):
        calls.append(args)
        record = _run_record("QUEUED")
        deep._persist(record)
        deep._runs[record.run_id] = record
        return record

    monkeypatch.setattr(main, "start_deepteam_run", create)
    client = TestClient(main.app)
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "synthetic-default-create"}
    first = client.post("/api/v1/deepteam-runs", headers=headers)
    assert first.status_code == 202
    assert client.post("/api/v1/deepteam-runs", headers=headers).status_code == 202
    assert len(calls) == 1
    path = f"/api/v1/deepteam-runs/{first.json()['run_id']}/cancellation"
    headers["Idempotency-Key"] = "synthetic-cancellation"
    assert client.post(path, headers=headers).status_code == 202
    assert client.post(path, headers=headers).status_code == 202


@pytest.mark.parametrize("change", ["host", "path"])
def test_restored_active_job_quarantines_changed_host_or_path(tmp_path, monkeypatch, change):
    session = accepted(tmp_path)
    if change == "host":
        session.ledger.update(session.job_id, session.token, machine="different-host")
    monkeypatch.setattr(jobs, "_epoch", "restored-controller")
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Restore must not infer"))
    roots = {kind: tmp_path / "changed-path" for kind in jobs.KINDS} if change == "path" else None
    session.ledger.reconcile(roots)
    value = session.ledger.get(session.job_id)
    assert value["state"] == "UNCERTAIN"
    assert value["reason"] == ("HOST_IDENTITY_CHANGED" if change == "host" else "RESTORE_REQUIRES_OFFLINE_RECONCILIATION")


def test_v1_migration_preserves_run_chain_and_request_identity(tmp_path):
    import sqlite3
    store = RunStore(tmp_path / "runs")
    payload = {"run_id": "chatmate-run-migration", "status": "AWAITING_SELECTION"}
    store.save(payload)
    before = store.verification(payload["run_id"])
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TABLE job_receipts")
        connection.execute("PRAGMA user_version=1")
    assert store.records()[payload["run_id"]] == payload
    assert store.verification(payload["run_id"]) == before
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
    cache = jobs.RequestCache(tmp_path / "lock")
    cache.reserve("legacy-key", digest({}), 200)
    with sqlite3.connect(cache.ledger.path) as connection:
        connection.execute("ALTER TABLE requests DROP COLUMN action")
        connection.execute("PRAGMA user_version=1")
    assert cache.reserve("legacy-key", digest({}), 200)["state"] == "PROCESSING"
    with sqlite3.connect(cache.ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_lease_loss_stops_real_worker_without_replay(tmp_path, monkeypatch):
    session = accepted(tmp_path)
    monkeypatch.setattr(session, "pulse", lambda: None)
    process = session.launch([sys.executable, "-c", "import time; time.sleep(60)"],
                             stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    session.ledger.update(session.job_id, session.token, lease_until=0, lease_monotonic_until=0)
    process.communicate(timeout=10)
    assert process.returncode != 0
    assert not session.finish()
    assert session.ledger.get(session.job_id)["state"] == "UNCERTAIN"
    with pytest.raises(FileExistsError):
        jobs.prepare(session.ledger.lock_path, "next", "JUDGE", tmp_path / "next")


def test_unsealed_managed_critic_cannot_be_promoted(isolated, monkeypatch):
    from test_chatmate_runs import _awaiting_evaluation
    from test_chatmate_critic import write_audit, review_for
    record = _awaiting_evaluation(monkeypatch, chat.CHATMATE_RUN_ROOT)
    record = record.model_copy(update={"status": "COMPLETED", "evaluation_id": "manual-eval-checkpoint",
        "completed_at": chat._now(), "final_status": "RESISTED", "artifact_available": True})
    write_audit(record, chat.CHATMATE_RUN_ROOT)
    chat._runs[record.run_id] = record
    chat._persist(record)
    python = isolated.parent / "python.exe"
    python.touch()
    monkeypatch.setattr(chat, "WORKER_PYTHON", python)
    monkeypatch.setattr(critic, "threading", SimpleNamespace(Thread=lambda **kwargs: SimpleNamespace(start=lambda: None)))
    active = critic.start_chatmate_critic(Settings("offline", "", 45, groq_critic_api_key="offline-critic"), record.run_id, True)
    review = review_for(active)
    # The real attempt begins and leaves no completion seal. A plausible loose
    # review must not make the startup legacy reconciler override uncertainty.
    session = jobs.session_for(isolated, record.run_id)
    process = session.launch([sys.executable, "-c", "import time; time.sleep(60)"],
                             stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    assert session.terminate()
    process.communicate(timeout=10)
    assert not session.finish()
    (critic._attempt_directory(active) / "critic-review.json").write_text(review.model_dump_json())
    chat._runs.clear()
    with TestClient(main.app) as client:
        loaded = chat.get_chatmate_run(record.run_id)
        assert loaded.critic_status != "COMPLETED"
        assert client.get(f"/api/v1/chatmate-runs/{record.run_id}/critic").status_code == 409
        assert client.post(f"/api/v1/chatmate-runs/{record.run_id}/follow-up", headers={"X-SecMate-Local-Run": "confirmed"}).status_code == 409
        assert jobs.JobLedger(isolated).get(session.job_id)["state"] == "UNCERTAIN"


@pytest.mark.parametrize("kind", sorted(jobs.KINDS))
def test_lifespan_recovers_sealed_output_through_real_workflow_without_spawn(isolated, monkeypatch, kind):
    """Crash boundary: worker sealed/exited, API publication has not happened."""
    from test_chatmate_runs import _record, _worker_payload, _awaiting_evaluation
    from test_chatmate_critic import write_audit, review_for
    from test_deepteam_runs import _run_record
    from secmate_api import synthetic_chatmate_smoke as smoke
    input_path = None
    if kind == "TARGET_SMOKE":
        from test_synthetic_chatmate_smoke import record as smoke_record
        monkeypatch.setattr(smoke, "RUN_ROOT", isolated.parent / "s")
        monkeypatch.setattr(smoke, "RUN_LOCK", isolated)
        monkeypatch.setattr(smoke, "_runs", {})
        record = smoke_record(job_id=None)
        smoke._persist(record)
        output = smoke.RUN_ROOT / record.run_id / "worker-output"
        files = {}
    elif kind == "GENERATION":
        record = _record("QUEUED")
        chat._runs[record.run_id] = record
        chat._persist(record)
        output = chat.CHATMATE_RUN_ROOT / record.run_id / "candidate-batch.json"
        files = {output.name: _worker_payload()}
    elif kind in {"JUDGE", "CRITIC"}:
        record = _awaiting_evaluation(monkeypatch, chat.CHATMATE_RUN_ROOT)
        record = record.model_copy(update={"status": "COMPLETED" if kind == "CRITIC" else "EVALUATING",
            "evaluation_id": "manual-eval-recovery", "completed_at": chat._now() if kind == "CRITIC" else None,
            "final_status": "RESISTED" if kind == "CRITIC" else None, "artifact_available": kind == "CRITIC",
            "evaluation_attempts": 1, "evaluation_started_at": chat._now()})
        directory = write_audit(record, chat.CHATMATE_RUN_ROOT)
        chat._runs[record.run_id] = record
        chat._persist(record)
        if kind == "JUDGE":
            output = directory.parent
            files = {f"{directory.name}/{path.name}": json.loads(path.read_text()) for path in directory.glob("*.json")}
            for path in directory.glob("*.json"):
                path.unlink()
            input_path = chat.CHATMATE_RUN_ROOT / record.run_id / "evaluation-input.json"
            chat._write_evaluation_input(record, input_path)
        else:
            python = isolated.parent / "python.exe"
            python.touch()
            monkeypatch.setattr(chat, "WORKER_PYTHON", python)
            monkeypatch.setattr(critic, "threading", SimpleNamespace(Thread=lambda **kwargs: SimpleNamespace(start=lambda: None)))
            record = critic.start_chatmate_critic(Settings("offline", "", 45, groq_critic_api_key="offline-critic"), record.run_id, True)
            output = critic._attempt_directory(record) / "critic-review.json"
            input_path = output.parent / "input.json"
            files = {output.name: review_for(record).model_dump(mode="json")}
    else:
        record = _run_record("QUEUED")
        deep._runs[record.run_id] = record
        deep._persist(record)
        output = deep.RUN_ROOT / record.run_id
        path_id = "run-recovered-path-1"
        files = {
            "run-recovered/manifest.json": {"run_id": "run-recovered", "campaign": {
                "scenario_id": record.scenario, "scenario_version": record.scenario_version,
                "target_profile_id": record.target_profile_id, "target_profile_version": record.target_profile_version,
                "vulnerability_types": [record.vulnerability_profile_id],
                "allowed_attack_methods": [record.attack_profile_id], "budget": {"max_paths": 1}}},
            "run-recovered/evidence.json": {"run_id": "run-recovered", "paths": [{"path_id": path_id,
                "vulnerability_type": record.vulnerability_profile_id, "attack_method": record.attack_profile_id}]},
            "run-recovered/deepteam-risk.json": {"run_id": "run-recovered", "execution_mode": "SINGLE", "max_paths": 1,
                "paths": [{"path_id": path_id, "attack_profile_id": record.attack_profile_id}]},
            "run-recovered/summary.json": {"run_id": "run-recovered", "final_status": "RESISTED",
                "attack_profile_id": record.attack_profile_id, "vulnerability_profile_id": record.vulnerability_profile_id,
                "target_profile_id": record.target_profile_id, "execution_mode": "SINGLE", "max_paths": 1,
                "paths": [{"path_id": path_id, "attack_method": record.attack_profile_id, "status": "RESISTED"}]},
        }
    source = smoke.RUN_ROOT if kind == "TARGET_SMOKE" else deep.RUN_ROOT if kind == "SYNTHETIC" else chat.CHATMATE_RUN_ROOT
    session = jobs.session_for(isolated, record.run_id) or jobs.prepare(isolated, record.run_id, kind, source)
    if session.state()["source_receipt"] is None:
        intent = session.intent(record.model_dump(mode="json"))
        RunStore(source).save(record.model_dump(mode="json"), job_intent=intent)
        session.acknowledge(intent)
    code = ("import sys,json; from pathlib import Path; "
            "out=Path(sys.argv[sys.argv.index('--output')+1]); root=out.parent if out.suffix=='.json' else out; "
            f"files=json.loads({json.dumps(files)!r}); "
            "[( (root/name).parent.mkdir(parents=True,exist_ok=True), (root/name).write_text(json.dumps(value,ensure_ascii=True))) for name,value in files.items()]")
    command = [sys.executable, "-c", code, "--output", str(output)]
    if kind == "TARGET_SMOKE":
        command = [str(smoke.WORKER_PYTHON), "-m", "secmate_worker.synthetic_chatmate.model_phase5",
                   "--output", str(output), "--mode", "mocked"]
    if input_path is not None:
        command.extend(["--input", str(input_path)])
    process = session.launch(command, stdout=jobs.subprocess.PIPE, stderr=jobs.subprocess.PIPE, text=True)
    # Wait on the raw process: deliberately skip communicate's API projection.
    _, error = session.process.communicate(timeout=130)
    assert process.returncode == 0, error
    assert not session.finish()  # completion exists but no API publication receipt
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Restart publication must not infer again"))
    chat._runs.clear()
    deep._runs.clear()
    if kind == "TARGET_SMOKE":
        smoke._runs.clear()
    with TestClient(main.app):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            value = session.ledger.get(session.job_id)
            if value["state"] in jobs.TERMINAL and not isolated.exists():
                break
            time.sleep(.05)
        assert value["state"] == "SUCCEEDED", value
        restored = (smoke._runs if kind == "TARGET_SMOKE" else deep._runs if kind == "SYNTHETIC" else chat._runs)[record.run_id]
        assert (restored.critic_status if kind == "CRITIC" else restored.status) == ("AWAITING_SELECTION" if kind == "GENERATION" else "COMPLETED")
        assert RunStore(source).job_receipt(session.job_id, "PUBLICATION") is not None
        assert not isolated.exists()
