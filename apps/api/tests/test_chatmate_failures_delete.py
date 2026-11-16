import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import secmate_api.chatmate_runs as runs
from secmate_api.config import Settings
from secmate_api.main import app
from test_chatmate_runs import _record, _awaiting_evaluation, _worker_payload


@pytest.fixture
def local_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(runs, "CHATMATE_RUN_ROOT", tmp_path / "runs")
    monkeypatch.setattr(runs, "RUN_LOCK", tmp_path / "active-run.lock")
    monkeypatch.setattr(runs, "WORKER_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_runs", {})
    monkeypatch.setattr(runs, "_processes", {})
    runs._generation_failure_reconciliation_cache.clear()
    return tmp_path


def store(status="AWAITING_SELECTION"):
    record = _record(status)
    runs._persist(record)
    runs._runs[record.run_id] = record
    return record


@pytest.mark.parametrize("provider_code,expected", [
    ("AUTHENTICATION", "PROVIDER_AUTHENTICATION_FAILED"),
    ("RATE_LIMITED", "PROVIDER_RATE_LIMITED"),
    ("ROUTE_UNAVAILABLE", "PROVIDER_MODEL_UNAVAILABLE"),
    ("READ_TIMEOUT", "PROVIDER_TIMEOUT"),
    ("NETWORK_ERROR", "PROVIDER_UNAVAILABLE"),
    ("SCHEMA_VALIDATION", "PROVIDER_INVALID_RESPONSE"),
    ("BUDGET_EXHAUSTED", "GENERATION_BUDGET_EXHAUSTED"),
    ("DEADLINE_EXCEEDED", "GENERATION_DEADLINE_EXCEEDED"),
    ("CONFIGURATION", "GENERATION_CONFIGURATION_ERROR"),
    ("REQUEST_REJECTED", "PROVIDER_REQUEST_REJECTED"),
])
def test_structured_provider_classification_and_redacted_details(provider_code, expected):
    payload = {"model_attempts": [{"outcome": "FAILURE", "provider": "GROQ",
        "model": "qwen/qwen3.8-27b", "error_code": provider_code,
        "status_code": 400, "provider_request_id": "req-123",
        "error_message": "provider detail: token=short"}]}
    code, message = runs._generation_failure_details(1, json.dumps(payload), "", diagnostics=True)
    assert code == expected
    assert "qwen/qwen3.8-27b" in message
    assert "req-123" in message
    assert "provider detail" in message
    assert "short" not in message


@pytest.mark.parametrize("stderr,expected", [
    ("ModelRequestError: Groq request failed with HTTP 429", "PROVIDER_RATE_LIMITED"),
    ("ModelRequestError: Groq request failed with HTTP 401", "PROVIDER_AUTHENTICATION_FAILED"),
    ("ModuleNotFoundError: No module named deepteam", "GENERATION_RUNTIME_ERROR"),
    ("GROQ_API_KEY is required for ChatMate candidate generation.", "GENERATION_CONFIGURATION_ERROR"),
    ("RuntimeError: unexpected failure", "GENERATION_PROCESS_EXIT"),
])
def test_traceback_classification(stderr, expected):
    assert runs._generation_failure_details(1, "", stderr)[0] == expected


def test_deadline_preserves_terminal_rate_limit_context_without_claiming_token_exhaustion():
    payload = {"error": {"code": "DEADLINE_EXCEEDED"}, "model_attempts": [
        {"outcome": "FAILURE", "error_code": "RATE_LIMITED", "status_code": 429}]}
    code, message = runs._generation_failure_details(1, "", "", payload)
    assert code == "GENERATION_DEADLINE_EXCEEDED"
    assert "deadline" in message and "rate limited" in message
    assert "token budget" not in message


