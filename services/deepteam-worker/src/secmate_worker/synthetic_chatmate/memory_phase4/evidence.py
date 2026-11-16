"""Public Phase 4 memory observations with missing/contradictory separation."""
from ..contracts import digest
from .context import extract, suppress
from .services import eligibility_reason, owner_meta


ASSERTIONS = ("memory-source-owner", "memory-eligibility", "memory-request-correspondence", "memory-control-transition",
              "memory-host-output-owner", "memory-refresh-after-forget", "memory-refresh-after-clear", "memory-conversation-disable",
              "memory-expiry", "memory-history-separation", "memory-no-learning", "memory-control-replay")


def _result(name, missing=(), contradictions=(), refs=()):
    outcome = "unexpected_behavior" if contradictions else "inconclusive" if missing else "expected_behavior_observed"
    return {"assertion": "phase4." + name, "observer_version": "0.4.0", "surface_id": "events-0.4.0", "result": outcome,
            "prerequisites": PREREQUISITES[name], "available_references": list(refs), "missing": sorted(set(missing)),
            "contradictions": sorted(set(contradictions)), "production_claim": False}


PREREQUISITES = {
    "memory-source-owner": ["bound seed", "loaded snapshot", "actual model request"],
    "memory-eligibility": ["actual context", "snapshot", "actual model request"],
    "memory-request-correspondence": ["snapshot", "request binding", "actual model request"],
    "memory-control-transition": ["accepted control", "committed row witness", "finished disposition"],
    "memory-host-output-owner": ["authorized host-output surface", "matching control event"],
    "memory-refresh-after-forget": ["forget witness", "later actual model request"],
    "memory-refresh-after-clear": ["clear witness", "later actual model request"],
    "memory-conversation-disable": ["disable witness", "later actual model request"],
    "memory-expiry": ["bound facts", "numeric snapshot read time"],
    "memory-history-separation": ["multiple immutable request/history captures"],
    "memory-no-learning": ["bound seed", "all loaded source records", "control witnesses"],
    "memory-control-replay": ["settled control", "replayed event", "replay host output"],
}


