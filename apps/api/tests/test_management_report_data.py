import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from secmate_api import chatmate_runs as chat, deepteam_runs as soc, main
from secmate_api.contracts import ChatMateResponseSubmission
from secmate_api.run_store import RunStore, RunStoreError
from test_chatmate_runs import _record
from test_chatmate_critic import write_audit


@pytest.fixture
def captured(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "CHATMATE_RUN_ROOT", tmp_path / "chat")
    monkeypatch.setattr(chat, "RUN_LOCK", tmp_path / "worker.lock")
    monkeypatch.setattr(chat, "_runs", {})
    monkeypatch.setattr(chat, "_processes", {})
    record = _record("AWAITING_RESPONSE")
    chat._runs[record.run_id] = record
    original = "Full response: operator@example.test token=synthetic-private-value. 安全な応答"
    accepted = chat.submit_chatmate_response(record.run_id, ChatMateResponseSubmission(
        candidate_id=record.selected_candidate_id, candidate_sha256=record.selected_candidate_sha256,
        outcome="RESPONSE", response_text=original, prompt_submitted_unchanged=True,
        observation_captured_verbatim=True, judge_data_collection_attested=True))
    return accepted, original


def test_original_capture_is_exact_and_separate_from_judge_input(captured):
    record, original = captured
    assert record.manual_evidence.redaction_applied
    assert "operator@example.test" not in record.manual_evidence.redacted_response_text
    retained = RunStore(chat.CHATMATE_RUN_ROOT).original_evidence(record.run_id)
    assert retained["response_text"] == original
    assert retained["response_sha256"] == chat._sha256(original)
    assert retained["correlation_sha256"] == record.manual_evidence.correlation_sha256
    path = chat.CHATMATE_RUN_ROOT / record.run_id / "evaluation-input.json"
    chat._write_evaluation_input(record, path)
    assert original not in path.read_text()
    assert original not in (path.parent / "record.json").read_text()


def test_report_reads_verified_original_without_starting_work(captured, monkeypatch):
    record, original = captured
    record = record.model_copy(update={"status": "COMPLETED", "evaluation_id": "manual-eval-report",
        "evaluation_attempts": 1, "completed_at": chat._now(), "final_status": "RESISTED", "artifact_available": True})
    write_audit(record, chat.CHATMATE_RUN_ROOT)
    chat._runs[record.run_id] = record
    chat._persist(record)
    monkeypatch.setattr(chat.jobs, "dispatch", lambda *args, **kwargs: pytest.fail("Report must not dispatch"))
    response = TestClient(main.app).get(f"/api/v1/chatmate-runs/{record.run_id}/report-data")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["source"] == "ChatMate"
    assert response.json()["original"]["response_text"] == original
    assert response.json()["audit"]["evidence"]["paths"][0]["turns"][0]["target_response"] == record.manual_evidence.redacted_response_text


@pytest.mark.parametrize("tamper", ["replace", "delete"])
def test_original_capture_tampering_fails_closed(captured, tamper):
    record, _ = captured
    store = RunStore(chat.CHATMATE_RUN_ROOT)
    with sqlite3.connect(store.path) as connection:
        if tamper == "delete":
            connection.execute("DELETE FROM report_evidence WHERE run_id=?", (record.run_id,))
        else:
            connection.execute("UPDATE report_evidence SET payload=? WHERE run_id=?", (json.dumps({"run_id": record.run_id, "response_text": "forged"}), record.run_id))
    with pytest.raises(RunStoreError):
        store.original_evidence(record.run_id)
    assert TestClient(main.app).get(f"/api/v1/chatmate-runs/{record.run_id}/report-data").status_code == 503


def test_original_capture_transaction_rolls_back_with_event(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    monkeypatch.setattr(store, "_append", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(RunStoreError):
        store.save({"run_id": "chatmate-run-rollback", "status": "QUEUED"}, original_evidence={"run_id": "chatmate-run-rollback", "response_text": "original"})
    assert store.records() == {}
    assert store.original_evidence("chatmate-run-rollback") is None


def test_delete_clears_original_capture_with_tombstone(captured):
    record, _ = captured
    store = RunStore(chat.CHATMATE_RUN_ROOT)
    store.delete(record.run_id)
    assert store.original_evidence(record.run_id) is None
    assert store.verification(record.run_id)["deleted"]
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT 1 FROM report_evidence WHERE run_id=?", (record.run_id,)).fetchone() is None


def test_historical_masked_capture_is_not_invented(captured, tmp_path, monkeypatch):
    saved, original = captured
    legacy_root = tmp_path / "legacy"
    # The historical projection retains only the already-masked response.
    RunStore(legacy_root).save(saved.model_dump(mode="json"), imported=True)
    monkeypatch.setattr(chat, "CHATMATE_RUN_ROOT", legacy_root)
    response = TestClient(main.app).get(f"/api/v1/chatmate-runs/{saved.run_id}/report-data")
    assert response.status_code == 200
    assert response.json()["original"] is None
    assert original not in response.text


def test_unknown_report_run_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "_runs", {})
    monkeypatch.setattr(soc, "_runs", {})
    client = TestClient(main.app)
    assert client.get("/api/v1/chatmate-runs/missing/report-data").status_code == 404
    assert client.get("/api/v1/deepteam-runs/missing/report-data").status_code == 404


def test_bad_critic_does_not_hide_verified_judge_report(captured, monkeypatch):
    from secmate_api import reporting, chatmate_critic
    record, _ = captured
    record = record.model_copy(update={"status": "COMPLETED", "evaluation_id": "manual-eval-report",
        "evaluation_attempts": 1, "completed_at": chat._now(), "final_status": "RESISTED", "artifact_available": True,
        "critic_status": "COMPLETED", "critic_review_id": "critic-review-aabbcc001122", "critic_attempts": 1,
        "critic_started_at": chat._now(), "critic_completed_at": chat._now(),
        "critic_review_available": True, "critic_review_sha256": "b" * 64})
    record = type(record).model_validate(record.model_dump(mode="json"))
    write_audit(record, chat.CHATMATE_RUN_ROOT)
    chat._runs[record.run_id] = record
    chat._persist(record)
    monkeypatch.setattr(chat, "get_chatmate_run", lambda run_id: record)
    def invalid(_):
        raise ValueError("synthetic artifact mismatch")
    monkeypatch.setattr(chatmate_critic, "_validated_review", invalid)
    result = reporting.chatmate_report_data(record.run_id)
    assert result["critic"] is None and result["critic_error"]
    assert result["run"]["final_status"] == "RESISTED"
    assert result["audit"]["summary"]["final_status"] == "RESISTED"