def test_real_subprocess_failure_is_sanitized_persisted_and_reloaded(local_runs, monkeypatch):
    record = store("QUEUED")
    monkeypatch.setenv("TEST_API_KEY", "environment-credential")
    # Real pipes, process exit, and stderr traceback; no provider is contacted.
    script = "import sys; print('provider stdout'); sys.stderr.write('HTTP 401 Authorization: Bearer tiny-secret\\nGROQ_API_KEY=short-key password=abc token=xyz https://user:pass@host/path environment-credential gsk_123456789abcdef\\n'); raise RuntimeError('authentication failed')"
    monkeypatch.setattr(runs, "_worker_command", lambda *args: [sys.executable, "-c", script])
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000, Settings("short-key", "", 45))
    failed = runs._runs[record.run_id]
    assert failed.error_code == "PROVIDER_AUTHENTICATION_FAILED"
    assert failed.evaluation_attempts == 0
    assert failed.final_status is None
    text = (runs.CHATMATE_RUN_ROOT / record.run_id / "record.json").read_text()
    for secret in ("tiny-secret", "short-key", "abc", "xyz", "user:pass", "environment-credential", "gsk_123456789abcdef"):
        assert secret not in text
    assert "provider stdout" in text
    assert "exit=1" in text
    runs._runs.clear()
    runs._load_records()
    assert runs._runs[record.run_id] == failed
    assert not runs.RUN_LOCK.exists()


def test_sanitization_redacts_before_bounding(monkeypatch):
    monkeypatch.setenv("TEST_SECRET", "a-credential-crossing-the-boundary")
    raw = "x" * 5000 + "a-credential-crossing-the-boundary" + "token=abc\n" * 1000
    sanitized = runs._sanitize_generation_output(raw)
    assert len(sanitized) <= 4000
    assert "credential" not in sanitized
    assert "abc" not in sanitized


def test_explicit_provider_code_outranks_incidental_traceback_text():
    code, message = runs._generation_failure_details(1, "", "authentication middleware: HTTP 401", {
        "error": {"code": "RATE_LIMITED", "message": "quota exhausted"},
    })
    assert code == "PROVIDER_RATE_LIMITED"
    assert "rate limits" in message


def test_recovered_503_is_not_reported_as_the_terminal_enhancement_failure():
    payload = {"error": {"code": "GENERATION_FAILED", "message": "DeepTeam did not apply Prompt Injection to candidate slot 3."},
               "model_attempts": [{"outcome": "FAILURE", "error_code": "PROVIDER_UNAVAILABLE", "status_code": 503},
                                  {"outcome": "SUCCESS", "error_code": None}]}
    code, message = runs._generation_failure_details(1, "", "Old HTTP 503", payload)
    assert code == "ENHANCEMENT_NOT_APPLIED"
    assert "selected attack method" in message
    assert "could not be reached" not in message


def test_terminal_503_has_service_outage_guidance_not_network_guidance():
    code, message = runs._generation_failure_details(1, "", "", {
        "error": {"code": "PROVIDER_UNAVAILABLE", "message": "Bounded provider failure."},
        "model_attempts": [{"outcome": "FAILURE", "error_code": "PROVIDER_UNAVAILABLE", "status_code": 503}],
    })
    assert code == "PROVIDER_UNAVAILABLE"
    assert "HTTP 503" in message
    assert "retries were exhausted" in message
    assert "network connectivity" not in message


def test_uncertain_completeness_does_not_claim_confirmed_truncation():
    code, message = runs._generation_failure_details(1, "", "", {
        "error": {"code": "COMPLETENESS_UNCERTAIN", "message": "Bounded uncertainty."},
        "model_attempts": [{"outcome": "SUCCESS"}],
    })
    assert code == "COMPLETENESS_UNCERTAIN"
    assert "uncertainty, not confirmed truncation" in message


