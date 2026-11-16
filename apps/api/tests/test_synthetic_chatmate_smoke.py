import os
import json

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
import time

from secmate_api import main, synthetic_chatmate_smoke as smoke
from secmate_api.contracts import SyntheticChatMateSmokeEvidence, SyntheticChatMateSmokeRun


def record(**changes):
    payload = {
        "run_id": "target-smoke-123456abcdef", "job_id": "job-test", "target_id": "secmate.synthetic-chatmate.fresh.v1",
        "target_name": "Synthetic ChatMate", "mode": "MOCKED", "status": "QUEUED", "verification": "UNVERIFIED",
        "progress": 5, "stage": "Accepted.", "created_at": "2026-11-14T12:00:00+00:00",
    }
    payload.update(changes)
    return SyntheticChatMateSmokeRun.model_validate(payload)


def evidence(**changes):
    payload = {
        "schema_version": "synthetic-chatmate-phase5-smoke-v1", "target_id": "secmate.synthetic-chatmate.fresh.v1",
        "target_version": "0.5.0", "mode": "MOCKED", "provider_profile": "openrouter-nemotron-35-super-vl-target",
        "model": "nvidia/nemotron-3.5-super-vl:free", "request_text": "Summarize my fictional lunch-planning mail.",
        "limits": {"max_model_turns": 2, "max_tool_calls": 1, "max_output_tokens_per_turn": 500,
                   "deadline_seconds": 120, "permitted_effect": "READ_ONLY_RETRIEVAL"},
        "model_turns_completed": 2, "tool_activity": [{"tool_call_id": "call-1", "name": "secmate.search_mail",
            "arguments": {"query": "lunch", "limit": 20, "cursor": None}, "authorization": "ALLOWED",
            "execution": "FICTIONAL_READ_COMPLETED", "source_refs": [{"resource_id": "mail-fixture-1"}]}],
        "final_response": "Ada's fictional lunch mail proposes Tuesday.", "terminal_outcome": "COMPLETED",
        "fake_write_count": 0, "fake_effect_count": 0, "reconciled": True, "artifacts_sha256": {"demo.json": "a" * 64},
    }
    payload.update(changes)
    return SyntheticChatMateSmokeEvidence.model_validate(payload)


def test_api_storage_is_isolated_before_application_imports():
    assert os.environ["SECMATE_API_DATA_ROOT"].startswith(os.path.abspath(os.getenv("TEMP", os.path.dirname(os.environ["SECMATE_API_DATA_ROOT"]))))
    assert "apps\\api\\data" not in str(main.deepteam_runs.RUN_ROOT).lower()


def test_evidence_contract_is_mock_only_bounded_and_has_no_verdict():
    assert evidence().tool_activity[0].source_refs == [{"resource_id": "mail-fixture-1"}]
    with pytest.raises(ValidationError):
        evidence(mode="LIVE")
    with pytest.raises(ValidationError):
        evidence(security_verdict="PASS")


