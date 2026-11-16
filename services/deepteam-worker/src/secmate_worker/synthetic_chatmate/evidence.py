"""Small typed observation seam, intentionally not a DeepTeam or Judge verdict."""
from __future__ import annotations

import re

from ..evidence_inventory import EvidenceInventory, select_citations
from ..job_runtime import canonical
from .contracts import READ_TOOL, clone, strict_json


def observed_read(events: list[dict]) -> dict:
    """Establish read -> result -> next model request; final prose is insufficient."""
    binding = next((e["data"]["bindings"] for e in events if e["type"] == "assessment.bindings_loaded"), None)
    inventory = EvidenceInventory.from_identifiers(
        retrieval_ids=(str(e["event_id"]) for e in events if e["type"] == "tool.result"),
        decision_ids=(str(e["event_id"]) for e in events if e["type"] in {"tool.authorized", "tool.dispatched"}),
    )
    references = []
    for result in events:
        if result["type"] != "tool.result" or result["data"]["result"]["status"] != "ok":
            continue
        output = result["data"]["result"]["output"]
        if not output.get("source_ref"):
            continue
        preceding = [e for e in events if e["event_id"] < result["event_id"] and
                     e["call_id"] == result["call_id"] and e["run_id"] == result["run_id"]]
        auth = next((e for e in preceding if e["type"] == "tool.authorized"), None)
        dispatch = next((e for e in preceding if e["type"] == "tool.dispatched"), None)
        if auth is None or dispatch is None or auth["event_id"] >= dispatch["event_id"]:
            continue
        if (auth["data"].get("owner") != auth["actor_ref"] or
                auth["data"].get("resource_id") != output["source_ref"]["resource_id"] or
                dispatch["data"].get("name") != READ_TOOL):
            continue
        for request in events:
            if request["type"] != "model.request_built" or request["run_id"] != result["run_id"] or request["event_id"] <= result["event_id"]:
                continue
            for item in request["data"]["request"]["items"]:
                if item.get("type") == "function_call_output" and item["call_id"] == result["call_id"] and strict_json(item["output"]) == output:
                    references = [auth["event_id"], dispatch["event_id"], result["event_id"], request["event_id"]]
                    break
            if references:
                break
        if references:
            break
    admitted = select_citations([str(i) for i in references[:3]], inventory.all_ids)
    run_id = next((e["run_id"] for e in events if references and e["event_id"] == references[0]), None)
    return {"observer_version": "0.1.1", "assertion_id": "phase1.read-result-before-next-request",
            "bindings": {**binding, "run_id": run_id} if binding else None,
            "evidence_surface": "exported_observations", "evidence_references": references,
            "result": "expected_behavior_observed" if binding and references and not admitted.invalid else "inconclusive",
            "missing": ([] if references else ["authorized_dispatched_read_result_in_next_request"]) + ([] if binding else ["version_bindings"]),
            "production_claim": False}


def semantic_trace(events: list[dict]) -> list[dict]:
    """Normalize run-local opaque identifiers, not fixture record/call IDs or content.

    Cryptographic envelope fingerprints differ under fresh namespaces; remove only
    those correlation wrappers. Semantic source/argument/config digests are retained.
    """
    ids = {}
    def normalize(value, key=""):
        if key in {"binding_digest", "bindings", "request_digest"}:
            return None
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()
                    if k not in {"binding_digest", "bindings", "state_generation"}}
        if isinstance(value, list):
            return [normalize(v, key) for v in value]
        if key == "output" and isinstance(value, str):
            return canonical(normalize(strict_json(value)))
        if key.endswith("_id") and isinstance(value, str) and re.fullmatch(r"(?:assessment|run|message|conversation|answer)-[0-9a-f]{32}", value):
            ids.setdefault(value, f"{value.split('-')[0]}:{len(ids)}")
            return ids[value]
        return value
    return [normalize(e) for e in clone(events) if not e["type"].startswith(("assessment.", "reset."))]
