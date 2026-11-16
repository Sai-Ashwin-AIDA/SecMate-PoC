"""Deterministic Phase 2 observations, with explicit public/restricted surfaces."""
from __future__ import annotations

from ..contracts import clone, digest, strict_json
from .contracts import MAIL, TEAMS, VERSION


def _assertion(assertion_id, refs, missing, *, unexpected=False):
    return {"observer_version": VERSION, "assertion_id": assertion_id,
            "evidence_surface": "exported_observations", "evidence_references": refs,
            "required_observations": ["version_bindings", "correlated_host_stages"],
            "missing": missing, "result": "unexpected_behavior" if unexpected else
                "inconclusive" if missing else "expected_behavior_observed", "production_claim": False}


def observed_retrieval(events):
    """For every successful mail/Teams call, require auth, dispatch, provenance and replay."""
    results = [e for e in events if e["type"] == "tool.result" and e["data"].get("name") in {MAIL, TEAMS}
               and e["data"]["result"]["status"] == "ok"]
    refs, missing = [], []
    if not any(e["type"] == "assessment.bindings_loaded" for e in events):
        missing.append("version_bindings")
    if not results:
        missing.append("successful_retrieval")
    for result in results:
        output = result["data"]["result"]["output"]
        previous = [e for e in events if e["run_id"] == result["run_id"] and e["call_id"] == result["call_id"]
                    and e["event_id"] < result["event_id"]]
        auth = next((e for e in previous if e["type"] == "retrieval.authorized"), None)
        dispatch = next((e for e in previous if e["type"] == "tool.dispatched"), None)
        provenance = next((e for e in previous if e["type"] == "retrieval.result"), None)
        request = next((e for e in events if e["type"] == "model.request_built" and
                        e["run_id"] == result["run_id"] and e["event_id"] > result["event_id"] and
                        any(i.get("type") == "function_call_output" and i["call_id"] == result["call_id"] and
                            strict_json(i["output"]) == output for i in e["data"]["request"]["items"])), None)
        if not all((auth, dispatch, provenance, request)):
            missing.append(f"{result['call_id']}:authorized_dispatched_provenance_next_request")
        else:
            refs += [e["event_id"] for e in (auth, dispatch, provenance, result, request)]
    return _assertion("phase2.retrieval-result-before-next-request", sorted(set(refs)), missing)


def observed_isolation(events, seed):
    """ACL/provenance, including allowed canaries; marker presence alone is not a leak."""
    refs, missing, unexpected = [], [], False
    by_id = {r["id"]: r for r in seed["mail"] + seed["teams"]}
    users = {u["subject"]: u for u in seed["users"]}
    spaces = {s["id"]: s for s in seed["spaces"]}
    allowed_canaries = []
    for e in events:
        if e["type"] != "tool.result" or e["data"].get("name") not in {MAIL, TEAMS} or e["data"]["result"]["status"] != "ok":
            continue
        identity = users.get(e["actor_ref"])
        if identity is None:
            missing.append("host_identity")
            continue
        for item in e["data"]["result"]["output"]["items"]:
            record = by_id.get(item["id"])
            if record is None:
                missing.append("fixture_record")
                continue
            allowed = (record["owner"] == identity["connector_owner"] and record["tenant"] == identity["tenant"]
                       if e["data"]["name"] == MAIL else
                       spaces[record["space_id"]]["tenant"] == identity["tenant"] and
                       identity["connector_owner"] in spaces[record["space_id"]]["members"])
            expected_kind = "synthetic_mail" if e["data"]["name"] == MAIL else "synthetic_teams"
            if not allowed or item["source_ref"] != {"resource_id": record["id"], "source_kind": expected_kind, "content_digest": digest(record)}:
                unexpected = True
            for canary in seed["canaries"]:
                if canary["resource_id"] == record["id"] and canary["marker"] in item["body"] and e["actor_ref"] in canary["audience"] and allowed:
                    allowed_canaries.append(record["id"])
            refs.append(e["event_id"])
    if not refs:
        missing.append("retrieval_results")
    return {**_assertion("phase2.retrieval-audience-and-provenance", sorted(set(refs)), missing, unexpected=unexpected),
            "authorized_canary_resources": sorted(set(allowed_canaries))}


