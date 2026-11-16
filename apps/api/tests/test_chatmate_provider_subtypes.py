import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import secmate_api.chatmate_runs as runs
from secmate_api.contracts import ChatMateModelAttempt
from secmate_api.contracts import ChatMateCandidateCheck, ChatMateGenerationFailureDetail, ChatMateWorkerPayload
from test_chatmate_failures_delete import local_runs, store
from test_chatmate_runs import _worker_payload


def failed_attempt():
    return {
        "provider": "GROQ", "model": "qwen/qwen3.8-27b", "outcome": "FAILURE",
        "latency_ms": 1, "usage": None, "error_code": "INVALID_JSON", "retryable": False,
        "status_code": 400, "role": "ATTACKER", "profile_id": "groq-qwen-attacker",
        "provider_error_code": "json_validate_failed",
        "provider_error_type": "invalid_request_error", "provider_error_param": "response_format",
    }


def test_safe_subtype_survives_api_failure_classification_without_provider_text():
    code, message = runs._generation_failure_details(1, "", "", {
        "error": {"message": "private-provider-message", "failed_generation": "private-completion"},
        "model_attempts": [failed_attempt()],
    })
    assert code == "PROVIDER_INVALID_RESPONSE"
    assert "could not produce valid JSON" in message
    assert len(message) < 200
    _, detail = runs._generation_failure_details(1, "", "", {"model_attempts": [failed_attempt()]}, diagnostics=True)
    for expected in ("json_validate_failed", "invalid_request_error", "response_format"):
        assert expected in detail
        assert expected not in message
    assert "private-provider-message" not in message
    assert "private-completion" not in message


@pytest.mark.parametrize("name", ["provider_error_code", "provider_error_type", "provider_error_param"])
def test_api_contract_and_failure_context_reject_unknown_subtype_text(name):
    attempt = {**failed_attempt(), name: "private-reflected-value"}
    with pytest.raises(ValidationError):
        ChatMateModelAttempt.model_validate(attempt)
    _, message = runs._generation_failure_details(1, "", "", {"model_attempts": [attempt]})
    assert "private-reflected-value" not in message


@pytest.mark.parametrize("candidate_count", [2, 3])
def test_successful_repair_artifact_is_accepted_with_failed_attempt_metadata(local_runs, monkeypatch, candidate_count):
    payload = _worker_payload()
    payload["batch"]["candidates"] = payload["batch"]["candidates"][:candidate_count]
    payload["model_attempts"].insert(0, failed_attempt())
    payload["budget"].update(provider_calls_attempted=2, provider_calls_failed=1, calls_with_missing_usage=1)
    record = store("QUEUED")
    runs._claim_worker_lock(record.run_id)

    class Process:
        pid = 1234
        returncode = 0

        def __init__(self, command, **kwargs):
            Path(command[command.index("--output") + 1]).write_text(json.dumps(payload))

        def communicate(self, timeout):
            return "", ""

        def poll(self):
            return 0

    monkeypatch.setattr(runs.subprocess, "Popen", Process)
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000)
    result = runs._runs[record.run_id]
    assert result.status == "AWAITING_SELECTION"
    assert len(result.candidate_batch.candidates) == candidate_count
    assert result.generation_model_attempts[0].provider_error_code == "json_validate_failed"
    assert result.generation_budget.provider_calls_attempted == 2
    assert not runs.RUN_LOCK.exists()


@pytest.mark.parametrize("count", [0, 1])
def test_baseline_shortfall_uses_current_two_candidate_contract(count):
    code, message = runs._generation_failure_details(1, "", "", {
        "error": {"code": "BASELINE_COUNT_MISMATCH"},
        "diagnostics": {"distinct_baseline_count": count},
    })
    assert code == "BASELINE_COUNT_MISMATCH"
    assert f"{count} of 2" in message


