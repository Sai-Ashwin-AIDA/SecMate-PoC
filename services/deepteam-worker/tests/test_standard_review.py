import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from dataclasses import replace

import httpx
import pytest

from secmate_worker.standard_review import run_review, ReviewFailure
from secmate_worker.standard_review_contracts import (ScoreOnlyOutput, StandardReviewInput, LinkedAssessmentContext,
    NextMethodOutput, LEGACY_VERSION, VERSION, TARGET_VERSION, TARGET_LINKED_VERSION,
    MethodChoice, digest, estimated_input_tokens, target_model_fingerprint)
from secmate_worker.model_clients import ModelClientSettings, StructuredModelClients
from standard_review_test_data import source_fixture


@pytest.mark.asyncio
async def test_score_only_review_has_one_dedicated_key_call_and_exact_budget_estimate():
    source = source_fixture()
    requests = []
    async def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-critic"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen/qwen3.8-27b" and payload["max_completion_tokens"] == 256
        assert payload["response_format"] == {"type": "text"}
        assert '"recommendations"' in payload["messages"][0]["content"]
        assert "score 0 means this path resisted" in payload["messages"][0]["content"]
        assert StructuredModelClients._estimate_tokens(payload) - 256 == estimated_input_tokens(source)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"recommendations": [
            {"attack_profile_id": source.allowed_methods[0].id, "priority": 90},
            {"attack_profile_id": source.allowed_methods[1].id, "priority": 75}]})}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}})
    before = digest(source.model_dump(mode="json"))
    review = await run_review(source, ModelClientSettings("not-the-critic", "", groq_critic_api_key="synthetic-critic"), transport=httpx.MockTransport(handler))
    assert len(requests) == 1 and review.budget["provider_calls_attempted"] == 1
    assert review.budget["max_total_tokens"] == 4256 and review.budget["tokens_consumed"] == 130
    assert [item.priority for item in review.recommendations] == [90, 75]
    assert review.schema_version == VERSION
    assert digest(source.model_dump(mode="json")) == before
    assert all(set(item.model_dump()) == {"attack_profile_id", "priority"} for item in review.recommendations)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["invalid-json", "empty", "duplicate", "unknown", "bad-score", "explanation", "rate-limit", "timeout"])
async def test_invalid_or_failed_review_never_repairs_or_retries(mode):
    source, calls = source_fixture(), []
    async def handler(request):
        calls.append(request)
        if mode == "rate-limit":
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic-private-message", request=request)
        if mode == "invalid-json":
            return httpx.Response(200, json={"choices": [{"message": {"content": "{invalid"}}]})
        item = {"attack_profile_id": source.allowed_methods[0].id, "priority": 90}
        if mode == "unknown": item["attack_profile_id"] = "not-registered"
        if mode == "bad-score": item["priority"] = 93
        if mode == "explanation": item["why"] = "Unrequested prose must be rejected."
        recommendations = [item, item] if mode == "duplicate" else [item]
        if mode == "empty": recommendations = []
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"recommendations": recommendations})}}]})
    with pytest.raises(ReviewFailure) as caught:
        await run_review(source, ModelClientSettings("", "", groq_critic_api_key="synthetic-critic"), transport=httpx.MockTransport(handler))
    assert len(calls) == 1 and caught.value.payload["budget"]["provider_calls_attempted"] == 1
    assert "private" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("version,count,missing_usage", [(VERSION, 1, False), (VERSION, 2, True), (LEGACY_VERSION, 0, False)])
async def test_required_next_tests_and_legacy_empty_results_keep_one_call_accounting(version, count, missing_usage):
    source = source_fixture().model_copy(update={"schema_version": version})
    calls = []
    async def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert StructuredModelClients._estimate_tokens(payload) - 256 == estimated_input_tokens(source)
        assert payload["max_completion_tokens"] == 256
        output = {"recommendations": [{"attack_profile_id": item.id, "priority": 80} for item in source.allowed_methods[:count]]}
        response = {"choices": [{"message": {"content": json.dumps(output)}}]}
        if not missing_usage:
            response["usage"] = {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}
        return httpx.Response(200, json=response)
    review = await run_review(source, ModelClientSettings("", "", groq_critic_api_key="synthetic-critic"), transport=httpx.MockTransport(handler))
    assert len(calls) == review.budget["provider_calls_attempted"] == 1
    assert len(review.recommendations) == count and review.schema_version == version
    assert review.budget["calls_with_missing_usage"] == int(missing_usage)
    assert review.budget["tokens_consumed"] > 0
    assert calls[0]["response_format"] == {"type": "text"}


