"""Keep frozen-context compatibility after retiring lexical diversity code."""
import pytest
from pydantic import ValidationError
from secmate_worker.critic_contracts import DiversityReference, FollowUpContext, text_hash, follow_up_suffix
from test_manual_chatmate_critic import follow_up_context, source_input


def test_parent_reference_rejects_tampering():
    with pytest.raises(ValidationError):
        DiversityReference(prompt="Frozen parent prompt", prompt_sha256="0" * 64)


def test_legacy_context_does_not_add_hash_inputs():
    payload = follow_up_context().model_dump(mode="json")
    assert "parent_candidates" not in payload and "recommendation_policy" not in payload
    with pytest.raises(ValidationError, match="requires frozen"):
        FollowUpContext.model_validate({**payload, "recommendation_policy": "boundary-preserving-v1"})


@pytest.mark.parametrize("policy", ["boundary-preserving-v1", "single-turn-continuation-v1"])
def test_compact_advisory_preserves_frozen_comparison_evidence(policy):
    source = source_input()
    context = FollowUpContext.model_validate({**follow_up_context().model_dump(mode="json"),
        "recommendation_policy": policy,
        "parent_candidates": [{"prompt": source.selected_prompt, "prompt_sha256": text_hash(source.selected_prompt)}]})
    suffix = follow_up_suffix(context)
    assert source.selected_prompt not in suffix
    assert "parent_candidates" not in suffix and "source_judge_sha256" not in suffix
    assert context.objective in suffix
    assert context.parent_candidates[0].prompt == source.selected_prompt
