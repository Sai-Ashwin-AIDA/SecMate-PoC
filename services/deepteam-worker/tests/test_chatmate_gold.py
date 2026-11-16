import json
from pathlib import Path

import pytest

from secmate_worker.chatmate_gold import execute_suite, load_suite


ROOT = Path(__file__).parents[1]
SUITE_PATH = ROOT / "verification" / "gold-cases" / "chatmate-indirect-injection-v1.json"
RESULT_PATH = ROOT / "verification" / "runs" / "chatmate-indirect-injection-v1.json"


def test_chatmate_gold_fixture_is_bounded_and_synthetic():
    suite, fixture_hash = load_suite(SUITE_PATH)

    assert suite.synthetic_only is True
    assert suite.calibration_claim is False
    assert len(suite.cases) == 4
    assert len(fixture_hash) == 64


@pytest.mark.asyncio
async def test_chatmate_gold_suite_matches_checked_result():
    generated = await execute_suite(SUITE_PATH)
    checked = json.loads(RESULT_PATH.read_text(encoding="ascii"))

    assert generated["summary"] == {
        "cases": 4,
        "passed": 4,
        "failed": 0,
        "observed_outcomes": {
            "COMPROMISED": 1,
            "ERROR": 1,
            "INCONCLUSIVE": 1,
            "RESISTED": 1,
        },
    }
    checked.pop("generated_at")
    generated.pop("generated_at")
    checked["runtime"].pop("python_version")
    generated["runtime"].pop("python_version")
    assert checked == generated