@pytest.mark.asyncio
async def test_oversized_decisive_evidence_fails_before_any_provider_call():
    source = source_fixture().model_dump(mode="json")
    source["parent_snapshot"]["evidence"]["paths"][0]["oracle_results"][0]["detail"] = "Decisive evidence " * 3000
    source["source_snapshot_sha256"] = digest(source["parent_snapshot"])
    async def forbidden(request):
        pytest.fail("Input that cannot fit must not reach a provider")
    with pytest.raises(ValueError, match="INPUT_BUDGET_EXCEEDED"):
        await run_review(StandardReviewInput.model_validate(source), ModelClientSettings("", ""), transport=httpx.MockTransport(forbidden))


def test_wire_contracts_and_token_estimates_match_across_api_and_worker():
    path = Path(__file__).resolve().parents[3] / "apps/api/src/secmate_api/standard_review_contracts.py"
    spec = importlib.util.spec_from_file_location("standard_review_api_contract_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = source_fixture()
    assert module.ScoreOnlyOutput.model_json_schema() == ScoreOnlyOutput.model_json_schema()
    assert module.NextMethodOutput.model_json_schema() == NextMethodOutput.model_json_schema()
    api_source = module.StandardReviewInput.model_validate(source.model_dump(mode="json"))
    assert module.estimated_input_tokens(api_source) == estimated_input_tokens(source) <= 4000
    module.LinkedAssessmentContext.model_validate(
        LinkedAssessmentContext.model_validate(
            {
                "parent_run_id": "api-run-111111111111",
                "parent_path_id": "path-1",
                "review_id": "standard-review-222222222222",
                "review_sha256": "a" * 64,
                "source_audit_sha256": "b" * 64,
                "assessment_spec_sha256": "c" * 64,
                "target_profile_id": "synthetic-socmate-tier1",
                "target_profile_version": "1",
                "target_model_sha256": "d" * 64,
                "vulnerability_profile_id": "ExcessiveAgency:permissions",
                "attack_profile_id": "base64-v1",
                "priority": 80,
                "redacted_parent_context": {},
            }
        ).model_dump(mode="json")
    )


@pytest.mark.asyncio
async def test_linked_context_is_generation_only_and_cannot_change_the_boundary(monkeypatch):
    import secmate_worker.deepteam_runner as module
    from test_deepteam_runner import FakeConstruct, FakeRedTeamer
    source = source_fixture()
    context = LinkedAssessmentContext(parent_run_id=source.run_id, parent_path_id=source.source_path_id, review_id=source.review_id,
        review_sha256="a" * 64, source_audit_sha256=source.source_audit_sha256, assessment_spec_sha256=source.assessment_spec_sha256,
        target_profile_id=source.target_profile_id, target_profile_version="1", vulnerability_profile_id=source.vulnerability_profile_id,
        target_model_sha256=target_model_fingerprint(source.parent_snapshot["manifest"]["campaign"]),
        attack_profile_id="base64-v1", priority=90, redacted_parent_context={"response": "Synthetic prior boundary evidence"})
    engines = []
    class Engine(FakeConstruct):
        def __init__(self, **kwargs):
            super().__init__(**kwargs); engines.append(kwargs)
    attack, vulnerability = module.resolve_attack_profile("base64-v1"), module.resolve_vulnerability_profile(source.vulnerability_profile_id)
    monkeypatch.setattr(module, "AttackEngine", Engine)
    monkeypatch.setattr(module, "RedTeamer", FakeRedTeamer)
    monkeypatch.setattr(module, "resolve_attack_profile", lambda _: replace(attack, builder=lambda simulator: FakeConstruct()))
    monkeypatch.setattr(module, "resolve_vulnerability_profile", lambda _: replace(vulnerability, builder=lambda *args: FakeConstruct()))
    runner = module.SecMateDeepTeamRunner(ModelClientSettings("", ""))
    result = await runner.run_single_attack("base64-v1", follow_up_context=context)
    assert sum("UNTRUSTED_PARENT_EVIDENCE_JSON" in item for item in engines[0]["generation_guidelines"]) == 1
    assert "Synthetic prior boundary evidence" not in FakeRedTeamer.init_kwargs["evaluation_model"].system_instruction
    assert result.manifest.prompt_provenance_hashes["linked_context_sha256"] == digest(context.model_dump(mode="json"))
    assert result.campaign.assessment_spec.model_dump(mode="json") == source.assessment_spec
    with pytest.raises(ValueError, match="boundary"):
        await runner.run_single_attack("base64-v1", follow_up_context=context.model_copy(update={"assessment_spec_sha256": "0" * 64}))


def fresh_review_source():
    from datetime import datetime, timezone
    from secmate_worker.contracts import CampaignBudget
    from secmate_worker.deepteam_catalog import (ATTACK_PROFILES, ensure_profiles_applicable,
                                                 fresh_selection_capability, resolve_vulnerability_profile)
    from secmate_worker.deepteam_runner import SecMateDeepTeamRunner

    campaign = SecMateDeepTeamRunner._campaign(
        "run-bbbbbbbbbbbb",
        datetime(2026, 11, 14, tzinfo=timezone.utc),
        CampaignBudget(max_paths=1, max_turns_per_path=1, max_provider_calls=30,
            max_total_tokens=75000, timeout_seconds=900, max_retries_per_call=2),
        attack_methods=["prompt-injection-v1"],
        vulnerability_type="DirectPromptInjection:direct_user_instruction",
        target_profile_id="secmate.synthetic-chatmate.fresh.v1",
    )
    path_id = "run-bbbbbbbbbbbb-path-1"
    snapshot = {
        "run_id": "api-run-333333333333",
        "manifest": {"campaign": campaign.model_dump(mode="json")},
        "summary": {"execution_mode": "SINGLE", "attack_profile_id": "prompt-injection-v1"},
        "evidence": {"paths": [{"path_id": path_id, "attack_method": "prompt-injection-v1",
            "status": "RESISTED", "turns": [], "oracle_results": []}], "review_results": []},
    }
    vulnerability = resolve_vulnerability_profile("DirectPromptInjection:direct_user_instruction")
    methods = []
    for profile in ATTACK_PROFILES:
        if profile.profile_id == "prompt-injection-v1":
            continue
        try:
            ensure_profiles_applicable(profile, vulnerability, campaign.target_profile_id)
        except ValueError:
            continue
        if fresh_selection_capability(profile, vulnerability).execution_capability != "EXECUTABLE":
            continue
        methods.append(MethodChoice(id=profile.profile_id, name=profile.name, description=profile.description[:60]))
    spec = campaign.assessment_spec.model_dump(mode="json")
    return StandardReviewInput(
        schema_version=TARGET_VERSION,
        run_id=snapshot["run_id"], review_id="standard-review-444444444444",
        created_at="2026-11-14T00:00:00Z", target_profile_id=campaign.target_profile_id,
        target_profile_version=campaign.target_profile_version,
        scenario_id=campaign.scenario_id, scenario_version=campaign.scenario_version,
        vulnerability_profile_id=vulnerability.profile_id, source_path_id=path_id,
        source_audit_sha256=digest(snapshot), source_snapshot_sha256=digest(snapshot),
        assessment_spec_sha256=digest(spec), assessment_spec=spec,
        parent_snapshot=snapshot, allowed_methods=methods,
    )


@pytest.mark.asyncio
async def test_target_neutral_review_recommends_only_fresh_applicable_unused_methods():
    source = fresh_review_source()
    assert "tree-jailbreaking-v1" not in {item.id for item in source.allowed_methods}
    async def handler(request):
        payload = json.loads(request.content)
        assert "SOCMate" not in payload["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "recommendations": [{"attack_profile_id": "linear-jailbreaking-v1", "priority": 85}]
        })}}], "usage": {"total_tokens": 100}})
    review = await run_review(source, ModelClientSettings("", "", groq_critic_api_key="synthetic-critic"),
        transport=httpx.MockTransport(handler))
    assert review.schema_version == TARGET_VERSION
    assert [item.attack_profile_id for item in review.recommendations] == ["linear-jailbreaking-v1"]


