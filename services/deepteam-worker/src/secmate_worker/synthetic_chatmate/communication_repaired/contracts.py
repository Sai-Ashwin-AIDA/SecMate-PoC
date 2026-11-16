"""Versioned bounded parser and output coverage for every enabled tool."""
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictStr

from ..contracts import Listing, MessagePage, READ_TOOL, StrictModel, strict_json as original_json
from ..communication.contracts import (
    CommunicationBudget as OldBudget, CommunicationFaults, Event as OldEvent,
    INPUTS, OUTPUTS, ToolResult, ToolError, ID, UTC,
)

VERSION = "0.2.1"
MAX_JSON_DEPTH = 32


class CommunicationBudget(OldBudget):
    profile_id: str = "communication-small-0.2.1"


class Event(OldEvent):
    target_version: Literal["0.2.1"]
    event_schema_version: Literal["0.2.1"]
    logical_time: UTC


class SnapshotMessage(StrictModel):
    message_id: ID
    role: Literal["user", "assistant"]
    content: Annotated[StrictStr, Field(max_length=240000)]


class Snapshot(StrictModel):
    id: ID
    owner: ID
    deleted: StrictBool
    messages: list[SnapshotMessage]


class Canary(StrictModel):
    marker: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    resource_id: ID
    audience: list[ID]


def bounded_json(text, *, maximum=240000):
    """Check nesting without recursion, respecting escaped strings, before decoding."""
    if not isinstance(text, str) or len(text) > maximum:
        raise ValueError("json_limit")
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("json_depth")
        elif char in "]}":
            depth -= 1
    try:
        return original_json(text)
    except RecursionError:
        raise ValueError("json_depth") from None


def validate_output(name, output):
    if name == READ_TOOL:
        model = Listing if output.get("kind") == "listing" else MessagePage
    else:
        model = OUTPUTS[name]
    return model.model_validate(output).model_dump()


OUTPUT_VALIDATORS = {READ_TOOL, *OUTPUTS}
