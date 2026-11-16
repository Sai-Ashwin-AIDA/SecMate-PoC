import hashlib
import ast
import json
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from secmate_worker.chatmate_candidates import (CHATMATE_CANDIDATE_ATTACK_IDS, ChatMateCandidateGenerationError,
    ChatMateCandidateGenerator, ChatMateBaselinePromptPair, ChatMateMethodAlignmentBatch, chatmate_candidate_assessment_spec)
from secmate_worker.contracts import ChatMatePromptCandidate
from deepeval.models import DeepEvalBaseLLM

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


class FakeAttackEngine:
    """Legacy fixture import; invoking the removed engine is a regression."""
    def __init__(self, **kwargs):
        raise AssertionError("The final baseline cannot invoke AttackEngine")


class FakeAttack:
    calls = []
    def __init__(self, method):
        self.method = method
    async def a_enhance(self, attack, simulator):
        raise AssertionError("The final baseline cannot invoke enhancement")


def fake_profile(profile_id="prompt-injection-v1"):
    name = {"prompt-injection-v1": "Prompt Injection", "system-override-v1": "System Override",
        "prompt-probing-v1": "Prompt Probing", "goal-redirection-v1": "Goal Redirection", "context-poisoning-v1": "Context Poisoning"}[profile_id]
    return SimpleNamespace(profile_id=profile_id, name=name, class_name=name.replace(" ", ""),
        turn_mode="SINGLE", builder=lambda simulator: FakeAttack(name))


class FakeDeepTeamModel(DeepEvalBaseLLM):
    def __init__(self):
        self.enhancement_count = 0
        self.calls = []
        super().__init__(model_name="fake-baseline-model")
    def load_model(self):
        return self
    def get_model_name(self):
        return "fake-baseline-model"
    def generate(self, prompt, schema=None):
        raise RuntimeError("Synchronous generation is not expected")
    async def a_generate(self, prompt, schema=None):
        self.calls.append((schema, prompt))
        if schema is ChatMateBaselinePromptPair:
            return schema(candidates=[{"candidate_id": f"candidate-{index}", "prompt": text} for index, text in enumerate(
                ["DeepTeam baseline attack one", "DeepTeam baseline attack two"], start=1)])
        if schema is ChatMateMethodAlignmentBatch:
            return schema(decisions=[{"candidate_id": f"candidate-{index}", "verdict": "ALIGNED"} for index in (1, 2)])
        raise AssertionError(f"Unexpected model call: {schema}")


def generator(**overrides):
    values = dict(simulator=FakeDeepTeamModel(), attack_profile_resolver=fake_profile,
        now=lambda: NOW, batch_id_factory=lambda: "chatmate-batch-test123")
    values.update(overrides)
    return ChatMateCandidateGenerator(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", CHATMATE_CANDIDATE_ATTACK_IDS)
async def test_final_baseline_uses_only_generation_and_batch_alignment(profile):
    model = FakeDeepTeamModel()
    pipeline = generator(simulator=model)
    batch = await pipeline.generate(profile)
    assert [candidate.prompt for candidate in batch.candidates] == ["DeepTeam baseline attack one", "DeepTeam baseline attack two"]
    assert [schema for schema, _ in model.calls] == [ChatMateBaselinePromptPair, ChatMateMethodAlignmentBatch]
    assert fake_profile(profile).name in model.calls[1][1]
    from secmate_worker.role_prompts import CHATMATE_METHOD_CONSTRAINTS
    method = fake_profile(profile).name
    sent = json.loads(model.calls[0][1].split("\n", 1)[1])["generation_guidelines"]
    assert sent.count(CHATMATE_METHOD_CONSTRAINTS[method]) == 1
    assert not any(value in sent for key, value in CHATMATE_METHOD_CONSTRAINTS.items() if key != method)
    assert batch.assessment_spec == chatmate_candidate_assessment_spec(profile)
    for candidate in batch.candidates:
        assert candidate.generation_mode == "BASELINE_METHOD_REVIEWED"
        assert candidate.method_review.verdict == "ALIGNED"
        assert candidate.method_review.candidate_id == candidate.candidate_id
        assert candidate.method_review.prompt_sha256 == candidate.prompt_sha256
        from secmate_worker.chatmate_candidates import _BASELINE_ALIGNMENT_INSTRUCTION
        assert candidate.method_review.reviewer_instruction_sha256 == hashlib.sha256(_BASELINE_ALIGNMENT_INSTRUCTION.encode()).hexdigest()
        assert candidate.prompt == candidate.source_prompt
        assert candidate.prompt_sha256 == candidate.source_prompt_sha256 == hashlib.sha256(candidate.prompt.encode()).hexdigest()
        assert candidate.explanation is None
    assert [check["outcome"] for check in pipeline.candidate_checks] == ["ALIGNED", "ALIGNED"]
    assert model.enhancement_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["ALIGNED", "NOT_ALIGNED", "UNCERTAIN"])