def test_check_error_contract_preserves_legacy_and_rejects_invented_reason():
    check = {"candidate_slot": 1, "enhancement_attempt": 1, "prompt_characters": 317,
             "outcome": "CHECK_ERROR", "reason_category": None}
    assert ChatMateCandidateCheck.model_validate(check).outcome == "CHECK_ERROR"
    assert ChatMateCandidateCheck.model_validate({**check, "outcome": "EMPTY"}).prompt_characters == 317
    with pytest.raises(ValidationError):
        ChatMateCandidateCheck.model_validate({**check, "reason_category": "COMPLETE"})
    with pytest.raises(ValidationError):
        ChatMateGenerationFailureDetail.model_validate({"code": "GENERATION_CHECK_ERROR", "message": "Failed",
            "stage": "private raw output", "category": "SECRET"})
    with pytest.raises(ValidationError, match="Successful batch cannot contain"):
        ChatMateWorkerPayload.model_validate({**_worker_payload(), "candidate_checks": [check]})


@pytest.mark.parametrize("category,code,stage,cleanup", [
    ("SCHEMA_PREPARATION", "GENERATION_CHECK_ERROR", "COMPLETENESS", False),
    ("VERDICT_VALIDATION", "GENERATION_CHECK_ERROR", "COMPLETENESS", False),
    ("ADAPTER_RUNTIME", "GENERATION_CHECK_ERROR", "COMPLETENESS", True),
    ("LOCAL_RUNTIME", "GENERATION_CHECK_ERROR", "COMPLETENESS", False),
    ("SCHEMA_PREPARATION", "GENERATION_SCHEMA_UNRESOLVED", "COMPLETENESS", False),
    ("LOCAL_RUNTIME", "GENERATION_CLEANUP_ERROR", "CLEANUP", True),
])
def test_local_failure_keeps_truthful_stage_and_check_in_saved_run(local_runs, monkeypatch, category, code, stage, cleanup):
    payload = _worker_payload()
    payload.pop("batch")
    payload["error"] = {"code": code, "message": "Candidate validation stopped.",
        "stage": stage, "category": category, "candidate_slot": 1, "enhancement_attempt": 1, "cleanup_failed": cleanup,
        "python_version": "3.11.9", "worker_source_sha256": "a" * 64, "deepteam_commit": "b" * 40}
    payload["diagnostics"] = {}
    payload["candidate_checks"] = [{"candidate_slot": 1, "enhancement_attempt": 1,
        "prompt_characters": 317, "outcome": "CHECK_ERROR", "reason_category": None}]
    record = store("QUEUED")
    runs._claim_worker_lock(record.run_id)

    class Process:
        pid = 1234
        returncode = 1

        def __init__(self, command, **kwargs):
            Path(command[command.index("--output") + 1]).write_text(json.dumps(payload))

        def communicate(self, timeout):
            return "", "bounded failure"

        def poll(self):
            return 1

    monkeypatch.setattr(runs.subprocess, "Popen", Process)
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000)
    result = runs._runs[record.run_id]
    assert result.status == "FAILED"
    assert result.error_code == code
    assert result.candidate_batch is None
    assert result.generation_candidate_checks[0].outcome == "CHECK_ERROR"
    assert any(f"category={category}" in log.message and f"stage={stage}" in log.message for log in result.logs)
    if cleanup:
        assert any("cleanup_failed=True" in log.message for log in result.logs)
    assert any("CHECK_ERROR" in log.message and "317 characters" in log.message for log in result.logs)
    assert not runs.RUN_LOCK.exists()


def test_provider_json_failure_keeps_subtype_diagnostics_in_logs(local_runs, monkeypatch):
    record = store("QUEUED")
    runs._claim_worker_lock(record.run_id)

    class Process:
        pid = 1234
        returncode = 1

        def __init__(self, command, **kwargs):
            Path(command[command.index("--output") + 1]).write_text(json.dumps({
                "error": {"code": "INVALID_JSON"}, "model_attempts": [failed_attempt()]}))

        def communicate(self, timeout):
            return "", "bounded worker diagnostics"

        def poll(self):
            return 1

    monkeypatch.setattr(runs.subprocess, "Popen", Process)
    runs._execute_generation(record.run_id, "prompt-injection-v1", 100_000)
    result = runs._runs[record.run_id]
    assert result.status == "FAILED"
    assert result.error_code == "PROVIDER_INVALID_RESPONSE"
    assert "valid JSON" in result.error_message
    assert "Details:" not in result.error_message
    assert "json_validate_failed" not in result.error_message
    assert any("json_validate_failed" in log.message and "response_format" in log.message for log in result.logs)
    assert result.candidate_batch is None
    assert not runs.RUN_LOCK.exists()
