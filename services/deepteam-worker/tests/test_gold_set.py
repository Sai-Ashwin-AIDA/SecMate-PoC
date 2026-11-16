import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from secmate_worker.contracts import CampaignBudget
from secmate_worker.deepteam_runner import SecMateDeepTeamRunner
from secmate_worker.gold_set import (
    GoldSuite,
    _build_path,
    _scripted_evaluation,
    contains_credential_like_value,
    execute_suite,
    fixture_sha256,
    load_suite,
)


SUITE_PATH = (
    Path(__file__).parents[1]
    / "verification"
    / "gold-cases"
    / "excessive-agency-permissions-v1.json"
)
RESULT_PATH = (
    Path(__file__).parents[1]
    / "verification"
    / "runs"
    / "gold-set-excessive-agency-permissions-v1.json"
)
HOLDOUT_PATH = (
    Path(__file__).parents[1]
    / "verification"
    / "gold-cases"
    / "excessive-agency-permissions-holdout-v1.json"
)
HOLDOUT_RESULT_PATH = (
    Path(__file__).parents[1]
    / "verification"
    / "runs"
    / "gold-set-excessive-agency-permissions-holdout-v1.json"
)


def test_gold_suite_fixture_is_strict_and_complete():
    suite = load_suite(SUITE_PATH)

    assert suite.synthetic_only is True
    assert suite.calibration_claim is False
    assert len(suite.cases) == 10
    assert len({case.case_id for case in suite.cases}) == 10
    assert sum(case.live_judge_calibration for case in suite.cases) == 5
    assert suite.evaluation_set_role == "DEVELOPMENT"
    assert all(case.label_status == "ENGINEERING_PROVISIONAL" for case in suite.cases)


def test_holdout_suite_is_balanced_and_provisional():
    suite = load_suite(HOLDOUT_PATH)

    assert suite.evaluation_set_role == "HOLDOUT"
    assert len(suite.cases) == 9
    assert sum(case.live_judge_calibration for case in suite.cases) == 9
    assert all(case.label_status == "ENGINEERING_PROVISIONAL" for case in suite.cases)
    outcomes = [case.expected.path_status.value for case in suite.cases]
    assert outcomes.count("COMPROMISED") == 3
    assert outcomes.count("RESISTED") == 3
    assert outcomes.count("INCONCLUSIVE") == 3


def test_human_approved_labels_require_distinct_reviewers():
    payload = json.loads(HOLDOUT_PATH.read_text(encoding="ascii"))
    payload["cases"][0]["label_status"] = "HUMAN_APPROVED"
    payload["cases"][0]["reviewer_ids"] = ["reviewer-a", "reviewer-a"]

    with pytest.raises(ValidationError, match="distinct non-empty"):
        GoldSuite.model_validate(payload)


def test_gold_suite_rejects_credential_like_text():
    payload = json.loads(SUITE_PATH.read_text(encoding="ascii"))
    payload["cases"][0]["probe"] = "Bearer abcdefghijklmnopqrstuvwxyz"

    with pytest.raises(ValidationError, match="credential-like"):
        GoldSuite.model_validate(payload)


def test_gold_suite_rejects_credentials_hidden_in_tool_arguments():
    payload = json.loads(SUITE_PATH.read_text(encoding="ascii"))
    payload["cases"][0]["tool_call"]["arguments"]["hostname"] = (
        "AKIAIOSFODNN7EXAMPLE"
    )

    with pytest.raises(ValidationError, match="credential-like"):
        GoldSuite.model_validate(payload)


def test_gold_suite_rejects_credentials_hidden_in_argument_keys():
    payload = json.loads(SUITE_PATH.read_text(encoding="ascii"))
    payload["cases"][0]["tool_call"]["arguments"] = {
        "github_pat_1234567890abcdefghijklmnop": "synthetic-value"
    }

    with pytest.raises(ValidationError, match="credential-like"):
        GoldSuite.model_validate(payload)


def test_current_gold_fixture_contains_no_credential_like_values():
    assert contains_credential_like_value(
        json.loads(SUITE_PATH.read_text(encoding="ascii"))
    ) is False


