"""One-call, score-only advisory for an already completed Standard assessment."""
import argparse
import asyncio
import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from .contracts import CampaignBudget, ModelRole
from .deepteam_catalog import (assessment_spec_for_vulnerability, ensure_profiles_applicable,
                               fresh_selection_capability, resolve_attack_profile, resolve_vulnerability_profile)
from .execution_budget import CampaignBudgetManager
from .job_runtime import read_frozen, require_permission
from .model_clients import ModelClientError, ModelClientSettings, StructuredModelClients
from .standard_review_contracts import (MODEL, PROFILE, VERSION, StandardReviewInput, output_schema, system_instruction,
                                       StandardReview, digest, estimated_input_tokens, review_prompt, target_model_fingerprint)
from .target_profiles import resolve_target_profile
from .runtime_policy import validate_runtime, validate_installed_frameworks


class ReviewFailure(RuntimeError):
    def __init__(self, payload):
        super().__init__("Standard review failed closed")
        self.payload = payload


def validate_scope(source):
    target = resolve_target_profile(source.target_profile_id)
    vulnerability = resolve_vulnerability_profile(source.vulnerability_profile_id)
    expected = assessment_spec_for_vulnerability(vulnerability, target.purpose, target.profile_id)
    if source.target_profile_version != target.version or digest(expected.model_dump(mode="json")) != source.assessment_spec_sha256:
        raise ValueError("The frozen assessment boundary no longer matches this worker")
    if target_model_fingerprint(source.parent_snapshot["manifest"]["campaign"]) != digest({
            "profile_id": target.model_profile_id, "provider": target.provider.value, "model": target.model}):
        raise ValueError("The target model snapshot no longer matches this worker")
    snapshot = source.parent_snapshot
    if snapshot.get("run_id") != source.run_id or snapshot.get("summary", {}).get("execution_mode") != "SINGLE":
        raise ValueError("Only a bound Standard assessment may be reviewed")
    used = {snapshot.get("summary", {}).get("attack_profile_id"), *(path.get("attack_method") for path in snapshot["evidence"]["paths"])}
    for method in source.allowed_methods:
        if method.id in used:
            raise ValueError("Review choices must exclude already used methods")
        profile = resolve_attack_profile(method.id)
        if method.name != profile.name or method.description != profile.description[:60]:
            raise ValueError("Method metadata does not match the worker catalog")
        ensure_profiles_applicable(profile, vulnerability, target.profile_id)
        if (target.gateway_kind == "CHATMATE_FRESH"
                and fresh_selection_capability(profile, vulnerability).execution_capability != "EXECUTABLE"):
            raise ValueError("Review choices must be executable for the selected target")


async def run_review(source, settings, *, transport=None):
    validate_runtime()
    validate_installed_frameworks()
    validate_scope(source)
    estimated = estimated_input_tokens(source)
    if estimated > 4000:
        raise ValueError("INPUT_BUDGET_EXCEEDED")
    budget = CampaignBudgetManager(CampaignBudget(max_paths=1, max_turns_per_path=1, max_provider_calls=1,
        max_concurrent_provider_calls=1, max_total_tokens=4256, timeout_seconds=75, max_retries_per_call=0))
    events = []
    clients = StructuredModelClients(replace(settings, request_timeout_seconds=min(settings.request_timeout_seconds, 45),
        max_provider_wait_seconds=15), budget_manager=budget, event_sink=events.append, transport=transport)
    try:
        require_permission()
        result = await clients.groq_structured(MODEL, review_prompt(source), output_schema(source),
            system_instruction=system_instruction(source), role=ModelRole.ATTACK_CRITIC, profile_id=PROFILE,
            structured_response_mode="TEXT_JSON")
        allowed = {method.id for method in source.allowed_methods}
        if any(item.attack_profile_id not in allowed for item in result.output.recommendations):
            raise ValueError("RECOMMENDATION_NOT_APPLICABLE")
        attempts = [{**asdict(event), "usage": event.usage.model_dump(mode="json") if event.usage else None} for event in events]
        return StandardReview(schema_version=source.schema_version, run_id=source.run_id, review_id=source.review_id, created_at=source.created_at,
            completed_at=datetime.now(timezone.utc).isoformat(), input_sha256=digest(source.model_dump(mode="json")),
            source_audit_sha256=source.source_audit_sha256, assessment_spec_sha256=source.assessment_spec_sha256,
            source_path_id=source.source_path_id,
            recommendations=sorted(result.output.recommendations, key=lambda item: (-item.priority, item.attack_profile_id)),
            input_tokens_estimate=estimated, budget=asdict(await budget.snapshot()), model_attempts=attempts)
    except Exception as error:
        raise ReviewFailure({"error_code": error.code.value if isinstance(error, ModelClientError) else "INPUT_OR_RESULT_INVALID",
            "budget": asdict(await budget.snapshot()), "model_attempts": [
                {**asdict(event), "usage": event.usage.model_dump(mode="json") if event.usage else None} for event in events]}) from None
    finally:
        await clients.close()


def main():
    parser = argparse.ArgumentParser(description="One bounded Standard assessment advisory")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = None
    try:
        if args.input.stat().st_size > 4_000_000:
            raise ValueError("INPUT_TOO_LARGE")
        document = json.loads(read_frozen(args.input))
        source = StandardReviewInput.model_validate(document)
        if digest(source.model_dump(mode="json")) != args.input_sha256:
            raise ValueError("Frozen input digest mismatch")
        settings = ModelClientSettings(groq_api_key="", openrouter_api_key="",
            groq_critic_api_key=os.getenv("GROQ_CRITIC_API_KEY", "").strip(),
            request_timeout_seconds=float(os.getenv("SECMATE_REQUEST_TIMEOUT_SECONDS", "45")))
        review = asyncio.run(run_review(source, settings))
        payload = review.model_dump(mode="json")
    except Exception as error:
        payload = {"schema_version": source.schema_version if source else VERSION, "run_id": source.run_id if source else None,
            "review_id": source.review_id if source else None, "input_sha256": args.input_sha256,
            "status": "FAILED", "error_code": error.code.value if isinstance(error, ModelClientError) else "INPUT_OR_RESULT_INVALID"}
        if isinstance(error, ReviewFailure):
            payload.update(error.payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=True), encoding="ascii")
    raise SystemExit(1 if payload.get("status") == "FAILED" else 0)


if __name__ == "__main__":
    main()