@pytest.mark.parametrize("second", ["ALIGNED", "NOT_ALIGNED", "UNCERTAIN"])
async def test_all_advisory_verdict_pairs_publish_honestly_without_regeneration(first, second):
    class Model(FakeDeepTeamModel):
        async def a_generate(self, prompt, schema=None):
            result = await super().a_generate(prompt, schema)
            if schema is ChatMateMethodAlignmentBatch:
                result.decisions[0].verdict = first
                result.decisions[1].verdict = second
            return result
    model = Model()
    pipeline = generator(simulator=model)
    batch = await pipeline.generate("prompt-injection-v1")
    assert [candidate.method_review.verdict for candidate in batch.candidates] == [first, second]
    assert [check["outcome"] for check in pipeline.candidate_checks] == [first, second]
    for candidate, check in zip(batch.candidates, pipeline.candidate_checks):
        assert check["candidate_id"] == candidate.candidate_id
        assert check["prompt_sha256"] == candidate.prompt_sha256
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_ids_bind_reversed_review_order_without_rewriting_prompt_bytes():
    class Model(FakeDeepTeamModel):
        async def a_generate(self, prompt, schema=None):
            result = await super().a_generate(prompt, schema)
            if schema is ChatMateBaselinePromptPair:
                result.candidates[0].prompt = "  exact prompt\n"
                result.candidates.reverse()
            else:
                result.decisions.reverse()
            return result
    batch = await generator(simulator=Model()).generate("prompt-injection-v1")
    assert batch.candidates[0].prompt == "  exact prompt\n"


@pytest.mark.parametrize("candidates", [[], [{"candidate_id": "candidate-1", "prompt": "one"}],
    [{"candidate_id": "candidate-1", "prompt": "one"}, {"candidate_id": "candidate-1", "prompt": "two"}],
    [{"candidate_id": "candidate-1", "prompt": "same"}, {"candidate_id": "candidate-2", "prompt": " same "}],
    [{"candidate_id": "candidate-1", "prompt": "  "}, {"candidate_id": "candidate-2", "prompt": "two"}]])
def test_invalid_pairs_fail_local_checks(candidates):
    with pytest.raises(ValidationError):
        ChatMateBaselinePromptPair(candidates=candidates)


@pytest.mark.asyncio
async def test_generation_mode_preserves_legacy_serialization_and_hashes():
    batch = await generator().generate("prompt-injection-v1")
    payload = batch.candidates[0].model_dump(mode="json")
    payload.pop("generation_mode")
    with pytest.raises(ValidationError, match="differ"):
        ChatMatePromptCandidate.model_validate(payload)
    payload.pop("method_review")
    payload["source_prompt"] = "historical source"
    payload["source_prompt_sha256"] = hashlib.sha256(b"historical source").hexdigest()
    legacy = ChatMatePromptCandidate.model_validate(payload)
    assert "generation_mode" not in legacy.model_dump(mode="json")
    assert "method_review" not in legacy.model_dump(mode="json")


@pytest.mark.parametrize("slot", [1, 2])
def test_failure_position_uses_explicit_slot_instead_of_last_review(slot):
    from secmate_worker.chatmate_candidates import _failure_position
    checks = [{"candidate_slot": index, "enhancement_attempt": 1, "outcome": "NOT_ALIGNED"} for index in (1, 2)]
    assert _failure_position(checks, {"candidate_slot": slot}) == {"candidate_slot": slot, "enhancement_attempt": 1}
    assert _failure_position(checks, {}) == {}


def test_method_constraints_and_canonical_guideline_hashes_match_api_without_loading_api_environment():
    from secmate_worker.role_prompts import CHATMATE_METHOD_CONSTRAINTS, chatmate_candidate_generation_guidelines
    from secmate_worker.critic_contracts import canonical_hash
    tree = ast.parse((Path(__file__).resolve().parents[3] / "apps/api/src/secmate_api/contracts.py").read_text(encoding="utf-8"))
    constants = {}
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0] if isinstance(node, ast.Assign) else None
        if isinstance(target, ast.Name) and target.id in {"CHATMATE_METHOD_CONSTRAINTS", "CHATMATE_GUIDELINE_HASHES", "CHATMATE_LEGACY_GUIDELINE_HASHES"}:
            constants[target.id] = ast.literal_eval(node.value)
    assert constants["CHATMATE_METHOD_CONSTRAINTS"] == CHATMATE_METHOD_CONSTRAINTS
    for profile in CHATMATE_CANDIDATE_ATTACK_IDS:
        spec, method = chatmate_candidate_assessment_spec(profile), fake_profile(profile).name
        old = chatmate_candidate_generation_guidelines(spec, method, include_method_constraint=False)
        new = chatmate_candidate_generation_guidelines(spec, method)
        assert new == [*old, CHATMATE_METHOD_CONSTRAINTS[method]]
        assert len(CHATMATE_METHOD_CONSTRAINTS[method]) <= 120
        assert canonical_hash(new) == constants["CHATMATE_GUIDELINE_HASHES"][profile]
        assert canonical_hash(old) == constants["CHATMATE_LEGACY_GUIDELINE_HASHES"][profile]


@pytest.mark.asyncio
async def test_pre_constraint_batches_remain_readable_without_rewriting_them():
    from secmate_worker.contracts import ChatMateCandidateBatch
    from secmate_worker.role_prompts import chatmate_candidate_generation_guidelines
    from secmate_worker.critic_contracts import canonical_hash
    batch = await generator().generate("prompt-injection-v1")
    payload = batch.model_dump(mode="json")
    old = chatmate_candidate_generation_guidelines(batch.assessment_spec, batch.attack_method, include_method_constraint=False)
    payload["provenance"]["generation_guidelines_sha256"] = canonical_hash(old)
    assert ChatMateCandidateBatch.model_validate(payload).model_dump(mode="json") == payload
