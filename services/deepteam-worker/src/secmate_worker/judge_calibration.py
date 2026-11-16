from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

from .contracts import CampaignBudget, ModelRole, PathStatus
from .deepteam_runner import SecMateDeepTeamRunner
from .execution_budget import CampaignBudgetManager
from .gold_set import (
    _build_path,
    _normalize_references,
    fixture_sha256,
    load_suite,
)
from .model_adapters import OpenRouterDeepEvalModel
from .model_clients import ModelAttemptEvent, ModelClientSettings, StructuredModelClients
from .model_profiles import OPENROUTER_NEMOTRON_EVALUATOR
from .role_prompts import TARGET_EVALUATOR_SYSTEM_INSTRUCTION
from .runtime_policy import DEEPEVAL_VERSION, DEEPTEAM_COMMIT
from .target_evaluator import SecMateTargetEvaluator


def _attempt_payload(event: ModelAttemptEvent) -> dict:
    return {
        "provider": event.provider.value,
        "model": event.model,
        "outcome": event.outcome,
        "latency_ms": event.latency_ms,
        "usage": event.usage.model_dump(mode="json") if event.usage else None,
        "error_code": event.error_code.value if event.error_code else None,
        "retryable": event.retryable,
        "status_code": event.status_code,
        "role": event.role.value if event.role else None,
        "profile_id": event.profile_id,
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize_runs(runs: list[dict], case_ids: list[str]) -> dict:
    total = len(runs)
    completed = [run for run in runs if run["execution_error"] is None]
    matches = sum(run["verdict_match"] for run in runs)
    compromise_false_positives = sum(
        run["expected_status"] != PathStatus.COMPROMISED.value
        and run["observed_status"] == PathStatus.COMPROMISED.value
        for run in runs
    )
    compromise_false_negatives = sum(
        run["expected_status"] == PathStatus.COMPROMISED.value
        and run["observed_status"] != PathStatus.COMPROMISED.value
        for run in runs
    )
    inconclusive = sum(
        run["observed_status"] == PathStatus.INCONCLUSIVE.value for run in runs
    )
    by_case: dict[str, list[dict]] = defaultdict(list)
    confusion_matrix: dict[str, Counter] = defaultdict(Counter)
    for run in runs:
        by_case[run["case_id"]].append(run)
        confusion_matrix[run["expected_status"]][run["observed_status"]] += 1
    stability = []
    for case_id in case_ids:
        case_runs = by_case[case_id]
        outcomes = Counter(run["observed_status"] for run in case_runs)
        confidences = [
            run["evaluation"]["confidence"]
            for run in case_runs
            if run["evaluation"] is not None
        ]
        stability_measured = len(case_runs) >= 2
        verdict_stable = stability_measured and len(outcomes) == 1
        stability.append(
            {
                "case_id": case_id,
                "expected_status": case_runs[0]["expected_status"],
                "observed_outcomes": dict(sorted(outcomes.items())),
                "verdict_stability_measured": stability_measured,
                "verdict_stable": verdict_stable,
                "all_verdicts_correct": all(
                    run["verdict_match"] for run in case_runs
                ),
                "verdict_matches": sum(run["verdict_match"] for run in case_runs),
                "runs": len(case_runs),
                "confidence": {
                    "minimum": min(confidences) if confidences else None,
                    "maximum": max(confidences) if confidences else None,
                    "mean": _mean(confidences),
                },
            }
        )
    return {
        "runs": total,
        "completed": len(completed),
        "execution_errors": total - len(completed),
        "verdict_matches": matches,
        "classification_errors": total - matches,
        "verdict_agreement_rate": round(matches / total, 4) if total else None,
        "confusion_matrix": {
            expected: dict(sorted(observed.items()))
            for expected, observed in sorted(confusion_matrix.items())
        },
        "compromise_false_positives": compromise_false_positives,
        "compromise_false_negatives": compromise_false_negatives,
        "inconclusive_outcomes": inconclusive,
        "inconclusive_rate": round(inconclusive / total, 4) if total else None,
        "evidence_selection_matches": sum(
            run["evidence_selection_match"] for run in runs
        ),
        "policy_selection_matches": sum(
            run["policy_selection_match"] for run in runs
        ),
        "reference_selection_errors": sum(
            not run["evidence_selection_match"]
            or not run["policy_selection_match"]
            for run in runs
        ),
        "stability_measured_cases": sum(
            item["verdict_stability_measured"] for item in stability
        ),
        "verdict_stable_cases": sum(
            item["verdict_stable"] for item in stability
        ),
        "stable_and_correct_cases": sum(
            item["verdict_stable"] and item["all_verdicts_correct"]
            for item in stability
        ),
        "stable_but_incorrect_cases": sum(
            item["verdict_stable"] and not item["all_verdicts_correct"]
            for item in stability
        ),
        "case_stability": stability,
    }


def _safe_error_payload(exception: Exception) -> dict:
    code = getattr(exception, "code", None)
    provider = getattr(exception, "provider", None)
    return {
        "type": type(exception).__name__,
        "code": code.value if code is not None else None,
        "provider": provider.value if provider is not None else None,
        "status_code": getattr(exception, "status_code", None),
        "retryable": bool(getattr(exception, "retryable", False)),
        "message": "Judge calibration evaluation failed.",
    }


async def run_calibration(
    suite_path: Path,
    settings: ModelClientSettings,
    repetitions: int,
    max_total_tokens: int,
    calibration_id: str = "openrouter-nemotron-permissions-v1",
) -> dict:
    suite = load_suite(suite_path)
    cases = [case for case in suite.cases if case.live_judge_calibration]
    if not cases:
        raise ValueError("Gold suite has no live Judge calibration cases.")
    total_runs = len(cases) * repetitions
    budget = CampaignBudget(
        max_paths=1,
        max_turns_per_path=1,
        max_provider_calls=total_runs * 3,
        max_concurrent_provider_calls=1,
        max_total_tokens=max_total_tokens,
        timeout_seconds=1800,
        max_retries_per_call=2,
    )
    budget_manager = CampaignBudgetManager(budget)
    model_attempts: list[ModelAttemptEvent] = []
    clients = StructuredModelClients(
        settings,
        budget_manager=budget_manager,
        event_sink=model_attempts.append,
    )
    model = OpenRouterDeepEvalModel(
        clients,
        OPENROUTER_NEMOTRON_EVALUATOR.model,
        system_instruction=TARGET_EVALUATOR_SYSTEM_INSTRUCTION,
        profile_id=OPENROUTER_NEMOTRON_EVALUATOR.profile_id,
        role=ModelRole.TARGET_EVALUATOR,
    )
    evaluator = SecMateTargetEvaluator(
        model,
        OPENROUTER_NEMOTRON_EVALUATOR.profile_id,
    )
    generated_at = datetime.now(timezone.utc)
    campaign = SecMateDeepTeamRunner._campaign(
        "judge-calibration",
        generated_at,
        budget,
    )
    runs = []
    try:
        for case in cases:
            expected_evaluation = case.scripted_evaluation
            if expected_evaluation is None:
                raise ValueError(f"{case.case_id} is missing its gold evaluation.")
            for repetition in range(1, repetitions + 1):
                path = _build_path(case, campaign.campaign_id)
                if SecMateDeepTeamRunner._review_deterministic_path(path) is not None:
                    raise ValueError(
                        f"{case.case_id} is not eligible for semantic calibration."
                    )
                attempt_start = len(model_attempts)
                evaluation = None
                observed_status = PathStatus.ERROR.value
                review_decision = "ERROR"
                error = None
                try:
                    evaluation = await evaluator.evaluate(path, campaign.assessment_spec)
                    reviewed_path, reviews = SecMateDeepTeamRunner._review_semantic_path(
                        path,
                        campaign,
                        evaluation,
                    )
                    observed_status = reviewed_path.status.value
                    review_decision = reviews[0].decision.value
                except Exception as exception:
                    error = _safe_error_payload(exception)
                attempts = model_attempts[attempt_start:]
                evaluation_payload = None
                evidence_references = []
                policy_references = []
                if evaluation is not None:
                    evaluation_payload = evaluation.model_dump(mode="json")
                    evidence_references = _normalize_references(
                        evaluation.evidence_references,
                        path.turns[0],
                    )
                    evaluation_payload["evidence_references"] = evidence_references
                    policy_references = evaluation.policy_references
                required_evidence = list(case.required_evidence_references)
                acceptable_evidence = list(case.acceptable_evidence_references)
                required_policies = case.required_policy_references
                acceptable_policies = case.acceptable_policy_references
                invalid_evidence = (
                    evaluation.invalid_evidence_references if evaluation else []
                )
                invalid_policies = (
                    evaluation.invalid_policy_references if evaluation else []
                )
                evidence_selection_match = (
                    set(required_evidence).issubset(evidence_references)
                    and set(evidence_references).issubset(acceptable_evidence)
                    and not invalid_evidence
                )
                policy_selection_match = (
                    set(required_policies).issubset(policy_references)
                    and set(policy_references).issubset(acceptable_policies)
                    and not invalid_policies
                )
                runs.append(
                    {
                        "case_id": case.case_id,
                        "label_status": case.label_status,
                        "label_review_note": case.label_review_note,
                        "repetition": repetition,
                        "expected_status": case.expected.path_status.value,
                        "observed_status": observed_status,
                        "review_decision": review_decision,
                        "verdict_match": observed_status
                        == case.expected.path_status.value,
                        "required_evidence_references": required_evidence,
                        "acceptable_evidence_references": acceptable_evidence,
                        "observed_evidence_references": evidence_references,
                        "invalid_evidence_references": invalid_evidence,
                        "evidence_selection_match": evidence_selection_match,
                        "required_policy_references": required_policies,
                        "acceptable_policy_references": acceptable_policies,
                        "observed_policy_references": policy_references,
                        "invalid_policy_references": invalid_policies,
                        "policy_selection_match": policy_selection_match,
                        "evaluation": evaluation_payload,
                        "provider_attempts": [
                            _attempt_payload(attempt) for attempt in attempts
                        ],
                        "execution_error": error,
                    }
                )
    finally:
        await clients.close()
    budget_snapshot = await budget_manager.snapshot()
    return {
        "calibration_id": calibration_id,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "fixture_sha256": fixture_sha256(suite_path),
        "synthetic_only": True,
        "calibration_claim": False,
        "status": "MEASURED_NOT_CALIBRATED",
        "measurement_valid": True,
        "evaluation_set_role": suite.evaluation_set_role,
        "labels_human_reviewed": all(
            case.label_status == "HUMAN_APPROVED" for case in cases
        ),
        "vulnerability_profile_id": suite.vulnerability_profile_id,
        "judge": {
            "profile_id": OPENROUTER_NEMOTRON_EVALUATOR.profile_id,
            "provider": OPENROUTER_NEMOTRON_EVALUATOR.provider.value,
            "model": OPENROUTER_NEMOTRON_EVALUATOR.model,
            "repetitions_per_case": repetitions,
            "cases": [case.case_id for case in cases],
        },
        "runtime": {
            "python_version": platform.python_version(),
            "deepteam_version": version("deepteam"),
            "deepteam_commit": DEEPTEAM_COMMIT,
            "deepeval_version": DEEPEVAL_VERSION,
        },
        "metrics": summarize_runs(runs, [case.case_id for case in cases]),
        "budget": {
            "max_provider_calls": budget.max_provider_calls,
            "provider_calls_attempted": budget_snapshot.provider_calls_attempted,
            "provider_calls_succeeded": budget_snapshot.provider_calls_succeeded,
            "provider_calls_failed": budget_snapshot.provider_calls_failed,
            "max_total_tokens": budget.max_total_tokens,
            "tokens_consumed": budget_snapshot.tokens_consumed,
            "tokens_reserved": budget_snapshot.tokens_reserved,
            "calls_with_missing_usage": budget_snapshot.calls_with_missing_usage,
            "token_budget_overrun": budget_snapshot.token_budget_overrun,
            "cancelled": budget_snapshot.cancelled,
            "cancellation_reason": budget_snapshot.cancellation_reason,
            "deadline_seconds_remaining": budget_snapshot.deadline_seconds_remaining,
        },
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run repeated live SecMate Judge evaluations against semantic gold cases."
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=4)
    parser.add_argument("--token-budget", type=int, default=250_000)
    parser.add_argument(
        "--calibration-id",
        default="openrouter-nemotron-permissions-v1",
    )
    parser.add_argument(
        "--allow-openrouter-data-collection",
        action="store_true",
    )
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    if not args.allow_openrouter_data_collection:
        raise SystemExit(
            "The configured free OpenRouter Judge requires explicit data-collection approval."
        )
    if args.repetitions < 1:
        raise SystemExit("Repetitions must be at least 1.")
    settings = ModelClientSettings(
        groq_api_key="",
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        request_timeout_seconds=float(
            os.getenv("SECMATE_REQUEST_TIMEOUT_SECONDS", "45")
        ),
        provider_min_spacing_seconds=float(
            os.getenv("SECMATE_PROVIDER_MIN_SPACING_SECONDS", "2")
        ),
        provider_tokens_per_second=float(
            os.getenv("SECMATE_PROVIDER_TOKENS_PER_SECOND", "300")
        ),
        provider_max_spacing_seconds=float(
            os.getenv("SECMATE_PROVIDER_MAX_SPACING_SECONDS", "12")
        ),
        provider_retry_base_seconds=float(
            os.getenv("SECMATE_PROVIDER_RETRY_BASE_SECONDS", "2")
        ),
        provider_max_cooldown_seconds=float(
            os.getenv("SECMATE_PROVIDER_MAX_COOLDOWN_SECONDS", "30")
        ),
        provider_retry_jitter_seconds=float(
            os.getenv("SECMATE_PROVIDER_RETRY_JITTER_SECONDS", "0.25")
        ),
        openrouter_allow_data_collection=True,
    )
    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is required.")
    result = asyncio.run(
        run_calibration(
            args.suite,
            settings,
            args.repetitions,
            args.token_budget,
            args.calibration_id,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result["metrics"], indent=2))
    if result["metrics"]["execution_errors"]:
        raise SystemExit(1)
    if (
        result["metrics"]["classification_errors"]
        or result["metrics"]["reference_selection_errors"]
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
