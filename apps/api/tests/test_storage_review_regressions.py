import json
import os

import pytest

from secmate_api import chatmate_runs as chatmate, deepteam_runs as deepteam
from secmate_api.run_store import RunStore, RunStoreError
from test_chatmate_runs import _record
from test_deepteam_runs import _run_record


@pytest.mark.parametrize("kind", ["synthetic", "chatmate"])
def test_projection_replace_failure_does_not_fail_committed_mutation(tmp_path, monkeypatch, kind):
    module = deepteam if kind == "synthetic" else chatmate
    root_name = "RUN_ROOT" if kind == "synthetic" else "CHATMATE_RUN_ROOT"
    monkeypatch.setattr(module, root_name, tmp_path)
    record = _run_record("RUNNING") if kind == "synthetic" else _record("AWAITING_SELECTION")
    monkeypatch.setattr(module, "_runs", {record.run_id: record})
    module._persist(record)

    def failed(*args):
        raise OSError("projection unavailable")

    monkeypatch.setattr(os, "replace", failed)
    module._update_locked(record.run_id, status="FAILED")
    committed = module._runs[record.run_id]
    assert committed.status == "FAILED"
    assert RunStore(tmp_path).records()[record.run_id] == committed.model_dump(mode="json")


def test_snapshot_and_baseline_rollback_together(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    store.save({"run_id": "test", "status": "RUNNING"})
    original = store._append

    def failed(*args):
        original(*args)
        raise OSError("interrupted after SQL writes")

    monkeypatch.setattr(store, "_append", failed)
    with pytest.raises(RunStoreError):
        store.save({"run_id": "test", "status": "COMPLETED"}, evidence_bundle=("run-original", {"summary": "accepted"}))
    assert store.records()["test"]["status"] == "RUNNING"
    assert store.verification("test")["evidence_baselines"] == {}
    assert store.verification("test")["events"] == 1


def synthetic_bundle(root, record, reference="run-original"):
    directory = root / record.run_id / reference
    directory.mkdir(parents=True)
    for name in ("manifest.json", "evidence.json", "deepteam-risk.json", "summary.json"):
        payload = {"run_id": reference, "final_status": record.final_status}
        if name in {"evidence.json", "deepteam-risk.json"}:
            payload["paths"] = [{"path_id": f"{reference}-path-1"}]
        (directory / name).write_text(json.dumps(payload), encoding="ascii")
    return directory


@pytest.mark.parametrize("legacy", [False, True])
def test_synthetic_directory_replacement_cannot_establish_new_baseline(tmp_path, monkeypatch, legacy):
    monkeypatch.setattr(deepteam, "RUN_ROOT", tmp_path)
    record = _run_record("COMPLETED").model_copy(update={"final_status": "RESISTED", "artifact_available": True})
    monkeypatch.setattr(deepteam, "_runs", {record.run_id: record})
    directory = synthetic_bundle(tmp_path, record)
    store = RunStore(tmp_path)
    if legacy:
        store.save(record.model_dump(mode="json"), imported=True)
    else:
        deepteam._persist(record)
    assert deepteam.get_deepteam_audit(record.run_id) is not None
    baselines = store.verification(record.run_id)["evidence_baselines"]
    directory.rename(directory.with_name("run-replaced"))
    assert deepteam.get_deepteam_audit(record.run_id) is None
    assert store.verification(record.run_id)["evidence_baselines"] == baselines


def test_unaccepted_synthetic_bundle_does_not_get_first_read_trust(tmp_path, monkeypatch):
    monkeypatch.setattr(deepteam, "RUN_ROOT", tmp_path)
    record = _run_record("COMPLETED").model_copy(update={"final_status": "RESISTED", "artifact_available": True})
    monkeypatch.setattr(deepteam, "_runs", {record.run_id: record})
    RunStore(tmp_path).save(record.model_dump(mode="json"))
    synthetic_bundle(tmp_path, record)
    assert deepteam.get_deepteam_audit(record.run_id) is None


def test_failed_cancel_can_be_retried_and_termination_is_not_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(deepteam, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(deepteam, "RUN_LOCK", tmp_path / "active-run.lock")
    record = _run_record("RUNNING")
    process = object()
    monkeypatch.setattr(deepteam, "_runs", {record.run_id: record})
    monkeypatch.setattr(deepteam, "_processes", {record.run_id: process})
    deepteam._persist(record)
    original = deepteam._persist
    attempts, terminated = [], []

    def persist(value):
        attempts.append(value)
        if len(attempts) == 1:
            raise RunStoreError("temporarily unavailable")
        original(value)

    monkeypatch.setattr(deepteam, "_persist", persist)
    monkeypatch.setattr(deepteam, "_terminate_process", lambda value: terminated.append(value) or False)
    with pytest.raises(RunStoreError):
        deepteam.cancel_deepteam_run(record.run_id)
    assert deepteam._runs[record.run_id].status == "RUNNING"
    assert RunStore(tmp_path).records()[record.run_id]["status"] == "RUNNING"
    assert terminated == []
    deepteam.cancel_deepteam_run(record.run_id)
    deepteam.cancel_deepteam_run(record.run_id)
    assert terminated == [process, process]
    assert RunStore(tmp_path).records()[record.run_id]["status"] == "CANCEL_REQUESTED"


def test_initial_running_save_failure_releases_undispatched_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(deepteam, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(deepteam, "RUN_LOCK", tmp_path / "active-run.lock")
    record = _run_record("QUEUED")
    monkeypatch.setattr(deepteam, "_runs", {record.run_id: record})
    monkeypatch.setattr(deepteam, "_processes", {})
    deepteam._claim_run_lock(record.run_id)

    def failed(*args, **kwargs):
        raise RunStoreError("unavailable")

    monkeypatch.setattr(deepteam, "_persist", failed)
    monkeypatch.setattr(deepteam.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Must not dispatch"))
    with pytest.raises(RunStoreError):
        deepteam._execute_run(record.run_id, "attack", "vulnerability", 10000, "SINGLE", 1)
    assert not deepteam.RUN_LOCK.exists()


@pytest.mark.parametrize("failure", ["open", "parent"])
def test_storage_open_errors_are_normalized(tmp_path, failure):
    root = tmp_path / "store"
    if failure == "open":
        root.mkdir()
        (root / "control.sqlite3").mkdir()
    else:
        root.write_text("not a directory")
    with pytest.raises(RunStoreError):
        RunStore(root).records()