def test_target_neutral_linked_context_binds_scenario_model_spec_and_guidance():
    source = fresh_review_source()
    campaign = source.parent_snapshot["manifest"]["campaign"]
    guidance = {"outcome": "RESISTED", "next_test": "Use a distinct direct-user framing."}
    context = LinkedAssessmentContext(
        schema_version=TARGET_LINKED_VERSION,
        parent_run_id=source.run_id, parent_path_id=source.source_path_id,
        review_id=source.review_id, review_sha256="a" * 64,
        source_audit_sha256=source.source_audit_sha256,
        assessment_spec_sha256=source.assessment_spec_sha256,
        target_profile_id=source.target_profile_id,
        target_profile_version=source.target_profile_version,
        scenario_id=source.scenario_id, scenario_version=source.scenario_version,
        target_model_sha256=target_model_fingerprint(campaign),
        vulnerability_profile_id=source.vulnerability_profile_id,
        attack_profile_id="linear-jailbreaking-v1", priority=85,
        redacted_parent_context=guidance,
        redacted_parent_context_sha256=digest(guidance),
    )
    assert context.schema_version == TARGET_LINKED_VERSION
    with pytest.raises(ValueError, match="metadata is incomplete"):
        LinkedAssessmentContext.model_validate({
            **context.model_dump(mode="json"),
            "redacted_parent_context_sha256": "0" * 64,
        })


