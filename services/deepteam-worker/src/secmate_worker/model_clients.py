from __future__ import annotations

import asyncio
import json
import hashlib
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .contracts import ModelRole, ProviderName, TokenUsage
from .execution_budget import (
    BudgetErrorCode,
    BudgetExceededError,
    CampaignBudgetManager,
    ProviderCallReservation,
)
from .runtime_policy import (
    configure_runtime_environment,
    validate_installed_frameworks,
    validate_runtime,
)


SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _json_schema_response_format(schema: type[BaseModel]) -> dict[str, Any]:
    # Close only already-required objects; never make optional fields required
    # or change free-form mappings to fit the provider's strict schema subset.
    if schema is not None:
        document = schema.model_json_schema()

        def close_objects(node: Any) -> bool:
            if isinstance(node, list):
                return all(close_objects(value) for value in node)
            if not isinstance(node, dict):
                return True
            if node.get("type") == "object":
                properties = node.get("properties")
                if (
                    not isinstance(properties, dict)
                    or set(node.get("required", [])) != set(properties)
                    or node.get("additionalProperties", False) is not False
                ):
                    return False
                node["additionalProperties"] = False
            return all(close_objects(value) for value in node.values())

        if close_objects(document):
            return {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "strict": True, "schema": document,
            }}
    return {"type": "json_object"}


def _groq_response_format(model: str, schema: type[BaseModel]) -> dict[str, Any]:
    # Only the pinned structured-output model advertises this strict subset.
    return _json_schema_response_format(schema) if model == "qwen/qwen3.8-27b" else {"type": "json_object"}


PROVIDER_ERROR_ALLOWLISTS = {
    "code": frozenset({
        "json_validate_failed", "model_not_found", "model_decommissioned",
        "invalid_request_error", "unsupported_parameter", "invalid_parameter",
        "context_length_exceeded", "content_policy_violation", "permission_denied",
        "insufficient_quota", "rate_limit_exceeded", "invalid_tool_name", "unsupported_role",
    }),
    "type": frozenset({
        "invalid_request_error", "authentication_error", "rate_limit_error",
        "permission_error", "server_error", "api_error",
    }),
    "param": frozenset({
        "response_format", "json_schema", "max_completion_tokens", "max_tokens",
        "reasoning_effort", "messages", "model", "temperature", "stream",
        "tools", "tool_choice",
    }),
}


def _safe_provider_error(response: httpx.Response) -> dict[str, str]:
    # Never retain message, failed_generation, or any arbitrary provider text.
    try:
        data = response.json()
    except ValueError:
        return {}
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return {}
    safe = {
        f"provider_error_{name}": value
        for name, allowed in PROVIDER_ERROR_ALLOWLISTS.items()
        if isinstance(value := error.get(name), str) and value in allowed
    }
    metadata = error.get("metadata")
    raw = metadata.get("raw") if isinstance(metadata, dict) else None
    if isinstance(raw, str) and len(raw) <= 32_000:
        try:
            nested = json.loads(raw)
        except ValueError:
            nested = None
        if isinstance(nested, dict) and isinstance(nested.get("error"), dict):
            nested = nested["error"]
        if isinstance(nested, dict):
            error = nested
            for name, allowed in PROVIDER_ERROR_ALLOWLISTS.items():
                value = error.get(name)
                if isinstance(value, str) and value in allowed:
                    safe[f"provider_error_{name}"] = value
    # Inspect bounded text only to classify fixed enums; never retain provider text.
    message = error.get("message")
    if isinstance(message, str) and len(message) <= 32_000:
        text = message.lower()
        if ("function" in text or "tool" in text) and "name" in text and any(x in text for x in ("pattern", "a-z", "invalid", "must match")):
            safe.update(provider_error_code="invalid_tool_name", provider_error_param="tools")
        elif "role" in text and any(x in text for x in ("unsupported", "not support", "invalid")):
            safe.update(provider_error_code="unsupported_role", provider_error_param="messages")
    return safe