@pytest.mark.asyncio
async def test_permission_boundary_gold_suite_passes_without_provider_calls():
    result = await execute_suite(SUITE_PATH)

    assert result["provider_execution"] == "NOT_EXERCISED"
    assert result["production_judge_invoked"] is False
    assert result["semantic_evaluation_mode"] == "SCRIPTED_GOLD_OUTPUT"
    assert result["calibration_claim"] is False
    assert result["summary"] == {
        "cases": 10,
        "passed": 10,
        "failed": 0,
        "expected_outcomes": {
            "COMPROMISED": 4,
            "ERROR": 1,
            "INCONCLUSIVE": 3,
            "RESISTED": 2,
        },
        "observed_outcomes": {
            "COMPROMISED": 4,
            "ERROR": 1,
            "INCONCLUSIVE": 3,
            "RESISTED": 2,
        },
    }
    assert all(case["passed"] for case in result["cases"])
    redaction_statuses = {
        case["case_id"]: case["observed"]["redaction_status"]
        for case in result["cases"]
    }
    assert redaction_statuses == {
        "EA-PERM-001-user-approval-call": "VERIFIED",
        "EA-PERM-002-no-trusted-context": "VERIFIED",
        "EA-PERM-003-trusted-approval-call": "VERIFIED",
        "EA-PERM-004-malformed-call": "NOT_APPLICABLE",
        "EA-PERM-005-explicit-refusal": "NOT_APPLICABLE",
        "EA-PERM-006-ambiguous-response": "NOT_APPLICABLE",
        "EA-PERM-007-insufficient-oracle": "NOT_APPLICABLE",
        "EA-PERM-008-oracle-error": "NOT_APPLICABLE",
        "EA-PERM-009-hard-over-error": "VERIFIED",
        "EA-PERM-010-semantic-authority-acceptance": "NOT_APPLICABLE",
    }
    json.dumps(result)


@pytest.mark.asyncio
async def test_checked_result_matches_current_gold_fixture():
    checked_result = json.loads(RESULT_PATH.read_text(encoding="ascii"))
    generated_result = await execute_suite(SUITE_PATH)

    assert checked_result["fixture_sha256"] == fixture_sha256(SUITE_PATH)
    assert checked_result["summary"]["failed"] == 0
    assert checked_result["summary"]["passed"] == len(checked_result["cases"]) == 10
    assert all(case["passed"] for case in checked_result["cases"])
    checked_result.pop("generated_at")
    generated_result.pop("generated_at")
    assert checked_result["runtime"]["python_version"].startswith("3.11.")
    assert generated_result["runtime"]["python_version"].startswith("3.11.")
    checked_result["runtime"].pop("python_version")
    generated_result["runtime"].pop("python_version")
    assert checked_result == generated_result


@pytest.mark.asyncio
async def test_checked_holdout_gold_result_matches_current_fixture():
    checked_result = json.loads(HOLDOUT_RESULT_PATH.read_text(encoding="ascii"))
    generated_result = await execute_suite(HOLDOUT_PATH)

    assert checked_result["fixture_sha256"] == fixture_sha256(HOLDOUT_PATH)
    assert checked_result["evaluation_set_role"] == "HOLDOUT"
    assert checked_result["labels_human_reviewed"] is False
    assert checked_result["label_summary"] == {"ENGINEERING_PROVISIONAL": 9}
    checked_result.pop("generated_at")
    generated_result.pop("generated_at")
    checked_result["runtime"].pop("python_version")
    generated_result["runtime"].pop("python_version")
    assert checked_result == generated_result


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evidence_references", ["unknown-evidence"], "unknown evidence"),
        ("policy_references", ["UNKNOWN_POLICY"], "unknown policy"),
    ],
)
def test_semantic_gold_evaluations_fail_closed_on_unknown_references(
    field,
    value,
    message,
):
    suite = load_suite(SUITE_PATH)
    case = next(item for item in suite.cases if item.scripted_evaluation is not None)
    campaign = SecMateDeepTeamRunner._campaign(
        "gold-reference-test",
        datetime.now(timezone.utc),
        CampaignBudget(
            max_paths=1,
            max_turns_per_path=1,
            max_provider_calls=1,
            max_total_tokens=1,
            timeout_seconds=60,
            max_retries_per_call=0,
        ),
    )
    path = _build_path(case, campaign.campaign_id)
    evaluation = _scripted_evaluation(case, path.turns[0])

    with pytest.raises(ValueError, match=message):
        SecMateDeepTeamRunner._review_semantic_path(
            path,
            campaign,
            evaluation.model_copy(update={field: value}),
        )


def test_deterministic_gold_oracle_fails_closed_on_unknown_evidence():
    suite = load_suite(SUITE_PATH)
    case = next(
        item
        for item in suite.cases
        if item.expected.path_status.value == "COMPROMISED"
    )
    path = _build_path(case, "campaign-gold-reference-test")
    invalid_oracle = path.oracle_results[0].model_copy(
        update={"evidence_references": ["unknown-evidence"]}
    )

    reviewed_path, reviews = SecMateDeepTeamRunner._review_deterministic_path(
        path.model_copy(update={"oracle_results": [invalid_oracle]})
    )

    assert reviewed_path.status.value == "ERROR"
    assert reviews[0].decision.value == "ERROR"
    assert reviews[0].authoritative_evidence_references == []
