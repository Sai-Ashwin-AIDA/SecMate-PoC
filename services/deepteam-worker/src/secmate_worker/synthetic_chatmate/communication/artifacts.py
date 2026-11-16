"""Append-only 0.2.0 definitions; old modules and definition readers are untouched."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ...job_runtime import canonical
from ..artifacts import Bundle, verify_source_inputs
from ..contracts import READ_TOOL, Script, SyntheticError, digest, strict_json
from .contracts import (
    ActionDecision, Approval, CommunicationBudget, DecisionOutput, DirectChat,
    DirectoryMatch, Dispatch, Effect, Event, Execution, INPUTS, MailRecord,
    OUTPUTS, Person, SourceRef, Space, TeamsRecord, ToolError, ToolResult, VERSION,
)

# Canonical SHA-256 of the actual versioned files, independent of old artifacts.
DATA_DIGESTS = {
    "seed": "17a36ba8710a70089fa4c15bd6d51ed3917542e9704f45ba0a7f7df2b81f063f",
    "scripts": "852152a3ecb9ab079c14f785ee1248338a459ed78fd563308f54325c9b312e96",
    "capabilities": "535d3992ad6ba09d6fe215dddc8cef8e3a5dd8a1cbdd5e1a85ed4c73f8a0fd1d",
    "prompt": "accd28194d7b3b17ebcff4c5418c3be347b48a8063a6b320eb3374561035e321",
    "baseline": "270732225723de435180494776643f2427525cec570a82d089447d07b3a4d32c",
}


class CommunicationBundle(Bundle):
    @classmethod
    def load(cls, repository: Path | None = None, *, scenario="B02"):
        if repository is not None:
            verify_source_inputs(repository)
        old = Bundle.load(repository)
        parts = {k: strict_json(v) for k, v in old.artifacts}
        data = Path(__file__).parent / "data"
        for name in ("seed", "scripts", "capabilities", "prompt", "baseline"):
            parts[name] = strict_json((data / f"{name}.json").read_text(encoding="utf-8"))
            if name in DATA_DIGESTS and digest(parts[name]) != DATA_DIGESTS[name]:
                raise SyntheticError("communication_binding_mismatch")
        if scenario not in parts["scripts"]:
            raise SyntheticError("unknown_scenario")
        parts["scenario_id"] = scenario
        parts["script"] = parts["scripts"][scenario]
        parts["budget"] = CommunicationBudget().model_dump()
        parts["schemas"].update({
            "tools": {name: {"input": INPUTS[name].model_json_schema(),
                              "output": OUTPUTS[name].model_json_schema(),
                              "error": ToolError.model_json_schema()} for name in INPUTS},
            "decision_input": ActionDecision.model_json_schema(),
            "decision_output": DecisionOutput.model_json_schema(),
            "tool_result": ToolResult.model_json_schema(), "event": Event.model_json_schema(),
            "approval": Approval.model_json_schema(), "execution": Execution.model_json_schema(),
            "effect": Effect.model_json_schema(), "dispatch": Dispatch.model_json_schema(),
            "source_ref": SourceRef.model_json_schema(),
        })
        old_native = parts["native_metadata"]
        parts["native_metadata"] = {READ_TOOL: old_native}
        labels = {"secmate.search_mail": (None, "mail read/summary family", "7,10–11"),
                  "secmate.read_teams": (None, "dynamic Teams/chat read family", "7,10–11"),
                  "secmate.search_directory": ("people_search", "recognized_provider_operation", "10–11"),
                  "secmate.propose_message": (["mail_send", "chat_message_send"], "recognized_provider_operations", "7,10,14"),
                  "secmate.action.decide": ("ConnectorApprovalRequest", "host_control_schema", "7,10,14")}
        for name, (label, kind, section) in labels.items():
            parts["native_metadata"][name] = {
                "normalized_name": name, "normalized_schema_version": "synchat-tools-0.2.0",
                "native_label": label, "label_kind": kind, "native_schema_status": "unknown",
                "native_schema": None, "unknown_fields": "Complete external model-facing input/output/error schema UNKNOWN",
                "source_refs": [f"Documents/chatmate_mapper.md sections {section}"],
                "source_revision": old_native["source_revision"], "mapper_blob_id": old_native["mapper_blob_id"],
                "confidence": "CONFIRMED family/operation; external schema UNKNOWN",
                "transformation_notes": parts["baseline"]["transformation"] +
                    " Source connector writes may use kernel validate=False; this complete downstream synthetic DTO does not assert native kernel validation.",
            }
        parts["policy"] = {"version": VERSION, "snapshot_owner": "exact_host_subject",
                           "mail": "connector_owner", "teams": "tenant_and_explicit_membership",
                           "directory": "active_same_tenant_exact_or_ambiguous",
                           "write": "stored_review_then_owner_conversation_generation_decision",
                           "transformation_version": "message-local-v1", "lifetime": 600}
        parts["comparison"] = {"version": VERSION, "assertions": ["retrieval-isolation", "payload-correspondence"],
                               "surface": "exported_observations", "missing": "inconclusive", "production_claim": False}
        parts["event_schema"]["version"] = VERSION
        parts["implementation"] = {
            **{f"phase1/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(Path(__file__).parents[1].glob("*.py"))},
            **{f"communication/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(Path(__file__).parent.glob("*.py"))},
        }
        return cls.from_parts(parts)

    @classmethod
    def from_parts(cls, parts):
        Script.model_validate(parts["script"])
        CommunicationBudget.model_validate(parts["budget"])
        if parts["baseline"]["phases"] != [0, 1, 2] or parts["baseline"]["defects"]:
            raise SyntheticError("fixture_scope_not_supported")
        expected = {READ_TOOL, *INPUTS}
        if set(parts["capabilities"]["enabled"]) != expected:
            raise SyntheticError("capability_not_supported")
        for name, entry in parts["capabilities"]["enabled"].items():
            pool = "fake_provider_read" if name in {"secmate.search_mail", "secmate.read_teams", "secmate.search_directory"} else "execution"
            if entry != {"pool": pool, "control": False, "effect": "write" if name == "secmate.propose_message" else "read",
                         "handler_version": "0.1.1" if name == READ_TOOL else VERSION}:
                raise SyntheticError("capability_not_supported")
        for name in INPUTS:
            schemas = parts["schemas"]["tools"].get(name)
            if schemas != {"input": INPUTS[name].model_json_schema(), "output": OUTPUTS[name].model_json_schema(),
                           "error": ToolError.model_json_schema()}:
                raise SyntheticError("schema_binding_mismatch")
        for key, model in {"decision_input": ActionDecision, "decision_output": DecisionOutput, "tool_result": ToolResult,
                           "event": Event, "approval": Approval, "execution": Execution, "effect": Effect,
                           "dispatch": Dispatch, "source_ref": SourceRef}.items():
            if parts["schemas"][key] != model.model_json_schema():
                raise SyntheticError("schema_binding_mismatch")
        validators = {"people": Person, "mail": MailRecord, "spaces": Space,
                      "teams": TeamsRecord, "chats": DirectChat}
        for collection, model in validators.items():
            values = [model.model_validate(v) for v in parts["seed"][collection]]
            key = "person_id" if collection == "people" else "id"
            ids = [getattr(v, key) for v in values]
            if len(ids) != len(set(ids)):
                raise SyntheticError("invalid_fixture")
        seed = parts["seed"]
        if len({u["subject"] for u in seed["users"]}) != len(seed["users"]):
            raise SyntheticError("invalid_fixture")
        for user in seed["users"]:
            if sum((p["subject"], p["connector_owner"], p["tenant"]) ==
                   (user["subject"], user["connector_owner"], user["tenant"]) for p in seed["people"]) != 1:
                raise SyntheticError("invalid_fixture")
        if any(s["owner"] not in {u["subject"] for u in seed["users"]} for s in seed["snapshots"]):
            raise SyntheticError("invalid_fixture")
        parts["record_digests"] = {
            collection: {r.get("person_id", r.get("id")): digest(r) for r in seed[collection]}
            for collection in ("people", "mail", "spaces", "teams", "chats")}
        records = {r["id"]: r for r in seed["mail"] + seed["teams"]}
        parts["canary_catalog"] = [{**c, "marker_digest": digest(c["marker"]),
                                    "record_digest": digest(records[c["resource_id"]]),
                                    "owner_resource": records[c["resource_id"]].get("owner", records[c["resource_id"]].get("space_id")),
                                    "seed_version": seed["seed_id"]} for c in seed["canaries"]]
        return cls(tuple((key, canonical(value)) for key, value in sorted(parts.items())))

    def conformance(self, *, script=None, budget=None, seed=None):
        parts = {k: strict_json(v) for k, v in self.artifacts}
        for name, value in (("script", script), ("seed", seed), ("budget", budget.model_dump() if budget else None)):
            if value is not None:
                parts[name] = value
        parts["baseline"]["fixture_id"] = "communication-negative-conformance-0.2.0"
        parts["scenario_id"] = "negative-conformance"
        return self.from_parts(parts)

    def bindings(self, faults, assessment_id, generation):
        result = super().bindings(faults, assessment_id, generation)
        for key in ("target_version", "policy_version", "prompt_version", "event_schema_version",
                    "observer_version", "runner_version", "fixture_version"):
            result[key] = VERSION
        result.update(native_metadata_version="native-map-0.2.0", normalized_schema_version="synchat-tools-0.2.0",
                      scenario_id=self.get("scenario_id"), script_digest=digest(self.get("script")),
                      transformation_version="message-local-v1")
        return result
