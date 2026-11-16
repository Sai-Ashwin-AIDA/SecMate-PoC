import json
from pathlib import Path
from dataclasses import replace

import httpx
import pytest
from pydantic import ValidationError

from secmate_worker.manual_judge_calibration import (CalibrationCase, CalibrationSuite, execute,
    fixture_input, request_fingerprint, summarize)
from secmate_worker.manual_chatmate import manual_chatmate_judge_request
from secmate_worker.model_clients import ModelClientSettings, StructuredModelClients

SUITE = Path(__file__).parents[1] / "verification/gold-cases/manual-chatmate-judge-v1.json"


def small_suite():
    suite = CalibrationSuite.model_validate_json(SUITE.read_text(encoding="utf-8"))
    return suite.model_copy(update={"cases": [suite.cases[0], suite.cases[3]]})


def settings():
    return ModelClientSettings("", "fake-offline", provider_min_spacing_seconds=0, provider_max_spacing_seconds=0)


def clients_factory(calls, *, status=200, invalid_citations=False, fail_close=False):
    async def handler(request):
        assert request.url.host == "openrouter.ai"
        payload = json.loads(request.content)
        calls.append(payload)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "synthetic-private-provider-detail"}})
        evidence = json.loads(payload["messages"][1]["content"].split("UNTRUSTED_EVIDENCE_JSON: ")[1])
        references = [evidence["candidate"]["evidence_id"], evidence["manual_collection"]["evidence_id"]]
        output = {"deviation_score": 0, "confidence": .95, "evidence_references": ["unknown-ref"] if invalid_citations else references,
            "policy_references": [], "reasoning": "Synthetic boundary refusal.", "missing_evidence": [], "boundary_fit": "FIT",
            "observations": {key: "NOT_OBSERVED" for key in ("format_followed", "harmful_content_generated", "authority_claim_accepted", "secret_disclosed")}}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})

    class Clients(StructuredModelClients):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, transport=httpx.MockTransport(handler), **kwargs)

        async def close(self):
            await super().close()
            if fail_close:
                raise RuntimeError("synthetic-private-close-detail")

    return Clients


def test_thirty_fixture_inputs_are_valid_and_all_five_methods_have_both_splits():
    suite = CalibrationSuite.model_validate_json(SUITE.read_text(encoding="utf-8"))
    assert len(suite.cases) == 30
    for split in ("development", "holdout"):
        assert len({case.attack_profile_id for case in suite.cases if case.split == split}) == 5
    for case in suite.cases:
        value = fixture_input(case)
        assert value.manual_evidence.redacted_response_text == case.response
        assert value.candidate_batch.candidates[0].prompt == case.prompt
        assert case.label_status == "ENGINEERING_PROVISIONAL"


def test_labels_review_notes_and_split_do_not_change_actual_request():
    case = small_suite().cases[0]
    changed = case.model_copy(update={"expected_status": "COMPROMISED", "split": "holdout",
        "rationale": "PRIVATE_LABEL_MARKER", "reviewer": "PRIVATE_REVIEWER_MARKER"})
    assert request_fingerprint(changed) == request_fingerprint(case)
    value = fixture_input(changed)
    request = manual_chatmate_judge_request(value, f"{value.run_id}-turn-1")
    assert "PRIVATE_LABEL_MARKER" not in str(request)
    assert "PRIVATE_REVIEWER_MARKER" not in str(request)


def test_no_fabricated_human_review_or_duplicate_case_ids():
    payload = small_suite().cases[0].model_dump(mode="json")
    with pytest.raises(ValidationError, match="reviewer"):
        CalibrationCase.model_validate({**payload, "label_status": "SINGLE_REVIEWER_PROVISIONAL"})
    suite = small_suite().model_dump(mode="json")
    with pytest.raises(ValidationError, match="unique"):
        CalibrationSuite.model_validate({**suite, "cases": [*suite["cases"], suite["cases"][0]]})


def test_blinded_review_packet_contains_criteria_but_no_predictions_or_labels():
    from secmate_worker.manual_judge_review import review_packet
    suite = small_suite()
    changed = suite.cases[0].model_copy(update={"rationale": "PRIVATE_LABEL_MARKER"})
    packet = review_packet(suite.model_copy(update={"cases": [changed, suite.cases[1]]}))
    text = json.dumps(packet)
    assert "PRIVATE_LABEL_MARKER" not in text
    assert "expected_status" not in text and "observed_status" not in text and '"split"' not in text
    assert packet["cases"][0]["trusted_assessment_spec"]["prohibited_outcome"]
    assert packet["cases"][0]["human_status"] is None
    assert packet["cases"][0]["request_sha256"] == request_fingerprint(changed)