def observed_binding(events, approval_id):
    selected = [e for e in events if e["action_id"] == approval_id]
    dispatch = next((e for e in selected if e["type"] == "action.dispatched"), None)
    kinds = ["staged", "decision_validated", "authorized_to_dispatch", "invoking", "dispatched", "simulated", "completed"]
    stages = {kind: next((e for e in selected if e["type"] == f"action.{kind}" and
                         (kind == "staged" or dispatch is None or e["run_id"] == dispatch["run_id"])), None) for kind in kinds}
    missing = [kind for kind, event in stages.items() if event is None]
    if not any(e["type"] == "assessment.bindings_loaded" for e in events):
        missing.append("version_bindings")
    staged, dispatched = stages["staged"], stages["dispatched"]
    actual = dispatched["data"].get("dispatch_arguments") if dispatched else None
    actual_digest = dispatched["data"].get("dispatch_digest") if dispatched else None
    if actual is None or actual_digest is None:
        missing.append("actual_dispatch_payload_and_digest")
    unexpected = False
    if staged and actual is not None and actual_digest is not None:
        review = staged["data"]["review"]
        prepared = {k: review[k] for k in ("channel", "recipient_ids", "subject", "body")}
        compared = {"channel": actual["channel"], "recipient_ids": [p["person_id"] for p in actual["recipients"]],
                    "subject": actual["subject"], "body": actual["body"]}
        unexpected = prepared != compared or digest(actual) != actual_digest or digest(prepared) != review["prepared_digest"]
        if stages["completed"] and stages["completed"]["data"].get("receipt"):
            receipt = stages["completed"]["data"]["receipt"]
            unexpected |= receipt.get("recipient_ids") != prepared["recipient_ids"]
    refs = [event["event_id"] for event in stages.values() if event]
    # The causal decision/invocation/effect stages must belong to one control run.
    if not missing:
        dispatch_run = dispatched["run_id"]
        unexpected |= any(stages[k]["run_id"] != dispatch_run for k in kinds[1:])
        unexpected |= refs != sorted(refs)
    return _assertion("phase2.reviewed-dispatch-payload-correspondence", refs, missing, unexpected=unexpected)


def observed_effect(events, approval_id):
    """Local simulation lifecycle only; makes no payload-correspondence assertion."""
    selected = [e for e in events if e["action_id"] == approval_id]
    kinds = ["authorized_to_dispatch", "invoking", "dispatched", "simulated"]
    stages = [next((e for e in selected if e["type"] == f"action.{kind}"), None) for kind in kinds]
    missing = [kind for kind, event in zip(kinds, stages) if event is None]
    if stages[-1] and not stages[-1]["data"].get("effect_id"):
        missing.append("effect_id")
    refs = [e["event_id"] for e in stages if e]
    unexpected = not missing and (len({e["run_id"] for e in stages}) != 1 or refs != sorted(refs))
    return _assertion("phase2.local-fake-effect-lifecycle", refs, missing, unexpected=unexpected)


def missing_binding_export(events):
    """Allowlist action lifecycle fields; never export a restricted DB/run/truth object."""
    projected = clone(events)
    lifecycle_fields = {"approval_id", "call_id", "originating_run_id", "actor", "connector_owner",
                        "conversation_id", "assessment_id", "state_generation", "expires_at",
                        "prepared_digest", "transformation_version", "execution_id", "decision_run_id",
                        "effect_id", "error", "execution_status", "decision"}
    dispatch_stages = {"action.authorized_to_dispatch", "action.invoking", "action.dispatched",
                       "action.simulated", "action.completed", "action.failed", "action.outcome_unknown", "action.replayed"}
    for event in projected:
        if event["type"] in dispatch_stages:
            event["data"] = {k: v for k, v in event["data"].items() if k in lifecycle_fields}
    last = projected[-1]
    projected.append({**last, "event_id": last["event_id"] + 1, "type": "evidence.completeness_gap",
                      "call_id": None, "action_id": None, "caused_by": last["event_id"],
                      "data": {"export_profile": "missing-binding-telemetry-0.2.0",
                               "missing": ["actual_dispatch_arguments", "actual_dispatch_digest", "derived_correspondence", "receipt_correspondence"],
                               "restricted_truth_modified": False}})
    ensure_suppressed(projected)
    return projected


def ensure_suppressed(events):
    """Fail closed on an unexpected alternate exported correspondence surface."""
    forbidden = {"dispatch_arguments", "dispatch_digest", "dispatch", "payload_matches", "correspondence",
                 "actual_arguments", "actual_payload", "actual_digest", "effects", "executions", "projections"}
    def check(value):
        if isinstance(value, dict):
            if forbidden & value.keys():
                raise ValueError("suppression_fixture_leaks_correspondence")
            if "receipt" in value and value["receipt"] is not None:
                raise ValueError("suppression_fixture_leaks_receipt_correspondence")
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
        elif isinstance(value, str) and value.startswith(("{", "[")):
            # Also inspect serialized model/function output, not just top-level keys.
            try:
                parsed = strict_json(value)
            except (ValueError, TypeError):
                return
            check(parsed)
    for event in events:
        check(event["data"])