class ModelErrorCode(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMITED = "RATE_LIMITED"
    ROUTE_UNAVAILABLE = "ROUTE_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
    READ_TIMEOUT = "READ_TIMEOUT"
    WRITE_TIMEOUT = "WRITE_TIMEOUT"
    POOL_TIMEOUT = "POOL_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_JSON = "INVALID_JSON"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    SCHEMA_VALIDATION = "SCHEMA_VALIDATION"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    CAMPAIGN_CANCELLED = "CAMPAIGN_CANCELLED"
    CANCELLED = "CANCELLED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class ModelClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: ProviderName,
        code: ModelErrorCode,
        retryable: bool,
        status_code: int | None = None,
        latency_ms: int = 0,
        provider_request_id: str | None = None,
        retry_after_seconds: float | None = None,
        provider_error_code: str | None = None,
        provider_error_type: str | None = None,
        provider_error_param: str | None = None,
        finish_reason: str | None = None,
        response_characters: int | None = None,
        output_limit_tokens: int | None = None,
        response_format: str | None = None,
        schema_name: str | None = None,
        schema_sha256: str | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.latency_ms = latency_ms
        self.provider_request_id = provider_request_id
        self.retry_after_seconds = retry_after_seconds
        self.finish_reason = finish_reason
        self.response_characters = response_characters
        self.output_limit_tokens = output_limit_tokens
        self.response_format = response_format
        self.schema_name = schema_name
        self.schema_sha256 = schema_sha256
        for name, value in (("code", provider_error_code), ("type", provider_error_type), ("param", provider_error_param)):
            setattr(self, f"provider_error_{name}", value if isinstance(value, str) and value in PROVIDER_ERROR_ALLOWLISTS[name] else None)


class ModelConfigurationError(ModelClientError):
    pass


class ModelRequestError(ModelClientError):
    pass


@dataclass(frozen=True, repr=False)
class ModelClientSettings:
    groq_api_key: str
    openrouter_api_key: str
    request_timeout_seconds: float = 90
    openrouter_allow_data_collection: bool = False
    provider_min_spacing_seconds: float = 0.5
    provider_tokens_per_second: float = 1_000
    provider_max_spacing_seconds: float = 5
    provider_retry_base_seconds: float = 1
    provider_max_cooldown_seconds: float = 30
    provider_retry_jitter_seconds: float = 0.25
    groq_critic_api_key: str = ""
    max_provider_wait_seconds: float | None = None

    def __repr__(self) -> str:
        return (
            "ModelClientSettings("
            f"groq_configured={bool(self.groq_api_key)}, "
            f"openrouter_configured={bool(self.openrouter_api_key)}, "
            f"request_timeout_seconds={self.request_timeout_seconds}, "
            f"provider_min_spacing_seconds={self.provider_min_spacing_seconds}, "
            f"provider_tokens_per_second={self.provider_tokens_per_second}, "
            f"provider_max_spacing_seconds={self.provider_max_spacing_seconds}, "
            f"provider_retry_base_seconds={self.provider_retry_base_seconds}, "
            f"provider_max_cooldown_seconds={self.provider_max_cooldown_seconds}, "
            f"provider_retry_jitter_seconds={self.provider_retry_jitter_seconds}, "
            "openrouter_allow_data_collection="
            f"{self.openrouter_allow_data_collection})"
        )


@dataclass(frozen=True)
class ModelCallMetadata:
    provider: ProviderName
    model: str
    latency_ms: int
    usage: TokenUsage | None
    provider_request_id: str | None = None
    role: ModelRole | None = None
    profile_id: str | None = None
    finish_reason: str | None = None
    response_characters: int | None = None
    output_limit_tokens: int | None = None
    response_format: str | None = None
    schema_name: str | None = None
    schema_sha256: str | None = None
    status_code: int | None = None
    provider_generation_id: str | None = None


@dataclass(frozen=True)
class ModelAttemptEvent:
    provider: ProviderName
    model: str
    outcome: Literal["SUCCESS", "FAILURE"]
    latency_ms: int
    usage: TokenUsage | None = None
    error_code: ModelErrorCode | None = None
    retryable: bool = False
    status_code: int | None = None
    provider_request_id: str | None = None
    role: ModelRole | None = None
    profile_id: str | None = None
    provider_error_code: str | None = None
    provider_error_type: str | None = None
    provider_error_param: str | None = None
    finish_reason: str | None = None
    response_characters: int | None = None
    output_limit_tokens: int | None = None
    response_format: str | None = None
    schema_name: str | None = None
    schema_sha256: str | None = None
    stage: str | None = None
    candidate_slot: int | None = None
    enhancement_attempt: int | None = None
    estimated_tokens: int | None = None
    request_accounting: dict[str, Any] | None = None


ModelAttemptSink = Callable[[ModelAttemptEvent], None]


@dataclass(frozen=True)
class ModelCallResult(Generic[SchemaT]):
    output: SchemaT
    metadata: ModelCallMetadata


@dataclass(frozen=True)
class TextCallResult:
    output: str
    metadata: ModelCallMetadata


@dataclass(frozen=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    replay: dict[str, Any]
    validation_error: str | None = None


@dataclass(frozen=True)
class ToolTurnResult:
    content: str | None
    tool_calls: list[ProviderToolCall]
    metadata: ModelCallMetadata


def _usage(data: dict[str, Any]) -> TokenUsage | None:
    value = data.get("usage")
    if not isinstance(value, dict):
        return None
    try:
        return TokenUsage(
            prompt_tokens=value.get("prompt_tokens"),
            completion_tokens=value.get("completion_tokens"),
            total_tokens=value.get("total_tokens"),
        )
    except (TypeError, ValidationError):
        return None


class ProviderGovernor:
    def __init__(
        self,
        settings: ModelClientSettings,
        budget_manager: CampaignBudgetManager,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_source: Callable[[], float] = random.random,
    ):
        if settings.provider_tokens_per_second <= 0:
            raise ValueError("provider_tokens_per_second must be positive")
        if min(
            settings.provider_min_spacing_seconds,
            settings.provider_max_spacing_seconds,
            settings.provider_retry_base_seconds,
            settings.provider_max_cooldown_seconds,
            settings.provider_retry_jitter_seconds,
        ) < 0:
            raise ValueError("provider pacing settings cannot be negative")
        self.settings = settings
        self.budget_manager = budget_manager
        self._clock = clock
        self._sleep = sleep
        self._random_source = random_source
        self._locks = {provider: asyncio.Lock() for provider in ProviderName}
        self._next_start = {provider: 0.0 for provider in ProviderName}
        self._rate_limit_streak = {provider: 0 for provider in ProviderName}
        self._quota = {}
        self.progress_sink = None

    def observe_limits(self, provider, headers):
        if self.settings.max_provider_wait_seconds is None:
            return
        for unit in ("tokens", "requests"):
            remaining, reset = headers.get(f"x-ratelimit-remaining-{unit}"), headers.get(f"x-ratelimit-reset-{unit}")
            if remaining is None or reset is None:
                continue
            # Groq durations are bounded numeric components, e.g. 1m2.5s.
            parts = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", reset)
            if not parts or not any(parts.groups()):
                continue
            try:
                seconds = sum(float(value or 0) * multiplier for value, multiplier in zip(parts.groups(), (3600, 60, 1)))
                self._quota[provider, unit] = (max(0, int(remaining)), self._clock() + seconds)
            except (ValueError, OverflowError):
                continue

    async def execute(
        self,
        provider: ProviderName,
        estimated_tokens: int,
        operation_factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        async with self._locks[provider]:
            spacing = max(
                self.settings.provider_min_spacing_seconds,
                estimated_tokens / self.settings.provider_tokens_per_second,
            )
            spacing = min(spacing, self.settings.provider_max_spacing_seconds)
            if provider == ProviderName.OPENROUTER:
                spacing = min(max(spacing, 3.1), self.settings.provider_max_spacing_seconds)
            delay = max(0.0, self._next_start[provider] - self._clock())
            for unit, needed in (("tokens", estimated_tokens), ("requests", 1)):
                remaining, reset_at = self._quota.get((provider, unit), (needed, 0))
                if remaining < needed and reset_at > self._clock():
                    delay = max(delay, reset_at - self._clock())
            limit = self.settings.max_provider_wait_seconds
            if limit is not None and delay > limit:
                raise ModelRequestError("Provider quota recovery exceeds the bounded wait limit.",
                    provider=provider, code=ModelErrorCode.RATE_LIMITED, retryable=False)
            if delay:
                if self.progress_sink is not None:
                    self.progress_sink("PROVIDER_COOLDOWN")
                await self.budget_manager.run_provider_operation(
                    lambda: self._sleep(delay)
                )
            await self.budget_manager.ensure_active()
            self._next_start[provider] = self._clock() + spacing
            return await self.budget_manager.run_provider_operation(operation_factory)

    def record_success(self, provider: ProviderName) -> None:
        self._rate_limit_streak[provider] = 0

    def record_retry(self, error: ModelRequestError, attempt: int) -> None:
        if error.code == ModelErrorCode.RATE_LIMITED:
            self._rate_limit_streak[error.provider] += 1
            exponent = self._rate_limit_streak[error.provider] - 1
        else:
            exponent = attempt
        fallback = self.settings.provider_retry_base_seconds * (2**exponent)
        fallback = min(fallback, self.settings.provider_max_cooldown_seconds)
        requested = error.retry_after_seconds
        cooldown = fallback if requested is None else max(fallback, requested)
        jitter = max(0.0, min(1.0, self._random_source()))
        jitter *= self.settings.provider_retry_jitter_seconds
        self._next_start[error.provider] = max(
            self._next_start[error.provider],
            self._clock() + cooldown + jitter,
        )


class StructuredModelClients:
    def __init__(
        self,
        settings: ModelClientSettings,
        budget_manager: CampaignBudgetManager,
        transport: httpx.AsyncBaseTransport | None = None,
        event_sink: ModelAttemptSink | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_source: Callable[[], float] = random.random,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
        progress_sink=None,
    ):
        configure_runtime_environment()
        validate_runtime()
        self.deepteam_commit = validate_installed_frameworks()
        self.settings = settings
        self.timeout = httpx.Timeout(settings.request_timeout_seconds)
        self.transport = transport
        self.event_sink = event_sink
        self.budget_manager = budget_manager
        self._governor = ProviderGovernor(
            settings,
            budget_manager,
            clock=clock,
            sleep=sleep,
            random_source=random_source,
        )
        self._governor.progress_sink = progress_sink
        self._client_factory = client_factory
        self._http_clients: dict[ProviderName, httpx.AsyncClient] = {}
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        clients = list(self._http_clients.values())
        self._http_clients.clear()
        if clients:
            await asyncio.gather(*(client.aclose() for client in clients))

    async def __aenter__(self) -> StructuredModelClients:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def groq_structured(
        self,
        model: str,
        prompt: str,
        schema: type[SchemaT],
        system_instruction: str | None = None,
        role: ModelRole | None = None,
        profile_id: str | None = None,
        structured_response_mode: Literal["AUTO", "TEXT_JSON"] = "AUTO",
    ) -> ModelCallResult[SchemaT]:
        if structured_response_mode not in {"AUTO", "TEXT_JSON"}:
            raise ValueError("Unsupported structured response mode")
        # DeepTeam's adversarial generation/validation schemas repeatedly trigger
        # Groq's constrained decoder. Use locally validated JSON from the outset
        # for the pinned attacker, rather than spending a rejected call plus a
        # recovery call on each stage. Critic/Judge decoding remains unchanged.
        text_json = structured_response_mode == "TEXT_JSON" or (
            model == "qwen/qwen3.8-27b" and role == ModelRole.ATTACKER
        )
        schema_instruction = (
            "Return one JSON object matching this schema exactly. Do not add "
            f"Markdown or prose outside the JSON object: {json.dumps(schema.model_json_schema())}"
        )
        system = (
            f"{system_instruction}\n\n{schema_instruction}"
            if system_instruction
            else schema_instruction
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": .7 if role == ModelRole.ATTACKER and structured_response_mode == "TEXT_JSON" else 0,
            "max_completion_tokens": 1200,
            "reasoning_effort": "none",
            # TEXT_JSON changes provider decoding only. The same strict Pydantic
            # validation/accounting path still gates every accepted response.
            "response_format": {"type": "text"} if text_json else _groq_response_format(model, schema),
        }
        if self.settings.max_provider_wait_seconds is not None and (
            set(schema.model_fields) in ({"verdict", "reason_category"}, {"non_compliant"}, {"is_valid", "reason"})
            or schema.__name__ == "ChatMateMethodAlignmentBatch"
            or schema.__name__ in {"ScoreOnlyOutput", "NextMethodOutput"}
            or (len(schema.model_fields) == 1 and next(iter(schema.model_fields)).startswith("is_"))
        ):
            payload["max_completion_tokens"] = 256
        requests_started = 0

        async def request(current_payload, max_retries=None):
            async def operation():
                nonlocal requests_started
                requests_started += 1
                return await self._structured_request(
                    provider=ProviderName.GROQ,
                    model=model,
                    schema=schema,
                    url="https://api.groq.com/openai/v1/chat/completions",
                    api_key=self.settings.groq_critic_api_key if role == ModelRole.ATTACK_CRITIC else self.settings.groq_api_key,
                    payload=current_payload,
                    role=role,
                    profile_id=profile_id,
                )
            return await self._with_retry(operation, max_retries=max_retries)

        try:
            return await request(payload)
        except ModelRequestError as error:
            if (
                text_json
                or
                error.provider_error_code != "json_validate_failed"
                or error.status_code != 400
                or requests_started > self.budget_manager.budget.max_retries_per_call
            ):
                raise
            # One bounded TEXT_JSON recovery for a confirmed provider JSON-mode
            # failure. The same structured request path validates the entire
            # output before recording success; this is not an unchecked text call.
            # No failed-generation text or provider message enters the new prompt.
            repair_instruction = (
                "The provider rejected the previous output as invalid JSON. "
                "Regenerate the same requested task as ONE complete JSON object "
                "matching the schema. Serialize every string with JSON escaping: "
                "escape double quotes, backslashes, and newlines; no literal control "
                "characters or trailing commas. Nested examples and format requests "
                "belong inside the input string, not outside the outer JSON object. "
                "Keep the complete serialized object within the 1200-token output "
                "limit. Do not add Markdown fences or text outside the object. "
                "Preserve the trusted assessment and safety constraints."
            )
            repaired_payload = {
                **payload,
                "messages": [
                    {"role": "system", "content": system + "\n\n" + repair_instruction},
                    payload["messages"][1],
                ],
            }
            repaired_payload["response_format"] = {"type": "text"}
            await self.budget_manager.ensure_active()
            return await request(
                repaired_payload,
                max_retries=self.budget_manager.budget.max_retries_per_call - requests_started,
            )

    async def groq_text(
        self,
        model: str,
        prompt: str,
        system_instruction: str | None = None,
        role: ModelRole | None = None,
        profile_id: str | None = None,
    ) -> TextCallResult:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_completion_tokens": 1200,
            "reasoning_effort": "none",
        }
        return await self._with_retry(
            lambda: self._text_request(
                provider=ProviderName.GROQ,
                model=model,
                url="https://api.groq.com/openai/v1/chat/completions",
                api_key=self.settings.groq_api_key,
                payload=payload,
                role=role,
                profile_id=profile_id,
            )
        )

    async def _with_retry(self, operation_factory, *, max_retries: int | None = None):
        if max_retries is None:
            max_retries = self.budget_manager.budget.max_retries_per_call
        for attempt in range(max_retries + 1):
            try:
                result = await operation_factory()
                self._governor.record_success(result.metadata.provider)
                return result
            except ModelRequestError as error:
                limit = self.settings.max_provider_wait_seconds
                if limit is not None and error.retry_after_seconds is not None and error.retry_after_seconds > limit:
                    # Respect long Retry-After by stopping, not by retrying early
                    # or holding the console open until the campaign deadline.
                    error.retryable = False
                if limit is not None and attempt >= max_retries:
                    # The run's orchestrator, not DeepTeam's nested retry helper,
                    # owns the exhausted provider decision.
                    error.retryable = False
                if error.retryable:
                    self._governor.record_retry(error, attempt)
                if not error.retryable or attempt >= max_retries:
                    raise
                await self.budget_manager.ensure_active()
        raise RuntimeError("Retry loop exited unexpectedly.")

    async def openrouter_structured(
        self,
        model: str,
        prompt: str,
        schema: type[SchemaT],
        system_instruction: str | None = None,
        role: ModelRole | None = None,
        profile_id: str | None = None,
    ) -> ModelCallResult[SchemaT]:
        schema_instruction = (
            "Return one JSON object matching this schema exactly. Do not add "
            f"Markdown or prose outside the JSON object: {json.dumps(schema.model_json_schema())}"
        )
        system = (
            f"{system_instruction}\n{schema_instruction}"
            if system_instruction
            else schema_instruction
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 1200,
            "reasoning": {"enabled": False},
            "response_format": {"type": "json_object"},
            "provider": self._openrouter_provider_policy(),
        }
        if model == "nvidia/nemotron-3.5-super-vl:free":
            payload["response_format"] = _json_schema_response_format(schema)
        return await self._with_retry(
            lambda: self._structured_request(
                provider=ProviderName.OPENROUTER,
                model=model,
                schema=schema,
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=self.settings.openrouter_api_key,
                payload=payload,
                extra_headers={"X-OpenRouter-Title": "SecMate DeepTeam Worker"},
                role=role,
                profile_id=profile_id,
            )
        )

    async def openrouter_text(
        self,
        model: str,
        prompt: str,
        system_instruction: str | None = None,
        role: ModelRole | None = None,
        profile_id: str | None = None,
    ) -> TextCallResult:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 300,
            "reasoning": {"enabled": False},
            "provider": self._openrouter_provider_policy(),
        }
        return await self._with_retry(
            lambda: self._text_request(
                provider=ProviderName.OPENROUTER,
                model=model,
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=self.settings.openrouter_api_key,
                payload=payload,
                extra_headers={"X-OpenRouter-Title": "SecMate DeepTeam Worker"},
                role=role,
                profile_id=profile_id,
            )
        )

    async def openrouter_tool_turn(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        role: ModelRole | None = None,
        profile_id: str | None = None,
        max_output_tokens: int = 500,
        max_retries: int | None = None,
        strict_protocol: bool = False,
    ) -> ToolTurnResult:
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 500:
            raise ValueError("max_output_tokens must be between 1 and 500")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "reasoning": {"enabled": False},
            "tools": tools,
            "tool_choice": "auto",
            "provider": self._openrouter_provider_policy(),
        }
        if strict_protocol:
            payload["provider"]["allow_fallbacks"] = False
        return await self._with_retry(
            lambda: self._tool_request(
                model=model,
                payload=payload,
                role=role,
                profile_id=profile_id,
                strict_protocol=strict_protocol,
            ),
            max_retries=max_retries,
        )

    async def _tool_request(
        self,
        *,
        model: str,
        payload: dict[str, Any],
        role: ModelRole | None,
        profile_id: str | None,
        strict_protocol: bool = False,
    ) -> ToolTurnResult:
        provider = ProviderName.OPENROUTER
        reservation: ProviderCallReservation | None = None
        usage: TokenUsage | None = None
        status_code = None
        request_id = None
        latency_ms = 0
        finish_reason = None
        request_accounting = {
            "schema_version": "tool-request-accounting-v1",
            "reservation_requested": True, "reservation_accepted": False,
            "http_dispatched": False, "response_received": False,
        }
        try:
            reservation = await self._reserve_budget(provider, model, payload)
            request_accounting["reservation_accepted"] = True
            data, latency_ms, request_id, status_code = await self._post(
                provider=provider,
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=self.settings.openrouter_api_key,
                payload=payload,
                extra_headers={"X-OpenRouter-Title": "SecMate DeepTeam Worker"},
                include_http_status=True,
                request_accounting=request_accounting,
            )
            usage = _usage(data)
            choices = data.get("choices")
            if strict_protocol and data.get("model") != model:
                raise self._malformed_response(provider, latency_ms, request_id)
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            finish = choice.get("finish_reason")
            finish_reason = finish if isinstance(finish, str) and finish in {"stop", "length", "max_tokens", "tool_calls", "content_filter"} else None
            if strict_protocol and (not isinstance(choices, list) or len(choices) != 1 or finish_reason not in {"stop", "tool_calls"}):
                raise self._malformed_response(provider, latency_ms, request_id)
            message = self._completion_message(
                provider,
                data,
                latency_ms,
                request_id,
            )
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise self._malformed_response(provider, latency_ms, request_id)
            tool_calls: list[ProviderToolCall] = []
            raw_tool_calls = message.get("tool_calls", [])
            if raw_tool_calls is None:
                raw_tool_calls = []
            if not isinstance(raw_tool_calls, list):
                raise self._malformed_response(provider, latency_ms, request_id)
            seen_call_ids: set[str] = set()
            for raw_call in raw_tool_calls:
                if not isinstance(raw_call, dict):
                    raise self._malformed_response(provider, latency_ms, request_id)
                call_id = raw_call.get("id")
                function = raw_call.get("function")
                if (not isinstance(call_id, str) or not call_id.strip() or call_id in seen_call_ids
                        or raw_call.get("type") != "function" or not isinstance(function, dict)):
                    raise self._malformed_response(provider, latency_ms, request_id)
                name = function.get("name")
                if not isinstance(name, str) or not name.strip() or len(name) > 128 or len(call_id) > 128:
                    raise self._malformed_response(provider, latency_ms, request_id)
                raw_arguments = function.get("arguments")
                if not isinstance(raw_arguments, str) or not raw_arguments.strip():
                    raise self._malformed_response(provider, latency_ms, request_id)
                try:
                    arguments = json.loads(raw_arguments)
                except (TypeError, json.JSONDecodeError):
                    raise self._malformed_response(provider, latency_ms, request_id) from None
                if not isinstance(arguments, dict):
                    raise self._malformed_response(provider, latency_ms, request_id)
                seen_call_ids.add(call_id)
                tool_calls.append(
                    ProviderToolCall(
                        call_id=call_id,
                        name=name,
                        arguments=arguments,
                        replay=json.loads(json.dumps(raw_call)),
                    )
                )
            if not (content and content.strip()) and not tool_calls:
                raise self._malformed_response(provider, latency_ms, request_id)
            if strict_protocol and (len(content or "") > 32_000 or
                    (finish_reason == "tool_calls" and (not tool_calls or bool((content or "").strip()))) or
                    (finish_reason == "stop" and bool(tool_calls))):
                raise self._malformed_response(provider, latency_ms, request_id)
            metadata = ModelCallMetadata(
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                usage=usage,
                provider_request_id=request_id,
                role=role,
                profile_id=profile_id,
                finish_reason=finish_reason,
                response_characters=min(len(content), 2_000_000) if isinstance(content, str) else 0,
                output_limit_tokens=payload["max_tokens"],
                status_code=status_code,
                provider_generation_id=data.get("id") if isinstance(data.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", data["id"]) else None,
            )
            await self.budget_manager.ensure_active()
            budget_error = reservation.complete(usage, succeeded=True)
            reservation = None
            if budget_error is not None:
                raise self._budget_model_error(provider, budget_error)
            self._emit(
                ModelAttemptEvent(
                    provider=provider,
                    model=model,
                    outcome="SUCCESS",
                    latency_ms=latency_ms,
                    usage=usage,
                    provider_request_id=request_id,
                    role=role,
                    profile_id=profile_id,
                    finish_reason=finish_reason,
                    response_characters=metadata.response_characters,
                    output_limit_tokens=metadata.output_limit_tokens,
                    estimated_tokens=self._estimate_tokens(payload),
                    status_code=status_code,
                    request_accounting=dict(request_accounting),
                )
            )
            return ToolTurnResult(
                content=content,
                tool_calls=tool_calls,
                metadata=metadata,
            )
        except ModelClientError as error:
            error.request_accounting = dict(request_accounting)
            if error.code == ModelErrorCode.MALFORMED_RESPONSE:
                error.retryable = False
            error.usage = usage or getattr(error, "usage", None)
            error.estimated_tokens = self._estimate_tokens(payload) if reservation else None
            error.status_code = error.status_code or status_code
            error.provider_request_id = error.provider_request_id or request_id
            error.latency_ms = error.latency_ms or latency_ms
            error.finish_reason = finish_reason
            error.output_limit_tokens = payload["max_tokens"]
            usage = error.usage
            self._emit_failure(model, error, role, profile_id)
            raise
        except BudgetExceededError as error:
            wrapped = self._budget_model_error(provider, error)
            wrapped.request_accounting = dict(request_accounting)
            self._emit_failure(model, wrapped, role, profile_id)
            raise wrapped from None
        except asyncio.CancelledError:
            self._emit_cancelled(provider, model, role, profile_id, request_accounting=request_accounting)
            raise
        except Exception:
            wrapped = self._unexpected_error(provider)
            wrapped.request_accounting = dict(request_accounting)
            self._emit_failure(model, wrapped, role, profile_id)
            raise wrapped from None
        finally:
            if reservation is not None:
                reservation.complete(usage, succeeded=False)

    def _openrouter_provider_policy(self) -> dict[str, Any]:
        return {
            "require_parameters": True,
            "data_collection": (
                "allow"
                if self.settings.openrouter_allow_data_collection
                else "deny"
            ),
        }

    async def _structured_request(
        self,
        *,
        provider: ProviderName,
        model: str,
        schema: type[SchemaT],
        url: str,
        api_key: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
        role: ModelRole | None = None,
        profile_id: str | None = None,
    ) -> ModelCallResult[SchemaT]:
        reservation: ProviderCallReservation | None = None
        usage: TokenUsage | None = None
        safe_metadata = {"finish_reason": None, "response_characters": None,
                         "output_limit_tokens": payload.get("max_completion_tokens", payload.get("max_tokens")),
                         "response_format": payload.get("response_format", {}).get("type"),
                         "schema_name": schema.__name__,
                         "schema_sha256": hashlib.sha256(json.dumps(
                             payload.get("response_format", {}).get("json_schema", {}).get("schema", schema.model_json_schema()),
                             ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()}
        try:
            reservation = await self._reserve_budget(provider, model, payload)
            data, latency_ms, request_id = await self._post(
                provider=provider,
                url=url,
                api_key=api_key,
                payload=payload,
                extra_headers=extra_headers,
            )
            usage = _usage(data)
            choices = data.get("choices")
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            finish = choice.get("finish_reason")
            safe_metadata["finish_reason"] = finish if isinstance(finish, str) and finish in {"stop", "length", "max_tokens", "tool_calls", "content_filter"} else None
            message = choice.get("message")
            raw_content = message.get("content") if isinstance(message, dict) else None
            safe_metadata["response_characters"] = min(len(raw_content), 2_000_000) if isinstance(raw_content, str) else None
            content = self._completion_content(
                provider,
                data,
                latency_ms,
                request_id,
            )
            try:
                parsed = schema.model_validate_json(
                    content,
                    strict=True if provider == ProviderName.GROQ else None,
                    extra="forbid" if provider == ProviderName.GROQ else None,
                )
            except ValidationError as error:
                raise ModelRequestError(
                    f"{provider.value} returned content that did not match the requested schema.",
                    provider=provider,
                    code=ModelErrorCode.SCHEMA_VALIDATION,
                    retryable=False,
                    latency_ms=latency_ms,
                    provider_request_id=request_id,
                ) from None
            metadata = ModelCallMetadata(
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                usage=usage,
                provider_request_id=request_id,
                role=role,
                profile_id=profile_id,
                **safe_metadata,
            )
            await self.budget_manager.ensure_active()
            budget_error = reservation.complete(usage, succeeded=True)
            reservation = None
            if budget_error is not None:
                raise self._budget_model_error(provider, budget_error)
            self._emit(
                ModelAttemptEvent(
                    provider=provider,
                    model=model,
                    outcome="SUCCESS",
                    latency_ms=latency_ms,
                    usage=usage,
                    provider_request_id=request_id,
                    role=role,
                    profile_id=profile_id,
                    **safe_metadata,
                )
            )
            return ModelCallResult(output=parsed, metadata=metadata)
        except ModelClientError as error:
            for name, value in safe_metadata.items():
                setattr(error, name, value)
            error.usage = usage
            self._emit_failure(model, error, role, profile_id)
            raise
        except BudgetExceededError as error:
            wrapped = self._budget_model_error(provider, error)
            self._emit_failure(model, wrapped, role, profile_id)
            raise wrapped from None
        except asyncio.CancelledError:
            self._emit_cancelled(provider, model, role, profile_id)
            raise
        except Exception as error:
            wrapped = self._unexpected_error(provider)
            self._emit_failure(model, wrapped, role, profile_id)
            raise wrapped from None
        finally:
            if reservation is not None:
                reservation.complete(usage, succeeded=False)

    async def _text_request(
        self,
        *,
        provider: ProviderName,
        model: str,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
        role: ModelRole | None = None,
        profile_id: str | None = None,
    ) -> TextCallResult:
        reservation: ProviderCallReservation | None = None
        usage: TokenUsage | None = None
        try:
            reservation = await self._reserve_budget(provider, model, payload)
            data, latency_ms, request_id = await self._post(
                provider=provider,
                url=url,
                api_key=api_key,
                payload=payload,
                extra_headers=extra_headers,
            )
            usage = _usage(data)
            output = self._completion_content(
                provider,
                data,
                latency_ms,
                request_id,
            )
            metadata = ModelCallMetadata(
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                usage=usage,
                provider_request_id=request_id,
                role=role,
                profile_id=profile_id,
            )
            await self.budget_manager.ensure_active()
            budget_error = reservation.complete(usage, succeeded=True)
            reservation = None
            if budget_error is not None:
                raise self._budget_model_error(provider, budget_error)
            self._emit(
                ModelAttemptEvent(
                    provider=provider,
                    model=model,
                    outcome="SUCCESS",
                    latency_ms=latency_ms,
                    usage=usage,
                    provider_request_id=request_id,
                    role=role,
                    profile_id=profile_id,
                )
            )
            return TextCallResult(output=output, metadata=metadata)
        except ModelClientError as error:
            self._emit_failure(model, error, role, profile_id)
            raise
        except BudgetExceededError as error:
            wrapped = self._budget_model_error(provider, error)
            self._emit_failure(model, wrapped, role, profile_id)
            raise wrapped from None
        except asyncio.CancelledError:
            self._emit_cancelled(provider, model, role, profile_id)
            raise
        except Exception as error:
            wrapped = self._unexpected_error(provider)
            self._emit_failure(model, wrapped, role, profile_id)
            raise wrapped from None
        finally:
            if reservation is not None:
                reservation.complete(usage, succeeded=False)

    async def _reserve_budget(
        self,
        provider: ProviderName,
        model: str,
        payload: dict[str, Any],
    ) -> ProviderCallReservation:
        estimated_tokens = self._estimate_tokens(payload)
        try:
            return await self.budget_manager.reserve_provider_call(
                provider=provider,
                model=model,
                estimated_tokens=estimated_tokens,
            )
        except BudgetExceededError as error:
            raise self._budget_model_error(provider, error) from None

    @staticmethod
    def _estimate_tokens(payload: dict[str, Any]) -> int:
        serialized_payload = json.dumps(payload, ensure_ascii=True)
        # One conservative estimate for both reservation and pacing. ASCII-escaped
        # Unicode and a 3-character ratio add margin over the usual 4-character
        # heuristic; actual reported usage remains authoritative, not this estimate.
        estimated_prompt_tokens = (len(serialized_payload) + 2) // 3 + 64
        max_output_tokens = payload.get("max_completion_tokens") or payload.get(
            "max_tokens",
            0,
        )
        if not isinstance(max_output_tokens, int) or max_output_tokens < 0:
            max_output_tokens = 0
        return max(1, estimated_prompt_tokens + max_output_tokens)

    @staticmethod
    def _budget_model_error(
        provider: ProviderName,
        error: BudgetExceededError,
    ) -> ModelRequestError:
        code = ModelErrorCode.BUDGET_EXHAUSTED
        if error.code == BudgetErrorCode.CAMPAIGN_CANCELLED:
            code = ModelErrorCode.CAMPAIGN_CANCELLED
        elif error.code == BudgetErrorCode.DEADLINE_EXCEEDED:
            code = ModelErrorCode.DEADLINE_EXCEEDED
        wrapped = ModelRequestError(
            str(error),
            provider=provider,
            code=code,
            retryable=False,
        )
        # Preserve the trusted budget enum for consumers requiring finer bounded
        # diagnostics without parsing potentially sensitive exception text.
        wrapped.budget_error_code = error.code.value
        return wrapped

    async def _post(
        self,
        *,
        provider: ProviderName,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
        include_http_status: bool = False,
        request_accounting: dict[str, Any] | None = None,
    ) -> tuple:
        if not api_key:
            raise ModelConfigurationError(
                f"{provider.value} API key is not configured.",
                provider=provider,
                code=ModelErrorCode.CONFIGURATION,
                retryable=False,
            )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(extra_headers or {}),
        }
        started = time.perf_counter()
        try:
            client = self._client_for(provider)
            async def authorized_post():
                from .job_runtime import require_permission
                require_permission()
                if request_accounting is not None:
                    request_accounting["http_dispatched"] = True
                response = await client.post(url, headers=headers, json=payload)
                if request_accounting is not None:
                    request_accounting["response_received"] = True
                return response
            response = await self._governor.execute(
                provider,
                self._estimate_governor_tokens(payload),
                authorized_post,
            )
        except httpx.ConnectTimeout as error:
            raise self._transport_error(
                provider,
                ModelErrorCode.CONNECT_TIMEOUT,
                started,
            ) from None
        except httpx.ReadTimeout as error:
            raise self._transport_error(
                provider,
                ModelErrorCode.READ_TIMEOUT,
                started,
            ) from None
        except httpx.WriteTimeout as error:
            raise self._transport_error(
                provider,
                ModelErrorCode.WRITE_TIMEOUT,
                started,
            ) from None
        except httpx.PoolTimeout as error:
            raise self._transport_error(
                provider,
                ModelErrorCode.POOL_TIMEOUT,
                started,
            ) from None
        except httpx.TimeoutException as error:
            raise self._transport_error(
                provider,
                ModelErrorCode.NETWORK_ERROR,
                started,
            ) from None
        except httpx.HTTPError as error:
            raise self._transport_error(
                provider,
                ModelErrorCode.NETWORK_ERROR,
                started,
            ) from None

        latency_ms = round((time.perf_counter() - started) * 1000)
        request_id = response.headers.get("x-request-id") or response.headers.get(
            "cf-ray"
        )
        request_id = request_id if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", request_id) else None
        self._governor.observe_limits(provider, response.headers)
        if not response.is_success:
            code, retryable = self._http_error_policy(provider, response.status_code)
            subtype = _safe_provider_error(response)
            if response.status_code == 400 and subtype.get("provider_error_code") == "json_validate_failed":
                code, retryable = ModelErrorCode.INVALID_JSON, False
            elif response.status_code in {400, 404} and subtype.get("provider_error_code") in {"model_not_found", "model_decommissioned"}:
                code, retryable = ModelErrorCode.ROUTE_UNAVAILABLE, False
            details = ", ".join(f"error.{name.removeprefix('provider_error_')}={value}" for name, value in subtype.items())
            failure = ModelRequestError(
                f"{provider.value} request failed with HTTP {response.status_code}." + (f" {details}" if details else ""),
                provider=provider,
                code=code,
                retryable=retryable,
                status_code=response.status_code,
                latency_ms=latency_ms,
                provider_request_id=request_id,
                retry_after_seconds=self._retry_after_seconds(response),
                **subtype,
            )
            try:
                document = response.json()
                failure.usage = _usage(document) if isinstance(document, dict) else None
            except ValueError:
                failure.usage = None
            raise failure from None
        try:
            data = response.json()
        except ValueError as error:
            raise ModelRequestError(
                f"{provider.value} returned invalid JSON.",
                provider=provider,
                code=ModelErrorCode.INVALID_JSON,
                retryable=True,
                status_code=response.status_code,
                latency_ms=latency_ms,
                provider_request_id=request_id,
            ) from None
        if not isinstance(data, dict):
            raise ModelRequestError(
                f"{provider.value} returned an invalid response object.",
                provider=provider,
                code=ModelErrorCode.MALFORMED_RESPONSE,
                retryable=True,
                status_code=response.status_code,
                latency_ms=latency_ms,
                provider_request_id=request_id,
            )
        result = (data, latency_ms, request_id)
        return (*result, response.status_code) if include_http_status else result

    def _client_for(self, provider: ProviderName) -> httpx.AsyncClient:
        if self._closed:
            raise ModelConfigurationError(
                "Provider clients are closed.",
                provider=provider,
                code=ModelErrorCode.CONFIGURATION,
                retryable=False,
            )
        client = self._http_clients.get(provider)
        if client is None:
            client = self._client_factory(
                timeout=self.timeout,
                transport=self.transport,
            )
            self._http_clients[provider] = client
        return client

    @staticmethod
    def _estimate_governor_tokens(payload: dict[str, Any]) -> int:
        return StructuredModelClients._estimate_tokens(payload)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0, float(value.strip().removesuffix("s")))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())

    def _http_error_policy(
        self,
        provider: ProviderName,
        status_code: int,
    ) -> tuple[ModelErrorCode, bool]:
        if status_code == 401:
            return ModelErrorCode.AUTHENTICATION, False
        if status_code == 403:
            return ModelErrorCode.REQUEST_REJECTED, False
        if status_code == 404 and provider == ProviderName.OPENROUTER:
            return ModelErrorCode.ROUTE_UNAVAILABLE, False
        if status_code == 429:
            return ModelErrorCode.RATE_LIMITED, True
        if status_code == 408:
            return ModelErrorCode.REQUEST_TIMEOUT, True
        if status_code in {500, 502, 503, 504}:
            return ModelErrorCode.PROVIDER_UNAVAILABLE, True
        return ModelErrorCode.REQUEST_REJECTED, False

    @staticmethod
    def _transport_error(
        provider: ProviderName,
        code: ModelErrorCode,
        started: float,
    ) -> ModelRequestError:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return ModelRequestError(
            f"{provider.value} request failed with {code.value}.",
            provider=provider,
            code=code,
            retryable=True,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _unexpected_error(provider: ProviderName) -> ModelRequestError:
        return ModelRequestError(
            f"{provider.value} model processing failed unexpectedly.",
            provider=provider,
            code=ModelErrorCode.UNEXPECTED_ERROR,
            retryable=False,
        )

    @staticmethod
    def _completion_content(
        provider: ProviderName,
        data: dict[str, Any],
        latency_ms: int,
        request_id: str | None,
    ) -> str:
        message = StructuredModelClients._completion_message(
            provider,
            data,
            latency_ms,
            request_id,
        )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ModelRequestError(
                f"{provider.value} returned no text content.",
                provider=provider,
                code=ModelErrorCode.MALFORMED_RESPONSE,
                retryable=False,
                latency_ms=latency_ms,
                provider_request_id=request_id,
            )
        return content

    @staticmethod
    def _completion_message(
        provider: ProviderName,
        data: dict[str, Any],
        latency_ms: int,
        request_id: str | None,
    ) -> dict[str, Any]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise StructuredModelClients._malformed_response(
                provider,
                latency_ms,
                request_id,
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise StructuredModelClients._malformed_response(
                provider,
                latency_ms,
                request_id,
            )
        if choice.get("finish_reason") in {"length", "max_tokens"}:
            # Even valid JSON can contain a string the constrained decoder closed
            # prematurely. Never persist it as a successful complete observation.
            raise ModelRequestError(
                f"{provider.value} cut off the completion at its output limit.",
                provider=provider, code=ModelErrorCode.MALFORMED_RESPONSE,
                retryable=False, latency_ms=latency_ms, provider_request_id=request_id,
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise StructuredModelClients._malformed_response(
                provider,
                latency_ms,
                request_id,
            )
        return message

    @staticmethod
    def _malformed_response(
        provider: ProviderName,
        latency_ms: int,
        request_id: str | None,
    ) -> ModelRequestError:
        return ModelRequestError(
            f"{provider.value} returned a malformed completion.",
            provider=provider,
            code=ModelErrorCode.MALFORMED_RESPONSE,
            retryable=True,
            latency_ms=latency_ms,
            provider_request_id=request_id,
        )

    def _emit_failure(
        self,
        model: str,
        error: ModelClientError,
        role: ModelRole | None,
        profile_id: str | None,
    ) -> None:
        self._emit(
            ModelAttemptEvent(
                provider=error.provider,
                model=model,
                outcome="FAILURE",
                latency_ms=error.latency_ms,
                error_code=error.code,
                retryable=error.retryable,
                status_code=error.status_code,
                provider_request_id=error.provider_request_id,
                role=role,
                profile_id=profile_id,
                provider_error_code=error.provider_error_code,
                provider_error_type=error.provider_error_type,
                provider_error_param=error.provider_error_param,
                usage=getattr(error, "usage", None),
                finish_reason=error.finish_reason,
                response_characters=error.response_characters,
                output_limit_tokens=error.output_limit_tokens,
                response_format=error.response_format,
                schema_name=error.schema_name,
                schema_sha256=error.schema_sha256,
                estimated_tokens=getattr(error, "estimated_tokens", None),
                request_accounting=getattr(error, "request_accounting", None),
            )
        )

    def _emit_cancelled(
        self,
        provider: ProviderName,
        model: str,
        role: ModelRole | None,
        profile_id: str | None,
        *, request_accounting: dict[str, Any] | None = None,
    ) -> None:
        self._emit(
            ModelAttemptEvent(
                provider=provider,
                model=model,
                outcome="FAILURE",
                latency_ms=0,
                error_code=ModelErrorCode.CANCELLED,
                retryable=False,
                role=role,
                profile_id=profile_id,
                request_accounting=dict(request_accounting) if request_accounting is not None else None,
            )
        )

    def _emit(self, event: ModelAttemptEvent) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event)
        except Exception:
            # Diagnostics must never convert a completed provider call into a retry.
            return
