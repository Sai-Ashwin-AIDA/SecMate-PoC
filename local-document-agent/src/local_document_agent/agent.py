"""Bounded explicit LangChain tool loop, independent of terminal input/output."""

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langsmith import tracing_context

from .config import Configuration, reject_tracing
from .context import Source, SourceLedger, ToolContext
from .contracts import CreateData, DocumentError, ToolResult
from .diagnostics import DiagnosticLog
from .filesystem import FilesystemRoots
from .prompts import SYSTEM_PROMPT
from .provider import ProviderFailure, provider_failure
from .tools import build_tools


@dataclass(frozen=True)
class ToolActivity:
    name: str
    status: str
    summary: str


@dataclass(frozen=True)
class TurnResult:
    session_id: str
    status: Literal["completed", "failed", "limited", "cancelled"]
    answer: str = ""
    sources: tuple[Source, ...] = ()
    retained_sources: tuple[Source, ...] = ()
    created_files: tuple[CreateData, ...] = ()
    uncertain_outputs: tuple[str, ...] = ()
    tool_events: tuple[ToolActivity, ...] = ()
    unverified_source_ids: tuple[str, ...] = ()
    error: ProviderFailure | None = None


@dataclass
class CompletedTurn:
    messages: tuple[BaseMessage, ...]
    source_ids: tuple[str, ...]


class StopTurn(Exception):
    def __init__(self, code: str, message: str, *, status: str = "limited") -> None:
        self.failure = ProviderFailure(code, message)
        self.status = status


def estimate_units(messages: list[BaseMessage], schemas: list[dict[str, Any]]) -> int:
    """Conservative UTF-8 serialized-byte units, not exact model tokens."""
    encoded = json.dumps(
        {"messages": [message.model_dump(mode="json") for message in messages], "tools": schemas},
        ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")
    return len(encoded) + 512 * len(messages)


def answer_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        block["text"] for block in message.content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )


