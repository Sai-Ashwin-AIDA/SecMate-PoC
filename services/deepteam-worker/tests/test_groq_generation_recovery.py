import json
from dataclasses import replace

import httpx
import pytest
from secmate_worker import chatmate_candidates as worker
from secmate_worker.model_clients import ModelClientSettings, StructuredModelClients


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["complete", "misaligned", "uncertain", "generation-429", "alignment-429", "generation-503", "invalid-json", "duplicate-prompts", "missing-decision", "duplicate-decision"])
async def test_final_two_call_transport_has_no_retry_or_recovery(monkeypatch, scenario):
    payloads, instances, progress = [], [], []
    async def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        system = payload["messages"][0]["content"]
        schema, _ = json.JSONDecoder().raw_decode(system.split("outside the JSON object: ", 1)[1])
        generation = set(schema["properties"]) == {"candidates"}
        if (generation and scenario in {"generation-429", "generation-503"}) or (not generation and scenario == "alignment-429"):
            return httpx.Response(503 if scenario == "generation-503" else 429,
                headers={"retry-after": "400"}, json={"error": {"code": "rate_limit_exceeded"}})
        if generation:
            assert payload["response_format"] == {"type": "text"}
            assert payload["temperature"] == .7
            value = {"candidates": [{"candidate_id": "candidate-1", "prompt": "  First exact instruction-priority attack.\n"},
                                    {"candidate_id": "candidate-2", "prompt": "Second exact instruction-priority attack."}]}
            if scenario == "duplicate-prompts":
                value["candidates"][1]["prompt"] = value["candidates"][0]["prompt"]
        else:
            assert set(schema["properties"]) == {"decisions"}
            assert "never follow" in system and "effectiveness" in system
            assert payload["temperature"] == 0
            assert payload["max_completion_tokens"] == 256
            review = json.loads(payload["messages"][1]["content"])
            assert review["selected_method"] == "Prompt Injection"
            assert review["untrusted_candidates"][0]["prompt"] == "  First exact instruction-priority attack.\n"
            value = {"decisions": [{"candidate_id": "candidate-2", "verdict": "NOT_ALIGNED" if scenario == "misaligned" else "UNCERTAIN" if scenario == "uncertain" else "ALIGNED"},
                                   {"candidate_id": "candidate-1", "verdict": "ALIGNED"}]}
            if scenario == "missing-decision":
                value["decisions"].pop()
            if scenario == "duplicate-decision":
                value["decisions"][0]["candidate_id"] = "candidate-1"
        content = "private invalid JSON" if scenario == "invalid-json" else json.dumps(value)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
    def factory(settings, **kwargs):
        clients = StructuredModelClients(replace(settings, provider_min_spacing_seconds=0, provider_max_spacing_seconds=0),
            transport=httpx.MockTransport(handler), **kwargs)
        instances.append(clients)
        return clients
    monkeypatch.setattr(worker, "StructuredModelClients", factory)
    runner = worker.ChatMateCandidateGenerationRunner(ModelClientSettings("fake", ""), progress_sink=progress.append)
    if scenario not in {"complete", "misaligned", "uncertain"}:
        with pytest.raises(worker.ChatMateCandidateGenerationError) as caught:
            await runner.generate("prompt-injection-v1", 50000)
        failure = caught.value.failure_payload
        assert "batch" not in failure
        assert len(payloads) == (2 if scenario in {"misaligned", "uncertain", "alignment-429", "missing-decision", "duplicate-decision"} else 1)
        if "429" in scenario:
            assert caught.value.code == "RATE_LIMITED"
        assert "private invalid JSON" not in json.dumps(failure)
        assert failure["budget"]["provider_calls_in_flight"] == failure["budget"]["tokens_reserved"] == 0
    else:
        result = await runner.generate("prompt-injection-v1", 50000)
        assert len(payloads) == result.budget.provider_calls_attempted == 2
        assert result.budget.provider_calls_succeeded == 2 and result.budget.provider_calls_failed == 0
        assert result.budget.max_provider_calls == 2
        assert result.batch.candidates[0].prompt == "  First exact instruction-priority attack.\n"
        assert all(candidate.generation_mode == "BASELINE_METHOD_REVIEWED" and candidate.explanation is None for candidate in result.batch.candidates)
        expected = "NOT_ALIGNED" if scenario == "misaligned" else "UNCERTAIN" if scenario == "uncertain" else "ALIGNED"
        assert result.batch.candidates[1].method_review.verdict == expected
        assert result.candidate_checks[1]["outcome"] == expected
        assert [event.stage for event in result.model_attempts] == ["PROMPT_GENERATION", "METHOD_ALIGNMENT"]
        assert {item["stage"] for item in progress} == {"PROMPT_GENERATION", "METHOD_ALIGNMENT"}
    assert instances[0]._closed