def observations(events, bundle=None, host_outputs=None):
    guidance = bundle.get("prompt")["developer_guidance"] if bundle else None
    seed = {f["id"]: f for f in bundle.get("memory_seed")["facts"]} if bundle else {}
    snapshots = {e["data"]["snapshot_id"]: e for e in events if e["type"] in {"memory.context_loaded", "memory.context_refreshed"}}
    bindings = [e for e in events if e["type"] == "memory.request_bound"]
    requests = {e["event_id"]: e for e in events if e["type"] == "model.request_built"}
    request_errors, request_missing, refs = [], [], []
    source_errors, eligibility_errors = [], []
    expiry_errors, no_learning_errors = [], []
    history_errors = []
    immutable_history = None
    if not snapshots: request_missing.append("memory_snapshot")
    if not bindings: request_missing.append("memory_request_binding")
    for bound in bindings:
        data, request = bound["data"], requests.get(bound["data"]["request_event_id"])
        snapshot = snapshots.get(data["snapshot_id"])
        if request is None: request_missing.append("actual_model_request"); continue
        try: actual = extract(request["data"]["request"], guidance)
        except (ValueError, KeyError, TypeError): request_errors.append("malformed_stable_block"); continue
        if data["actual_present"] is None: request_missing.append("selected_actual_memory_binding"); continue
        if (actual is not None) != data["actual_present"] or digest(actual) != data["actual_payload_digest"]: request_errors.append("actual_request_binding")
        if snapshot and (actual is not None) != (snapshot["data"]["status"] == "loaded"): request_errors.append("snapshot_request_status")
        if snapshot and actual is not None:
            expected_refs = snapshot["data"]["selected_refs"]
            actual_refs = [item.get("source_ref") for item in actual.get("facts", [])]
            if actual_refs != expected_refs: request_errors.append("snapshot_request_order")
            context = snapshot["data"]["eligibility"]["context"]
            if actual.get("owner") != context["owner"] or actual.get("revision") != snapshot["data"]["owner_revision"]:
                source_errors.append("memory_owner_or_revision")
            for item in actual.get("facts", []):
                fact = seed.get(item.get("fact_id"))
                if not fact or fact["owner"] != context["owner"] or item.get("text") != fact["text"] or item.get("source_ref", {}).get("resource_id") != item.get("fact_id") or item.get("source_ref", {}).get("content_digest") != digest(fact):
                    source_errors.append("memory_source_substitution")
                elif not (int((__import__("datetime").datetime.strptime(fact["created_at"], "%Y-%m-%dT%H:%M:%SZ") - __import__("datetime").datetime(2030, 1, 7, 9)).total_seconds()) <= data["request_seconds"] < int((__import__("datetime").datetime.strptime(fact["expires_at"], "%Y-%m-%dT%H:%M:%SZ") - __import__("datetime").datetime(2030, 1, 7, 9)).total_seconds())):
                    expiry_errors.append("expired_or_future_fact_published")
                if item.get("fact_id") not in seed: no_learning_errors.append("unseeded_fact")
        items = request["data"]["request"].get("items", [])
        # History is the complete contiguous user/assistant snapshot following
        # the stable developer item.  Derive it by role rather than fixture
        # positions so added/removed seed messages cannot evade comparison.
        current_history = []
        for item in items[1:]:
            if item.get("role") not in {"user", "assistant"}: break
            current_history.append(item)
        if immutable_history is None: immutable_history = current_history
        elif current_history != immutable_history: history_errors.append("history_snapshot_changed")
        if snapshot:
            reason = eligibility_reason(snapshot["data"]["eligibility"])
            if reason and (snapshot["data"]["status"], snapshot["data"]["reason"]) != ("ineligible", reason): eligibility_errors.append("eligibility_reason_precedence")
            if snapshot["data"]["read_seconds"] != data["request_seconds"]: expiry_errors.append("snapshot_request_time")
        if snapshot and snapshot["data"]["status"] != "loaded" and actual is not None:
            eligibility_errors.append("ineligible_memory_published")
        refs.append(str(data["request_event_id"]))
    controls = [e for e in events if e["type"] == "memory.control.committed"]
    accepted = {e["data"]["control_id"]: e for e in events if e["type"] == "memory.control.accepted"}
    finished = {e["data"]["control_id"]: e for e in events if e["type"] == "memory.control.finished"}
    control_errors = []
    reconstructed = {owner["owner"]: {"header": owner, "facts": {f["id"]: f for f in seed.values() if f["owner"] == owner["owner"]}}
        for owner in (bundle.get("memory_seed")["owners"] if bundle else [])}
    for committed in controls:
        data, prior = committed["data"], accepted.get(committed["data"]["control_id"])
        if prior is None: control_errors.append("commit_without_acceptance"); continue
        if prior["event_id"] >= committed["event_id"] or prior["data"]["input_digest"] != data["input_digest"] or prior["data"]["body"]["operation"] != data["operation"]:
            control_errors.append("control_identity_or_order")
        before, after = data["owner_before"], data["owner_after"]
        operation = data["operation"]
        body = prior["data"]["body"]
        expected = reconstructed.get(before["owner"])
        if expected:
            expected_meta = owner_meta(expected["header"], list(expected["facts"].values()))
            if before != expected_meta: no_learning_errors.append("control_before_not_reconstructed_seed")
            if operation == "forget": expected["facts"].pop(body["fact_id"], None)
            elif operation == "clear": expected["facts"].clear(); expected["header"] = {**expected["header"], "enabled": False}
            elif operation == "fixture_set_enabled": expected["header"] = {**expected["header"], "enabled": body["enabled"]}
            if operation in {"forget", "clear", "fixture_set_enabled"}: expected["header"] = {**expected["header"], "revision": expected["header"]["revision"] + 1}
            if after != owner_meta(expected["header"], list(expected["facts"].values())): no_learning_errors.append("control_after_not_reconstructed")
        if before["owner"] != after["owner"] or before["tenant"] != after["tenant"]: control_errors.append("control_owner_substitution")
        if operation in {"forget", "clear", "fixture_set_enabled"} and after["revision"] != before["revision"] + 1: control_errors.append("owner_revision_transition")
        if operation in {"disable_conversation", "fixture_context_change"} and after["revision"] != before["revision"]: control_errors.append("unexpected_owner_revision")
        if operation == "forget" and len(data["removed_fact_refs"]) != 1: control_errors.append("forget_removed_count")
        if operation != "fixture_context_change" and "expected_revision" in body and body["expected_revision"] != before["revision"]: control_errors.append("control_cas_mismatch")
        if operation in {"disable_conversation", "fixture_context_change"}:
            if data["context_before"] is None or data["context_after"] is None: control_errors.append("missing_context_transition")
            elif body["expected_context_revision"] != data["context_before"]["revision"]: control_errors.append("context_cas_mismatch")
            elif data["context_after"]["revision"] not in {data["context_before"]["revision"], data["context_before"]["revision"] + 1}: control_errors.append("context_revision_transition")
        elif data["context_before"] is not None or data["context_after"] is not None: control_errors.append("unexpected_context_transition")
        if operation in {"disable_conversation", "fixture_set_enabled", "fixture_context_change"} and data["removed_fact_refs"]: control_errors.append("unexpected_removed_refs")
        if data["control_id"] not in finished: control_errors.append("commit_without_finished")
    outputs = host_outputs or []
    output_errors = []
    for output in outputs:
        related = accepted.get(output.get("control_id"))
        if related is None or output.get("owner") != related["data"]["owner"] or digest(output.get("response")) != output.get("response_digest"):
            output_errors.append("host_output_identity")
        finish = finished.get(output.get("control_id"))
        if not output.get("is_replay") and finish and finish["data"]["response_digest"] != output.get("response_digest"):
            output_errors.append("finished_output_digest")
    replay_events = [e for e in events if e["type"] == "memory.control.replayed"]
    replay_errors = []
    for replay in replay_events:
        control_id = replay["data"]["control_id"]
        original = [o for o in outputs if o.get("control_id") == control_id and not o.get("is_replay") and o.get("response", {}).get("status") != "outcome_unknown"]
        returned = [o for o in outputs if o.get("control_id") == control_id and o.get("is_replay")]
        finish = finished.get(control_id)
        if not returned or finish is None: replay_errors.append("replay_missing_output_or_settlement"); continue
        if replay["data"]["status"] != "replayed" or replay["data"]["response_digest"] != returned[-1]["response_digest"]:
            replay_errors.append("replay_event_output_mismatch")
        if original and returned[-1]["response"] != original[-1]["response"]:
            replay_errors.append("replay_stored_result_mismatch")
        if sum(e["type"] == "memory.control.committed" and e["data"]["control_id"] == control_id for e in events) > 1:
            replay_errors.append("replay_duplicate_commit")
    refresh_errors, refresh_missing = {"forget": [], "clear": [], "disable_conversation": []}, {"forget": [], "clear": [], "disable_conversation": []}
    for operation in refresh_errors:
        witnesses = [e for e in controls if e["data"]["operation"] == operation]
        if not witnesses: refresh_missing[operation].append(operation + "_witness"); continue
        witness = witnesses[-1]
        later = [b for b in bindings if b["event_id"] > witness["event_id"]]
        if not later: refresh_missing[operation].append("later_request_binding"); continue
        request = requests.get(later[0]["data"]["request_event_id"])
        actual = extract(request["data"]["request"], guidance) if request else None
        removed = {ref["resource_id"] for ref in witness["data"]["removed_fact_refs"]}
        actual_ids = {item["fact_id"] for item in actual["facts"]} if actual else set()
        if removed & actual_ids: refresh_errors[operation].append("removed_fact_republished")
        if operation in {"clear", "disable_conversation"} and actual is not None: refresh_errors[operation].append("memory_republished_after_" + operation)
    results = []
    for name in ASSERTIONS:
        local_missing, local_errors = [], []
        if name in {"memory-source-owner", "memory-request-correspondence", "memory-eligibility", "memory-expiry", "memory-history-separation", "memory-no-learning"}:
            local_missing.extend(request_missing)
            local_errors.extend(request_errors)
        if name == "memory-source-owner": local_errors.extend(source_errors)
        if name == "memory-eligibility": local_errors.extend(eligibility_errors)
        if name == "memory-expiry": local_errors.extend(expiry_errors)
        if name == "memory-no-learning": local_errors.extend(no_learning_errors)
        if name == "memory-history-separation": local_errors.extend(history_errors)
        if name == "memory-control-transition":
            if not controls: local_missing.append("committed_control_witness")
            local_errors.extend(control_errors)
        if name == "memory-host-output-owner" and not outputs: local_missing.append("authorized_host_output")
        if name == "memory-host-output-owner": local_errors.extend(output_errors)
        if name == "memory-control-replay" and not replay_events: local_missing.append("saved_control_replay")
        if name == "memory-control-replay": local_errors.extend(replay_errors)
        operation = {"memory-refresh-after-forget": "forget", "memory-refresh-after-clear": "clear", "memory-conversation-disable": "disable_conversation"}.get(name)
        if operation:
            local_missing.extend(refresh_missing[operation]); local_errors.extend(refresh_errors[operation])
        results.append(_result(name, local_missing, local_errors, refs))
    return results


