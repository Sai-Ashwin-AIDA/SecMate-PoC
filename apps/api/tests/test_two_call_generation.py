import copy
import hashlib

import pytest
from pydantic import ValidationError
from secmate_api.contracts import ChatMateWorkerPayload
from secmate_api.chatmate_runs import _generation_failure_details
from test_chatmate_runs import _worker_payload


def aligned_payload():
    payload = _worker_payload()
    payload["batch"]["candidates"] = payload["batch"]["candidates"][:2]
    for candidate in payload["batch"]["candidates"]:
        candidate["generation_mode"] = "BASELINE_METHOD_ALIGNED"
        candidate["prompt"] = candidate["source_prompt"]
        candidate["prompt_sha256"] = candidate["source_prompt_sha256"]
    payload["budget"].update(max_provider_calls=2, provider_calls_attempted=2, provider_calls_succeeded=2, tokens_consumed=300)
    event = payload["model_attempts"][0]
    payload["model_attempts"] = [{**copy.deepcopy(event), "stage": stage} for stage in ("PROMPT_GENERATION", "METHOD_ALIGNMENT")]
    payload["candidate_checks"] = [{"candidate_slot": item["ordinal"], "enhancement_attempt": 1,
        "prompt_characters": len(item["prompt"]), "outcome": "ALIGNED", "reason_category": None}
        for item in payload["batch"]["candidates"]]
    return payload


def test_two_call_success_and_legacy_batches_are_both_readable():
    result = ChatMateWorkerPayload.model_validate(aligned_payload())
    assert result.budget.max_provider_calls == 2
    assert all(item.prompt == item.source_prompt for item in result.batch.candidates)
    assert ChatMateWorkerPayload.model_validate(_worker_payload()).batch.candidates[0].generation_mode is None


@pytest.mark.parametrize("tamper", ["missing-check", "not-aligned", "repeated-slot", "stages", "calls", "mode", "bytes"])
def test_no_unreviewed_or_rewritten_pair_can_publish_as_method_aligned(tamper):
    payload = aligned_payload()
    if tamper == "missing-check":
        payload["candidate_checks"].pop()
    elif tamper == "not-aligned":
        payload["candidate_checks"][0]["outcome"] = "NOT_ALIGNED"
    elif tamper == "repeated-slot":
        payload["candidate_checks"][1]["candidate_slot"] = 1
    elif tamper == "stages":
        payload["model_attempts"][1]["stage"] = "EXPLANATION"
    elif tamper == "calls":
        payload["budget"]["max_provider_calls"] = 60
    elif tamper == "mode":
        payload["batch"]["candidates"][0].pop("generation_mode")
    else:
        candidate = payload["batch"]["candidates"][0]
        candidate["prompt"] += " rewritten"
        candidate["prompt_sha256"] = hashlib.sha256(candidate["prompt"].encode()).hexdigest()
    with pytest.raises(ValidationError):
        ChatMateWorkerPayload.model_validate(payload)


def test_alignment_failure_names_candidate_without_claiming_security_result():
    code, message = _generation_failure_details(1, "", "", {"error": {"code": "METHOD_ALIGNMENT_FAILED", "message": "bounded failure"},
        "diagnostics": {"candidate_slot": 2}})
    assert code == "METHOD_ALIGNMENT_FAILED"
    assert "Candidate 2" in message and "No candidates were published" in message


def test_current_and_historical_guideline_hashes_both_validate_without_migration():
    from secmate_api.contracts import CHATMATE_GUIDELINE_HASHES, CHATMATE_LEGACY_GUIDELINE_HASHES
    for hashes in (CHATMATE_GUIDELINE_HASHES, CHATMATE_LEGACY_GUIDELINE_HASHES):
        payload = aligned_payload()
        payload["batch"]["provenance"]["generation_guidelines_sha256"] = hashes["prompt-injection-v1"]
        assert ChatMateWorkerPayload.model_validate(payload).batch.provenance.generation_guidelines_sha256 == hashes["prompt-injection-v1"]


def test_active_openrouter_profiles_and_compatibility_urls_never_use_retired_models():
    from secmate_api.profiles import MODEL_PROFILES, MODEL_PROFILES_BY_ID
    active = [profile for profile in MODEL_PROFILES if profile.provider == "OPENROUTER"]
    assert {profile.role for profile in active} == {"OUTCOME_JUDGE", "TARGET"}
    assert {profile.model for profile in active} == {"nvidia/nemotron-3.5-super-vl:free"}
    for legacy_id in ("openrouter-nemotron-judge", "openrouter-nemotron-target"):
        assert MODEL_PROFILES_BY_ID[legacy_id].model == "nvidia/nemotron-3.5-super-vl:free"


def reviewed_payload(verdicts):
    payload = aligned_payload()
    for candidate, check, verdict in zip(payload["batch"]["candidates"], payload["candidate_checks"], verdicts):
        candidate["generation_mode"] = "BASELINE_METHOD_REVIEWED"
        candidate["method_review"] = {"candidate_id": candidate["candidate_id"], "prompt_sha256": candidate["prompt_sha256"],
            "verdict": verdict, "reviewer_instruction_version": "baseline-method-review-v1", "reviewer_instruction_sha256": "a" * 64}
        check.update(candidate_id=candidate["candidate_id"], prompt_sha256=candidate["prompt_sha256"], outcome=verdict,
                     reason_category="UNCERTAIN" if verdict == "UNCERTAIN" else None)
    return payload


@pytest.mark.parametrize("first", ["ALIGNED", "NOT_ALIGNED", "UNCERTAIN"])
@pytest.mark.parametrize("second", ["ALIGNED", "NOT_ALIGNED", "UNCERTAIN"])
def test_advisory_policy_accepts_all_real_verdict_pairs(first, second):
    result = ChatMateWorkerPayload.model_validate(reviewed_payload([first, second]))
    assert [item.method_review.verdict for item in result.batch.candidates] == [first, second]
    assert [item.outcome for item in result.candidate_checks] == [first, second]
    assert result.budget.provider_calls_attempted == 2


@pytest.mark.parametrize("tamper", ["review-id", "review-hash", "check-id", "check-hash", "check-verdict", "reviewer-hash", "missing-review", "legacy-mode"])
def test_advisory_review_cannot_be_substituted_or_presented_as_mandatory_alignment(tamper):
    payload = reviewed_payload(["NOT_ALIGNED", "UNCERTAIN"])
    candidate, check = payload["batch"]["candidates"][0], payload["candidate_checks"][0]
    if tamper == "review-id":
        candidate["method_review"]["candidate_id"] = "wrong"
    elif tamper == "review-hash":
        candidate["method_review"]["prompt_sha256"] = "0" * 64
    elif tamper == "check-id":
        check["candidate_id"] = "wrong"
    elif tamper == "check-hash":
        check["prompt_sha256"] = "0" * 64
    elif tamper == "check-verdict":
        check["outcome"] = "ALIGNED"
    elif tamper == "reviewer-hash":
        candidate["method_review"]["reviewer_instruction_sha256"] = "b" * 64
    elif tamper == "missing-review":
        candidate.pop("method_review")
    else:
        for item in payload["batch"]["candidates"]:
            item["generation_mode"] = "BASELINE_METHOD_ALIGNED"
    with pytest.raises(ValidationError):
        ChatMateWorkerPayload.model_validate(payload)