class DocumentAssistant:
    """A model is explicitly injected; production construction belongs to the CLI."""

    def __init__(
        self, configuration: Configuration, model: Any, *,
        roots: FilesystemRoots | None = None,
        observer: Callable[[ToolActivity], None] | None = None,
        diagnostics: DiagnosticLog | None = None,
    ) -> None:
        self.configuration = configuration
        self.roots = roots or FilesystemRoots(configuration.input_dir, configuration.output_dir)
        self.model = model
        self.observer = observer
        self.diagnostics = diagnostics
        self._active = False
        self._history: list[CompletedTurn] = []
        self.new_session()

    def new_session(self) -> str:
        if self._active:
            raise RuntimeError("Cannot reset an active turn.")
        self.session_id = uuid.uuid4().hex
        self._history.clear()
        capacity = max(1, (self.configuration.max_history_turns + 1) * self.configuration.max_tool_calls_per_turn)
        self.ledger = SourceLedger(capacity=capacity)
        return self.session_id

    def _drop_oldest(self) -> None:
        self.ledger.discard(list(self._history.pop(0).source_ids))

    def _messages(self, active: list[BaseMessage], schemas: list[dict[str, Any]]) -> list[BaseMessage]:
        while True:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                *(message for turn in self._history for message in turn.messages),
                *active,
            ]
            size = estimate_units(messages, schemas) + self.configuration.max_output_tokens
            if size <= self.configuration.context_budget_units:
                return messages
            if not self._history:
                raise StopTurn("CONTEXT_LIMIT", "The active turn exceeds the context budget; narrow the task or start /new.")
            self._drop_oldest()

    async def chat(self, message: str) -> TurnResult:
        if self._active:
            if self.diagnostics:
                self.diagnostics.record("turn", "BUSY", session_id=self.session_id)
            return TurnResult(
                self.session_id, "failed",
                error=ProviderFailure("BUSY", "This conversation already has an active turn."),
            )
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            if self.diagnostics:
                self.diagnostics.record("turn", "INVALID_INPUT", session_id=self.session_id)
            return TurnResult(
                self.session_id, "failed",
                error=ProviderFailure("INVALID_INPUT", "Enter 1–4000 characters of nonblank text."),
            )
        try:
            message.encode("utf-8", errors="strict")
            reject_tracing(os.environ)
        except (ValueError, UnicodeError):
            if self.diagnostics:
                self.diagnostics.record("turn", "CONFIGURATION_ERROR", session_id=self.session_id)
            return TurnResult(
                self.session_id, "failed",
                error=ProviderFailure("CONFIGURATION_ERROR", "Valid UTF-8 input and disabled tracing are required."),
            )
        while len(self._history) > self.configuration.max_history_turns:
            self._drop_oldest()
        self._active = True
        context = ToolContext(ledger=self.ledger, deadline=time.monotonic() + self.configuration.turn_timeout_seconds)
        active: list[BaseMessage] = [HumanMessage(content=message)]
        events: list[ToolActivity] = []
        available_sources: dict[str, Source] = {}
        before = {source.source_id for source in self.ledger.snapshot()}
        answer = ""
        status = "completed"
        error = None
        diagnostic_exception = None
        try:
            with tracing_context(enabled=False):
                async with asyncio.timeout(self.configuration.turn_timeout_seconds):
                    answer = await self._loop(context, active, events, available_sources)
        except StopTurn as stopped:
            status, error = stopped.status, stopped.failure
        except asyncio.CancelledError as stopped:
            status = "cancelled"
            diagnostic_exception = stopped
            error = ProviderFailure("CANCELLED", "Turn cancelled; the incomplete conversation was not retained.")
        except TimeoutError as stopped:
            status = "limited"
            diagnostic_exception = stopped
            error = ProviderFailure("TURN_TIMEOUT", "The turn deadline expired; the incomplete conversation was not retained.")
        except DocumentError as stopped:
            status = "limited"
            diagnostic_exception = stopped
            error = ProviderFailure(stopped.error.code, stopped.error.message)
        except Exception as stopped:
            status, error = "failed", provider_failure(stopped)
            diagnostic_exception = stopped
        finally:
            self._active = False
        if error is not None and self.diagnostics:
            self.diagnostics.record("turn", error.code, session_id=self.session_id, exception=diagnostic_exception)
        introduced = tuple(source for source in self.ledger.snapshot() if source.source_id not in before)
        if status == "completed":
            self._history.append(CompletedTurn(tuple(active), tuple(source.source_id for source in introduced)))
            while len(self._history) > self.configuration.max_history_turns:
                self._drop_oldest()
        else:
            self.ledger.discard([source.source_id for source in introduced])
        introduced_ids = {source.source_id for source in introduced}
        cited_ids = set(re.findall(r"\[(R[1-9][0-9]*)\]", answer))
        used_ids = cited_ids | {identifier for item in context.created for identifier in item.source_ids}
        valid_ids = set(available_sources) | introduced_ids
        invented = tuple(sorted(cited_ids - valid_ids))
        return TurnResult(
            session_id=self.session_id, status=status, answer=answer, sources=introduced,
            retained_sources=tuple(
                source for identifier, source in available_sources.items()
                if identifier in used_ids and identifier not in introduced_ids
            ),
            created_files=tuple(context.created), uncertain_outputs=tuple(context.uncertain_outputs),
            tool_events=tuple(events), unverified_source_ids=invented, error=error,
        )

    async def _loop(
        self, context: ToolContext, active: list[BaseMessage], events: list[ToolActivity],
        available_sources: dict[str, Source],
    ) -> str:
        tools = {item.name: item for item in build_tools(self.roots, context)}
        schemas = [convert_to_openai_tool(item) for item in tools.values()]
        bound = self.model.bind_tools(list(tools.values()), tool_choice="auto")
        seen_ids: set[str] = set()
        failed_calls: set[str] = set()
        tool_calls = 0
        charged = 0
        for _ in range(self.configuration.max_model_calls_per_turn):
            context.check_deadline()
            messages = self._messages(active, schemas)
            available_sources.update({source.source_id: source for source in self.ledger.snapshot()})
            reservation = estimate_units(messages, schemas) + self.configuration.max_output_tokens
            if charged + reservation > self.configuration.max_turn_token_budget:
                raise StopTurn("TOKEN_LIMIT", "The turn token budget is exhausted; narrow the task.")
            context.check_deadline()
            remaining = max(1, int((context.deadline - time.monotonic()) * 1000))
            timeout_ms = min(self.configuration.request_timeout_seconds * 1000, remaining)
            try:
                async with asyncio.timeout(timeout_ms / 1000):
                    response = await bound.ainvoke(messages, retries=None, timeout_ms=timeout_ms)
            except TimeoutError:
                raise StopTurn("REQUEST_TIMEOUT", "The inference request timed out; no retry was made.", status="failed") from None
            if not isinstance(response, AIMessage) or response.invalid_tool_calls:
                raise StopTurn("PROVIDER_PROTOCOL_ERROR", "The provider returned an invalid tool-call response.", status="failed")
            if response.response_metadata.get("finish_reason") in ("length", "max_tokens"):
                raise StopTurn("OUTPUT_LIMIT", "Model output was truncated; no incomplete tool call was executed.")
            usage = response.usage_metadata or {}
            total = usage.get("total_tokens")
            charged += total if type(total) is int and total >= 0 else reservation
            if charged > self.configuration.max_turn_token_budget:
                raise StopTurn("TOKEN_LIMIT", "The turn token budget was exhausted.")
            active.append(response)
            # Check response size before any filesystem side effect.
            self._messages(active, schemas)
            if not response.tool_calls:
                answer = answer_text(response)
                if not answer.strip():
                    raise StopTurn("PROVIDER_PROTOCOL_ERROR", "The provider returned no usable answer.", status="failed")
                return answer
            calls = response.tool_calls
            if tool_calls + len(calls) > self.configuration.max_tool_calls_per_turn:
                raise StopTurn("TOOL_LIMIT", "The turn tool-call budget is exhausted; no oversized batch was executed.")
            batch_ids: set[str] = set()
            for call in calls:
                identifier, name, args = call.get("id"), call.get("name"), call.get("args")
                if (
                    not isinstance(identifier, str) or not 1 <= len(identifier) <= 128
                    or identifier in seen_ids or identifier in batch_ids
                    or not isinstance(name, str) or not 1 <= len(name) <= 128
                    or not isinstance(args, dict)
                ):
                    raise StopTurn("PROVIDER_PROTOCOL_ERROR", "Tool calls have invalid or repeated IDs/structure.", status="failed")
                batch_ids.add(identifier)
            seen_ids.update(batch_ids)
            for call in calls:
                context.check_deadline()
                tool_calls += 1
                name = call["name"]
                signature = json.dumps({"name": name, "args": call["args"]}, sort_keys=True, ensure_ascii=True)
                if signature in failed_calls:
                    raise StopTurn("REPEATED_FAILURE", "The same failed tool call was repeated; stopping without retry.")
                if name not in tools:
                    result = ToolMessage(
                        content=json.dumps({
                            "ok": False, "tool": name, "data": None, "warnings": [],
                            "error": {"code": "UNKNOWN_TOOL", "message": "Only search_documents, read_document, and create_document are available."},
                        }),
                        name=name, tool_call_id=call["id"], status="error",
                    )
                    data = None
                    summary = "UNKNOWN_TOOL"
                else:
                    result = tools[name].invoke({**call, "type": "tool_call"})
                    envelope = ToolResult.model_validate_json(result.content)
                    data = envelope.data
                    summary = envelope.error.code if envelope.error else self._summary(name, data)
                active.append(result)
                if result.status == "error":
                    failed_calls.add(signature)
                    if self.diagnostics:
                        self.diagnostics.record("tool", summary, session_id=self.session_id, tool=name)
                activity = ToolActivity(name, result.status, summary)
                events.append(activity)
                if self.observer is not None:
                    try:
                        self.observer(activity)
                    except Exception as observer_error:
                        # Presentation failure cannot retry or undo a completed write.
                        if self.diagnostics:
                            self.diagnostics.record(
                                "cli", "ACTIVITY_RENDER_ERROR", session_id=self.session_id,
                                exception=observer_error,
                            )
                        self.observer = None
        raise StopTurn("MODEL_LIMIT", "The turn model-call budget is exhausted; no additional request was made.")

    @staticmethod
    def _summary(name: str, data: Any) -> str:
        if name == "search_documents":
            return f"{data.returned} match(es)" + ("; partial search" if data.partial else "")
        if name == "read_document":
            return f"input/{data.path}: lines {data.start_line}–{data.end_line}"
        return f"output/{data.path}: created" + ("; draft not sent" if data.not_sent else "")
