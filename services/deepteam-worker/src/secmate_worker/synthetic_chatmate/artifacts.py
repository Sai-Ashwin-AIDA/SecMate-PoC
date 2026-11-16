"""Content-bound input artifacts; no registry/UI mutation or source ingestion prompt."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    Budget, ConversationRead, Listing, MAPPER_BLOB, MANIFESTO_BLOB,
    MessageCreate, MessagePage, READ_TOOL, SOURCE_REVISION, Script, ToolCall, EvidenceEvent, ErrorOutput,
    ToolResult, TARGET_ID, TARGET_VERSION, SyntheticError, clone, digest, strict_json,
)

BASELINE_DIGESTS = {
    "seed": "d3edb15e0db3f1e5a4a1395f5131778ad729cf26631e45bf5f05a8381cd665ba",
    "script": "766feb2622d172e23479f09e81bd02232f460949c71c3c88c8340adacbc8a817",
    "capabilities": "f698f0431bd2d40883a03e589fac818ee066e93dd077e029871f8191e4d14f6f",
    "prompt": "e93c5f374d147b37feb05951c1fc6efeec201044a4e71226c18e784e250718fd",
    "baseline": "6472e8210654367c24e5d97d035f5b7cec28e8f943be26fcc1ab25cca3f87b60",
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def verify_source_inputs(repository: Path) -> dict:
    expected = {"chatmate_mapper.md": MAPPER_BLOB, "synthetic_chatmate_manifesto.md": MANIFESTO_BLOB}
    result = {}
    for name, expected_blob in expected.items():
        actual = git_blob((repository / "Documents" / name).read_bytes())
        if actual != expected_blob:
            raise SyntheticError("source_binding_mismatch")
        result[name] = actual
    return result


@dataclass(frozen=True)
class Bundle:
    """Canonical byte snapshots; accessors return copies, never mutable truth."""

    artifacts: tuple[tuple[str, str], ...]

    @classmethod
    def load(cls, repository: Path | None = None) -> Bundle:
        if repository is not None:
            verify_source_inputs(repository)
        data = Path(__file__).parent / "data"
        parts = {name: strict_json((data / f"{name}.json").read_text(encoding="utf-8"))
                 for name in ("seed", "script", "capabilities", "prompt", "baseline")}
        if any(digest(parts[name]) != expected for name, expected in BASELINE_DIGESTS.items()):
            raise SyntheticError("baseline_binding_mismatch")
        parts["budget"] = Budget().model_dump()
        parts["schemas"] = {
            "message": MessageCreate.model_json_schema(), "call": ToolCall.model_json_schema(),
            "read_input": ConversationRead.model_json_schema(),
            "listing": Listing.model_json_schema(), "message_page": MessagePage.model_json_schema(),
            "tool_result": ToolResult.model_json_schema(), "script": Script.model_json_schema(),
            "event": EvidenceEvent.model_json_schema(),
            "error_output": ErrorOutput.model_json_schema(),
        }
        parts["native_metadata"] = {
            "normalized_name": READ_TOOL, "normalized_schema_version": "synchat-tools-0.1.1",
            "native_label": "conversation_read", "label_kind": "exact_model_facing_name",
            "native_schema_status": "partial_projection",
            "native_schema": {"type": "object", "required": ["message_id", "offset"],
                              "additionalProperties": False,
                              "properties": {"message_id": {"type": ["string", "null"]},
                                             "offset": {"type": "integer", "minimum": 0}}},
            "source_refs": ["Documents/chatmate_mapper.md#10-native-contracts-and-partial-tool-inventory",
                            "services/chatmate-api/src/chatmate_api/agents/context_tools.py:conversation_read"],
            "source_revision": SOURCE_REVISION, "mapper_blob_id": MAPPER_BLOB,
            "confidence": "CONFIRMED", "transformation_notes": "Synthetic output, code-point paging; no files or native alias.",
        }
        parts["policy"] = {"version": "0.1.1", "owner": "exact_host_subject",
                           "ordinary_snapshot": "owner_and_non_deleted", "mutations": "disabled"}
        parts["comparison"] = {"version": "0.1.1", "ids": "semantic-first-occurrence",
                               "clock": "logical-offset", "verdict": "no-production-claim"}
        parts["event_schema"] = {"version": "0.1.0", "envelope": [
            "event_schema_version", "target_id", "target_version", "assessment_id", "state_generation",
            "run_id", "event_id", "logical_time", "type", "actor_ref", "call_id", "action_id",
            "caused_by", "data", "binding_digest"]}
        parts["implementation"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(Path(__file__).parent.glob("*.py"))}
        return cls.from_parts(parts)

    @classmethod
    def from_parts(cls, parts: dict) -> Bundle:
        from ..job_runtime import canonical
        Script.model_validate(parts["script"])
        Budget.model_validate(parts["budget"])
        if parts["baseline"]["defects"] or parts["baseline"]["phases"] != [0, 1]:
            raise SyntheticError("fixture_scope_not_supported")
        if set(parts["capabilities"]["enabled"]) != {READ_TOOL}:
            raise SyntheticError("capability_not_supported")
        enabled = parts["capabilities"]["enabled"][READ_TOOL]
        if enabled != {"pool": "execution", "control": False, "effect": "read", "handler_version": "0.1.1"}:
            raise SyntheticError("capability_not_supported")
        users = parts["seed"]["users"]
        if len({u["subject"] for u in users}) != len(users):
            raise SyntheticError("invalid_fixture")
        ids = set()
        for snap in parts["seed"]["snapshots"]:
            if snap["id"] in ids or snap["owner"] not in {u["subject"] for u in users}:
                raise SyntheticError("invalid_fixture")
            ids.add(snap["id"])
            mids = set()
            for msg in snap["messages"]:
                if msg["message_id"] in mids or msg["role"] not in {"user", "assistant"}:
                    raise SyntheticError("invalid_fixture")
                mids.add(msg["message_id"])
        return cls(tuple((key, canonical(value)) for key, value in sorted(parts.items())))

    def get(self, name: str):
        return strict_json(dict(self.artifacts)[name])

    def conformance(self, *, script: dict | None = None, budget: Budget | None = None,
                    seed: dict | None = None) -> Bundle:
        parts = {key: strict_json(value) for key, value in self.artifacts}
        if script is not None:
            parts["script"] = script
        if budget is not None:
            parts["budget"] = budget.model_dump()
        if seed is not None:
            parts["seed"] = seed
        parts["baseline"]["fixture_id"] = "phase1-conformance-0.1.1"
        return self.from_parts(parts)

    def bindings(self, faults: dict, assessment_id: str, generation: int) -> dict:
        hashes = {key: digest(strict_json(value)) for key, value in self.artifacts}
        return {
            "target_id": TARGET_ID, "target_version": TARGET_VERSION, "manifesto_version": "0.1.2",
            "source_revision": SOURCE_REVISION, "mapper_blob_id": MAPPER_BLOB,
            "manifesto_blob_id": MANIFESTO_BLOB, "native_metadata_version": "native-map-0.1.0",
            "normalized_schema_version": "synchat-tools-0.1.1", "policy_version": "0.1.1",
            "prompt_version": "0.1.0", "event_schema_version": "0.1.0", "observer_version": "0.1.1",
            "runner_version": "0.1.1", "fixture_id": self.get("baseline")["fixture_id"],
            "runner_digest": hashes["implementation"],
            "fixture_version": "0.1.1", "fixture_digest": digest(hashes),
            "capability_manifest_digest": hashes["capabilities"],
            "budget_profile_id": self.get("budget")["profile_id"], "budget_config_digest": hashes["budget"],
            "comparison_rules_digest": hashes["comparison"], "artifact_digests": hashes,
            "seed": self.get("seed")["seed_id"], "clock_origin": self.get("seed")["clock_origin"],
            "fault_schedule_digest": digest(faults), "model_mode": "scripted",
            "model_binding": hashes["script"], "generation_parameters": {"inference": False},
            "assessment_id": assessment_id, "state_generation": generation,
        }
