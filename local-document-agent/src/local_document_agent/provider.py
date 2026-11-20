"""Explicit OpenRouter construction and sanitized failures; no calls on import."""

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Configuration, reject_tracing


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    message: str


def provider_failure(error: Exception) -> ProviderFailure:
    """Use typed exceptions/statuses, never parse or print response bodies."""
    from openrouter.errors import OpenRouterError, ResponseValidationError

    if isinstance(error, ResponseValidationError):
        return ProviderFailure("PROVIDER_PROTOCOL_ERROR", "The provider returned an unsupported response shape; no retry was made.")
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return ProviderFailure("REQUEST_TIMEOUT", "The inference request timed out; no retry was made.")
    if isinstance(error, httpx.TransportError):
        return ProviderFailure("NETWORK_ERROR", "The inference connection failed; no retry was made.")
    if isinstance(error, OpenRouterError):
        code = error.status_code
        if code in (401, 403):
            return ProviderFailure("AUTHENTICATION_ERROR", "OpenRouter rejected authentication or access.")
        if code == 402:
            return ProviderFailure("QUOTA_ERROR", "OpenRouter rejected the account quota; no paid fallback was used.")
        if code == 429:
            return ProviderFailure("RATE_LIMIT", "OpenRouter rate-limited the request; no retry was made.")
        if code in (404, 500, 502, 503, 529):
            return ProviderFailure("PROVIDER_UNAVAILABLE", "The requested route is unavailable; no fallback was used.")
        if code in (408, 524):
            return ProviderFailure("REQUEST_TIMEOUT", "OpenRouter timed out; no retry was made.")
        return ProviderFailure("PROVIDER_REJECTED", "OpenRouter rejected the request; narrow the task or check route support.")
    return ProviderFailure("PROVIDER_ERROR", "Inference failed or returned an unsupported response; no retry was made.")


class QuietSDKLogger:
    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Intentionally discard SDK payload diagnostics, even with inherited DEBUG."""


@dataclass
class Provider:
    model: Any
    sync_client: httpx.Client
    async_client: httpx.AsyncClient

    async def aclose(self) -> None:
        try:
            await self.async_client.aclose()
        finally:
            self.sync_client.close()


def create_provider(
    configuration: Configuration, *,
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
) -> Provider:
    """The optional trusted transport is for explicit offline tests, not CLI config."""
    configuration.require_inference_ready()
    reject_tracing(os.environ)
    from langchain_openrouter import ChatOpenRouter
    from openrouter import OpenRouter

    sync = httpx.Client(
        transport=transport, follow_redirects=False, trust_env=False,
        headers={"X-Title": "Local Document Agent"},
    )
    asynchronous = httpx.AsyncClient(
        transport=transport, follow_redirects=False, trust_env=False,
        headers={"X-Title": "Local Document Agent"},
    )
    try:
        sdk = OpenRouter(
            api_key=configuration.api_key.get_secret_value(),
            server_url=configuration.base_url, client=sync, async_client=asynchronous,
            retry_config=None, timeout_ms=configuration.request_timeout_seconds * 1000,
            debug_logger=QuietSDKLogger(),
        )
        model = ChatOpenRouter(
            client=sdk, api_key=configuration.api_key, base_url=configuration.base_url,
            model=configuration.model, temperature=0,
            max_tokens=configuration.max_output_tokens,
            timeout=configuration.request_timeout_seconds * 1000,
            max_retries=0, streaming=False, app_url=None,
            app_title="Local Document Agent", session_id=None, trace=None,
            openrouter_provider={"allow_fallbacks": False, "require_parameters": True},
            cache=False, verbose=False,
        )
    except Exception:
        sync.close()
        # Construction is synchronous and starts no async requests. Nothing is sent.
        raise
    return Provider(model, sync, asynchronous)