def test_saved_legacy_failure_diagnosis_is_corrected_without_changing_failed_outcome(local_runs):
    record = store("FAILED").model_copy(update={"error_code": "PROVIDER_UNAVAILABLE",
        "error_message": "Groq could not be reached. Check network connectivity and provider availability."})
    runs._runs[record.run_id] = record
    runs._persist(record)
    path = runs.CHATMATE_RUN_ROOT / record.run_id / "candidate-batch.json"
    worker = _worker_payload()
    success = worker["model_attempts"][0]
    failure = {**success, "outcome": "FAILURE", "usage": None, "error_code": "PROVIDER_UNAVAILABLE", "retryable": True, "status_code": 503}
    budget = {**worker["budget"], "provider_calls_attempted": 2, "provider_calls_failed": 1,
              "provider_calls_succeeded": 1, "calls_with_missing_usage": 1}
    payload = {"error": {"code": "GENERATION_FAILED", "message": "DeepTeam did not apply Prompt Injection to candidate slot 3."},
        "diagnostics": {}, "budget": budget, "model_attempts": [failure, success]}
    path.write_text(json.dumps(payload), encoding="ascii")
    updated = runs.get_chatmate_run(record.run_id)
    assert updated.error_code == "ENHANCEMENT_NOT_APPLIED"
    assert updated.status == "FAILED" and updated.final_status is None
    assert updated.candidate_batch is None and updated.manual_evidence is None
    assert updated.logs == record.logs
    assert json.loads((path.parent / "record.json").read_text(encoding="ascii"))["error_code"] == "ENHANCEMENT_NOT_APPLIED"


@pytest.mark.parametrize("kind", ["oversized", "bad_budget", "bad_count", "unsupported"])
def test_legacy_failure_reconciliation_rejects_unbounded_or_inconsistent_artifacts(local_runs, monkeypatch, kind):
    record = store("FAILED").model_copy(update={"error_code": "GENERATION_PROCESS_EXIT",
        "error_message": "The candidate worker failed. Review the sanitized worker diagnostics before starting a new run."})
    runs._runs[record.run_id] = record
    runs._persist(record)
    worker = _worker_payload()
    payload = {"error": {"code": "BASELINE_COUNT_MISMATCH", "message": "Synthetic shortfall."},
        "diagnostics": {"distinct_baseline_count": 2}, "budget": worker["budget"], "model_attempts": worker["model_attempts"]}
    if kind == "bad_budget": payload["budget"]["max_total_tokens"] = 50_000
    if kind == "bad_count": payload["model_attempts"] = []
    if kind == "unsupported": payload["error"]["code"] = "UNKNOWN_PRIVATE_FAILURE"
    path = runs.CHATMATE_RUN_ROOT / record.run_id / "candidate-batch.json"
    path.write_text(json.dumps(payload), encoding="ascii")
    if kind == "oversized":
        monkeypatch.setattr(runs, "CHATMATE_FAILURE_ARTIFACT_MAX_BYTES", 10)
    unchanged = runs.get_chatmate_run(record.run_id)
    assert unchanged.error_code == "GENERATION_PROCESS_EXIT"
    assert unchanged.error_message == record.error_message


def test_unchanged_legacy_failure_artifact_is_reconciled_only_once(local_runs, monkeypatch):
    record = store("FAILED").model_copy(update={"error_code": "GENERATION_PROCESS_EXIT",
        "error_message": "The candidate worker failed. Review the sanitized worker diagnostics before starting a new run."})
    runs._runs[record.run_id] = record
    runs._persist(record)
    worker = _worker_payload()
    payload = {"error": {"code": "UNKNOWN_PRIVATE_FAILURE", "message": "Synthetic unsupported failure."},
        "diagnostics": {"distinct_baseline_count": 2}, "budget": worker["budget"], "model_attempts": worker["model_attempts"]}
    path = runs.CHATMATE_RUN_ROOT / record.run_id / "candidate-batch.json"
    path.write_text(json.dumps(payload), encoding="ascii")
    validations = 0
    original = runs.ChatMateWorkerFailurePayload.model_validate_json

    def traced(cls, content):
        nonlocal validations
        validations += 1
        return original(content)

    monkeypatch.setattr(runs.ChatMateWorkerFailurePayload, "model_validate_json", classmethod(traced))
    assert runs.get_chatmate_run(record.run_id).error_code == "GENERATION_PROCESS_EXIT"
    assert runs.get_chatmate_run(record.run_id).error_code == "GENERATION_PROCESS_EXIT"
    assert validations == 1


