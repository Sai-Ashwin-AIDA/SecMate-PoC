"""Strict facts-only contracts for synthetic ChatMate 0.4.0."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from ..contracts import StrictModel
from ..calendar_repaired.contracts import Phase3FaultPlan, bounded_json

VERSION = "0.4.0"
LIFETIME = 7_776_000
MAX_REVISION = 2_147_483_647
SHA = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
ID = Annotated[StrictStr, Field(min_length=1, max_length=128)]


class Fact(StrictModel):
    id: ID
    owner: ID
    tenant: ID
    ordinal: Annotated[StrictInt, Field(ge=1, le=30)]
    text: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    created_at: StrictStr
    expires_at: StrictStr

    @model_validator(mode="after")
    def valid_fact(self):
        if not self.text.strip():
            raise ValueError("blank_fact")
        created, expires = utc_seconds(self.created_at), utc_seconds(self.expires_at)
        if expires - created != LIFETIME or created > 0:
            raise ValueError("fact_time")
        return self


class OwnerHeader(StrictModel):
    owner: ID
    tenant: ID
    revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]
    enabled: StrictBool
    preferences: dict = Field(default_factory=dict, max_length=0)


class MemorySeed(StrictModel):
    seed_id: Literal["seed-memory-facts-0.4.0"]
    clock_origin: Literal["2030-01-07T09:00:00Z"]
    owners: Annotated[list[OwnerHeader], Field(min_length=3, max_length=3)]
    facts: Annotated[list[Fact], Field(max_length=90)]

    @model_validator(mode="after")
    def relationships(self):
        owners = {o.owner: o for o in self.owners}
        if len(owners) != 3 or len({f.id for f in self.facts}) != len(self.facts):
            raise ValueError("memory_identity")
        keys = [(f.owner, f.ordinal) for f in self.facts]
        if len(keys) != len(set(keys)) or any(f.owner not in owners or owners[f.owner].tenant != f.tenant for f in self.facts):
            raise ValueError("memory_relationship")
        if any(sum(f.owner == owner for f in self.facts) > 30 for owner in owners):
            raise ValueError("memory_capacity")
        return self


class MemoryLoadFault(StrictModel):
    round: Annotated[StrictInt, Field(ge=1, le=4)]
    attempt: Literal[1, 2]
    duration: Annotated[float, Field(ge=0, le=60, allow_inf_nan=False)] = 0.0
    mode: Literal["none", "unavailable", "raise", "malformed_success", "cancel_before_read", "cancel_before_publication", "disconnect"] = "none"


class MemoryControlFault(StrictModel):
    ordinal: Annotated[StrictInt, Field(ge=1, le=32)]
    phase: Literal["before_commit", "after_commit", "return"]
    duration: Annotated[float, Field(ge=0, le=60, allow_inf_nan=False)] = 0.0
    mode: Literal["none", "raise", "cancel", "response_loss", "journal_insert_failure", "witness_insert_failure", "cancel_before_apply", "cancel_after_commit", "disconnect"] = "none"

    @model_validator(mode="after")
    def phase_mode(self):
        before_only = {"cancel", "journal_insert_failure", "witness_insert_failure", "cancel_before_apply"}
        after_only = {"response_loss", "cancel_after_commit", "disconnect"}
        if self.phase == "before_commit" and self.mode in after_only or self.phase != "before_commit" and self.mode in before_only:
            raise ValueError("memory_fault_phase")
        return self


class MemoryFaults(StrictModel):
    loads: Annotated[list[MemoryLoadFault], Field(max_length=8)] = Field(default_factory=list)
    controls: Annotated[list[MemoryControlFault], Field(max_length=96)] = Field(default_factory=list)
    failure_recording_unavailable: StrictBool = False

    @model_validator(mode="after")
    def unique(self):
        if len({(x.round, x.attempt) for x in self.loads}) != len(self.loads) or len({(x.ordinal, x.phase) for x in self.controls}) != len(self.controls):
            raise ValueError("duplicate_memory_fault")
        return self


class Phase4FaultPlan(Phase3FaultPlan):
    memory: MemoryFaults = Field(default_factory=MemoryFaults)


class InspectInput(StrictModel):
    operation: Literal["inspect"]


class ForgetInput(StrictModel):
    operation: Literal["forget"]
    expected_revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]
    fact_id: ID


class ClearInput(StrictModel):
    operation: Literal["clear"]
    expected_revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]


class DisableInput(StrictModel):
    operation: Literal["disable_conversation"]
    expected_revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]
    expected_context_revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]
    conversation_id: ID


class FixtureEnabledInput(StrictModel):
    operation: Literal["fixture_set_enabled"]
    expected_revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]
    enabled: StrictBool


class MutableContext(StrictModel):
    shared: StrictBool
    participant_ids: Annotated[list[ID], Field(min_length=1, max_length=4)]
    project_id: ID | None
    deleted: StrictBool

    @field_validator("participant_ids")
    @classmethod
    def unique_participants(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("duplicate_participant")
        return value


class FixtureContextInput(StrictModel):
    operation: Literal["fixture_context_change"]
    expected_context_revision: Annotated[StrictInt, Field(ge=1, le=MAX_REVISION)]
    conversation_id: ID
    context: MutableContext


def control_input(value):
    if not isinstance(value, dict):
        raise ValueError("invalid_arguments")
    cls = {"inspect": InspectInput, "forget": ForgetInput, "clear": ClearInput, "disable_conversation": DisableInput}.get(value.get("operation"))
    if cls is None:
        raise ValueError("invalid_arguments")
    return cls.model_validate(value).model_dump()


def fixture_control_input(value):
    if not isinstance(value, dict):
        raise ValueError("invalid_arguments")
    cls = {"fixture_set_enabled": FixtureEnabledInput, "fixture_context_change": FixtureContextInput}.get(value.get("operation"))
    if cls is None:
        raise ValueError("invalid_arguments")
    return cls.model_validate(value).model_dump()


def strict_control_json(raw):
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError("invalid_arguments")
    # The inherited parser enforces depth, duplicate-key and non-finite-number
    # rejection. Decode only once at the public raw JSON boundary.
    return control_input(bounded_json(raw, maximum=8192))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def utc_seconds(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise ValueError("invalid_utc") from None
    origin = datetime(2030, 1, 7, 9, tzinfo=timezone.utc)
    if not datetime(2000, 1, 1, tzinfo=timezone.utc) <= parsed < datetime(2100, 1, 1, tzinfo=timezone.utc):
        raise ValueError("utc_domain")
    return int((parsed - origin).total_seconds())


MEMORY_EVENT_FIELDS = {
    "memory.seed_bound": {"seed_digest", "owner_ids", "fact_count"},
    "memory.context_created": {"context", "profile_id", "context_digest"},
    "memory.context_loaded": {"snapshot_id", "previous_snapshot_id", "round", "attempt", "read_seconds", "read_at", "eligibility", "status", "reason", "owner_revision", "owner_enabled", "owner_state_digest", "selected_refs", "expected_payload_digest"},
    "memory.context_refreshed": {"snapshot_id", "previous_snapshot_id", "round", "attempt", "read_seconds", "read_at", "eligibility", "status", "reason", "owner_revision", "owner_enabled", "owner_state_digest", "selected_refs", "expected_payload_digest"},
    "memory.request_bound": {"snapshot_id", "round", "attempt", "request_event_id", "request_seconds", "actual_present", "actual_payload_digest"},
    "memory.checkpoint": {"conversation_id", "after_round"},
    "memory.checkpoint_clock_advanced": {"after_round", "before_seconds", "after_seconds"},
    "memory.control.accepted": {"control_id", "ordinal", "owner", "body", "input_digest", "deadline_seconds"},
    "memory.control.validation_rejected": {"error", "field"},
    "memory.control.cancel_requested": {"control_id"},
    "memory.control.inspected": {"control_id", "owner_meta", "active_refs", "expired_count", "read_seconds", "read_at"},
    "memory.control.committed": {"control_id", "operation", "input_digest", "owner_before", "owner_after", "context_before", "context_after", "affected_run_ids", "removed_fact_refs", "commit_seconds", "committed_at"},
    "memory.control.finished": {"control_id", "operation", "status", "error", "response_digest"},
    "memory.control.replayed": {"control_id", "operation", "status", "error", "response_digest"},
}

MEMORY_EVENT_ROOTS = {
    "memory.seed_bound": "SeedBoundData", "memory.context_created": "ContextCreatedData",
    "memory.context_loaded": "Snapshot", "memory.context_refreshed": "Snapshot", "memory.request_bound": "RequestBoundData",
    "memory.checkpoint": "CheckpointData", "memory.checkpoint_clock_advanced": "CheckpointClockData",
    "memory.control.accepted": "ControlAcceptedData", "memory.control.validation_rejected": "ControlValidationData",
    "memory.control.cancel_requested": "ControlCancelData", "memory.control.inspected": "InspectedData",
    "memory.control.committed": "ControlCommittedData", "memory.control.finished": "ControlFinishedData",
    "memory.control.replayed": "ControlFinishedData",
}


def validate_event(event):
    fields = {"event_schema_version", "target_id", "target_version", "assessment_id", "state_generation", "run_id", "event_id", "logical_time",
              "type", "actor_ref", "call_id", "action_id", "caused_by", "data", "binding_digest", "production_claim"}
    if not isinstance(event, dict) or set(event) != fields or event["event_schema_version"] != VERSION or event["target_version"] != VERSION:
        raise ValueError("event_envelope")
    if type(event["event_id"]) is not int or event["event_id"] < 1 or event["production_claim"] is not False:
        raise ValueError("event_semantics")
    expected = MEMORY_EVENT_FIELDS.get(event["type"])
    if expected is not None:
        if set(event["data"]) != expected or event["call_id"] is not None or event["action_id"] is not None:
            raise ValueError("memory_event_data")
        if event["type"].startswith("memory.control.") and event["run_id"] is not None:
            raise ValueError("control_run_binding")
        validate_root(MEMORY_EVENT_ROOTS[event["type"]], event["data"])
    elif event["type"].startswith("memory."):
        raise ValueError("unknown_memory_event")
    else:
        from ..calendar_repaired.contracts import validate_event as validate_inherited_event
        validate_inherited_event({**event, "target_version": "0.3.1", "event_schema_version": "0.3.1"})
    return event


# The blueprint catalog is deliberately local: every named root is closed and
# references only this dictionary. Runtime validation below supplies the
# cross-field rules JSON Schema cannot express.
ROOT_FIELDS = {
    "Fact": ("id", "owner", "tenant", "ordinal", "text", "created_at", "expires_at"),
    "FactRef": ("resource_id", "source_kind", "content_digest"),
    "OwnerHeader": ("owner", "tenant", "revision", "enabled", "preferences"),
    "OwnerState": ("owner", "tenant", "revision", "enabled", "preferences", "facts"),
    "OwnerMeta": ("owner", "tenant", "revision", "enabled", "preferences", "stored_fact_refs", "state_digest"),
    "Context": ("assessment_id", "state_generation", "conversation_id", "owner", "tenant", "revision", "shared", "participant_ids", "project_id", "deleted", "memory_disabled"),
    "Eligibility": ("context", "memory_owner", "requested_by", "run_memory_disabled", "subsystem_enabled"),
    "MemoryItem": ("fact_id", "text", "source_ref"),
    "MemoryPayload": ("source_kind", "owner", "revision", "facts"),
    "Snapshot": ("snapshot_id", "previous_snapshot_id", "round", "attempt", "read_seconds", "read_at", "eligibility", "status", "reason", "owner_revision", "owner_enabled", "owner_state_digest", "selected_refs", "expected_payload_digest"),
    "InspectInput": ("operation",), "ForgetInput": ("operation", "expected_revision", "fact_id"),
    "ClearInput": ("operation", "expected_revision"), "DisableInput": ("operation", "expected_revision", "expected_context_revision", "conversation_id"),
    "ReplayInput": ("control_id",), "FixtureEnabledInput": ("operation", "expected_revision", "enabled"),
    "MutableContext": ("shared", "participant_ids", "project_id", "deleted"),
    "FixtureContextInput": ("operation", "expected_context_revision", "conversation_id", "context"),
    "InspectResult": ("control_id", "operation", "status", "owner_state", "active_facts", "stored_count", "expired_count", "context", "read_seconds", "read_at"),
    "MutationResult": ("control_id", "operation", "status", "owner", "before_revision", "revision", "enabled", "conversation_id", "before_context_revision", "context_revision", "removed_fact_refs", "state_digest", "context_digest", "commit_seconds", "committed_at"),
    "ErrorResult": ("control_id", "status", "error", "field", "current_revision", "current_context_revision"),
    "ControlRecord": ("id", "ordinal", "assessment_id", "state_generation", "owner", "tenant", "body", "input_digest", "status", "accepted_seconds", "deadline_seconds", "result", "result_digest"),
    "HostOutput": ("target_id", "target_version", "assessment_id", "state_generation", "owner", "control_id", "is_replay", "returned_at", "response", "response_digest"),
    "ControlAcceptedData": ("control_id", "ordinal", "owner", "body", "input_digest", "deadline_seconds"),
    "ControlCommittedData": ("control_id", "operation", "input_digest", "owner_before", "owner_after", "context_before", "context_after", "affected_run_ids", "removed_fact_refs", "commit_seconds", "committed_at"),
    "ControlFinishedData": ("control_id", "operation", "status", "error", "response_digest"),
    "ContextCreatedData": ("context", "profile_id", "context_digest"),
    "RequestBoundData": ("snapshot_id", "round", "attempt", "request_event_id", "request_seconds", "actual_present", "actual_payload_digest"),
    "CheckpointData": ("conversation_id", "after_round"), "CheckpointClockInput": ("seconds",),
    "CheckpointClockData": ("after_round", "before_seconds", "after_seconds"),
    "MemoryLoadFault": ("round", "attempt", "duration", "mode"),
    "MemoryControlFault": ("ordinal", "phase", "duration", "mode"),
    "MemoryFaults": ("loads", "controls", "failure_recording_unavailable"),
    "MemorySeed": ("seed_id", "clock_origin", "owners", "facts"),
    "SeedBoundData": ("seed_digest", "owner_ids", "fact_count"),
    "InspectedData": ("control_id", "owner_meta", "active_refs", "expired_count", "read_seconds", "read_at"),
    "CancelControlInput": ("control_id",), "MemoryBoundaryInput": ("requested_owner", "eligibility"),
    "MemoryBoundarySuccess": ("status", "reason", "read_seconds", "payload"),
    "ControlCancelData": ("control_id",), "ControlValidationData": ("error", "field"),
    "MutationJournal": ("control_id", "input_digest", "before_owner", "after_owner", "before_context", "after_context", "removed_facts", "affected_run_ids", "commit_seconds"),
    "SnapshotRecord": ("run_id", "snapshot", "candidate"), "ControlFence": ("control_id", "owner", "persistence_fenced"),
    "MemoryCounters": ("checks_remaining", "controls_remaining"),
    "MemoryFaultHit": ("kind", "phase", "round", "attempt", "ordinal", "control_id", "status", "before_seconds", "after_seconds", "deadline_seconds", "error"),
    "RestrictedMemoryState": ("owner_states", "contexts", "controls", "journals", "snapshots", "host_outputs", "fault_hits", "counters", "fence"),
    "ContextTemplate": ("id", "shared", "participant_mode", "project_id", "deleted", "memory_disabled", "subsystem_enabled"),
    "ContextTemplates": ("version", "default_profile", "profiles"),
    "PlanInspect": ("kind",), "PlanForget": ("kind", "fact_id", "expected_revision"),
    "PlanClear": ("kind", "expected_revision"), "PlanDisable": ("kind", "conversation_ref", "expected_revision", "expected_context_revision"),
    "PlanAdvance": ("kind", "seconds"), "BetweenRoundAction": ("after_round", "action"),
    "HostSchedule": ("id", "before_submit", "between_rounds"),
    "EventEnvelope": ("event_schema_version", "target_id", "target_version", "assessment_id", "state_generation", "run_id", "event_id", "logical_time", "type", "actor_ref", "call_id", "action_id", "caused_by", "data", "binding_digest", "production_claim"),
}

SCALAR_DEFS = {
    "ID": {"type": "string", "minLength": 1, "maxLength": 128},
    "SHA": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "Rev": {"type": "integer", "minimum": 1, "maximum": MAX_REVISION},
    "Seconds": {"type": "number", "minimum": 0},
    "UTC": {"type": "string", "minLength": 20, "maxLength": 20},
    "LogicalUTC": {"type": "string", "maxLength": 40},
    "Preferences": {"type": "object", "additionalProperties": False, "properties": {}, "required": [], "const": {}},
    "Refs": {"type": "array", "maxItems": 30, "items": {"$ref": "#/$defs/FactRef"}},
    "Reason": {"enum": [None, "owner_mismatch", "deleted", "shared", "multiparticipant", "project", "conversation_disabled", "rollout_disabled", "owner_disabled", "no_active_facts", "memory_unavailable", "memory_failed", "memory_timeout", "memory_budget_exhausted"]},
    "Operation": {"enum": ["inspect", "forget", "clear", "disable_conversation", "fixture_set_enabled", "fixture_context_change"]},
    "ErrorCode": {"enum": ["invalid_arguments", "invalid_session", "stale_generation", "stale_lease", "resource_unavailable", "capability_disabled", "memory_revision_conflict", "memory_revision_exhausted", "memory_unavailable", "memory_timeout", "memory_failed", "memory_cancelled", "memory_outcome_unknown", "memory_budget_exhausted", "memory_output_limit_exceeded", "memory_control_busy", "persistence_unavailable"]},
}

UNION_MEMBERS = {
    "ControlInput": ("InspectInput", "ForgetInput", "ClearInput", "DisableInput"),
    "ControlBody": ("InspectInput", "ForgetInput", "ClearInput", "DisableInput", "FixtureEnabledInput", "FixtureContextInput"),
    "ControlResponse": ("InspectResult", "MutationResult", "ErrorResult"),
    "MemoryBoundaryResult": ("MemoryBoundarySuccess", "ErrorResult"),
    "PlanAction": ("PlanInspect", "PlanForget", "PlanClear", "PlanDisable", "PlanAdvance"),
}

# These are the status/operation-bearing schemas for which a string-shaped
# fallback would weaken the contract.  Keep them as literal blueprint schemas;
# nested references are validated recursively by _validate_schema.
EXACT_SCHEMAS = {
    "FactRef": {"type": "object", "additionalProperties": False, "required": list(ROOT_FIELDS["FactRef"]), "properties": {
        "resource_id": {"$ref": "#/$defs/ID"}, "source_kind": {"const": "synthetic_personal_memory"}, "content_digest": {"$ref": "#/$defs/SHA"}}},
    "Snapshot": {"type": "object", "additionalProperties": False, "required": list(ROOT_FIELDS["Snapshot"]), "properties": {
        "snapshot_id": {"$ref": "#/$defs/ID"}, "previous_snapshot_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 128},
        "round": {"type": "integer", "minimum": 1, "maximum": 4}, "attempt": {"enum": [1, 2]},
        "read_seconds": {"$ref": "#/$defs/Seconds"}, "read_at": {"$ref": "#/$defs/LogicalUTC"}, "eligibility": {"$ref": "#/$defs/Eligibility"},
        "status": {"enum": ["loaded", "empty", "ineligible", "disabled", "unavailable"]}, "reason": {"$ref": "#/$defs/Reason"},
        "owner_revision": {"type": ["integer", "null"], "minimum": 1, "maximum": MAX_REVISION}, "owner_enabled": {"type": ["boolean", "null"]},
        "owner_state_digest": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}, "selected_refs": {"$ref": "#/$defs/Refs"},
        "expected_payload_digest": {"$ref": "#/$defs/SHA"}}},
    "ControlCommittedData": {"type": "object", "additionalProperties": False, "required": list(ROOT_FIELDS["ControlCommittedData"]), "properties": {
        "control_id": {"$ref": "#/$defs/ID"}, "operation": {"enum": ["forget", "clear", "disable_conversation", "fixture_set_enabled", "fixture_context_change"]},
        "input_digest": {"$ref": "#/$defs/SHA"}, "owner_before": {"$ref": "#/$defs/OwnerMeta"}, "owner_after": {"$ref": "#/$defs/OwnerMeta"},
        "context_before": {"oneOf": [{"$ref": "#/$defs/Context"}, {"type": "null"}]}, "context_after": {"oneOf": [{"$ref": "#/$defs/Context"}, {"type": "null"}]},
        "affected_run_ids": {"type": "array", "maxItems": 64, "uniqueItems": True, "items": {"$ref": "#/$defs/ID"}},
        "removed_fact_refs": {"$ref": "#/$defs/Refs"}, "commit_seconds": {"$ref": "#/$defs/Seconds"}, "committed_at": {"$ref": "#/$defs/LogicalUTC"}}},
    "ControlFinishedData": {"type": "object", "additionalProperties": False, "required": list(ROOT_FIELDS["ControlFinishedData"]), "properties": {
        "control_id": {"$ref": "#/$defs/ID"}, "operation": {"$ref": "#/$defs/Operation"},
        "status": {"enum": ["inspected", "applied", "already_disabled", "failed", "cancelled", "outcome_unknown", "replayed"]},
        "error": {"oneOf": [{"$ref": "#/$defs/ErrorCode"}, {"type": "null"}]}, "response_digest": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}}},
    "MemoryFaultHit": {"type": "object", "additionalProperties": False, "required": list(ROOT_FIELDS["MemoryFaultHit"]), "properties": {
        "kind": {"enum": ["load", "control"]}, "phase": {"enum": ["load", "before_commit", "after_commit", "return"]},
        "round": {"type": ["integer", "null"], "minimum": 1, "maximum": 4}, "attempt": {"enum": [None, 1, 2]},
        "ordinal": {"type": ["integer", "null"], "minimum": 1, "maximum": 32}, "control_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 128},
        "status": {"enum": ["completed", "failed", "cancelled", "not_reached"]},
        "before_seconds": {"type": ["number", "null"], "minimum": 0}, "after_seconds": {"type": ["number", "null"], "minimum": 0},
        "deadline_seconds": {"type": ["number", "null"], "minimum": 0}, "error": {"oneOf": [{"$ref": "#/$defs/ErrorCode"}, {"type": "null"}]}}},
}


def memory_schema_catalog():
    definitions = dict(SCALAR_DEFS)
    definitions.update({name: {"type": "object", "additionalProperties": False,
        "required": list(fields), "properties": {field: _field_schema(name, field) for field in fields}} for name, fields in ROOT_FIELDS.items()})
    definitions.update({name: {"oneOf": [{"$ref": "#/$defs/" + member} for member in members]} for name, members in UNION_MEMBERS.items()})
    for model in (Fact, OwnerHeader, MemorySeed, MemoryLoadFault, MemoryControlFault, MemoryFaults, InspectInput, ForgetInput,
                  ClearInput, DisableInput, FixtureEnabledInput, MutableContext, FixtureContextInput):
        schema = model.model_json_schema()
        definitions.update(schema.pop("$defs", {})); definitions[model.__name__] = schema
    definitions.update(EXACT_SCHEMAS)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:secmate:synthetic-chatmate:memory:0.4.0:schemas", "$defs": definitions}


def _field_schema(root, field):
    if root == "InspectResult" and field == "context": return {"oneOf": [{"$ref": "#/$defs/Context"}, {"type": "null"}]}
    if root == "MemoryFaultHit" and field in {"round", "attempt", "ordinal"}: return {"type": ["integer", "null"]}
    if root == "MemoryFaultHit" and field in {"before_seconds", "after_seconds", "deadline_seconds"}: return {"type": ["number", "null"], "minimum": 0}
    refs = {
        "context": "MutableContext" if root == "FixtureContextInput" else "Context", "eligibility": "Eligibility", "owner_state": "OwnerHeader", "owner_meta": "OwnerMeta",
        "owner_before": "OwnerMeta", "owner_after": "OwnerMeta", "before_owner": "OwnerState", "after_owner": "OwnerState",
        "snapshot": "Snapshot", "counters": "MemoryCounters", "source_ref": "FactRef", "body": "ControlBody", "response": "ControlResponse",
    }
    if field in refs: return {"$ref": "#/$defs/" + refs[field]}
    if field in {"enabled", "shared", "deleted", "memory_disabled", "run_memory_disabled", "subsystem_enabled", "is_replay", "persistence_fenced", "production_claim"}: return {"type": "boolean"}
    if field in {"ordinal", "round", "attempt", "event_id", "request_event_id", "after_round", "state_generation", "revision", "before_revision", "expected_revision", "expected_context_revision", "stored_count", "expired_count", "fact_count", "checks_remaining", "controls_remaining"}: return {"type": "integer"}
    if field.endswith("_seconds") or field == "seconds": return {"type": "number", "minimum": 0}
    if (field.endswith("_digest") or field == "state_digest") and field not in {"owner_state_digest", "context_digest", "actual_payload_digest", "result_digest", "response_digest"}: return {"$ref": "#/$defs/SHA"}
    if field in {"preferences"}: return {"$ref": "#/$defs/Preferences"}
    array_items = {
        "facts": "MemoryItem" if root == "MemoryPayload" else "Fact", "active_facts": "Fact", "stored_fact_refs": "FactRef",
        "selected_refs": "FactRef", "active_refs": "FactRef", "removed_fact_refs": "FactRef", "removed_facts": "Fact", "owner_states": "OwnerState",
        "contexts": "Context", "controls": "ControlRecord", "journals": "MutationJournal", "snapshots": "SnapshotRecord",
        "host_outputs": "HostOutput", "fault_hits": "MemoryFaultHit", "profiles": "ContextTemplate", "between_rounds": "BetweenRoundAction",
        "before_submit": "PlanAction",
    }
    if field in array_items: return {"type": "array", "items": {"$ref": "#/$defs/" + array_items[field]}}
    if field in {"affected_run_ids", "participant_ids", "owner_ids"}: return {"type": "array", "uniqueItems": True, "items": {"$ref": "#/$defs/ID"}}
    nullable_refs = {"result": "ControlResponse", "candidate": "MemoryPayload", "payload": "MemoryPayload", "context_before": "Context",
        "context_after": "Context", "before_context": "Context", "after_context": "Context", "fence": "ControlFence"}
    if field in nullable_refs: return {"oneOf": [{"$ref": "#/$defs/" + nullable_refs[field]}, {"type": "null"}]}
    if field in {"project_id", "conversation_id", "control_id", "run_id", "call_id", "action_id", "previous_snapshot_id"}: return {"type": ["string", "null"], "minLength": 1, "maxLength": 128}
    if field == "field": return {"type": ["string", "null"], "maxLength": 128, "pattern": "^/"}
    if field == "error": return {"oneOf": [{"$ref": "#/$defs/ErrorCode"}, {"type": "null"}]}
    if field == "reason": return {"$ref": "#/$defs/Reason"}
    if field in {"owner_revision", "context_revision", "before_context_revision", "current_revision", "current_context_revision"}: return {"type": ["integer", "null"], "minimum": 1, "maximum": MAX_REVISION}
    if field in {"owner_enabled", "actual_present"}: return {"type": ["boolean", "null"]}
    if field in {"owner_state_digest", "context_digest", "actual_payload_digest", "result_digest"}: return {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
    if field == "response_digest": return {"$ref": "#/$defs/SHA"}
    return {"type": "string"}


def _finite_tree(value, depth=0):
    if depth > 32: raise ValueError("json_depth")
    if isinstance(value, float) and not math.isfinite(value): raise ValueError("nonfinite")
    if isinstance(value, dict):
        for child in value.values(): _finite_tree(child, depth + 1)
    elif isinstance(value, list):
        for child in value: _finite_tree(child, depth + 1)


def _validate_schema(value, schema, definitions):
    if "$ref" in schema:
        return _validate_schema(value, definitions[schema["$ref"].rsplit("/", 1)[1]], definitions)
    alternatives = schema.get("oneOf") or schema.get("anyOf")
    if alternatives:
        successes = 0
        for alternative in alternatives:
            try: _validate_schema(value, alternative, definitions); successes += 1
            except (ValueError, TypeError): pass
        if successes != 1: raise ValueError("schema_union:" + repr(value)[:500])
        return
    if "const" in schema and value != schema["const"]: raise ValueError("schema_const")
    if "enum" in schema and value not in schema["enum"]: raise ValueError("schema_enum")
    expected = schema.get("type")
    allowed = set(expected if isinstance(expected, list) else [expected]) if expected else set()
    actual = "null" if value is None else "boolean" if type(value) is bool else "integer" if type(value) is int else "number" if type(value) is float else "string" if isinstance(value, str) else "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "invalid"
    if allowed and actual not in allowed and not (actual == "integer" and "number" in allowed): raise ValueError("schema_type:" + repr(value)[:200] + ":" + repr(schema)[:200])
    if actual == "object":
        required = set(schema.get("required", []))
        if not required <= set(value): raise ValueError("schema_required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties): raise ValueError("schema_extra")
        for key, child in value.items():
            if key in properties: _validate_schema(child, properties[key], definitions)
    elif actual == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1 << 30): raise ValueError("schema_items")
        if schema.get("uniqueItems") and len({canonical_item(item) for item in value}) != len(value): raise ValueError("schema_unique")
        if "items" in schema:
            for child in value: _validate_schema(child, schema["items"], definitions)
    elif actual == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 30): raise ValueError("schema_string")
        if schema.get("pattern") and re.search(schema["pattern"], value) is None: raise ValueError("schema_pattern")
    elif actual in {"integer", "number"}:
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf): raise ValueError("schema_number")


def canonical_item(value):
    import json
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _semantic_tree(value):
    if isinstance(value, list):
        for child in value: _semantic_tree(child)
        return
    if not isinstance(value, dict): return
    for key, child in value.items():
        if key in {"id", "owner", "tenant", "assessment_id", "conversation_id", "control_id", "snapshot_id", "run_id", "resource_id", "requested_by", "memory_owner", "profile_id"} and child is not None:
            if not isinstance(child, str) or not 1 <= len(child) <= 128: raise ValueError("id_semantics")
        if key in {"created_at", "expires_at"}: utc_seconds(child)
        if key in {"read_at", "committed_at", "returned_at", "logical_time"} and child is not None:
            try: datetime.fromisoformat(child.replace("Z", "+00:00"))
            except (TypeError, ValueError): raise ValueError("logical_time") from None
        if key in {"input_digest", "result_digest", "response_digest", "content_digest", "state_digest", "context_digest", "expected_payload_digest", "actual_payload_digest", "seed_digest", "binding_digest"} and child is not None:
            if not isinstance(child, str) or re.fullmatch(r"[0-9a-f]{64}", child) is None: raise ValueError("digest_semantics")
        _semantic_tree(child)


def validate_root(name, value):
    _finite_tree(value)
    _semantic_tree(value)
    if name == "EventEnvelope": return validate_event(value)
    if name == "MemorySeed": return MemorySeed.model_validate(value).model_dump()
    if name == "Phase4FaultPlan": return Phase4FaultPlan.model_validate(value).model_dump()
    if name in {"InspectInput", "ForgetInput", "ClearInput", "DisableInput", "ControlInput"}: return control_input(value)
    if name in {"FixtureEnabledInput", "FixtureContextInput"}: return fixture_control_input(value)
    catalog = memory_schema_catalog()["$defs"]
    if name in catalog: _validate_schema(value, catalog[name], catalog)
    if name in UNION_MEMBERS or name in SCALAR_DEFS: return value
    fields = ROOT_FIELDS.get(name)
    if fields is None: raise ValueError("unknown_schema_root")
    if not isinstance(value, dict) or set(value) != set(fields): raise ValueError("closed_schema")
    for key, item in value.items():
        if key.endswith("_seconds") and item is not None and (type(item) not in {int, float} or not math.isfinite(item) or item < 0): raise ValueError("seconds_type")
        if (key == "revision" or key.startswith("expected_") and key.endswith("revision") or key.endswith("_revision")) and item is not None and (type(item) is not int or not 1 <= item <= MAX_REVISION): raise ValueError("revision_type")
        if key.endswith("digest") and item is not None and (not isinstance(item, str) or len(item) != 64 or any(c not in "0123456789abcdef" for c in item)): raise ValueError("digest_type")
    if name == "Fact": return Fact.model_validate(value).model_dump()
    if name == "OwnerHeader": return OwnerHeader.model_validate(value).model_dump()
    if name == "Snapshot":
        status = value["status"]
        metadata = (value["owner_revision"], value["owner_enabled"], value["owner_state_digest"])
        if status in {"loaded", "empty", "disabled"} and any(item is None for item in metadata): raise ValueError("snapshot_metadata")
        if status in {"ineligible", "unavailable"} and any(item is not None for item in metadata): raise ValueError("snapshot_metadata")
        if status == "loaded" and (value["reason"] is not None or not value["selected_refs"]): raise ValueError("snapshot_loaded")
        if status != "loaded" and value["selected_refs"]: raise ValueError("snapshot_refs")
        validate_root("Eligibility", value["eligibility"])
        for ref in value["selected_refs"]: validate_root("FactRef", ref)
    if name == "ControlCommittedData":
        if value["owner_before"]["owner"] != value["owner_after"]["owner"] or value["owner_before"]["tenant"] != value["owner_after"]["tenant"]:
            raise ValueError("committed_owner_scope")
    if name == "FactRef" and value["source_kind"] != "synthetic_personal_memory": raise ValueError("fact_ref_kind")
    if name == "MemoryItem":
        validate_root("FactRef", value["source_ref"])
        if value["fact_id"] != value["source_ref"]["resource_id"]: raise ValueError("fact_ref_identity")
    if name == "MemoryPayload":
        if value["source_kind"] != "synthetic_personal_memory" or not value["facts"]: raise ValueError("memory_payload")
        for item in value["facts"]: validate_root("MemoryItem", item)
        if len({item["fact_id"] for item in value["facts"]}) != len(value["facts"]): raise ValueError("duplicate_memory_item")
    if name == "Context":
        if not value["participant_ids"] or len(value["participant_ids"]) != len(set(value["participant_ids"])): raise ValueError("context_participants")
    if name == "Eligibility": validate_root("Context", value["context"])
    if name == "OwnerState":
        validate_root("OwnerHeader", {k: value[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")})
        for fact in value["facts"]:
            validate_root("Fact", fact)
            if fact["owner"] != value["owner"] or fact["tenant"] != value["tenant"]: raise ValueError("owner_fact_scope")
    if name == "OwnerMeta":
        validate_root("OwnerHeader", {k: value[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")})
        for ref in value["stored_fact_refs"]: validate_root("FactRef", ref)
    if name == "ControlRecord":
        settled = value["status"] in {"inspected", "applied", "already_disabled", "failed", "cancelled"}
        if settled != (value["result"] is not None and value["result_digest"] is not None): raise ValueError("control_settlement")
        if value["result"] is not None:
            validate_root("ControlResponse", value["result"])
            from ..contracts import digest
            if digest(value["result"]) != value["result_digest"]: raise ValueError("control_result_digest")
    if name == "ErrorResult":
        if value["status"] not in {"error", "outcome_unknown"} or value["error"] not in SCALAR_DEFS["ErrorCode"]["enum"]:
            raise ValueError("error_result_enum")
        if value["field"] is not None and (not isinstance(value["field"], str) or re.fullmatch(r"/(?:[^~/]|~0|~1)*(?:/(?:[^~/]|~0|~1)*)*", value["field"]) is None):
            raise ValueError("error_result_pointer")
    if name == "InspectResult" and (value["operation"], value["status"]) != ("inspect", "inspected"): raise ValueError("inspect_result_stage")
    if name == "MutationResult":
        if value["operation"] not in {"forget", "clear", "disable_conversation", "fixture_set_enabled", "fixture_context_change"} or value["status"] not in {"applied", "already_disabled"}: raise ValueError("mutation_result_stage")
    if name == "ControlFinishedData":
        if value["operation"] not in SCALAR_DEFS["Operation"]["enum"] or value["status"] not in {"inspected", "applied", "already_disabled", "failed", "cancelled", "outcome_unknown", "replayed"}: raise ValueError("control_finished_stage")
    if name == "MemoryFaultHit":
        if value["kind"] not in {"load", "control"} or value["status"] not in {"completed", "failed", "cancelled", "not_reached"}: raise ValueError("fault_hit_stage")
    if name == "HostOutput":
        from ..contracts import digest
        if value["target_id"] != "secmate.synthetic-chatmate.fresh.v1" or value["target_version"] != VERSION or digest(value["response"]) != value["response_digest"]:
            raise ValueError("host_output_semantics")
    if name == "ControlAcceptedData":
        from ..contracts import digest
        if digest(value["body"]) != value["input_digest"]: raise ValueError("control_input_digest")
    if name == "ContextCreatedData":
        from ..contracts import digest
        validate_root("Context", value["context"])
        if digest(value["context"]) != value["context_digest"]: raise ValueError("context_digest")
    if name == "SnapshotRecord":
        from ..contracts import digest
        validate_root("Snapshot", value["snapshot"])
        if value["snapshot"]["status"] == "loaded" and value["candidate"] is None or value["snapshot"]["status"] != "loaded" and value["candidate"] is not None: raise ValueError("snapshot_candidate_stage")
        if digest(value["candidate"]) != value["snapshot"]["expected_payload_digest"]: raise ValueError("snapshot_candidate_digest")
    if name == "RestrictedMemoryState":
        for state in value["owner_states"]: validate_root("OwnerState", state)
        for context in value["contexts"]: validate_root("Context", context)
        for control in value["controls"]: validate_root("ControlRecord", control)
        for journal in value["journals"]: validate_root("MutationJournal", journal)
        for snapshot in value["snapshots"]: validate_root("SnapshotRecord", snapshot)
        for output in value["host_outputs"]: validate_root("HostOutput", output)
        validate_root("MemoryCounters", value["counters"])
        if value["fence"] is not None: validate_root("ControlFence", value["fence"])
    if name == "RequestBoundData" and (value["actual_present"] is None) != (value["actual_payload_digest"] is None): raise ValueError("request_binding_stage")
    return value
