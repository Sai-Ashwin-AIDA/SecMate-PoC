import json
from dataclasses import asdict

import httpx
import pytest

from secmate_worker.model_clients import ModelClientSettings, ModelErrorCode, ModelRequestError
from test_model_adapters import Reply, completion, configured_clients


PRIVATE = "private-provider-body-and-failed-generation"


@pytest.mark.asyncio
@pytest.mark.parametrize("content,expected", [
    ('{"status":"READY"}', None),
    ('{"wrong_field":"READY"}', ModelErrorCode.SCHEMA_VALIDATION),
    ('not json', ModelErrorCode.SCHEMA_VALIDATION),
])
async def test_pinned_attacker_avoids_constrained_decoder_but_validates_output(content, expected):
    from secmate_worker.contracts import ModelRole
    payloads, events = [], []

    async def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if payload["response_format"]["type"] != "text":
            return httpx.Response(400, json=rejection())
        return httpx.Response(200, json=completion(content))

    clients = configured_clients(ModelClientSettings("fake", ""),
                                 transport=httpx.MockTransport(handler), event_sink=events.append)
    async with clients:
        if expected is None:
            result = await clients.groq_structured("qwen/qwen3.8-27b", "synthetic task", Reply,
                                                   role=ModelRole.ATTACKER)
            assert result.output == Reply(status="READY")
        else:
            with pytest.raises(ModelRequestError) as caught:
                await clients.groq_structured("qwen/qwen3.8-27b", "synthetic task", Reply,
                                               role=ModelRole.ATTACKER)
            assert caught.value.code == expected
        assert len(payloads) == 1
        assert payloads[0]["temperature"] == 0
        snapshot = await clients.budget_manager.snapshot()
        assert snapshot.provider_calls_attempted == 1
        assert snapshot.tokens_reserved == snapshot.provider_calls_in_flight == 0


def rejection(code="json_validate_failed", error_type="invalid_request_error", param="response_format"):
    return {"error": {"code": code, "type": error_type, "param": param,
                      "message": PRIVATE, "failed_generation": PRIVATE}}


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [
    ("json_validate_failed", ModelErrorCode.INVALID_JSON),
    ("model_not_found", ModelErrorCode.ROUTE_UNAVAILABLE),
    ("unsupported_parameter", ModelErrorCode.REQUEST_REJECTED),
    (PRIVATE, ModelErrorCode.REQUEST_REJECTED),
])
async def test_http_errors_capture_only_allowlisted_subtypes(code, expected):
    events = []

    async def handler(request):
        return httpx.Response(400, json=rejection(code, param="reasoning_effort"))

    clients = configured_clients(ModelClientSettings("fake", ""),
                                 transport=httpx.MockTransport(handler), event_sink=events.append)
    with pytest.raises(ModelRequestError) as caught:
        await clients.groq_text("model", "synthetic request")
    assert caught.value.code == expected
    assert caught.value.retryable is False
    assert len(events) == 1
    assert events[0].provider_error_code == (None if code == PRIVATE else code)
    assert events[0].provider_error_type == "invalid_request_error"
    assert events[0].provider_error_param == "reasoning_effort"
    assert PRIVATE not in str(caught.value)
    assert PRIVATE not in json.dumps(asdict(events[0]))
    await clients.close()


@pytest.mark.asyncio
async def test_unknown_or_nonstr_subtype_fields_are_discarded_without_repair():
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(400, json=rejection({"secret": PRIVATE}, [PRIVATE], PRIVATE))

    clients = configured_clients(ModelClientSettings("fake", ""), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelRequestError) as caught:
        await clients.groq_structured("model", "synthetic request", Reply)
    assert len(calls) == 1
    assert caught.value.provider_error_code is None
    assert caught.value.provider_error_type is None
    assert caught.value.provider_error_param is None
    assert PRIVATE not in str(caught.value)
    await clients.close()


