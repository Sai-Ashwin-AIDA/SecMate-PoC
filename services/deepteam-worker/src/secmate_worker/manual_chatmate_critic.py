from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from .chatmate_candidates import wait_for_start_gate, _model_attempt_payload
from .contracts import CampaignBudget, AssessmentSpec, CHATMATE_ASSESSMENT_SPEC_HASHES
from .critic_contracts import (ManualChatMateCriticInput, ManualChatMateCriticOutput,
                               CompleteManualChatMateCriticOutput,
                               ChatMateCriticReview, canonical_hash, text_hash,
                               critic_prompts, critic_system_hash, validate_review_sources,
                               ChatMateCriticFailure, CriticFailureAttempt, CriticFailureCode)
from .execution_budget import CampaignBudgetManager, BudgetExceededError
from .model_clients import ModelClientSettings, StructuredModelClients, ModelClientError, PROVIDER_ERROR_ALLOWLISTS
from .model_profiles import GROQ_QWEN_CRITIC
from .artifact_redaction import redact_advisory_output as _redact
from .evidence_inventory import select_citations


class CriticInputError(ValueError):
    pass


def _write_json_artifact(path, payload):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="ascii")
    os.replace(temporary, path)


def _failure_payload(error, source, digest, phase):
    # Exceptions, provider messages, request IDs and completions are never serialized.
    attempts = []
    if isinstance(error, ModelClientError):
        code = error.code.value if error.code.value in CriticFailureCode.__args__ else "RUNTIME_ERROR"
        budget_code = getattr(error, "budget_error_code", None)
        if code == "BUDGET_EXHAUSTED" and budget_code in {"CALL_BUDGET_EXHAUSTED", "TOKEN_BUDGET_EXHAUSTED"}:
            code = budget_code
        if code != "CONFIGURATION" and error.provider.value == "GROQ":
            details = {
                "error_code": code,
                "status_code": error.status_code if type(error.status_code) is int and 100 <= error.status_code <= 599 else None,
                "latency_ms": min(error.latency_ms, 3_600_000) if type(error.latency_ms) is int and error.latency_ms >= 0 else 0,
                "retryable": error.retryable is True,
            }
            for name, allowed in PROVIDER_ERROR_ALLOWLISTS.items():
                value = getattr(error, f"provider_error_{name}", None)
                if isinstance(value, str) and value in allowed:
                    details[f"provider_error_{name}"] = value
            attempts.append(CriticFailureAttempt.model_validate(details))
    elif isinstance(error, BudgetExceededError):
        code = error.code.value if error.code.value in {"CALL_BUDGET_EXHAUSTED", "TOKEN_BUDGET_EXHAUSTED", "DEADLINE_EXCEEDED"} else "BUDGET_EXHAUSTED"
    elif phase == "gate" and isinstance(error, TimeoutError):
        code = "START_GATE_TIMEOUT"
    elif isinstance(error, CriticInputError) or phase == "input":
        code = "INPUT_INVALID"
    elif phase == "configuration":
        code = "CONFIGURATION"
    elif phase == "artifact":
        code = "ARTIFACT_INVALID"
    elif isinstance(error, ValidationError):
        code = "SCHEMA_VALIDATION"
    elif isinstance(error, TimeoutError):
        code = "REQUEST_TIMEOUT"
    else:
        code = "RUNTIME_ERROR"
    return ChatMateCriticFailure(error_code=code,
        critic_review_id=source.critic_review_id if source else None,
        run_id=source.run_id if source else None,
        source_input_sha256=digest if re.fullmatch(r"[a-f0-9]{64}", digest or "") else None,
        model_attempts=attempts)