@pytest.mark.parametrize("error_code", ["BASELINE_COUNT_MISMATCH", "INCOMPLETE_CANDIDATE"])
def test_baseline_shortfall_has_actionable_failure_and_preserved_accounting(local_runs, monkeypatch, error_code):
    record = store("QUEUED")
    worker = _worker_payload()
    failure = {"error": {"code": error_code, "message": "Synthetic bounded shortfall."},
               "diagnostics": {"distinct_baseline_count": 1, "refined_case_count": 1},
               "budget": worker["budget"], "model_attempts": worker["model_attempts"]}
    failure["candidate_checks"] = [] if error_code == "BASELINE_COUNT_MISMATCH" else [{"candidate_slot": 1, "enhancement_attempt": 3,
        "prompt_characters": 500, "outcome": "INCOMPLETE", "reason_category": "ABRUPT_ENDING"}]

    class Process:
        pid = 1234
        returncode = 1

        def __init__(self, command, **kwargs):
            Path(command[command.index("--output") + 1]).write_text(json.dumps(failure), encoding="ascii")

        def communicate(self, timeout):
            return "", "Candidate generation failed; code=BASELINE_COUNT_MISMATCH"

        def poll(self):
            return self.returncode

    monkeypatch.setattr(runs.subprocess, "Popen", Process)
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000)
    failed = runs._runs[record.run_id]
    assert failed.status == "FAILED"
    assert failed.error_code == error_code
    assert ("1 of 2" if error_code == "BASELINE_COUNT_MISMATCH" else "self-contained attack") in failed.error_message
    assert failed.generation_budget.provider_calls_attempted == 1
    assert len(failed.generation_model_attempts) == 1
    if error_code == "INCOMPLETE_CANDIDATE":
        assert failed.generation_candidate_checks[0].reason_category == "ABRUPT_ENDING"
        assert any("ABRUPT_ENDING" in log.message for log in failed.logs)
    assert failed.candidate_batch is None
    assert failed.final_status is None
    persisted = json.loads((runs.CHATMATE_RUN_ROOT / record.run_id / "record.json").read_text(encoding="ascii"))
    assert persisted["generation_budget"] == failure["budget"]
    code, message = runs._generation_failure_details(1, "", "authentication middleware: HTTP 401", failure)
    assert code == error_code


@pytest.mark.parametrize("mode,expected", [
    ("missing", "GENERATION_ARTIFACT_MISSING"),
    ("invalid", "GENERATION_ARTIFACT_INVALID"),
    ("exit", "GENERATION_PROCESS_EXIT"),
    ("timeout", "GENERATION_TIMEOUT"),
])
def test_worker_exit_missing_invalid_and_timeout_are_distinct(local_runs, monkeypatch, mode, expected):
    record = store("QUEUED")

    class Process:
        pid = 1234
        returncode = 1 if mode == "exit" else 0

        def __init__(self, command, **kwargs):
            if mode == "invalid":
                Path(command[command.index("--output") + 1]).write_text("{invalid")

        def communicate(self, timeout):
            if mode == "timeout":
                raise subprocess.TimeoutExpired("worker", timeout, stderr=b"token=abc timed out")
            return "", "diagnostic"

        def poll(self):
            return self.returncode

    monkeypatch.setattr(runs.subprocess, "Popen", Process)
    monkeypatch.setattr(runs, "_terminate_process", lambda process: True)
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000)
    failed = runs._runs[record.run_id]
    assert failed.error_code == expected
    assert "abc" not in json.dumps(failed.model_dump(mode="json"))