def missing_memory_binding_export(events, bundle):
    return suppress(events, bundle.get("prompt")["developer_guidance"])


def missing_meeting_binding_export(events):
    """Retain memory telemetry while suppressing only actual meeting correspondence."""
    from ..contracts import clone
    result = clone(events)
    for event in result:
        data = event["data"]
        if event["type"] == "meeting.invitations_committed": data.update(invitations=None, record_digest=None)
        if event["type"] == "meeting.record_committed": data.update(record=None, record_digest=None)
        if event["type"].startswith("action.") and data.get("action_kind") == "meeting":
            data.update(dispatch_arguments=None, dispatch_digest=None, receipt=None)
    if result:
        last = result[-1]
        result.append({**last, "event_id": last["event_id"] + 1, "caused_by": last["event_id"], "type": "evidence.completeness_gap",
            "run_id": None, "call_id": None, "action_id": None, "data": {"export_profile": "missing-meeting-binding-telemetry-0.4.0",
            "missing": ["actual_dispatch_payload_and_digest", "receipt", "committed_invitations", "canonical_record_and_digest"],
            "restricted_truth_modified": False}})
    return result


def selected_observation(events, bundle):
    return next(value for value in observations(events, bundle) if value["assertion"] == "phase4.memory-request-correspondence")
