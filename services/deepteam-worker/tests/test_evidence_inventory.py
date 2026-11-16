import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from secmate_worker.evidence_inventory import EvidenceInventory, select_citations


def item(identifier):
    return SimpleNamespace(evidence_id=identifier)


def test_inventory_indexes_each_kind_without_broadening_automatic_judge_scope():
    turn = SimpleNamespace(turn_id="turn", tool_attempts=[item("tool")], retrieval_evidence=[item("retrieval")],
        retrieval_decisions=[item("decision")], manual_collection=[item("manual")])
    inventory = EvidenceInventory.from_turns([turn], policy_ids=["policy"])
    assert inventory.automatic_ids == {"turn", "tool", "retrieval", "decision"}
    assert inventory.all_ids == {"turn", "tool", "retrieval", "decision", "manual"}
    assert inventory.policy_ids == {"policy"}
    assert "policy" not in inventory.all_ids


@pytest.mark.parametrize("groups", [
    {"turn_ids": ["same", "same"]}, {"turn_ids": ["same"], "tool_ids": ["same"]},
    {"turn_ids": [" "]}, {"policy_ids": ["p", "p"]}, {"manual_ids": [None]},
])
def test_ambiguous_or_missing_identity_is_rejected(groups):
    with pytest.raises(ValueError):
        EvidenceInventory.from_identifiers(**groups)


def test_policy_namespace_is_separate_and_citations_keep_old_set_semantics():
    inventory = EvidenceInventory.from_identifiers(turn_ids=["turn"], policy_ids=["turn", "policy"])
    result = select_citations(["turn", "turn", "unknown", "", "policy"], inventory.all_ids)
    assert result.valid == ("turn",)
    assert result.invalid == ("", "policy", "unknown")
    assert select_citations(["policy"], inventory.policy_ids).valid == ("policy",)


def test_phase5_inventory_is_bound_to_the_exact_path_and_assessment():
    assessment = SimpleNamespace(
        evidence_id="run-a-phase5-assessment",
        parent_path_id="path-a",
        tools=[item("run-a-phase5-tool-1")],
    )
    path = SimpleNamespace(
        path_id="path-a",
        turns=[],
        phase5_assessments=[assessment],
    )

    inventory = EvidenceInventory.from_path(path, policy_ids=["PHASE5_POLICY"])
    citations = select_citations(
        [
            assessment.evidence_id,
            assessment.tools[0].evidence_id,
            "fabricated-phase5-id",
            "other-path-phase5-assessment",
            "path-a-other-phase5-assessment",
        ],
        inventory.all_ids,
    )

    assert inventory.phase5_ids == {
        "run-a-phase5-assessment",
        "run-a-phase5-tool-1",
    }
    assert citations.valid == (
        "run-a-phase5-assessment",
        "run-a-phase5-tool-1",
    )
    assert citations.invalid == (
        "fabricated-phase5-id",
        "other-path-phase5-assessment",
        "path-a-other-phase5-assessment",
    )
    assert inventory.policy_ids == {"PHASE5_POLICY"}
    assert "PHASE5_POLICY" not in inventory.all_ids

    foreign = SimpleNamespace(
        evidence_id="other-path-phase5-assessment",
        parent_path_id="path-b",
        tools=[],
    )
    with pytest.raises(ValueError, match="parent path"):
        EvidenceInventory.from_path(SimpleNamespace(
            path_id="path-a",
            turns=[],
            phase5_assessments=[assessment, foreign],
        ))

    bound = SimpleNamespace(
        evidence_id="run-a-bound-phase5-assessment",
        parent_path_id="path-a",
        parent_turn_id="path-a-turn-1",
        tools=[],
    )
    bound_path = SimpleNamespace(
        path_id="path-a",
        turns=[SimpleNamespace(
            turn_id="path-a-turn-1",
            tool_attempts=[],
            retrieval_evidence=[],
            retrieval_decisions=[],
            manual_collection=[],
        )],
        phase5_assessments=[bound],
    )
    assert bound.evidence_id in EvidenceInventory.from_path(bound_path).phase5_ids
    bound.parent_turn_id = "path-a-turn-2"
    with pytest.raises(ValueError, match="parent turn"):
        EvidenceInventory.from_path(bound_path)


@pytest.mark.asyncio
async def test_all_live_baseline_requests_and_verdicts_are_unchanged_without_api_calls():
    """Parity against actual saved model outputs; never rerun the consumed holdout."""
    from secmate_worker.manual_judge_calibration import CalibrationSuite, fixture_input, request_fingerprint
    from secmate_worker.manual_chatmate import ManualChatMateEvaluator, ManualChatMateJudgeOutput, _build_path_and_review
    root = Path(__file__).parents[1] / "verification"
    suite = CalibrationSuite.model_validate_json((root / "gold-cases/manual-chatmate-judge-v1.json").read_text())
    report = json.loads((root / "runs/manual-chatmate-judge-baseline-v2.json").read_text())
    entries = {row["case_id"]: row for row in report["entries"]}
    assert len(entries) == 30
    for case in suite.cases:
        row = entries[case.case_id]
        assert request_fingerprint(case) == row["request_sha256"]

        class RecordedModel:
            system_instruction = ""

            async def a_generate(self, prompt, schema=None):
                assert schema is ManualChatMateJudgeOutput
                return schema.model_validate(row["raw_judge"])

        value = fixture_input(case)
        turn_id = f"{value.run_id}-turn-1"
        evaluated = await ManualChatMateEvaluator(RecordedModel(), report["identity"]["profile"]).evaluate(value, turn_id)
        for key in ("category", "deviation_score", "confidence", "evidence_references", "policy_references",
                    "invalid_evidence_references", "invalid_policy_references", "reasoning", "missing_evidence"):
            assert evaluated.model_dump(mode="json")[key] == row["evaluation"][key], (case.case_id, key)
        now = datetime.now(timezone.utc)
        _, _, status = _build_path_and_review(value, "parity-eval", turn_id, now, now, evaluated, None)
        assert status == row["observed_status"]
