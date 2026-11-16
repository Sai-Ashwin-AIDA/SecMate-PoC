"""Strict translation between accepted synthetic requests and OpenRouter turns."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Literal
from dataclasses import replace
import re

from ...job_runtime import canonical
from ...model_clients import ProviderToolCall, StructuredModelClients, ToolTurnResult
from ...model_profiles import OPENROUTER_NEMOTRON_TARGET
from .onboarding import load_execution_profile
from .model_interface import TOOL_DESCRIPTIONS, annotate_parameters


ADAPTER_VERSION = "0.5.1"
OUTPUT_TOKEN_LIMIT = load_execution_profile()["budgets"]["output_token_limit"]


def provider_name(canonical_name: str) -> str:
    # OpenAI-compatible function names use letters, digits, '_' and '-'.
    # This transport projection never changes the host registry or its schemas.
    name = canonical_name.replace(".", "__")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ModelProtocolError("invalid_provider_tool_name")
    return name


class ModelProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class AcceptedTurn:
    kind: Literal["tool_call", "final"]
    content: str | None
    calls: tuple[ProviderToolCall, ...]
    metadata: dict[str, Any]
    rendered_payload: dict[str, Any]


class Phase5ModelAdapter:
    """Reusable protocol adapter; demo turn/read limits remain in the runtime."""

    def __init__(self, clients: StructuredModelClients):
        self.clients = clients

    @staticmethod
    def _provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Remove unreachable local definitions without changing the schema."""
        value = json.loads(canonical(schema))
        definitions = value.pop("$defs", None)
        if not isinstance(definitions, dict):
            return value
        # Tool parameters must visibly be an object for OpenAI-compatible routes.
        # Resolve only the root reference; retain nested definitions and constraints.
        root_ref = value.get("$ref")
        if root_ref is not None:
            if not isinstance(root_ref, str) or not root_ref.startswith("#/$defs/") or root_ref[8:] not in definitions:
                raise ModelProtocolError("unresolved_tool_schema")
            root = definitions[root_ref[8:]]
            siblings = {key: child for key, child in value.items() if key not in {"$ref", "$id", "$schema"}}
            value = {**root, **siblings} if not siblings else {"allOf": [root, siblings]}
        needed: set[str] = set()

        def references(node):
            if isinstance(node, dict):
                ref = node.get("$ref")
                if isinstance(ref, str) and ref.startswith("#/$defs/"):
                    needed.add(ref.rsplit("/", 1)[1])
                for child in node.values():
                    references(child)
            elif isinstance(node, list):
                for child in node:
                    references(child)

        references(value)
        scanned: set[str] = set()
        while needed - scanned:
            name = next(iter(needed - scanned))
            if name not in definitions:
                raise ModelProtocolError("unresolved_tool_schema")
            scanned.add(name)
            references(definitions[name])
        value["$defs"] = {name: definitions[name] for name in definitions if name in needed}
        return value

    @staticmethod
    def render(request: dict[str, Any], replay: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not isinstance(request.get("instructions"), str) or not request["instructions"].strip():
            raise ModelProtocolError("invalid_instructions")
        messages: list[dict[str, Any]] = [{"role": "system", "content": request["instructions"]}]
        for item in request.get("items", []):
            if not isinstance(item, dict):
                raise ModelProtocolError("invalid_request_item")
            role = item.get("role")
            if role in {"developer", "user", "assistant"} and isinstance(item.get("content"), str):
                messages.append({"role": role, "content": item["content"]})
            elif item.get("type") in {"function_call", "function_call_output"}:
                continue
            else:
                raise ModelProtocolError("unsupported_request_item")
        history = request.get("trusted_conversation_history", [])
        if history:
            if (
                not isinstance(history, list)
                or len(history) > 6
                or any(
                    not isinstance(item, dict)
                    or set(item) != {"role", "content"}
                    or item["role"] != ("user" if index % 2 == 0 else "assistant")
                    or not isinstance(item["content"], str)
                    or not item["content"].strip()
                    for index, item in enumerate(history)
                )
                or history[-1]["role"] != "assistant"
            ):
                raise ModelProtocolError("invalid_trusted_conversation_history")
            current_user = max(
                (index for index, message in enumerate(messages) if message["role"] == "user"),
                default=-1,
            )
            if current_user < 0:
                raise ModelProtocolError("missing_current_user_prompt")
            messages[current_user:current_user] = history
        tools = []
        for tool in request.get("tools", []):
            if not isinstance(tool, dict) or set(tool) != {"type", "name", "parameters"} or tool.get("type") != "function":
                raise ModelProtocolError("invalid_tool_schema")
            tools.append({"type": "function", "function": {
                "name": provider_name(tool["name"]),
                "description": TOOL_DESCRIPTIONS.get(tool["name"], "Use this registered tool with exactly typed JSON arguments."),
                "parameters": annotate_parameters(tool["name"], Phase5ModelAdapter._provider_schema(tool["parameters"])),
            }})
        for item in replay or []:
            if not isinstance(item, dict):
                raise ModelProtocolError("invalid_replay")
            call, output = item.get("call"), item.get("output")
            if not isinstance(call, dict) or not isinstance(call.get("id"), str) or not call["id"].strip() or not isinstance(output, dict):
                raise ModelProtocolError("invalid_replay")
            messages.extend([
                {"role": "assistant", "content": None, "tool_calls": [call]},
                {"role": "tool", "tool_call_id": call["id"], "content": canonical(output)},
            ])
        return messages, tools

    async def turn(
        self,
        request: dict[str, Any],
        *,
        timeout_seconds: float,
        replay: list[dict[str, Any]] | None = None,
    ) -> AcceptedTurn:
        messages, tools = self.render(request, replay)
        rendered = {
            "model": OPENROUTER_NEMOTRON_TARGET.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": OUTPUT_TOKEN_LIMIT,
            "reasoning": {"enabled": False},
            "tools": tools,
            "tool_choice": "auto",
            "provider": {**self.clients._openrouter_provider_policy(), "allow_fallbacks": False},
        }
        try:
            result: ToolTurnResult = await asyncio.wait_for(
                self.clients.openrouter_tool_turn(
                    OPENROUTER_NEMOTRON_TARGET.model,
                    messages,
                    tools,
                    role=OPENROUTER_NEMOTRON_TARGET.role,
                    profile_id=OPENROUTER_NEMOTRON_TARGET.profile_id,
                    max_output_tokens=OUTPUT_TOKEN_LIMIT,
                    max_retries=0,
                    strict_protocol=True,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise ModelProtocolError("model_timeout") from None
        names = {provider_name(tool["name"]): tool["name"] for tool in request["tools"]}
        if len(names) != len(request["tools"]):
            raise ModelProtocolError("tool_alias_collision")
        if any(call.name not in names for call in result.tool_calls):
            raise ModelProtocolError("unknown_tool")
        result = replace(result, tool_calls=[replace(call, name=names[call.name]) for call in result.tool_calls])
        return self._accept(result, rendered=rendered)

    @staticmethod
    def _accept(result: ToolTurnResult, *, rendered: dict[str, Any]) -> AcceptedTurn:
        finish = result.metadata.finish_reason
        content = result.content.strip() if isinstance(result.content, str) else None
        calls = tuple(result.tool_calls)
        if finish in {None, "length", "max_tokens", "content_filter"}:
            raise ModelProtocolError("incomplete_model_response")
        if finish == "tool_calls":
            if content or not calls:
                raise ModelProtocolError("invalid_tool_turn")
            if any(len(call.call_id) > 128 for call in calls):
                raise ModelProtocolError("invalid_tool_call_id")
            kind = "tool_call"
        elif finish != "stop" or not content or calls:
            raise ModelProtocolError("invalid_final_turn")
        else:
            kind = "final"
        metadata = {
            "provider": result.metadata.provider.value,
            "model": result.metadata.model,
            "profile_id": result.metadata.profile_id,
            "role": result.metadata.role.value if result.metadata.role else None,
            "provider_request_id": result.metadata.provider_request_id,
            "latency_ms": result.metadata.latency_ms,
            "finish_reason": finish,
            "response_characters": result.metadata.response_characters,
            "output_limit_tokens": result.metadata.output_limit_tokens,
            "usage": result.metadata.usage.model_dump() if result.metadata.usage else None,
        }
        return AcceptedTurn(kind, content, calls, metadata, rendered)
