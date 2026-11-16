"""Exact blueprint catalog and a bounded local validator for its closed subset.

The approved blueprint is an immutable, hash-checked build input. Its two JSON
catalog blocks supply the normative roots; there are no remote references or
third-party schema-validator dependencies.
"""
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from typing import Annotated, Literal
from pydantic import Field, StrictStr, StrictBool, StrictInt, model_validator
from ..contracts import StrictModel
from ..communication_repaired.contracts import CommunicationFaults
from ..communication.contracts import ID, SHA

from ..contracts import SyntheticError, clone
from ..communication_repaired.contracts import bounded_json

VERSION = "0.3.0"
READ_CALENDAR = "secmate.read_calendar"
PROPOSE_MEETING = "secmate.propose_meeting"
BLUEPRINT_BLOB = "34bbffff2929dc236806cb1d2fdc39a07f62ea28"
BLUEPRINT = Path(__file__).resolve().parents[6] / "Documents" / "SYNTHETIC_CHATMATE_PHASE3_BLUEPRINT.md"
INVITATION_EVENT = "meeting.invitations_committed"
AMENDMENT_VERSION = "phase3-invitation-commit-1.0.0"


class CommittedInvitation(StrictModel):
    id: ID
    approval_id: ID
    execution_id: ID
    effect_id: ID
    event_id: ID
    attendee_id: ID
    calendar_id: ID
    record_digest: SHA


class InvitationCommitData(StrictModel):
    amendment_version: Literal["phase3-invitation-commit-1.0.0"]
    action_kind: Literal["meeting"]
    approval_id: ID
    execution_id: ID
    decision_run_id: ID
    effect_id: ID
    event_id: ID
    record_digest: SHA
    invitations: Annotated[list[CommittedInvitation], Field(min_length=1, max_length=4)]


class SuppressedInvitationCommitData(InvitationCommitData):
    record_digest: None
    invitations: None


class CalendarFault(StrictModel):
    phase: Literal["calendar_read", "meeting_prepare", "after_resolve", "preflight", "after_preflight", "before_commit", "projection", "after_commit", "receipt", "settlement", "failure_recording"]
    call_id: Annotated[StrictStr, Field(min_length=1, max_length=128)] | None
    mode: Literal["raise", "timeout", "hold", "cancel", "receipt_loss"]
    duration: Annotated[float, Field(ge=0, le=60, allow_inf_nan=False)]
    occurrence: Annotated[StrictInt, Field(ge=1, le=4)]

    @model_validator(mode="after")
    def combinations(self):
        allowed = {"raise": None, "timeout": {"calendar_read", "meeting_prepare", "preflight", "before_commit"},
                   "hold": {"after_resolve", "after_preflight", "after_commit"},
                   "cancel": {"after_resolve", "after_preflight", "after_commit", "before_commit"},
                   "receipt_loss": {"after_commit", "receipt"}}
        if allowed[self.mode] is not None and self.phase not in allowed[self.mode]:
            raise ValueError("fault_combination")
        return self


class Phase3FaultPlan(CommunicationFaults):
    calendar_read_unavailable: StrictBool = False
    calendar_faults: Annotated[list[CalendarFault], Field(max_length=32)] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_calendar_schedule(self):
        keys = [(f.phase, f.call_id, f.occurrence) for f in self.calendar_faults]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate_calendar_fault")
        return self


@lru_cache(maxsize=1)
def blueprint_inputs():
    raw = BLUEPRINT.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    blob = hashlib.sha1(b"blob " + str(len(normalized)).encode("ascii") + b"\0" + normalized).hexdigest()
    if blob != BLUEPRINT_BLOB:
        raise SyntheticError("blueprint_binding_unavailable")
    blocks = [json.loads(b) for b in re.findall(r"```json\s*\n(.*?)\n```", raw.decode("utf-8"), re.S)]
    catalogs = [b for b in blocks if "$defs" in b]
    definitions = {}
    for catalog in catalogs:
        if definitions.keys() & catalog["$defs"].keys():
            raise SyntheticError("invalid_fixture")
        definitions.update(catalog["$defs"])
    if len(definitions) != 57:
        raise SyntheticError("invalid_fixture")
    catalog = {"$schema": catalogs[0]["$schema"], "$id": catalogs[0]["$id"], "$defs": definitions}
    def references(value):
        if isinstance(value, dict):
            if "$ref" in value and (not value["$ref"].startswith("#/$defs/") or value["$ref"][8:] not in definitions):
                raise SyntheticError("invalid_fixture")
            for item in value.values():
                references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)
    references(catalog)
    seed = next(b for b in blocks if "calendar_seed_id" in b)
    return catalog, seed, {"blob_id": blob, "file_sha256": hashlib.sha256(raw).hexdigest()}


