import json
import sqlite3

import pytest

from secmate_api import maintenance


def test_cleanup_removes_run_artifacts_and_jobs_but_preserves_configuration(tmp_path):
    data = tmp_path / "data"
    for directory in (data / "deepteam-runs" / "api-run-old", data / "chatmate-runs" / "chatmate-run-old"):
        directory.mkdir(parents=True)
        (directory / "evidence.json").write_text("private run evidence")
    config = tmp_path / ".env"
    config.write_text("configuration retained")
    with sqlite3.connect(data / "deepteam-runs" / "jobs.sqlite3") as connection:
        connection.execute("CREATE TABLE jobs (payload TEXT)")
        connection.execute("INSERT INTO jobs VALUES (?)", (json.dumps({"pid": None, "launch_intent": False}),))
    connection.close()
    result = maintenance.clear_history(data)
    assert result["deleted_runs"] == 2
    assert not (data / "chatmate-runs" / "chatmate-run-old").exists()
    assert not (data / "deepteam-runs" / "api-run-old").exists()
    assert config.read_text() == "configuration retained"
    assert not (data / "deepteam-runs" / "jobs.sqlite3").exists()
    assert (data / "history-epoch").read_text() == result["history_epoch"]


def test_cleanup_refuses_to_delete_a_possibly_live_worker(tmp_path, monkeypatch):
    root = tmp_path / "deepteam-runs"
    root.mkdir()
    with sqlite3.connect(root / "jobs.sqlite3") as connection:
        connection.execute("CREATE TABLE jobs (payload TEXT)")
        connection.execute("INSERT INTO jobs VALUES (?)", (json.dumps({"pid": 123, "launch_intent": True}),))
    monkeypatch.setattr(maintenance, "original_worker_exited", lambda job: False)
    with pytest.raises(RuntimeError, match="worker may still be alive"):
        maintenance.clear_history(tmp_path)
    assert (root / "jobs.sqlite3").exists()