@pytest.mark.asyncio
async def test_confirmed_json_failure_recovers_with_strictly_validated_text_json():
    payloads, events = [], []

    async def handler(request):
        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return httpx.Response(400, json=rejection())
        return httpx.Response(200, json=completion('{"status":"READY"}'))

    clients = configured_clients(ModelClientSettings("fake", ""),
                                 transport=httpx.MockTransport(handler), event_sink=events.append)
    result = await clients.groq_structured("model", "unaltered framework task", Reply,
                                         system_instruction="trusted assessment and safety constraints")
    assert result.output == Reply(status="READY")
    assert len(payloads) == 2
    assert payloads[0]["messages"][1] == payloads[1]["messages"][1]
    assert payloads[0]["response_format"] == {"type": "json_object"}
    assert payloads[1]["response_format"] == {"type": "text"}
    for payload in payloads:
        assert payload["model"] == "model"
        assert payload["max_completion_tokens"] == 1200
        assert PRIVATE not in json.dumps(payload)
    assert "JSON escaping" in payloads[1]["messages"][0]["content"]
    assert "trusted assessment and safety constraints" in payloads[1]["messages"][0]["content"]
    assert [event.outcome for event in events] == ["FAILURE", "SUCCESS"]
    assert events[0].provider_error_code == "json_validate_failed"
    snapshot = await clients.budget_manager.snapshot()
    assert snapshot.provider_calls_attempted == 2
    assert snapshot.provider_calls_failed == 1
    assert snapshot.provider_calls_succeeded == 1
    assert snapshot.tokens_reserved == snapshot.provider_calls_in_flight == 0
    await clients.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("second_response,expected", [
    (httpx.Response(400, json=rejection()), ModelErrorCode.INVALID_JSON),
    (httpx.Response(200, json=completion('{"wrong_field":"not-valid"}')), ModelErrorCode.SCHEMA_VALIDATION),
    (httpx.Response(200, json=completion('```json\n{"status":"READY"}\n```')), ModelErrorCode.SCHEMA_VALIDATION),
    (httpx.Response(200, json=completion('{"status":123}')), ModelErrorCode.SCHEMA_VALIDATION),
    (httpx.Response(200, json=completion('{"status":"READY","extra":true}')), ModelErrorCode.SCHEMA_VALIDATION),
])
async def test_repair_is_once_only_and_still_requires_schema_validation(second_response, expected):
    count = 0

    async def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(400, json=rejection()) if count == 1 else second_response

    clients = configured_clients(ModelClientSettings("fake", ""), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelRequestError) as caught:
        await clients.groq_structured("model", "synthetic request", Reply)
    assert caught.value.code == expected
    assert count == 2
    snapshot = await clients.budget_manager.snapshot()
    assert snapshot.provider_calls_attempted == snapshot.provider_calls_failed == 2
    assert snapshot.provider_calls_succeeded == 0
    assert snapshot.tokens_reserved == snapshot.provider_calls_in_flight == 0
    await clients.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status", [("unsupported_parameter", 400), ("invalid_request_error", 400),
    ("content_policy_violation", 400), ("json_validate_failed", 403), ("model_not_found", 400)])
async def test_other_rejections_never_request_text_json(code, status):
    payloads = []

    async def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(status, json=rejection(code))

    clients = configured_clients(ModelClientSettings("fake", ""), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelRequestError):
        await clients.groq_structured("qwen/qwen3.8-27b", "synthetic task", Reply)
    assert len(payloads) == 1
    assert payloads[0]["response_format"]["type"] == "json_schema"
    await clients.close()


@pytest.mark.asyncio
async def test_recovery_transient_retries_share_original_retry_allowance():
    payloads, events = [], []

    async def handler(request):
        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return httpx.Response(400, json=rejection())
        return httpx.Response(503)

    clients = configured_clients(ModelClientSettings("fake", "", provider_retry_base_seconds=0),
        transport=httpx.MockTransport(handler), event_sink=events.append)
    with pytest.raises(ModelRequestError):
        await clients.groq_structured("model", "synthetic task", Reply)
    assert len(payloads) == len(events) == 3
    assert [p["response_format"]["type"] for p in payloads] == ["json_object", "text", "text"]
    snapshot = await clients.budget_manager.snapshot()
    assert snapshot.provider_calls_attempted == snapshot.provider_calls_failed == 3
    await clients.close()