def schema(root):
    catalog = clone(blueprint_inputs()[0])
    return {**catalog, "$ref": "#/$defs/" + root}


def closed(properties, required=None):
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties) if required is None else required}


def event_schemas():
    """Closed typed inherited data shapes; optionality reflects actual branches."""
    ident = {"type": "string", "minLength": 1, "maxLength": 128}
    text = {"type": "string", "maxLength": 240000}
    number = {"type": "number", "minimum": 0}
    integer = {"type": "integer", "minimum": 0}
    boolean = {"type": "boolean"}
    nullable = lambda value: {"oneOf": [value, {"type": "null"}]}
    obj = {"type": "object"}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    schemas = {
        "assessment.created": closed({"binding_digest": sha}), "assessment.bindings_loaded": closed({"bindings": obj}),
        "assessment.finished": closed({"status": ident}), "message.accepted": closed({"message_id": ident}),
        "run.created": {"oneOf": [closed({}), closed({"kind": {"const": "decision"}, "model_invocation": {"const": False}})]},
        "run.started": closed({}), "run.enqueued": {"oneOf": [closed({"kind": {"const": "decision"}}), closed({"accepted_message_id": ident})]},
        "run.cancel_requested": closed({"source": ident}),
        "budget.charged": {"oneOf": [closed({"pool": {"const": "rounds"}, "round": integer}), closed({"pool": ident, "remaining": integer})]},
        "budget.refunded": closed({"pool": ident, "reason": ident, "remaining": integer}),
        "budget.exhausted": closed({"pool": ident}), "tool.requested": closed({"name": ident, "arguments": text}),
        "tool.dispatched": closed({"name": ident, "destination": ident}), "tool.timeout": closed({}),
        "directory.state_changed": closed({"person_id": ident, "digest": sha}), "clock.advanced": closed({"seconds": number}),
        "decision.deadline_bound": closed({"deadline": text, "seconds": number}),
        "decision.not_started": closed({"error": ident, "cancelled": boolean}),
        "runtime.handler_failed": closed({"error": ident, "phase": ident}),
        "reset.started": closed({}), "reset.completed": closed({"next_generation": integer}),
        "model.error": closed({"code": ident, "attempt": integer, "after_output": boolean}),
        "model.retry": closed({"attempt": integer}),
        "evidence.completeness_gap": closed({"export_profile": ident, "missing": {"type": "array", "items": ident}, "restricted_truth_modified": {"const": False}}),
    }
    for kind in ("snapshot.authorized", "snapshot.authorization_rejected"):
        schemas[kind] = closed({"resource_id": ident, "requested_by": ident, "resource_owner": nullable(ident)})
    for kind in ("tool.validated", "tool.validation_rejected"):
        schemas[kind] = closed({"name": ident, "code": nullable(ident), "native_metadata": nullable(obj)})
    for kind in ("tool.authorized", "tool.authorization_rejected", "retrieval.authorized", "retrieval.authorization_rejected"):
        fields = {"name": ident, "resource_id": ident, "connector_owner": ident, "owner": ident, "code": nullable(ident), "boundary": ident}
        schemas[kind] = closed(fields, ["resource_id", "connector_owner", "code"])
    for kind in ("run.completed", "run.failed", "run.cancelled"):
        schemas[kind] = closed({"message_id": nullable(ident), "content": nullable(text), "kernel_outcome": nullable(ident),
                                "partial": boolean, "reason": ident, "error_code": nullable(ident)})
    for kind in ("model.response_received", "model.incomplete_step"):
        schemas[kind] = closed({"round": integer, "text": text, "calls": {"type": "array", "items": obj}, "completion": boolean})
    schemas["model.request_built"] = closed({"round": integer, "attempt": integer, "request": obj})
    schemas["tool.result"] = closed({"name": ident, "result": obj})
    schemas["directory.resolution"] = closed({"matches": {"type": "array", "items": obj}, "resolution": {"enum": ["exact", "ambiguous", "none"]}})
    schemas["retrieval.result"] = closed({"name": ident, "record_ids": {"type": "array", "items": ident},
                                         "source_refs": {"type": "array", "items": obj}, "boundary": ident, "result": obj}, [])
    from ..communication_repaired.evidence import COMMON_ACTION, ACTION_EXTRA, SURFACES
    types = {"review": obj, "recipient_snapshot": {"type": "array", "items": obj}, "receipt": obj,
             "dispatch_arguments": obj, "state_generation": integer, "code": nullable(ident)}
    for stage in ("requested", "validated", "validation_rejected", "authorized_to_prepare", "authorization_rejected", *ACTION_EXTRA):
        allowed = COMMON_ACTION | ACTION_EXTRA[stage] if stage in ACTION_EXTRA else SURFACES["action." + stage]
        props = {k: types.get(k, sha if k.endswith("digest") else text if k == "arguments" else ident) for k in allowed}
        if "prepared_digest" in props and stage not in ACTION_EXTRA:
            props["prepared_digest"] = nullable(sha)
        # Correlations and stage-specific values are checked by the message
        # observer; branch variants remain closed and typed at append/export.
        required = list(COMMON_ACTION) if stage in ACTION_EXTRA else {
            "requested": ["name", "arguments"], "validated": ["code", "prepared_digest"],
            "validation_rejected": ["code", "prepared_digest"], "authorized_to_prepare": ["connector_owner", "conversation_id", "code"],
            "authorization_rejected": ["connector_owner", "conversation_id", "code"],
        }[stage]
        schemas["action." + stage] = closed(props, required)
    return schemas


