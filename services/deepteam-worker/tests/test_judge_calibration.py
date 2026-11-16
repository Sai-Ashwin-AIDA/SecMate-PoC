import json
import re
from pathlib import Path

from secmate_worker.gold_set import contains_credential_like_value, fixture_sha256
from secmate_worker.judge_calibration import summarize_runs


ROOT = Path(__file__).parents[1]
SUITE_PATH = (
    ROOT
    / "verification"
    / "gold-cases"
    / "excessive-agency-permissions-v1.json"
)
RESULT_PATH = (
    ROOT
    / "verification"
    / "runs"
    / "judge-calibration-excessive-agency-permissions-v1.json"
)
HOLDOUT_SUITE_PATH = (
    ROOT
    / "verification"
    / "gold-cases"
    / "excessive-agency-permissions-holdout-v1.json"
)
HOLDOUT_RESULT_PATH = (
    ROOT
    / "verification"
    / "runs"
    / "judge-calibration-excessive-agency-permissions-holdout-v1.json"
)


def test_calibration_summary_measures_accuracy_and_stability():
    runs = [
        {
            "case_id": "resisted",
            "expected_status": "RESISTED",
            "observed_status": "RESISTED",
            "verdict_match": True,
            "evidence_selection_match": True,
            "policy_selection_match": True,
            "evaluation": {"confidence": 0.9},
            "execution_error": None,
        },
        {
            "case_id": "resisted",
            "expected_status": "RESISTED",
            "observed_status": "COMPROMISED",
            "verdict_match": False,
            "evidence_selection_match": False,
            "policy_selection_match": False,
            "evaluation": {"confidence": 0.8},
            "execution_error": None,
        },
        {
            "case_id": "compromised",
            "expected_status": "COMPROMISED",
            "observed_status": "INCONCLUSIVE",
            "verdict_match": False,
            "evidence_selection_match": True,
            "policy_selection_match": False,
            "evaluation": {"confidence": 0.7},
            "execution_error": None,
        },
    ]

    summary = summarize_runs(runs, ["resisted", "compromised"])

    assert summary["runs"] == 3
    assert summary["verdict_matches"] == 1
    assert summary["classification_errors"] == 2
    assert summary["verdict_agreement_rate"] == 0.3333
    assert summary["confusion_matrix"] == {
        "COMPROMISED": {"INCONCLUSIVE": 1},
        "RESISTED": {"COMPROMISED": 1, "RESISTED": 1},
    }
    assert summary["compromise_false_positives"] == 1
    assert summary["compromise_false_negatives"] == 1
    assert summary["inconclusive_outcomes"] == 1
    assert summary["reference_selection_errors"] == 2
    assert summary["stability_measured_cases"] == 1
    assert summary["verdict_stable_cases"] == 0
    assert summary["stable_and_correct_cases"] == 0
    assert summary["stable_but_incorrect_cases"] == 0
    assert summary["case_stability"][0]["verdict_stable"] is False
    assert summary["case_stability"][1]["verdict_stability_measured"] is False
    assert summary["case_stability"][1]["verdict_stable"] is False


def test_checked_live_calibration_result_is_consistent_and_contains_no_credentials():
    text = RESULT_PATH.read_text(encoding="ascii")
    result = json.loads(text)

    assert result["fixture_sha256"] == fixture_sha256(SUITE_PATH)
    assert result["calibration_claim"] is False
    assert result["status"] == "INVALIDATED_LABEL_LEAKAGE"
    assert result["measurement_valid"] is False
    assert "opaque evidence IDs" in result["invalidation_reason"]
    assert result["metrics"]["runs"] == len(result["runs"]) == 20
    assert result["metrics"]["completed"] + result["metrics"]["execution_errors"] == 20
    assert result["metrics"]["verdict_matches"] == sum(
        run["verdict_match"] for run in result["runs"]
    )
    assert result["metrics"] == summarize_runs(
        result["runs"], result["judge"]["cases"]
    )
    assert result["budget"]["provider_calls_attempted"] == sum(
        len(run["provider_attempts"]) for run in result["runs"]
    )
    attempts = [
        attempt
        for run in result["runs"]
        for attempt in run["provider_attempts"]
    ]
    assert result["budget"]["provider_calls_succeeded"] == sum(
        attempt["outcome"] == "SUCCESS" for attempt in attempts
    )
    assert result["budget"]["provider_calls_failed"] == sum(
        attempt["outcome"] == "FAILURE" for attempt in attempts
    )
    calls_with_missing_usage = sum(attempt["usage"] is None for attempt in attempts)
    assert result["budget"]["calls_with_missing_usage"] == calls_with_missing_usage
    if calls_with_missing_usage == 0:
        assert result["budget"]["tokens_consumed"] == sum(
            attempt["usage"]["total_tokens"] for attempt in attempts
        )
    assert contains_credential_like_value(result) is False
    assert not re.search(
        r"(?i)(?:gsk_[a-z0-9_-]{8,}|sk-or-v1-[a-z0-9_-]{8,}|OPENROUTER_API_KEY|GROQ_API_KEY)",
        text,
    )


def test_checked_holdout_result_is_consistent_and_provisional():
    text = HOLDOUT_RESULT_PATH.read_text(encoding="ascii")
    result = json.loads(text)

    assert result["fixture_sha256"] == fixture_sha256(HOLDOUT_SUITE_PATH)
    assert result["evaluation_set_role"] == "HOLDOUT"
    assert result["labels_human_reviewed"] is False
    assert result["calibration_claim"] is False
    assert result["measurement_valid"] is False
    assert result["status"] == "INVALIDATED_LABEL_LEAKAGE"
    assert result["judge"]["repetitions_per_case"] == 1
    assert result["metrics"]["runs"] == len(result["runs"]) == 9
    assert result["metrics"] == summarize_runs(
        result["runs"], result["judge"]["cases"]
    )
    assert result["metrics"]["stability_measured_cases"] == 0
    assert all(
        run["label_status"] == "ENGINEERING_PROVISIONAL"
        for run in result["runs"]
    )
    assert contains_credential_like_value(result) is False
