from pathlib import Path

import pytest

from secmate_api.deepteam_runs import (
    DeepTeamRunError,
    _execute_run,
    _is_successful_worker_result,
    _redact_payload,
    _worker_failure_details,
    _worker_stderr_diagnostic,
    _worker_command,
    _worker_environment,
    cancel_deepteam_run,
    list_deepteam_runs,
)
from secmate_api.contracts import DeepTeamRunRecord
import secmate_api.deepteam_runs as runs_module
from secmate_api.deepteam_catalog import (
    attack_profile_name,
    validate_profile_selection,
    vulnerability_profile_name,
)


def test_worker_environment_is_allowlisted(monkeypatch):
    monkeypatch.setenv("PATH", "test-path")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-pass")
    monkeypatch.setenv("CONFIDENT_API_KEY", "must-not-pass")

    environment = _worker_environment()

    assert environment["PATH"] == "test-path"
    assert "UNRELATED_SECRET" not in environment
    assert "CONFIDENT_API_KEY" not in environment


def test_worker_success_requires_known_non_error_status():
    assert _is_successful_worker_result(0, "RESISTED") is True
    assert _is_successful_worker_result(0, "COMPROMISED") is True
    assert _is_successful_worker_result(0, None) is False
    assert _is_successful_worker_result(0, "UNKNOWN") is False
    assert _is_successful_worker_result(1, "RESISTED") is False


def test_worker_authentication_failure_names_provider_and_action():
    code, message = _worker_failure_details(
        [{"provider": "GROQ", "error_code": "AUTHENTICATION"}]
    )

    assert code == "PROVIDER_AUTHENTICATION_FAILED"
    assert message == "Groq rejected its API key. Update the configured key and restart SecMate."


def test_audit_redaction_is_recursive():
    payload = _redact_payload(
        {
            "approval_token": "synthetic-token",
            "nested": {"password": "synthetic-password"},
            "safe": "retained",
        }
    )

    assert payload == {
        "approval_token": "<redacted>",
        "nested": {"password": "<redacted>"},
        "safe": "retained",
    }


def test_worker_stderr_diagnostic_exposes_only_allowlisted_configuration_errors():
    secret = "gsk_test-secret"
    unsafe = _worker_stderr_diagnostic(
        f"Traceback\nValueError: provider rejected {secret}",
        {"GROQ_API_KEY": secret},
    )
    safe = _worker_stderr_diagnostic(
        "Traceback\nValueError: DeepTeam vulnerability profile unknown is not applicable",
        {"GROQ_API_KEY": secret},
    )

    assert unsafe is None
    assert safe == "ValueError: DeepTeam vulnerability profile unknown is not applicable"


def test_run_listing_is_newest_first(monkeypatch):
    older = _run_record().model_copy(
        update={"run_id": "api-run-older", "created_at": "2026-10-01T10:00:00Z"}
    )
    newer = _run_record().model_copy(
        update={"run_id": "api-run-newer", "created_at": "2026-10-01T11:00:00Z"}
    )
    monkeypatch.setattr(runs_module, "_runs", {older.run_id: older, newer.run_id: newer})

    assert [record.run_id for record in list_deepteam_runs(limit=1)] == [
        "api-run-newer",
    ]


def test_attack_profile_allowlist_rejects_arbitrary_names():
    assert attack_profile_name("base64-v1") == "Base64"

    try:
        attack_profile_name("client-controlled-import")
    except ValueError as error:
        assert "Unknown or unavailable" in str(error)
    else:
        raise AssertionError("Unknown attack profile must fail closed")


def test_vulnerability_profile_uses_display_name():
    assert vulnerability_profile_name(
        "IndirectInstruction:document_embedded_instructions"
    ) == "Indirect Instruction / Document Embedded Instructions"


def test_catalog_selection_accepts_registered_vulnerability():
    _, vulnerability = validate_profile_selection(
        "base64-v1",
        "PromptLeakage:instructions",
        "synthetic-socmate-tier1",
        "socmate-tier1-permission-escalation",
    )

    assert vulnerability.applicability == "APPLICABLE"
    assert vulnerability.capability_level == "REGISTERED"


def test_catalog_selection_rejects_target_scope_mismatch():
    with pytest.raises(ValueError, match="is not applicable"):
        validate_profile_selection(
            "base64-v1",
            "ExcessiveAgency:permissions",
            "another-target",
            "socmate-tier1-permission-escalation",
        )


def test_worker_command_can_preserve_legacy_bounded_adaptive_selection():
    command = _worker_command(
        Path("output"),
        "leetspeak-v1",
        "IndirectInstruction:document_embedded_instructions",
        75_000,
        "ADAPTIVE",
        2,
        "synthetic-socmate-tier1",
    )

    assert command[command.index("--execution-mode") + 1] == "ADAPTIVE"
    assert command[command.index("--max-paths") + 1] == "2"
    assert command[command.index("--attack-profile") + 1] == "leetspeak-v1"
    assert command[command.index("--target-profile") + 1] == "synthetic-socmate-tier1"


