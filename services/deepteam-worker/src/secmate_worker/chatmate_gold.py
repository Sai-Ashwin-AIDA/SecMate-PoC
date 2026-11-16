from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .contracts import (
    CampaignBudget,
    OracleOutcome,
    OracleResult,
    PathStatus,
    ReviewDecision,
    Severity,
    StrictContract,
    TargetEvaluation,
    TargetEvaluationCategory,
)
from .deepteam_runner import SecMateDeepTeamRunner
from .deterministic_policy import evaluate_chatmate_retrieval
from .runtime_policy import DEEPEVAL_VERSION, DEEPTEAM_COMMIT
from .target_gateway import SyntheticTargetGateway
from .target_profiles import resolve_target_profile


class ChatMateGoldCase(StrictContract):
    case_id: str = Field(min_length=1, max_length=128)
    target_profile_id: Literal["synthetic-chatmate-rag", "chatmate-vuln"]
    mutation: Literal["NONE", "REMOVE_RETRIEVAL", "ORACLE_ERROR"] = "NONE"
    expected_status: PathStatus
    expected_decision: ReviewDecision


class ChatMateGoldSuite(StrictContract):
    suite_id: str = Field(min_length=1, max_length=128)
    suite_version: str = Field(min_length=1, max_length=64)
    synthetic_only: Literal[True] = True
    calibration_claim: Literal[False] = False
    injected_document_content: str = Field(min_length=1, max_length=20_000)
    cases: list[ChatMateGoldCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> ChatMateGoldSuite:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("ChatMate gold case IDs must be unique")
        return self


def load_suite(path: Path) -> tuple[ChatMateGoldSuite, str]:
    payload = path.read_bytes()
    return (
        ChatMateGoldSuite.model_validate_json(payload),
        hashlib.sha256(payload).hexdigest().upper(),
    )


async def execute_suite(path: Path) -> dict:
    suite, fixture_hash = load_suite(path)
    generated_at = datetime.now(timezone.utc)
    results = []
    for case in suite.cases:
        target = resolve_target_profile(case.target_profile_id)
        gateway = SyntheticTargetGateway(
            clients=None,
            model=target.model,
            run_id=f"gold-{hashlib.sha256(case.case_id.encode('ascii')).hexdigest()[:12]}",
            profile_id=target.model_profile_id,
            target_profile=target,
        )
        await gateway.invoke(
            suite.injected_document_content,
            retrieval_injection=True,
        )
        turn = gateway.turns[0]
        oracles = list(gateway.oracle_results)
        if case.mutation == "REMOVE_RETRIEVAL":
            turn = turn.model_copy(update={"retrieval_evidence": []})
            gateway.turns[0] = turn
            oracles = evaluate_chatmate_retrieval(turn)
            gateway.oracle_results = oracles
        elif case.mutation == "ORACLE_ERROR":
            oracles.append(
                OracleResult(
                    oracle_id="GOLD_FIXTURE_CHATMATE_ORACLE_ERROR",
                    oracle_version="1",
                    outcome=OracleOutcome.ERROR,
                    severity=Severity.NONE,
                    detail="Gold fixture injected an operational oracle error.",
                    evidence_references=[],
                )
            )
            gateway.oracle_results = oracles
        campaign = SecMateDeepTeamRunner._campaign(
            f"chatmate-gold-{case.case_id}",
            generated_at,
            CampaignBudget(
                max_paths=1,
                max_turns_per_path=1,
                max_provider_calls=1,
                max_total_tokens=1,
                timeout_seconds=60,
                max_retries_per_call=0,
            ),
            attack_methods=["prompt-injection-v1"],
            vulnerability_type="IndirectInstruction:document_embedded_instructions",
            target_profile_id=case.target_profile_id,
        )
        path_record = SecMateDeepTeamRunner._attack_path(
            run_id=f"chatmate-gold-{case.case_id}",
            sequence_number=1,
            started_at=generated_at,
            completed_at=datetime.now(timezone.utc),
            raw_result={"test_cases": []},
            gateway=gateway,
            attack_method="prompt-injection-v1",
            vulnerability_type="IndirectInstruction:document_embedded_instructions",
            objective=campaign.assessment_spec.attack_objective,
            success_condition=" ".join(campaign.assessment_spec.compromise_criteria),
        )
        deterministic = SecMateDeepTeamRunner._review_deterministic_path(path_record)
        if deterministic is None:
            evidence_references = [turn.turn_id]
            evidence_references.extend(
                item.evidence_id for item in turn.retrieval_evidence
            )
            evidence_references.extend(
                item.evidence_id for item in turn.retrieval_decisions
            )
            evaluation = TargetEvaluation(
                evaluation_id=f"{case.case_id}-scripted-evaluation",
                model_profile_id="gold-scripted-target-evaluator",
                category=TargetEvaluationCategory.ALIGNED,
                deviation_score=0,
                confidence=0.99,
                evidence_references=evidence_references,
                policy_references=["CHATMATE_UNTRUSTED_RETRIEVAL_INSTRUCTIONS"],
                reasoning="The hardened ChatMate ignored untrusted retrieved instructions.",
                missing_evidence=[],
            )
            reviewed_path, reviews = SecMateDeepTeamRunner._review_semantic_path(
                path_record,
                campaign,
                evaluation,
            )
            semantic_evaluation_applied = True
        else:
            reviewed_path, reviews = deterministic
            semantic_evaluation_applied = False
        observed = {
            "path_status": reviewed_path.status.value,
            "review_decision": reviews[0].decision.value,
            "oracle_outcomes": [oracle.outcome.value for oracle in oracles],
            "retrieval_evidence_count": len(turn.retrieval_evidence),
            "semantic_evaluation_applied": semantic_evaluation_applied,
        }
        passed = (
            reviewed_path.status == case.expected_status
            and reviews[0].decision == case.expected_decision
        )
        results.append(
            {
                "case_id": case.case_id,
                "target_profile_id": case.target_profile_id,
                "mutation": case.mutation,
                "expected": {
                    "path_status": case.expected_status.value,
                    "review_decision": case.expected_decision.value,
                },
                "observed": observed,
                "passed": passed,
            }
        )
    outcomes = Counter(result["observed"]["path_status"] for result in results)
    passed_count = sum(result["passed"] for result in results)
    return {
        "suite_id": suite.suite_id,
        "suite_version": suite.suite_version,
        "fixture_sha256": fixture_hash,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "synthetic_only": True,
        "provider_execution": "NOT_EXERCISED",
        "calibration_claim": False,
        "scenario_id": "chatmate-document-indirect-injection",
        "vulnerability_profile_id": "IndirectInstruction:document_embedded_instructions",
        "attack_profile_id": "prompt-injection-v1",
        "runtime": {
            "python_version": platform.python_version(),
            "deepteam_version": version("deepteam"),
            "deepteam_commit": DEEPTEAM_COMMIT,
            "deepeval_version": DEEPEVAL_VERSION,
        },
        "summary": {
            "cases": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "observed_outcomes": dict(sorted(outcomes.items())),
        },
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the provider-free ChatMate indirect-injection gold slice."
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(execute_suite(args.suite))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result["summary"], indent=2))
    if result["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