@pytest.mark.asyncio
async def test_real_evaluator_resume_holdout_freeze_and_call_accounting(tmp_path):
    calls = []
    factory = clients_factory(calls)
    report_path = tmp_path / "report.json"
    suite = small_suite()
    report = await execute(suite, report_path, settings(), max_calls=2, clients_factory=factory)
    assert len(calls) == 1
    assert report["entries"][0]["observed_status"] == "RESISTED"
    assert report["entries"][0]["required_citations_complete"]
    assert len(report["entries"][0]["attempts"]) == 1
    assert report["entries"][0]["tokens_charged"] == 20
    await execute(suite, report_path, settings(), max_calls=2, clients_factory=factory)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="Freeze"):
        await execute(suite, report_path, settings(), split="holdout", max_calls=2, clients_factory=factory)
    report = await execute(suite, report_path, settings(), split="holdout", max_calls=2,
        freeze_development=True, clients_factory=factory)
    assert len(calls) == 2
    assert report["summary"]["holdout"]["correct"] == 1
    assert report["development_frozen_at"]
    with pytest.raises(ValueError, match="Frozen"):
        await execute(suite, report_path, settings(), max_calls=2, clients_factory=factory)


@pytest.mark.asyncio
async def test_changed_experiment_or_caps_and_uncertain_reservation_cannot_replay(tmp_path):
    calls = []
    factory = clients_factory(calls)
    path = tmp_path / "report.json"
    suite = small_suite()
    report = await execute(suite, path, settings(), clients_factory=factory)
    with pytest.raises(ValueError, match="limits"):
        await execute(suite, path, settings(), max_calls=31, clients_factory=factory)
    changed = suite.model_copy(update={"version": "changed"})
    with pytest.raises(ValueError, match="identity"):
        await execute(changed, path, settings(), clients_factory=factory)
    report["entries"][0]["state"] = "STARTED"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Uncertain"):
        await execute(suite, path, settings(), clients_factory=factory)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_error_not_counted_as_verdict_no_retry_and_cleanup_is_safe(tmp_path):
    calls = []
    report = await execute(small_suite(), tmp_path / "report.json", settings(),
        clients_factory=clients_factory(calls, status=429, fail_close=True))
    assert len(calls) == 1
    assert report["entries"][0]["state"] == "ERROR"
    assert report["summary"]["development"]["completed"] == 0
    assert report["summary"]["development"]["agreement_on_completed"] is None
    assert report["cleanup_failed"] is True
    assert "synthetic-private" not in json.dumps(report)


@pytest.mark.asyncio
async def test_invalid_citations_cannot_make_a_conclusive_verdict(tmp_path):
    report = await execute(small_suite(), tmp_path / "report.json", settings(),
        clients_factory=clients_factory([], invalid_citations=True))
    assert report["entries"][0]["observed_status"] == "INCONCLUSIVE"
    assert report["summary"]["development"]["invalid_citation_cases"] == 1


@pytest.mark.asyncio
async def test_concurrent_lock_prevents_calls(tmp_path):
    path = tmp_path / "report.json"
    path.with_suffix(".lock").write_text("existing")
    calls = []
    with pytest.raises(FileExistsError):
        await execute(small_suite(), path, settings(), clients_factory=clients_factory(calls))
    assert calls == []


@pytest.mark.asyncio
async def test_call_cap_and_provider_consent_cannot_change_on_resume(tmp_path):
    calls = []
    path = tmp_path / "report.json"
    consented = replace(settings(), openrouter_allow_data_collection=True)
    factory = clients_factory(calls)
    report = await execute(small_suite(), path, consented, max_calls=1, clients_factory=factory)
    assert report["identity"]["provider_data_collection_allowed"] is True
    assert calls[0]["provider"]["data_collection"] == "allow"
    report = await execute(small_suite(), path, consented, split="holdout", freeze_development=True,
                           max_calls=1, clients_factory=factory)
    assert report["stop_reason"] == "EXPERIMENT_BUDGET_EXHAUSTED"
    assert len(calls) == 1
    with pytest.raises(ValueError, match="identity"):
        await execute(small_suite(), path, settings(), split="holdout", max_calls=1, clients_factory=factory)
    assert len(calls) == 1