def _run_record(status="RUNNING"):
    return DeepTeamRunRecord(
        run_id="api-run-cancel",
        status=status,
        created_at="2026-10-01T12:00:00Z",
        started_at="2026-10-01T12:00:01Z",
        scenario="socmate-tier1-permission-escalation",
        vulnerability="ExcessiveAgency:permissions",
        attack="PermissionEscalation",
        artifact_available=False,
        logs=[],
    )


def test_legacy_run_records_do_not_inherit_new_verification_claims():
    record = _run_record()

    assert record.catalog_schema_version == "1.0"
    assert record.attack_applicability == "UNREVIEWED"
    assert record.attack_capability_level == "REGISTERED"
    assert record.vulnerability_applicability == "UNREVIEWED"
    assert record.vulnerability_capability_level == "REGISTERED"


def test_cancellation_updates_state_once_and_terminates_retained_process(monkeypatch, tmp_path):
    process = object()
    terminated = []
    monkeypatch.setattr(runs_module, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(runs_module, "_runs", {"api-run-cancel": _run_record()})
    monkeypatch.setattr(runs_module, "_processes", {"api-run-cancel": process})
    monkeypatch.setattr(runs_module, "_terminate_process", lambda value: terminated.append(value) or True)

    first = cancel_deepteam_run("api-run-cancel")
    second = cancel_deepteam_run("api-run-cancel")

    assert first.status == "CANCEL_REQUESTED"
    assert first.cancellation_requested_at is not None
    assert second.status == "CANCEL_REQUESTED"
    assert len(second.logs) == 1
    assert terminated == [process]


def test_cancellation_rejects_finished_run(monkeypatch, tmp_path):
    monkeypatch.setattr(runs_module, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(runs_module, "_runs", {"api-run-cancel": _run_record("COMPLETED")})
    monkeypatch.setattr(runs_module, "_processes", {})

    with pytest.raises(DeepTeamRunError, match="already finished"):
        cancel_deepteam_run("api-run-cancel")


def test_cancellation_does_not_terminate_a_reusable_pid_from_a_legacy_lock(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_root.mkdir()
    lock_path = run_root / "active-run.lock"
    lock_path.write_text('{"run_id": "api-run-cancel", "pid": 4321}', encoding="ascii")
    terminated = []
    monkeypatch.setattr(runs_module, "RUN_ROOT", run_root)
    monkeypatch.setattr(runs_module, "RUN_LOCK", lock_path)
    monkeypatch.setattr(runs_module, "_runs", {"api-run-cancel": _run_record()})
    monkeypatch.setattr(runs_module, "_processes", {})
    monkeypatch.setattr(runs_module, "_terminate_pid_tree", lambda pid: terminated.append(pid) or True)

    result = cancel_deepteam_run("api-run-cancel")

    assert result.status == "CANCEL_REQUESTED"
    assert terminated == []
    assert lock_path.exists()


def test_queued_cancellation_releases_lock_only_after_final_state(monkeypatch, tmp_path):
    run_root = tmp_path / "runs"
    run_root.mkdir()
    lock_path = run_root / "active-run.lock"
    lock_path.write_text('{"run_id": "api-run-cancel", "pid": null}', encoding="ascii")
    monkeypatch.setattr(runs_module, "RUN_ROOT", run_root)
    monkeypatch.setattr(runs_module, "RUN_LOCK", lock_path)
    monkeypatch.setattr(
        runs_module,
        "_runs",
        {"api-run-cancel": _run_record("CANCEL_REQUESTED")},
    )
    monkeypatch.setattr(runs_module, "_processes", {})

    _execute_run(
        "api-run-cancel",
        "permission-escalation-v1",
        "ExcessiveAgency:permissions",
        250_000,
        "SINGLE",
        1,
    )

    assert runs_module._runs["api-run-cancel"].status == "CANCELLED"
    assert runs_module._runs["api-run-cancel"].completed_at is not None
    assert not lock_path.exists()


def test_windows_termination_escalates_to_process_tree_kill(monkeypatch):
    class WorkerProcess:
        pid = 1234

        def __init__(self):
            self.returncode = None
            self.signals = []
            self.killed = False

        def poll(self):
            return self.returncode

        def send_signal(self, value):
            self.signals.append(value)

        def wait(self, timeout=None):
            if not self.killed:
                raise runs_module.subprocess.TimeoutExpired("worker", timeout)
            self.returncode = 1
            return self.returncode

        def kill(self):
            self.killed = True

    class TreeKillProcess:
        def wait(self, timeout=None):
            return 0

    worker = WorkerProcess()
    taskkill_commands = []
    monkeypatch.setattr(runs_module.os, "name", "nt")
    monkeypatch.setattr(runs_module.signal, "CTRL_BREAK_EVENT", 99, raising=False)
    monkeypatch.setattr(
        runs_module.subprocess,
        "Popen",
        lambda command, **kwargs: taskkill_commands.append(command) or TreeKillProcess(),
    )

    assert runs_module._terminate_process(worker) is True
    assert worker.signals == [99]
    assert taskkill_commands == [["taskkill", "/PID", "1234", "/T", "/F"]]
    assert worker.killed is True