def test_advertised_qwen_schema_capability_preserves_schema_semantics():
    from pydantic import BaseModel
    from deepteam.attacks.single_turn.prompt_injection.schema import EnhancedInjection
    from secmate_worker.model_clients import _groq_response_format

    original = EnhancedInjection.model_json_schema()
    format = _groq_response_format("qwen/qwen3.8-27b", EnhancedInjection)
    assert format["type"] == "json_schema"
    assert format["json_schema"]["strict"] is True
    assert format["json_schema"]["schema"] == {**original, "additionalProperties": False}
    assert EnhancedInjection.model_json_schema() == original

    class OptionalOutput(BaseModel):
        value: str | None = None

    class MappingOutput(BaseModel):
        values: dict[str, str]

    for schema in (OptionalOutput, MappingOutput):
        assert _groq_response_format("qwen/qwen3.8-27b", schema) == {"type": "json_object"}
    assert _groq_response_format("other-model", EnhancedInjection) == {"type": "json_object"}


@pytest.mark.asyncio
async def test_local_schema_failure_without_confirmed_provider_error_never_uses_text_json():
    payloads = []

    async def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"wrong":"field"}'))

    clients = configured_clients(ModelClientSettings("fake", ""), transport=httpx.MockTransport(handler))
    with pytest.raises(ModelRequestError) as caught:
        await clients.groq_structured("qwen/qwen3.8-27b", "synthetic task", Reply)
    assert caught.value.code == ModelErrorCode.SCHEMA_VALIDATION
    assert len(payloads) == 1
    assert payloads[0]["response_format"]["type"] == "json_schema"
    await clients.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", ["calls", "tokens"])
async def test_json_recovery_cannot_bypass_campaign_reservation_limits(exhausted):
    from secmate_worker.contracts import CampaignBudget
    from secmate_worker.execution_budget import CampaignBudgetManager

    payloads = []

    async def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        return httpx.Response(400, json=rejection())

    clients = configured_clients(ModelClientSettings("fake", ""), transport=httpx.MockTransport(handler))
    clients.budget_manager = CampaignBudgetManager(CampaignBudget(
        max_paths=1, max_turns_per_path=1, max_provider_calls=1 if exhausted == "calls" else 10,
        max_concurrent_provider_calls=1,
        max_total_tokens=3_000 if exhausted == "tokens" else 100_000,
        timeout_seconds=60, max_retries_per_call=2,
    ))
    clients._governor.budget_manager = clients.budget_manager
    with pytest.raises(ModelRequestError) as caught:
        await clients.groq_structured("model", "synthetic task", Reply)
    assert caught.value.code == ModelErrorCode.BUDGET_EXHAUSTED
    assert len(payloads) == 1
    snapshot = await clients.budget_manager.snapshot()
    assert snapshot.provider_calls_attempted == snapshot.provider_calls_failed == 1
    assert snapshot.provider_calls_succeeded == 0
    assert snapshot.tokens_reserved == snapshot.provider_calls_in_flight == 0
    await clients.close()


@pytest.mark.asyncio
async def test_json_repair_respects_total_call_retry_limit_after_transient_failure():
    count = 0
    settings = ModelClientSettings("fake", "", provider_retry_base_seconds=0, provider_max_cooldown_seconds=0)

    async def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(429) if count == 1 else httpx.Response(400, json=rejection())

    clients = configured_clients(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(ModelRequestError):
        await clients.groq_structured("model", "synthetic request", Reply)
    assert count == 3  # Original, transient retry, and single remaining repair.
    await clients.close()