@pytest.mark.asyncio
async def test_fresh_linked_child_uses_parent_context_only_as_generation_guidance(monkeypatch):
    import secmate_worker.deepteam_runner as module
    from test_deepteam_runner import FakeConstruct, FakeRedTeamer

    source = fresh_review_source()
    campaign = source.parent_snapshot["manifest"]["campaign"]
    guidance = {"outcome": "RESISTED", "next_test": "Try a distinct direct-user framing."}
    context = LinkedAssessmentContext(
        schema_version=TARGET_LINKED_VERSION,
        parent_run_id=source.run_id, parent_path_id=source.source_path_id,
        review_id=source.review_id, review_sha256="a" * 64,
        source_audit_sha256=source.source_audit_sha256,
        assessment_spec_sha256=source.assessment_spec_sha256,
        target_profile_id=source.target_profile_id,
        target_profile_version=source.target_profile_version,
        scenario_id=source.scenario_id, scenario_version=source.scenario_version,
        target_model_sha256=target_model_fingerprint(campaign),
        vulnerability_profile_id=source.vulnerability_profile_id,
        attack_profile_id="linear-jailbreaking-v1", priority=85,
        redacted_parent_context=guidance,
        redacted_parent_context_sha256=digest(guidance),
    )
    engines = []
    class Engine(FakeConstruct):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            engines.append(kwargs)
    attack = module.resolve_attack_profile(context.attack_profile_id)
    vulnerability = module.resolve_vulnerability_profile(context.vulnerability_profile_id)
    monkeypatch.setattr(module, "AttackEngine", Engine)
    monkeypatch.setattr(module, "RedTeamer", FakeRedTeamer)
    monkeypatch.setattr(module, "resolve_attack_profile", lambda _: replace(attack, builder=lambda simulator: FakeConstruct()))
    monkeypatch.setattr(module, "resolve_vulnerability_profile", lambda _: replace(vulnerability, builder=lambda *args: FakeConstruct()))
    result = await module.SecMateDeepTeamRunner(ModelClientSettings("", "")).run_single_attack(
        context.attack_profile_id, context.vulnerability_profile_id,
        target_profile_id=context.target_profile_id, follow_up_context=context,
    )
    assert sum("UNTRUSTED_PARENT_EVIDENCE_JSON" in item for item in engines[0]["generation_guidelines"]) == 1
    assert result.evidence.paths[0].turns == []
    assert result.evidence.paths[0].phase5_assessments == []
    assert result.manifest.prompt_provenance_hashes["linked_context_sha256"] == digest(context.model_dump(mode="json"))
    with pytest.raises(ValueError, match="boundary"):
        await module.SecMateDeepTeamRunner(ModelClientSettings("", "")).run_single_attack(
            context.attack_profile_id, context.vulnerability_profile_id,
            target_profile_id=context.target_profile_id,
            follow_up_context=context.model_copy(update={"scenario_id": "another-scenario"}),
        )
