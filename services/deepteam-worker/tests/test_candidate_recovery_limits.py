import httpx
import pytest

from secmate_worker.model_clients import ModelClientSettings, ModelErrorCode, ModelRequestError
from test_model_adapters import Reply, completion, configured_clients


@pytest.mark.asyncio
async def test_long_rate_limit_does_not_sleep_until_campaign_deadline():
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "400"}, json={"error": {"code": "rate_limit_exceeded"}})
    clients = configured_clients(ModelClientSettings("fake", "", max_provider_wait_seconds=30), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ModelRequestError) as caught:
            await clients.groq_structured("synthetic", "synthetic", Reply)
        assert caught.value.code == ModelErrorCode.RATE_LIMITED
        assert caught.value.retryable is False
        assert len(calls) == 1
        snapshot = await clients.budget_manager.snapshot()
        assert snapshot.provider_calls_in_flight == snapshot.tokens_reserved == 0
    finally:
        await clients.close()


@pytest.mark.asyncio
async def test_reported_quota_prevents_a_known_over_quota_request():
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(200, headers={"x-ratelimit-remaining-tokens": "1", "x-ratelimit-reset-tokens": "6m30s"}, json=completion('{"status":"ok"}'))
    clients = configured_clients(ModelClientSettings("fake", "", max_provider_wait_seconds=30), transport=httpx.MockTransport(handler))
    try:
        assert (await clients.groq_structured("synthetic", "synthetic", Reply)).output.status == "ok"
        with pytest.raises(ModelRequestError) as caught:
            await clients.groq_structured("synthetic", "synthetic", Reply)
        assert caught.value.code == ModelErrorCode.RATE_LIMITED
        assert not caught.value.retryable
        assert len(calls) == 1
    finally:
        await clients.close()