def validate(root, value, *, external=None):
    """Enforce every keyword used by the pinned 57-root catalog, fail closed."""
    catalog = blueprint_inputs()[0]

    def check(s, v, depth=0):
        if depth > 32:
            raise ValueError("schema_depth")
        if "$ref" in s:
            return check(catalog["$defs"][s["$ref"][8:]], v, depth + 1)
        if "anyOf" in s or "oneOf" in s:
            successes = 0
            for branch in s.get("oneOf", s.get("anyOf")):
                try:
                    check(branch, v, depth + 1)
                    successes += 1
                except ValueError:
                    pass
            if (successes != 1 if "oneOf" in s else successes < 1):
                raise ValueError("schema_union")
        if "const" in s and (v != s["const"] or isinstance(v, bool) != isinstance(s["const"], bool)):
            raise ValueError("schema_const")
        if "enum" in s and not any(v == x and isinstance(v, bool) == isinstance(x, bool) for x in s["enum"]):
            raise ValueError("schema_enum")
        types = s.get("type", [])
        types = [types] if isinstance(types, str) else types
        matches = {"object": type(v) is dict, "array": type(v) is list,
                   "string": type(v) is str, "integer": type(v) is int,
                   "number": type(v) in (int, float) and math.isfinite(v),
                   "boolean": type(v) is bool, "null": v is None}
        if types and not any(matches[t] for t in types):
            raise ValueError("schema_type")
        if type(v) is dict and "properties" in s:
            if not set(s.get("required", [])) <= v.keys():
                raise ValueError("schema_required")
            if s.get("additionalProperties") is False and v.keys() - s["properties"].keys():
                raise ValueError("schema_extra")
            for key, item in v.items():
                if key in s["properties"]:
                    check(s["properties"][key], item, depth + 1)
        if type(v) is list:
            if len(v) < s.get("minItems", 0) or len(v) > s.get("maxItems", math.inf):
                raise ValueError("schema_items")
            if s.get("uniqueItems") and any(x in v[:i] for i, x in enumerate(v)):
                raise ValueError("schema_unique")
            if "items" in s:
                for item in v:
                    check(s["items"], item, depth + 1)
        if type(v) is str:
            if len(v) < s.get("minLength", 0) or len(v) > s.get("maxLength", math.inf):
                raise ValueError("schema_length")
            if "pattern" in s and re.search(s["pattern"], v) is None:
                raise ValueError("schema_pattern")
        if type(v) in (int, float):
            if not math.isfinite(v) or v < s.get("minimum", -math.inf) or v > s.get("maximum", math.inf):
                raise ValueError("schema_number")
    check(external if external is not None else catalog["$defs"][root], value)
    return clone(value)


