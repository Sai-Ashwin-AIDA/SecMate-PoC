import json
from types import SimpleNamespace
import pytest

from secmate_api import chatmate_runs as runs
from secmate_api.contracts import ChatMateRunRecord


def test_progress_is_read_only_bounded_and_contains_no_worker_text(tmp_path, monkeypatch):
    record = ChatMateRunRecord(run_id="chatmate-run-progress", status="GENERATING", created_at="2026-10-21T00:00:00+00:00",
        attack_profile_id="prompt-injection-v1", attack_method="Prompt Injection", max_total_tokens=50000, authorization_attested=True, logs=[])
    monkeypatch.setattr(runs, "_runs", {record.run_id: record})
    monkeypatch.setattr(runs.jobs, "session_for", lambda *args: SimpleNamespace(directory=tmp_path, job_id="progress-job", token=7))
    path = tmp_path / "generation-progress.json"
    path.write_text(json.dumps({"run_id": record.run_id, "job_id": "progress-job", "token": 7, "stage": "PROVIDER_COOLDOWN", "candidate_slot": 1,
        "enhancement_attempt": 2, "succeeded": 8, "failed": 1, "updated_at": record.created_at,
        "message": "private worker text must never be projected"}))
    result = runs.get_chatmate_run(record.run_id)
    assert "Provider Cooldown" in result.logs[-1].message
    assert "candidate 1/2" in result.logs[-1].message
    assert "8 calls succeeded, 1 failed" in result.logs[-1].message
    assert "private" not in result.logs[-1].message
    assert runs._runs[record.run_id].logs == []
    path.write_text("[]")
    assert runs.get_chatmate_run(record.run_id) == record


@pytest.mark.parametrize("change", [{"run_id": "attempt-directory"}, {"job_id": "another-job"}, {"token": 6}, {"token": True}])
def test_progress_rejects_another_run_or_attempt(tmp_path, monkeypatch, change):
    record = ChatMateRunRecord(run_id="chatmate-run-child-progress", status="GENERATING", created_at="2026-10-30T00:00:00+00:00",
        attack_profile_id="system-override-v1", attack_method="System Override", max_total_tokens=50000, authorization_attested=True, logs=[])
    monkeypatch.setattr(runs, "_runs", {record.run_id: record})
    monkeypatch.setattr(runs.jobs, "session_for", lambda *args: SimpleNamespace(directory=tmp_path, job_id="progress-job", token=7))
    document = {"run_id": record.run_id, "job_id": "progress-job", "token": 7, "stage": "METHOD_ALIGNMENT",
        "succeeded": 2, "failed": 0, "updated_at": record.created_at}
    path = tmp_path / "generation-progress.json"
    path.write_text(json.dumps(document))
    assert "Method Alignment" in runs.get_chatmate_run(record.run_id).logs[-1].message
    path.write_text(json.dumps({**document, **change}))
    assert runs.get_chatmate_run(record.run_id) == record
    path.write_text(json.dumps({"run_id": "different", "stage": "ENHANCEMENT"}))
    assert runs.get_chatmate_run(record.run_id) == record