async def run_manual_chatmate_critic(source: ManualChatMateCriticInput, settings: ModelClientSettings, *, clients_factory=StructuredModelClients) -> ChatMateCriticReview:
    # Revalidate even callers supplying a constructed/mutated model; never trust CLI input.
    try:
        source = ManualChatMateCriticInput.model_validate(source.model_dump(mode="json"))
        spec = AssessmentSpec.model_validate(source.assessment_spec)
    except ValidationError:
        raise CriticInputError("Invalid critic input contract") from None
    if spec.target_profile_id != "chatmate" or canonical_hash(source.assessment_spec) not in CHATMATE_ASSESSMENT_SPEC_HASHES.values():
        raise CriticInputError("Noncanonical critic assessment specification")
    budget = CampaignBudgetManager(CampaignBudget(max_paths=1, max_turns_per_path=1,
        max_provider_calls=1, max_concurrent_provider_calls=1, max_total_tokens=50_000,
        timeout_seconds=300, max_retries_per_call=0))
    attempts = []
    clients = clients_factory(settings, budget_manager=budget, event_sink=attempts.append)
    system, user = critic_prompts(source, "1.1")
    try:
        result = await clients.groq_structured(GROQ_QWEN_CRITIC.model, user,
            CompleteManualChatMateCriticOutput, system_instruction=system,
            role=GROQ_QWEN_CRITIC.role, profile_id=GROQ_QWEN_CRITIC.profile_id,
            structured_response_mode="TEXT_JSON")
        output = CompleteManualChatMateCriticOutput.model_validate(_redact(result.output.model_dump(mode="json")))
    finally:
        await clients.close()
    payload = output.model_dump(mode="json")
    evidence_citations = select_citations(output.evidence_references, source.evidence_ids)
    policy_citations = select_citations(output.policy_references, source.policy_ids)
    invalid_evidence = list(evidence_citations.invalid)
    invalid_policies = list(policy_citations.invalid)
    payload["evidence_references"] = list(evidence_citations.valid)
    payload["policy_references"] = list(policy_citations.valid)
    available = not (invalid_evidence or invalid_policies) and bool(payload["evidence_references"]) and bool(payload["policy_references"])
    # Unsupported evidence claims remain visibly incomplete hypotheses.
    if output.weak_point_status == "EVIDENCE_SUPPORTED" and not available:
        payload["weak_point_status"] = "HYPOTHESIS"
    review = ChatMateCriticReview.model_validate({**payload, "schema_version": "1.1",
        "critic_review_id": source.critic_review_id, "run_id": source.run_id,
        "source_evaluation_id": source.source_evaluation_id, "created_at": source.created_at,
        "source_candidate_sha256": source.source_candidate_sha256,
        "source_correlation_sha256": source.source_correlation_sha256,
        "source_judge_sha256": source.source_judge_sha256,
        "source_input_sha256": canonical_hash(source.model_dump(mode="json")),
        "critic_system_instruction_sha256": critic_system_hash(system, "1.1"), "critic_user_prompt_sha256": text_hash(user),
        "invalid_evidence_references": invalid_evidence, "invalid_policy_references": invalid_policies,
        "recommendation_available": available, "critic_data_collection_attested": True,
        "budget": {**asdict(await budget.snapshot()), "max_retries_per_call": 0},
        "model_attempts": [_redact(_model_attempt_payload(event)) for event in attempts]})
    validate_review_sources(review, source)
    return review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--start-gate", type=Path, required=True)
    parser.add_argument("--allow-groq-data-collection", action="store_true")
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args()
    source = None
    phase = "gate"
    try:
        wait_for_start_gate(args.start_gate)
        phase = "input"
        if not args.allow_groq_data_collection:
            raise CriticInputError("Explicit Groq critic collection approval is required")
        from .job_runtime import read_frozen
        source = ManualChatMateCriticInput.model_validate_json(read_frozen(args.input).decode("ascii"))
        if canonical_hash(source.model_dump(mode="json")) != args.input_sha256:
            raise CriticInputError("Frozen critic input digest mismatch")
        phase = "configuration"
        if args.env_file:
            load_dotenv(args.env_file)
        settings = ModelClientSettings(groq_api_key="", groq_critic_api_key=os.getenv("GROQ_CRITIC_API_KEY", "").strip(),
            openrouter_api_key="", request_timeout_seconds=float(os.getenv("SECMATE_REQUEST_TIMEOUT_SECONDS", "90")))
        if not settings.groq_critic_api_key:
            raise ValueError("Dedicated Groq Critic configuration unavailable")
        phase = "inference"
        review = asyncio.run(run_manual_chatmate_critic(source, settings))
        phase = "artifact"
        _write_json_artifact(args.output, review.model_dump(mode="json"))
    except Exception as error:
        failure = _failure_payload(error, source, args.input_sha256, phase)
        try:
            _write_json_artifact(args.output.with_name("critic-failure.json"), failure.model_dump(mode="json"))
        except OSError:
            pass
        # A bounded allowlisted fallback also works when the artifact cannot be written.
        print(json.dumps(failure.model_dump(mode="json"), ensure_ascii=True))
        raise SystemExit(f"Manual ChatMate critic failed closed ({failure.error_code})") from None


if __name__ == "__main__":
    main()
