import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from secmate_api.run_store import RunStore, RunStoreError
from secmate_api.run_store import canonical, digest
import secmate_api.chatmate_runs as chatmate
import secmate_api.deepteam_runs as deepteam
from secmate_api.main import app
from test_chatmate_runs import _record


def snapshot(status="DRAFT"):
    return {"run_id": "chatmate-run-test", "status": status, "manual_evidence": None}


def test_transactional_snapshot_is_restart_safe_and_duplicate_writes_are_idempotent(tmp_path):
    store = RunStore(tmp_path)
    store.save(snapshot())
    store.save(snapshot())
    store.save(snapshot("COMPLETED"))
    restored = RunStore(tmp_path)
    assert restored.records() == {"chatmate-run-test": snapshot("COMPLETED")}
    assert restored.verification("chatmate-run-test")["events"] == 2


def test_concurrent_writes_produce_one_verifiable_chain(tmp_path):
    store = RunStore(tmp_path)
    store.save(snapshot())
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda number: store.save({**snapshot(), "revision": number}), range(16)))
    assert store.verification("chatmate-run-test")["events"] == 17


def test_atomic_failure_rolls_back_snapshot_and_event(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    store.save(snapshot())
    original = store._append

    def failed(*args):
        original(*args)
        raise OSError("simulated interrupted transaction")

    monkeypatch.setattr(store, "_append", failed)
    with pytest.raises(RunStoreError):
        store.save(snapshot("COMPLETED"))
    assert store.records()["chatmate-run-test"] == snapshot()
    assert store.verification("chatmate-run-test")["events"] == 1


@pytest.mark.parametrize("tamper", ["snapshot", "event", "evidence", "missing_snapshot"])
def test_database_tampering_is_rejected_on_read_and_write(tmp_path, tamper):
    store = RunStore(tmp_path)
    store.save(snapshot())
    with sqlite3.connect(store.path) as connection:
        if tamper == "snapshot":
            connection.execute("UPDATE runs SET payload=?", (json.dumps(snapshot("COMPLETED")),))
        elif tamper == "evidence":
            connection.execute("UPDATE runs SET evidence='{}{}'")
        elif tamper == "missing_snapshot":
            connection.execute("DELETE FROM runs")
        else:
            connection.execute("DROP TRIGGER events_no_update")
            connection.execute("UPDATE events SET event_hash=?", ("0" * 64,))
    with pytest.raises(RunStoreError):
        store.records() if tamper != "missing_snapshot" else store.verification("chatmate-run-test")
    with pytest.raises(RunStoreError):
        store.save(snapshot())


def test_event_triggers_prevent_accidental_history_edits(tmp_path):
    store = RunStore(tmp_path)
    store.save(snapshot())
    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM events")


def test_evidence_pin_cannot_be_replaced_and_whitespace_does_not_change_digest(tmp_path):
    store = RunStore(tmp_path)
    store.save(snapshot())
    store.verify_evidence("chatmate-run-test", "evaluation-1", {"reasoning": "original"})
    store.verify_evidence("chatmate-run-test", "evaluation-1", json.loads('{ "reasoning" : "original" }'))
    with pytest.raises(RunStoreError):
        store.verify_evidence("chatmate-run-test", "evaluation-1", {"reasoning": "edited"})
    assert store.verification("chatmate-run-test")["events"] == 2


def test_deletion_erases_snapshot_and_digest_manifest_but_keeps_hash_only_audit(tmp_path):
    store = RunStore(tmp_path)
    store.save({**snapshot(), "response": "private-redacted-evidence"})
    store.delete("chatmate-run-test")
    assert store.records() == {}
    assert store.verification("chatmate-run-test")["deleted"]
    with pytest.raises(RunStoreError):
        store.save(snapshot())
    with sqlite3.connect(store.path) as connection:
        assert "private-redacted-evidence" not in " ".join(row[0] for row in connection.execute("SELECT body FROM events"))
        assert connection.execute("SELECT payload FROM runs").fetchone()[0] is None


def test_legacy_import_and_database_recovery_without_json_projection(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    record = _record()
    directory = root / record.run_id
    directory.mkdir(parents=True)
    path = directory / "record.json"
    path.write_text(record.model_dump_json(), encoding="ascii")
    monkeypatch.setattr(chatmate, "CHATMATE_RUN_ROOT", root)
    monkeypatch.setattr(chatmate, "_runs", {})
    chatmate._load_records()
    assert chatmate._runs[record.run_id] == record
    path.unlink()
    chatmate._runs.clear()
    chatmate._load_records()
    assert chatmate._runs[record.run_id] == record
    assert RunStore(root).verification(record.run_id)["events"] == 1
    response = TestClient(app).get(f"/api/v1/chatmate-runs/{record.run_id}/integrity")
    assert response.status_code == 200
    assert response.json()["verified"] is True


def test_unknown_database_migration_version_fails_closed(tmp_path):
    store = RunStore(tmp_path)
    store.save(snapshot())
    with sqlite3.connect(store.path) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RunStoreError, match="schema version"):
        store.records()


def test_rehashing_an_old_event_does_not_break_chain_link_detection(tmp_path):
    store = RunStore(tmp_path)
    store.save(snapshot())
    store.save(snapshot("COMPLETED"))
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER events_no_update")
        body = json.loads(connection.execute("SELECT body FROM events WHERE sequence=1").fetchone()[0])
        body["timestamp"] = "changed"
        connection.execute("UPDATE events SET body=?, event_hash=? WHERE sequence=1", (canonical(body), digest(body)))
    with pytest.raises(RunStoreError):
        store.verification("chatmate-run-test")


def test_synthetic_restart_and_paginated_events_without_json_projection(tmp_path, monkeypatch):
    from test_deepteam_runs import _run_record
    monkeypatch.setattr(deepteam, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(deepteam, "RUN_LOCK", tmp_path / "active-run.lock")
    monkeypatch.setattr(deepteam, "_runs", {})
    record = _run_record("FAILED")
    deepteam._persist(record)
    (tmp_path / record.run_id / "record.json").unlink()
    deepteam._load_records()
    assert deepteam._runs[record.run_id] == record
    client = TestClient(app)
    assert client.get(f"/api/v1/deepteam-runs/{record.run_id}/integrity").json()["verified"]
    response = client.get(f"/api/v1/deepteam-runs/{record.run_id}/audit-events?limit=1")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert client.get(f"/api/v1/deepteam-runs/{record.run_id}/audit-events?after_sequence=1").json() == []
    assert client.get(f"/api/v1/deepteam-runs/{record.run_id}/audit-events?limit=201").status_code == 422


def test_integrity_endpoint_fails_closed_without_exposing_corruption_details(tmp_path, monkeypatch):
    monkeypatch.setattr(chatmate, "CHATMATE_RUN_ROOT", tmp_path)
    monkeypatch.setattr(chatmate, "_runs", {})
    record = _record()
    chatmate._persist(record)
    chatmate._runs[record.run_id] = record
    with sqlite3.connect(RunStore(tmp_path).path) as connection:
        connection.execute("UPDATE runs SET payload='private-corrupt-value'")
    response = TestClient(app).get(f"/api/v1/chatmate-runs/{record.run_id}/integrity")
    assert response.status_code == 503
    assert "private-corrupt-value" not in response.text


@pytest.mark.parametrize("kind", ["synthetic", "chatmate"])
def test_failed_persistence_does_not_publish_an_uncommitted_state(monkeypatch, kind):
    from test_deepteam_runs import _run_record
    module = deepteam if kind == "synthetic" else chatmate
    record = _run_record("RUNNING") if kind == "synthetic" else _record("AWAITING_SELECTION")
    monkeypatch.setattr(module, "_runs", {record.run_id: record})

    def failed(_):
        raise RunStoreError("storage unavailable")

    monkeypatch.setattr(module, "_persist", failed)
    with pytest.raises(RunStoreError):
        module._update_locked(record.run_id, status="FAILED")
    assert module._runs[record.run_id] == record


def test_failed_synthetic_creation_releases_worker_lock_without_dispatch(tmp_path, monkeypatch):
    from secmate_api.config import Settings
    python = tmp_path / "python.exe"
    python.touch()
    monkeypatch.setattr(deepteam, "WORKER_PYTHON", python)
    monkeypatch.setattr(deepteam, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(deepteam, "RUN_LOCK", tmp_path / "active-run.lock")
    monkeypatch.setattr(deepteam, "_runs", {})

    def failed(_):
        raise RunStoreError("storage unavailable")

    monkeypatch.setattr(deepteam, "_persist", failed)
    with pytest.raises(RunStoreError):
        deepteam.start_deepteam_run(Settings("fake", "fake", 45))
    assert not deepteam.RUN_LOCK.exists()
    assert deepteam._runs == {}