def test_worker_artifacts_are_normalized_only_after_mock_reconciliation(tmp_path):
    assessment_id = "assessment-fixture"
    artifact = tmp_path / "targets" / "secmate.synthetic-chatmate.fresh.v1" / "0.5.0" / "assessments" / assessment_id
    artifact.mkdir(parents=True)
    meta = {"target_id": "secmate.synthetic-chatmate.fresh.v1", "target_version": "0.5.0",
        "assessment_id": assessment_id, "model_mode": "openrouter_nemotron",
        "compatibility_claim": "OpenRouter/Nemotron-profile-shaped and mock-verified", "live_call_performed": False}
    verification = {"assessment_id": assessment_id, "version": "0.5.0", "sqlite_read_only": True,
        "terminal_status": "completed",
        "logical_turns": 2, "provider_attempts": 2, "authorized_reads": 1, "fake_writes": 0,
        "fake_effects": 0, "model_tools": 7, "mock_verified": True, "source_refs": [{"resource_id": "mail-fixture-1"}]}
    final = {"final_text": "Fictional lunch is Tuesday.", "logical_turns": 2,
             "model_mode": "openrouter_nemotron", "mock_verified": True}
    events = [{"type": "tool.requested", "call_id": "call-1",
               "data": {"name": "secmate.search_mail", "arguments": json.dumps({"query": "lunch"})}}]
    for path, value in ((tmp_path / "demo.json", meta), (tmp_path / "verification.json", verification),
                        (artifact / "final-output.json", final), (artifact / "events.json", events)):
        path.write_text(json.dumps(value), encoding="utf-8")
    normalized = smoke._validated_evidence(tmp_path)
    assert normalized.final_response == final["final_text"]
    assert normalized.tool_activity[0].source_refs == [{"resource_id": "mail-fixture-1"}]
    meta["live_call_performed"] = True
    (tmp_path / "demo.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(smoke.SyntheticChatMateSmokeError, match="provenance"):
        smoke._validated_evidence(tmp_path)


def test_target_and_smoke_lifecycle_endpoints(monkeypatch):
    queued = record()
    completed_evidence = evidence()
    monkeypatch.setattr(main.synthetic_chatmate_smoke, "list_runs", lambda limit=100: [])
    monkeypatch.setattr(main.synthetic_chatmate_smoke, "start_run", lambda: queued)
    monkeypatch.setattr(main.synthetic_chatmate_smoke, "get_run", lambda run_id: queued if run_id == queued.run_id else None)
    monkeypatch.setattr(main.synthetic_chatmate_smoke, "get_evidence", lambda run_id: completed_evidence)
    client = TestClient(main.app)

    target = client.get("/api/v1/synthetic-chatmate-target")
    assert target.status_code == 200
    assert target.json()["state"] == "UNFINISHED_UNVERIFIED"
    assert target.json()["mode"] == "MOCKED_ONLY"
    body = {"target_id": "secmate.synthetic-chatmate.fresh.v1", "mode": "MOCKED", "bounded_test_attested": True}
    assert client.post("/api/v1/synthetic-chatmate-smoke-runs", json=body).status_code == 403
    assert client.post("/api/v1/synthetic-chatmate-smoke-runs", headers={"X-SecMate-Local-Run": "confirmed"}, json=body).status_code == 400
    created = client.post("/api/v1/synthetic-chatmate-smoke-runs", headers={"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "smoke-create-1"}, json=body)
    assert created.status_code == 202
    assert created.json()["verification"] == "UNVERIFIED"
    assert client.get(f"/api/v1/synthetic-chatmate-smoke-runs/{queued.run_id}").json()["mode"] == "MOCKED"
    assert client.get(f"/api/v1/synthetic-chatmate-smoke-runs/{queued.run_id}/evidence").json()["final_response"] == completed_evidence.final_response
    assert client.post("/api/v1/synthetic-chatmate-smoke-runs", headers={"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "smoke-create-2"}, json={**body, "mode": "LIVE"}).status_code == 422


def test_real_managed_smoke_long_projection_reload_and_idempotency(tmp_path, monkeypatch):
    from secmate_api import jobs
    monkeypatch.setattr(smoke, "RUN_ROOT", tmp_path / ("long-evidence-" + "x" * 45))
    monkeypatch.setattr(smoke, "RUN_LOCK", tmp_path / "worker.lock")
    monkeypatch.setattr(main.deepteam_runs, "RUN_LOCK", smoke.RUN_LOCK)
    monkeypatch.setattr(smoke, "_runs", {})
    dispatched = []
    monkeypatch.setattr(jobs, "dispatch", lambda function, args, *a, **k: dispatched.append((function, args)))
    client = TestClient(main.app)
    body = {"target_id": "secmate.synthetic-chatmate.fresh.v1", "mode": "MOCKED", "bounded_test_attested": True}
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "real-smoke-create-1"}
    first = client.post("/api/v1/synthetic-chatmate-smoke-runs", headers=headers, json=body)
    second = client.post("/api/v1/synthetic-chatmate-smoke-runs", headers=headers, json=body)
    assert first.status_code == second.status_code == 202
    run_id = first.json()["run_id"]
    assert second.json()["run_id"] == run_id and len(dispatched) == 1
    function, args = dispatched[0]
    function(*args)
    assert smoke.get_run(run_id).status == "COMPLETED"
    smoke._runs.clear()
    smoke.load_records()
    assert smoke.get_evidence(run_id).reconciled
    monkeypatch.setattr(jobs, "launch", lambda *a, **k: pytest.fail("GET must not launch"))
    assert client.get(f"/api/v1/synthetic-chatmate-smoke-runs/{run_id}").status_code == 200
    assert client.get(f"/api/v1/synthetic-chatmate-smoke-runs/{run_id}/evidence").status_code == 200


def test_malformed_smoke_event_is_bounded(tmp_path):
    meta = {"assessment_id": "assessment-fixture"}
    root = tmp_path / "targets" / "secmate.synthetic-chatmate.fresh.v1" / "0.5.0" / "assessments" / meta["assessment_id"]
    root.mkdir(parents=True)
    for path, value in ((tmp_path / "demo.json", meta), (tmp_path / "verification.json", {}),
                        (root / "final-output.json", {}), (root / "events.json", [None])):
        path.write_text(json.dumps(value))
    with pytest.raises(smoke.SyntheticChatMateSmokeError, match="envelopes"):
        smoke._validated_evidence(tmp_path)


def test_queued_cancellation_is_durable_idempotent_and_never_spawns(tmp_path, monkeypatch):
    from secmate_api import jobs
    monkeypatch.setattr(smoke, "RUN_ROOT", tmp_path / "s")
    monkeypatch.setattr(smoke, "RUN_LOCK", tmp_path / "worker.lock")
    monkeypatch.setattr(main.deepteam_runs, "RUN_LOCK", smoke.RUN_LOCK)
    monkeypatch.setattr(smoke, "_runs", {})
    tasks = []
    monkeypatch.setattr(jobs, "dispatch", lambda function, args, *a, **k: tasks.append((function, args)))
    run = smoke.start_run()
    client = TestClient(main.app)
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "queued-cancel-123"}
    url = f"/api/v1/synthetic-chatmate-smoke-runs/{run.run_id}/cancellation"
    assert client.post(url, headers=headers).status_code == 202
    assert client.post(url, headers=headers).status_code == 202
    monkeypatch.setattr(jobs, "launch", lambda *a, **k: pytest.fail("cancelled queued smoke must not spawn"))
    tasks[0][0](*tasks[0][1])
    smoke._runs.clear()
    smoke.load_records()
    assert smoke.get_run(run.run_id).status == "CANCELLED"


def test_cancel_after_worker_completion_wins_over_publication(tmp_path, monkeypatch):
    from secmate_api import jobs
    monkeypatch.setattr(smoke, "RUN_ROOT", tmp_path / "s")
    monkeypatch.setattr(smoke, "RUN_LOCK", tmp_path / "worker.lock")
    monkeypatch.setattr(smoke, "_runs", {})
    tasks = []
    monkeypatch.setattr(jobs, "dispatch", lambda function, args, *a, **k: tasks.append((function, args)))
    run = smoke.start_run()
    validate = smoke._validated_evidence
    def cancel_before_publish(output):
        result = validate(output)
        smoke.cancel_run(run.run_id)
        return result
    monkeypatch.setattr(smoke, "_validated_evidence", cancel_before_publish)
    tasks[0][0](*tasks[0][1])
    assert smoke.get_run(run.run_id).status == "CANCELLED"
    assert not smoke.get_run(run.run_id).evidence_available
