import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from secmate_api import main
from secmate_api.config import Settings
from secmate_api.contracts import ProviderQuota, JudgeOutput
from secmate_api.providers import ProviderClients, ProviderRequestError


@pytest.mark.asyncio
async def test_direct_api_critic_and_attacker_use_distinct_credentials(monkeypatch):
    observed = []
    async def handler(request):
        observed.append(request.headers["authorization"])
        return httpx.Response(200, json={"choices": []})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    clients = ProviderClients(Settings("attacker-only", "", 1, groq_critic_api_key="critic-only"))
    await clients._post_groq({}, critic=True)
    await clients._post_groq({})
    assert observed == ["Bearer critic-only", "Bearer attacker-only"]
    with pytest.raises(ProviderRequestError, match="Critic"):
        await ProviderClients(Settings("attacker-only", "", 1))._post_groq({}, critic=True)
    assert len(observed) == 2


@pytest.mark.asyncio
async def test_status_probes_start_together_and_preserve_partial_availability(monkeypatch):
    groq_started, router_started = asyncio.Event(), asyncio.Event()

    class Clients:
        async def groq_models(self):
            groq_started.set()
            await asyncio.wait_for(router_started.wait(), .5)
            return {}, ProviderQuota(requests_remaining=42)

        async def openrouter_key(self):
            router_started.set()
            await asyncio.wait_for(groq_started.wait(), .5)
            raise httpx.ReadTimeout("private credential response")

    monkeypatch.setattr(main, "clients", Clients)
    monkeypatch.setattr(main, "get_settings", lambda: Settings("synthetic-groq", "synthetic-router", 1))
    statuses = await main.provider_status()
    assert [status.provider for status in statuses] == ["GROQ", "OPENROUTER"]
    assert statuses[0].reachable and statuses[0].quota.requests_remaining == 42
    assert not statuses[1].reachable and "timed out" in statuses[1].detail
    assert "private credential" not in statuses[1].detail


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 503])
def test_provider_http_errors_never_include_response_bodies(status):
    response = httpx.Response(status, json={"error": {"message": "PRIVATE_CONTENT api_key=synthetic-secret", "failed_generation": "PRIVATE_GENERATION"}})
    with pytest.raises(ProviderRequestError) as caught:
        ProviderClients._raise_for_status("Groq", response)
    assert f"HTTP {status}" in caught.value.public_detail
    assert "PRIVATE" not in str(caught.value)
    assert "synthetic-secret" not in caught.value.public_detail


@pytest.mark.parametrize("failure", [ProviderRequestError("PRIVATE_PROVIDER_MESSAGE"), httpx.ConnectError("PRIVATE_NETWORK_DETAIL"), ValueError("PRIVATE_RESPONSE")])
def test_connectivity_routes_return_safe_diagnostics(monkeypatch, failure):
    class Clients:
        async def groq_structured(self, *args, **kwargs):
            raise failure

    monkeypatch.setattr(main, "clients", Clients)
    response = TestClient(main.app).post("/api/v1/model-profiles/groq-qwen-attacker/test")
    assert response.status_code == 502
    assert "PRIVATE" not in response.text


@pytest.mark.asyncio
async def test_unconfigured_status_does_not_contact_providers(monkeypatch):
    monkeypatch.setattr(main, "clients", lambda: object())
    monkeypatch.setattr(main, "get_settings", lambda: Settings("", "", 1))
    assert all(not status.configured and not status.reachable for status in await main.provider_status())


@pytest.mark.asyncio
async def test_malformed_success_response_never_becomes_raw_exception_text(monkeypatch):
    clients = ProviderClients(Settings("", "synthetic-router", 1))

    async def malformed(_):
        return httpx.Response(200, json={"error": {"message": "PRIVATE_COMPLETION"}})

    async def no_wait(_):
        pass

    monkeypatch.setattr(clients, "_post_openrouter", malformed)
    monkeypatch.setattr("secmate_api.providers.asyncio.sleep", no_wait)
    with pytest.raises(ProviderRequestError) as caught:
        await clients.openrouter_structured("synthetic-model", "synthetic instruction", "synthetic prompt", "judge", JudgeOutput)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.asyncio
async def test_missing_key_has_actionable_safe_message():
    with pytest.raises(ProviderRequestError) as caught:
        await ProviderClients(Settings("", "", 1)).groq_models()
    assert caught.value.public_detail == "Groq API key is not configured."