@pytest.mark.parametrize("status", ["AWAITING_SELECTION", "AWAITING_RESPONSE", "REJECTED", "FAILED", "ABANDONED", "AWAITING_EVALUATION", "COMPLETED"])
def test_delete_idle_and_terminal_removes_all_artifacts_without_resurrection(local_runs, monkeypatch, status):
    if status in {"AWAITING_EVALUATION", "COMPLETED"}:
        record = _awaiting_evaluation(monkeypatch, runs.CHATMATE_RUN_ROOT)
        record = record.model_copy(update={"status": status})
        runs._runs[record.run_id] = record
        runs._persist(record)
    elif status == "ABANDONED":
        record = runs.abandon_chatmate_run(store().run_id)
    else:
        record = store(status)
    directory = runs.CHATMATE_RUN_ROOT / record.run_id
    nested = directory / "evaluations" / "eval-test"
    nested.mkdir(parents=True)
    (nested / "evidence.json").write_text("artifact")
    runs.delete_chatmate_run(record.run_id)
    assert not directory.exists()
    assert runs.get_chatmate_run(record.run_id) is None
    assert runs.list_chatmate_runs() == []
    with pytest.raises(runs.ChatMateRunError, match="cannot be persisted"):
        runs._persist(record)
    # Even a stale writer recreating the record cannot reload deleted history.
    directory.mkdir()
    (directory / "record.json").write_text(record.model_dump_json())
    runs._load_records()
    assert runs.get_chatmate_run(record.run_id) is None


@pytest.mark.parametrize("status,ownership", [("QUEUED", "none"), ("GENERATING", "none"), ("EVALUATING", "none"), ("FAILED", "process"), ("FAILED", "restart-lock")])
def test_delete_rejects_active_and_restart_owned_workers(local_runs, status, ownership):
    record = store("FAILED" if status == "EVALUATING" else status)
    runs._runs[record.run_id] = record.model_copy(update={"status": status})
    if ownership == "process":
        runs._processes[record.run_id] = object()
    elif ownership == "restart-lock":
        runs.RUN_LOCK.write_text(json.dumps({"run_id": record.run_id, "pid": 1234}))
    with pytest.raises(runs.ChatMateRunError, match="finish first"):
        runs.delete_chatmate_run(record.run_id)
    assert (runs.CHATMATE_RUN_ROOT / record.run_id / "record.json").exists()


@pytest.mark.parametrize("run_id", ["../outside", "chatmate-run-../outside", "chatmate-run-x/y", "chatmate-run-x\\y", "chatmate-run-x:stream", "C:\\outside"])
def test_invalid_paths_cannot_delete_or_persist(local_runs, run_id):
    with pytest.raises(runs.ChatMateRunError, match="identifier"):
        runs.delete_chatmate_run(run_id)
    with pytest.raises(runs.ChatMateRunError, match="identifier"):
        runs._persist(_record().model_copy(update={"run_id": run_id}))


def test_restart_uses_verified_database_instead_of_tampered_json_projection(local_runs):
    record = store()
    directory = runs.CHATMATE_RUN_ROOT / record.run_id
    (directory / "record.json").write_text(record.model_copy(update={"run_id": "chatmate-run-other"}).model_dump_json())
    runs._runs.clear()
    runs._load_records()
    assert runs._runs == {record.run_id: record}


def test_delete_rejects_linked_artifacts_and_keeps_external_files(local_runs):
    record = store()
    outside = local_runs / "outside"
    outside.mkdir()
    external = outside / "keep.txt"
    external.write_text("must remain")
    link = runs.CHATMATE_RUN_ROOT / record.run_id / "linked"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(runs.ChatMateRunError, match="Unsafe"):
        runs.delete_chatmate_run(record.run_id)
    assert external.read_text() == "must remain"
    assert runs.get_chatmate_run(record.run_id) == record
    link.rmdir() if os.name == "nt" else link.unlink()