def validate_event(event, bundle=None, *, selected=False):
    """Closed event registry shared by append, export and reconciliation."""
    from ..communication_repaired.evidence import SURFACES, COMMON_ACTION, ACTION_EXTRA
    from ..communication_repaired.contracts import validate_output
    from ..communication.contracts import ToolError
    from ..contracts import ToolCall
    validate("EventEnvelope", event)
    kind, data = event["type"], event["data"]
    roots = {"time.rules_loaded": "TimeRulesLoadedData", "calendar.account_changed": "CalendarAccountChangedData",
             "meeting.normalized": "MeetingNormalizedData"}
    if kind == INVITATION_EVENT:
        (SuppressedInvitationCommitData if selected else InvitationCommitData).model_validate(data)
    elif kind in roots:
        validate(roots[kind], data)
    elif kind in {"calendar.retrieval_authorized", "calendar.retrieval_rejected", "calendar.retrieval_result"}:
        validate("CalendarRetrievalData", data)
    elif kind.startswith("action.") and data.get("action_kind") == "meeting":
        if kind[7:] not in {"requested", "validated", "validation_rejected", "authorized_to_prepare", "authorization_rejected", *ACTION_EXTRA}:
            raise ValueError("event_type")
        validate("MeetingActionData", data)
    else:
        stage = kind.removeprefix("action.")
        allowed = COMMON_ACTION | ACTION_EXTRA[stage] if kind.startswith("action.") and stage in ACTION_EXTRA else SURFACES.get(kind)
        if allowed is None or data.keys() - allowed:
            raise ValueError("event_surface")
        validate(None, data, external=event_schemas()[kind])
        if kind.startswith("action."):
            from ..communication.contracts import Review, Dispatch, Receipt, DirectoryMatch
            for key, model in (("review", Review), ("dispatch_arguments", Dispatch), ("receipt", Receipt)):
                if key in data:
                    model.model_validate(data[key])
            for person in data.get("recipient_snapshot", []):
                DirectoryMatch.model_validate(person)
    if "calls" in data and kind != "model.incomplete_step":
        for call in data["calls"]:
            ToolCall.model_validate(call)
    if kind == "directory.resolution":
        from ..communication.contracts import DirectoryResult
        DirectoryResult.model_validate(data)
    if kind == "assessment.bindings_loaded" and bundle is not None:
        expected = bundle.bindings({}, "shape", 1)
        if set(data["bindings"]) != set(expected) or set(data["bindings"]["artifact_digests"]) != set(expected["artifact_digests"]):
            raise ValueError("binding_shape")
    if kind == "tool.result":
        name, result = data["name"], data["result"]
        if name in {READ_CALENDAR, PROPOSE_MEETING}:
            validate("CalendarToolResult", result)
        else:
            from ..communication.contracts import ToolResult
            envelope = ToolResult.model_validate(result)
            if envelope.status == "error":
                ToolError.model_validate(envelope.output)
            else:
                validate_output(name, envelope.output)
        if result["call_id"] != event["call_id"]:
            raise ValueError("call_correlation")
        output = result["output"]
        refs = [] if result["status"] == "error" else [output["source_ref"]] if "source_ref" in output else [i["source_ref"] for i in output.get("items", [])]
        if refs != result["source_refs"]:
            raise ValueError("source_correlation")
    if bundle is not None and kind in {"tool.validated", "tool.validation_rejected"}:
        if data.get("native_metadata") != bundle.get("native_metadata").get(data.get("name")):
            raise ValueError("native_metadata")
    if "request" in data:
        request = data["request"]
        if set(request) != {"instructions", "items", "tools", "tool_choice", "parallel_tool_calls"} or request["tool_choice"] != "auto" or request["parallel_tool_calls"] is not False:
            raise ValueError("request_shape")
        if bundle is not None:
            expected_tools = [{"type": "function", "name": "secmate.conversation.history.read", "parameters": bundle.get("schemas")["read_input"]}]
            expected_tools += [{"type": "function", "name": name, "parameters": bundle.get("schemas")["tools"][name]["input"]}
                               for name in bundle.get("capabilities")["enabled"] if name != "secmate.conversation.history.read"]
            if request["tools"] != expected_tools:
                raise ValueError("request_tool_binding")
            if request["instructions"] != bundle.get("prompt")["instructions"]:
                raise ValueError("request_instruction_binding")
        calls = {}
        for item in request["items"]:
            if item.get("type") == "function_call":
                ToolCall.model_validate({k: v for k, v in item.items() if k != "type"})
                if item["call_id"] in calls:
                    raise ValueError("duplicate_transcript_call")
                calls[item["call_id"]] = item["name"]
            elif item.get("type") == "function_call_output":
                if set(item) != {"type", "call_id", "output"} or type(item["output"]) is not str:
                    raise ValueError("output_shape")
                output = bounded_json(item["output"])
                if type(output) is not dict:
                    raise ValueError("output_object")
                name = calls.get(item["call_id"])
                if name is None:
                    raise ValueError("uncorrelated_transcript_output")
                if "error" in output:
                    if name in {READ_CALENDAR, PROPOSE_MEETING}:
                        validate("CalendarError", output)
                    else:
                        ToolError.model_validate(output)
                elif name in {READ_CALENDAR, PROPOSE_MEETING}:
                    validate("CalendarPage" if name == READ_CALENDAR else "Staged", output)
                else:
                    validate_output(name, output)
            elif set(item) != {"role", "content"} or item["role"] not in {"user", "assistant", "developer"} or type(item["content"]) is not str:
                raise ValueError("message_shape")
    return event
