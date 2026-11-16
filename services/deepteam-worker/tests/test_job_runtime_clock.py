import os

import pytest

from secmate_worker import job_runtime


@pytest.mark.parametrize("change", [
    {}, {"lease_monotonic_until": 99}, {"lease_clock": "legacy"},
    {"authorized": False}, {"cancel_requested": True}, {"worker_pid": -1},
    {"worker_identity": "different"}, {"state": "UNCERTAIN"},
])
def test_cross_version_clock_preserves_worker_authorization_checks(monkeypatch, change):
    monkeypatch.setenv("SECMATE_JOB_ID", "clock-test")
    value = {"state": "RUNNING", "authorized": True, "cancel_requested": False,
             "worker_pid": os.getpid(), "worker_identity": "worker-test",
             "lease_monotonic_until": 130, "lease_clock": "perf_counter", **change}
    monkeypatch.setattr(job_runtime, "job", lambda: value)
    monkeypatch.setattr(job_runtime, "identity", lambda: "worker-test")
    monkeypatch.setattr(job_runtime.time, "perf_counter", lambda: 100)
    # Deliberately different epoch, as on Python 3.11 vs 3.14 on Windows.
    monkeypatch.setattr(job_runtime.time, "monotonic", lambda: 1000)
    if change:
        with pytest.raises(RuntimeError, match="authorization expired or was revoked"):
            job_runtime.require_permission()
    else:
        job_runtime.require_permission()