def test_delete_rejects_unreadable_worker_ownership(local_runs):
    record = store()
    runs.RUN_LOCK.write_text("not json")
    with pytest.raises(runs.ChatMateRunError, match="ownership cannot be verified"):
        runs.delete_chatmate_run(record.run_id)
    assert runs.get_chatmate_run(record.run_id) == record


def test_failed_artifact_preserves_provider_details_and_runtime_settings(local_runs, monkeypatch):
    record = store("QUEUED")
    configured_key = "custom-key-not-in-server-env"
    captured = {}

    class Process:
        pid = 1234
        returncode = 1

        def __init__(self, command, **kwargs):
            captured.update(kwargs)
            assert configured_key not in " ".join(command)
            Path(command[command.index("--output") + 1]).write_text(json.dumps({
                "error": {"code": "RATE_LIMITED", "provider": "GROQ", "status_code": 429,
                    "message": f"daily quota exhausted {configured_key}"}}))

        def communicate(self, timeout):
            return "", "generic worker failure"

        def poll(self):
            return 1

    monkeypatch.setattr(runs.subprocess, "Popen", Process)
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000, Settings(configured_key, "", 17))
    assert captured["env"]["GROQ_API_KEY"] == configured_key
    assert captured["env"]["SECMATE_REQUEST_TIMEOUT_SECONDS"] == "17"
    failed = runs._runs[record.run_id]
    assert failed.error_code == "PROVIDER_RATE_LIMITED"
    assert "daily quota exhausted" not in failed.error_message
    assert any("daily quota exhausted" in log.message for log in failed.logs)
    assert configured_key not in failed.model_dump_json()


def test_partial_cleanup_failure_still_prevents_restart_resurrection(local_runs, monkeypatch):
    record = store()
    monkeypatch.setattr(runs.shutil, "rmtree", lambda directory: (_ for _ in ()).throw(OSError("access denied")))
    with pytest.raises(runs.ChatMateRunError, match="artifact cleanup failed"):
        runs.delete_chatmate_run(record.run_id)
    runs._load_records()
    assert runs.get_chatmate_run(record.run_id) is None
    with pytest.raises(runs.ChatMateRunError, match="cannot be persisted"):
        runs._persist(record)


def test_deletion_marker_failure_keeps_history(local_runs, monkeypatch):
    from pathlib import Path

    record = store()
    monkeypatch.setattr(Path, "touch", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("access denied")))
    with pytest.raises(runs.ChatMateRunError, match="marker could not be persisted"):
        runs.delete_chatmate_run(record.run_id)
    assert runs.get_chatmate_run(record.run_id) == record
    runs._runs.clear()
    runs._load_records()
    assert runs.get_chatmate_run(record.run_id) == record


def test_delete_guards_cors_and_exact_http_interface(local_runs):
    client = TestClient(app)
    record = store()
    endpoint = f"/api/v1/chatmate-runs/{record.run_id}"
    headers = {"X-SecMate-Local-Run": "confirmed"}
    assert client.delete(endpoint).status_code == 403
    assert client.delete(endpoint, headers={**headers, "Origin": "https://untrusted.example"}).status_code == 403
    preflight = client.options(endpoint, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "X-SecMate-Local-Run"})
    assert preflight.status_code == 200
    assert "DELETE" in preflight.headers["access-control-allow-methods"]
    runs._processes[record.run_id] = object()
    blocked = client.delete(endpoint, headers=headers)
    assert blocked.status_code == 409
    assert "finish first" in blocked.json()["detail"]
    runs._processes.clear()
    response = client.delete(endpoint, headers={**headers, "Origin": "http://127.0.0.1:5173"})
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(endpoint).status_code == 404
    assert client.delete(endpoint, headers=headers).status_code == 404
