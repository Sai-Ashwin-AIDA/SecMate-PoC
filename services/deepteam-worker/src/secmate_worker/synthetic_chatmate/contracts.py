"""Strict Phase 0–1 projections. Native external schemas remain unknown."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from ..job_runtime import canonical

TARGET_ID = "secmate.synthetic-chatmate.fresh.v1"
TARGET_VERSION = "0.1.1"
READ_TOOL = "secmate.conversation.history.read"
SOURCE_REVISION = "9335db39cd92f98cbefb91ffb98bb995fe32048b"
MAPPER_BLOB = "559bf61ace74094996df9a871dd276569a7a7aa9"
MANIFESTO_BLOB = "518b848480a43f8e7d17838c6f7136cd1d903765"


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def clone(value):
    return json.loads(canonical(value))


class SyntheticError(RuntimeError):
    def __init__(self, code: str, run_id: str | None = None):
        super().__init__(code)
        self.code, self.run_id = code, run_id


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MessageCreate(StrictModel):
    content: Annotated[StrictStr, Field(min_length=1, max_length=8000)]

    @field_validator("content", mode="before")
    @classmethod
    def bounded_content(cls, value):
        return value.strip() if isinstance(value, str) else value


class ConversationRead(StrictModel):
    message_id: Annotated[StrictStr, Field(min_length=1, max_length=128)] | None
    offset: Annotated[StrictInt, Field(ge=0)]


class ToolCall(StrictModel):
    call_id: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    name: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    arguments: StrictStr


class ScriptRound(StrictModel):
    text: StrictStr
    # Invalid calls are deliberately admitted to the adapter's *input* in negative
    # conformance scenarios, then rejected at the runtime protocol boundary.
    calls: list[dict]
    completion: StrictBool
    error: Literal["model_timeout", "model_transport_unavailable", "model_failed"] | None


class Script(StrictModel):
    rounds: list[ScriptRound]


class Budget(StrictModel):
    profile_id: StrictStr = "slice-small-0.1.1"
    rounds: Annotated[StrictInt, Field(ge=1, le=24)] = 4
    calls_per_round: Annotated[StrictInt, Field(ge=1, le=8)] = 2
    execution: Annotated[StrictInt, Field(ge=1, le=24)] = 4
    output_characters: Annotated[StrictInt, Field(ge=1, le=32000)] = 32000
    context_characters: Annotated[StrictInt, Field(ge=1, le=240000)] = 240000
    run_seconds: Annotated[StrictInt, Field(ge=1, le=1800)] = 60
    model_seconds: Annotated[StrictInt, Field(ge=1, le=60)] = 20
    tool_seconds: Annotated[StrictInt, Field(ge=1, le=60)] = 5
    retries: Literal[1] = 1
    retry_delay: Literal[1] = 1
    parallel_reads: Literal[1] = 1
    partial_summary: Literal[False] = False


class ModelFault(StrictModel):
    round: Annotated[StrictInt, Field(ge=1)]
    attempt: Annotated[StrictInt, Field(ge=1, le=2)] = 1
    duration: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    error: Literal["model_timeout", "model_transport_unavailable", "model_failed"] | None = None
    after_output: StrictBool = False


class ToolFault(StrictModel):
    call_id: StrictStr
    duration: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    error: Literal["tool_failed", "tool_timeout"] | None = None
    halt: StrictBool = False


class FaultPlan(StrictModel):
    model: list[ModelFault] = Field(default_factory=list)
    tools: list[ToolFault] = Field(default_factory=list)
    cancel_at: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    enqueue_failure: StrictBool = False

    @field_validator("model", "tools")
    @classmethod
    def unique_faults(cls, value):
        keys = [(v.round, v.attempt) if isinstance(v, ModelFault) else v.call_id for v in value]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_fault")
        return value


class SourceRef(StrictModel):
    resource_id: StrictStr
    source_kind: Literal["conversation_snapshot"]
    content_digest: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class ListedMessage(StrictModel):
    message_id: StrictStr
    role: Literal["user", "assistant"]


class Listing(StrictModel):
    kind: Literal["listing"]
    messages: list[ListedMessage]
    offset: Annotated[StrictInt, Field(ge=0)]
    next_offset: Annotated[StrictInt, Field(ge=0)] | None
    truncated: StrictBool
    source_ref: SourceRef


class MessagePage(StrictModel):
    kind: Literal["message"]
    message_id: StrictStr
    role: Literal["user", "assistant"]
    content: StrictStr
    offset: Annotated[StrictInt, Field(ge=0)]
    next_offset: Annotated[StrictInt, Field(ge=0)] | None
    truncated: StrictBool
    files: list = Field(max_length=0)
    source_ref: SourceRef


class ErrorOutput(StrictModel):
    error: StrictStr
    message: Annotated[StrictStr, Field(max_length=240)] | None = None
    field: Annotated[StrictStr, Field(max_length=128)] | None = None


class ToolResult(StrictModel):
    call_id: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    status: Literal["ok", "error", "staged", "interrupt"]
    output: dict
    source_refs: list[SourceRef]


class EvidenceEvent(StrictModel):
    event_schema_version: Literal["0.1.0"]
    target_id: Literal["secmate.synthetic-chatmate.fresh.v1"]
    target_version: Literal["0.1.1"]
    assessment_id: StrictStr
    state_generation: Annotated[StrictInt, Field(ge=1)]
    run_id: StrictStr | None
    event_id: Annotated[StrictInt, Field(ge=1)]
    logical_time: StrictStr
    type: StrictStr
    actor_ref: StrictStr
    call_id: StrictStr | None
    action_id: None
    caused_by: StrictInt | None
    data: dict
    binding_digest: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


@dataclass(frozen=True)
class Session:
    token: str


@dataclass(frozen=True)
class Lease:
    assessment_id: str
    state_generation: int
    run_id: str
    token: str


def strict_json(value: str):
    def pairs(items):
        result = {}
        for key, val in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = val
        return result

    def invalid(_):
        raise ValueError("nonfinite_json")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=invalid)
