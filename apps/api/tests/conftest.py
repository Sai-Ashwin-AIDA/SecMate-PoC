"""Legacy fake workers now simulate the outer durable-worker protocol as well.

New job protocol tests are deliberately excluded and exercise the real handshake.
Only old mocked subprocesses receive a synthetic PID/ready/completion fixture.
"""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Pytest imports application modules while collecting tests, before fixtures run.
# Select an isolated store here so collection can never open the development DB.
_TEST_DATA = tempfile.TemporaryDirectory(prefix="secmate-api-tests-")
os.environ["SECMATE_API_DATA_ROOT"] = _TEST_DATA.name

REAL_POPEN = subprocess.Popen


@pytest.fixture(autouse=True)
def legacy_worker_protocol(request, monkeypatch):
    if request.node.path.name not in {"test_chatmate_critic.py", "test_chatmate_runs.py", "test_chatmate_provider_subtypes.py",
                                      "test_chatmate_failures_delete.py", "test_deepteam_runs.py", "test_offline_chatmate_contract.py"}:
        return
    from secmate_api import jobs
    original_identity = jobs.process_identity
    original_absent = jobs.process_absent
    original_authorize = jobs.JobSession.authorize
    original_containment = jobs.ProcessContainment

    class SimulatedContainment:
        def __init__(self, process):
            self.process = process

        def close(self):
            pass

        def terminate_and_wait(self):
            from secmate_api.deepteam_runs import _terminate_process
            return _terminate_process(self.process)

    monkeypatch.setattr(jobs, "ProcessContainment", lambda process: original_containment(process) if isinstance(process, REAL_POPEN) else SimulatedContainment(process))

    def identity(pid):
        for session in jobs._sessions.values():
            process = session.process
            if process is not None and getattr(process, "pid", None) == pid and not isinstance(process, REAL_POPEN):
                return f"fixture-process:{pid}"
        return original_identity(pid)

    def absent(pid):
        for session in jobs._sessions.values():
            process = session.process
            if process is not None and getattr(process, "pid", None) == pid and not isinstance(process, REAL_POPEN):
                return process.poll() is not None
        return original_absent(pid)

    def authorize(session):
        if isinstance(session.process, REAL_POPEN):
            return original_authorize(session)
        state = session.state()
        (session.directory / "ready.json").write_text(json.dumps({"job_id": session.job_id, "token": session.token,
            "pid": state["pid"], "identity": state["identity"]}), encoding="ascii")
        underlying = session.process.communicate

        def complete(*args, **kwargs):
            streams = underlying(*args, **kwargs)
            root = session.directory / "results"
            files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in root.rglob("*") if path.is_file()}
            (session.directory / "completion.json").write_text(json.dumps({"job_id": session.job_id,
                "token": session.token, "command_hash": session.state()["command_hash"],
                "returncode": session.process.returncode, "files": files}), encoding="ascii")
            marker = json.loads((session.directory / "completion.json").read_text())
            from secmate_api.run_store import digest
            session.ledger.update(session.job_id, session.token, completion_manifest=marker,
                                  completion_hash=digest(marker), worker_completion=True)
            return streams

        monkeypatch.setattr(session.process, "communicate", complete)
        return original_authorize(session)

    monkeypatch.setattr(jobs, "process_identity", identity)
    monkeypatch.setattr(jobs, "process_absent", absent)
    monkeypatch.setattr(jobs.JobSession, "authorize", authorize)
