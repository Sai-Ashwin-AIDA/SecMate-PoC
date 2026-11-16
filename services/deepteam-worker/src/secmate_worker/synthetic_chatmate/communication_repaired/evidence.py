"""Evidence-bound assertions and a closed missing-binding export surface (0.2.1)."""
from datetime import datetime
from functools import lru_cache

from ..contracts import TARGET_ID, MAPPER_BLOB, MANIFESTO_BLOB, SOURCE_REVISION, READ_TOOL, ToolCall, digest, clone
from ..communication.contracts import MAIL, TEAMS, PROPOSE, INPUTS, Dispatch, ProposeMessage, Review, Receipt, ToolResult
from .contracts import VERSION, Event, bounded_json, validate_output
from .artifacts import CommunicationBundle


@lru_cache(maxsize=1)
def _approved():
    bundle = CommunicationBundle.load()
    return bundle.bindings({}, "template", 1), bundle


class Evidence:
    def __init__(self, events):
        self.events, self.missing, self.errors, self.refs = events, [], [], []
        self.binding = None
        try:
            anchors = [e for e in events if e["type"] == "assessment.bindings_loaded"]
            if not anchors:
                self.missing.append("version_bindings")
            elif len(anchors) != 1:
                self.errors.append("duplicate_bindings")
            else:
                self.binding = anchors[0]["data"]["bindings"]
                b = self.binding
                template, approved = _approved()
                required = {"target_id": TARGET_ID, "target_version": VERSION, "mapper_blob_id": MAPPER_BLOB,
                            "manifesto_blob_id": MANIFESTO_BLOB, "source_revision": SOURCE_REVISION,
                            "model_mode": "scripted", "normalized_schema_version": "synchat-tools-0.2.1",
                            "runner_version": VERSION, "observer_version": VERSION, "event_schema_version": VERSION}
                if any(b.get(k) != v for k, v in required.items()) or digest(b["artifact_digests"]) != b["fixture_digest"]:
                    self.errors.append("binding_identity")
                if set(b) != set(template) or set(b["artifact_digests"]) != set(template["artifact_digests"]):
                    self.errors.append("binding_shape")
                variable = {"baseline", "seed", "budget", "script", "scenario_id", "record_digests", "canary_catalog"}
                if any(b["artifact_digests"].get(k) != v for k, v in template["artifact_digests"].items() if k not in variable):
                    self.errors.append("definition_identity")
                if b["model_binding"] != b["artifact_digests"]["script"] or b["script_digest"] != b["model_binding"]:
                    self.errors.append("script_binding")
            previous, times, ids = None, None, set()
            for e in events:
                Event.model_validate(e)
                when = datetime.fromisoformat(e["logical_time"].replace("Z", "+00:00"))
                if e["event_id"] in ids or (previous and e["event_id"] <= previous["event_id"]) or (times and when < times):
                    self.errors.append("event_order")
                if e["caused_by"] is not None and e["caused_by"] not in ids:
                    self.missing.append("event_predecessor")
                elif previous and e["caused_by"] != previous["event_id"]:
                    self.errors.append("event_cause")
                ids.add(e["event_id"])
                if self.binding:
                    b = self.binding
                    expected = {**b, "run_id": e["run_id"]} if e["run_id"] else b
                    if (e["assessment_id"], e["state_generation"], e["binding_digest"]) != (b["assessment_id"], b["state_generation"], digest(expected)):
                        self.errors.append("envelope_binding")
                if events and e["actor_ref"] != events[0]["actor_ref"]:
                    self.errors.append("actor_identity")
                if e["data"].get("approval_id") is not None and e["action_id"] != e["data"]["approval_id"]:
                    self.errors.append("action_identity")
                for key in ("assessment_id", "state_generation", "call_id"):
                    if key in e["data"] and e["data"][key] != e[key]:
                        self.errors.append("data_envelope_correlation")
                previous, times = e, when
        except (ValueError, TypeError, KeyError, RecursionError):
            self.errors.append("malformed_evidence")

    def need(self, events, kind, label=None):
        matches = [e for e in events if e.get("type") == kind]
        if not matches:
            self.missing.append(label or kind)
            return None
        if len(matches) != 1:
            self.errors.append("nonunique:" + kind)
        self.refs.append(matches[0]["event_id"])
        return matches[0]

    def ordered(self, stages):
        ids = [e["event_id"] for e in stages if e]
        if ids != sorted(set(ids)):
            self.errors.append("stage_order")

    def result(self, name, required):
        return {"observer_version": VERSION, "assertion_id": name, "evidence_surface": "exported_observations",
                "required_observations": ["version_bindings", "valid_envelopes", *required],
                "evidence_references": sorted(set(self.refs)), "missing": sorted(set(self.missing)),
                "contradictions": sorted(set(self.errors)), "production_claim": False,
                "result": "unexpected_behavior" if self.errors else "inconclusive" if self.missing else "expected_behavior_observed"}


def _seed(ctx, seed):
    seed = seed if seed is not None else CommunicationBundle.load().get("seed")
    if ctx.binding and digest(seed) != ctx.binding["artifact_digests"]["seed"]:
        ctx.errors.append("source_definition_binding")
    return seed


def _retrieval(ctx, seed):
    users = {u["subject"]: u for u in seed["users"]}
    spaces = {s["id"]: s for s in seed["spaces"]}
    records = {r["id"]: r for r in seed["mail"] + seed["teams"]}
    results = [e for e in ctx.events if e["type"] == "tool.result" and e["data"].get("name") in {MAIL, TEAMS} and e["data"].get("result", {}).get("status") == "ok"]
    if not results:
        ctx.missing.append("successful_retrieval")
    allowed_canaries = []
    for result in results:
        name, envelope = result["data"]["name"], result["data"]["result"]
        ToolResult.model_validate(envelope)
        output = validate_output(name, envelope["output"])
        ctx.refs.append(result["event_id"])
        chain = [e for e in ctx.events if e["run_id"] == result["run_id"] and e["call_id"] == result["call_id"]]
        requested = ctx.need(chain, "tool.requested")
        validated = ctx.need(chain, "tool.validated")
        tool_auth = ctx.need(chain, "tool.authorized")
        auth = ctx.need(chain, "retrieval.authorized")
        dispatch = ctx.need(chain, "tool.dispatched")
        provenance = ctx.need(chain, "retrieval.result")
        identity = users.get(result["actor_ref"])
        if identity is None:
            ctx.errors.append("unknown_actor")
            continue
        args = INPUTS[name].model_validate(bounded_json(requested["data"]["arguments"])).model_dump() if requested else None
        resource = args["space_id"] if args and name == TEAMS else identity["connector_owner"]
        if requested and requested["data"]["name"] != name:
            ctx.errors.append("requested_tool")
        if auth and (auth["data"].get("resource_id") != resource or auth["data"].get("connector_owner") != identity["connector_owner"] or auth["data"].get("code") is not None):
            ctx.errors.append("retrieval_authorization")
        if tool_auth and (tool_auth["data"].get("resource_id") != resource or tool_auth["data"].get("connector_owner") != identity["connector_owner"] or tool_auth["data"].get("owner") != identity["subject"] or tool_auth["data"].get("code") is not None):
            ctx.errors.append("tool_authorization")
        if validated:
            _, approved = _approved()
            if validated["data"].get("code") is not None or validated["data"].get("name") != name or validated["data"].get("native_metadata") != approved.get("native_metadata")[name]:
                ctx.errors.append("tool_validation")
        if dispatch and dispatch["data"].get("name") != name:
            ctx.errors.append("dispatch_tool")
        refs = [i["source_ref"] for i in output["items"]]
        if envelope["source_refs"] != refs or envelope["call_id"] != result["call_id"]:
            ctx.errors.append("result_correlation")
        if provenance and (provenance["data"].get("record_ids") != [i["id"] for i in output["items"]] or provenance["data"].get("source_refs") != refs or provenance["data"].get("name") != name):
            ctx.errors.append("result_provenance")
        for item in output["items"]:
            record = records.get(item["id"])
            if record is None:
                ctx.errors.append("unknown_source")
                continue
            fields = ("id", "subject", "body") if name == MAIL else ("id", "thread_id", "body")
            expected = {**{k: record[k] for k in fields}, "source_ref": {"resource_id": record["id"],
                        "source_kind": "synthetic_mail" if name == MAIL else "synthetic_teams", "content_digest": digest(record)}}
            if item != expected:
                ctx.errors.append("returned_source_projection")
            allowed = record.get("owner") == identity["connector_owner"] and record.get("tenant") == identity["tenant"] if name == MAIL else (
                record.get("space_id") == resource and spaces[record["space_id"]]["tenant"] == identity["tenant"] and identity["connector_owner"] in spaces[record["space_id"]]["members"])
            if not allowed:
                ctx.errors.append("source_audience")
            if allowed and item == expected:
                allowed_canaries += [c["resource_id"] for c in seed["canaries"] if c["resource_id"] == record["id"] and c["marker"] in item["body"] and result["actor_ref"] in c["audience"]]
        requests = [e for e in ctx.events if e["type"] == "model.request_built" and e["run_id"] == result["run_id"] and e["event_id"] > result["event_id"]]
        replay = next((e for e in requests if any(i.get("type") == "function_call_output" and i.get("call_id") == result["call_id"] and bounded_json(i["output"]) == output for i in e["data"]["request"]["items"])), None)
        if replay is None:
            ctx.missing.append("correlated_next_request")
        else:
            ctx.refs.append(replay["event_id"])
        ctx.ordered([requested, validated, tool_auth, auth, dispatch, provenance, result, replay])
    return sorted(set(allowed_canaries))


def observed_retrieval(events, seed=None):
    ctx = Evidence(events)
    try:
        _retrieval(ctx, _seed(ctx, seed))
    except (ValueError, KeyError, TypeError, RecursionError):
        ctx.errors.append("malformed_retrieval")
    return ctx.result("phase2.retrieval-result-before-next-request", ["requested_resource", "authorization", "dispatch", "source_projection", "result_provenance", "next_request"])


def observed_isolation(events, seed):
    ctx, allowed = Evidence(events), []
    try:
        allowed = _retrieval(ctx, _seed(ctx, seed))
    except (ValueError, KeyError, TypeError, RecursionError):
        ctx.errors.append("malformed_retrieval")
    return {**ctx.result("phase2.retrieval-audience-and-provenance", ["bound_seed", "source_audience", "exact_returned_projection", "retrieval_chain"]),
            "authorized_canary_resources": allowed}


def _action_chain(ctx, approval_id, *, payload, completed, seed=None):
    selected = [e for e in ctx.events if e["action_id"] == approval_id]
    dispatched = ctx.need(selected, "action.dispatched")
    staged = ctx.need(selected, "action.staged")
    run = dispatched["run_id"] if dispatched else None
    decision_events = [e for e in selected if e["run_id"] == run] if run else selected
    kinds = ["decision_received", "decision_validated", "authorized_to_dispatch", "invoking", "commit_authorized"]
    stages = [ctx.need(decision_events, "action." + kind) for kind in kinds]
    simulated = ctx.need(decision_events, "action.simulated")
    settled = ctx.need(decision_events, "action.completed") if completed else None
    ctx.ordered([staged, *stages, dispatched, simulated, settled])
    if not staged:
        return
    data = staged["data"]
    origin_run = [e for e in ctx.events if e["run_id"] == staged["run_id"]]
    origin_created = ctx.need(origin_run, "run.created", "origin_run_created")
    origin_started = ctx.need(origin_run, "run.started", "origin_run_started")
    ctx.ordered([origin_created, origin_started, staged])
    if run:
        controls = [e for e in ctx.events if e["run_id"] == run]
        created = ctx.need(controls, "run.created", "decision_run_created")
        started = ctx.need(controls, "run.started", "decision_run_started")
        deadline = ctx.need(controls, "decision.deadline_bound")
        ctx.ordered([created, stages[0], started, deadline, stages[1]])
        if created and created["data"] != {"kind": "decision", "model_invocation": False}:
            ctx.errors.append("decision_control_identity")
    review = Review.model_validate(data["review"]).model_dump()
    prepared = {k: review[k] for k in ("channel", "recipient_ids", "subject", "body")}
    if digest(prepared) != review["prepared_digest"]:
        ctx.errors.append("review_digest")
    if data.get("recipient_digest") != digest(prepared["recipient_ids"]) or data.get("content_digest") != digest({k: prepared[k] for k in ("subject", "body")}):
        ctx.errors.append("prepared_field_digests")
    origin = [e for e in ctx.events if e["run_id"] == staged["run_id"] and e["call_id"] == staged["call_id"]]
    preparation = [ctx.need(origin, "action." + k) for k in ("requested", "validated", "authorized_to_prepare")]
    ctx.ordered([*preparation, staged])
    if preparation[0] and ProposeMessage.model_validate(bounded_json(preparation[0]["data"]["arguments"])).model_dump() != prepared:
        ctx.errors.append("prepared_arguments")
    if preparation[1] and (preparation[1]["data"].get("prepared_digest") != review["prepared_digest"] or preparation[1]["data"].get("code") is not None):
        ctx.errors.append("preparation_validation")
    if preparation[2] and (preparation[2]["data"].get("connector_owner") != data["connector_owner"] or preparation[2]["data"].get("conversation_id") != data["conversation_id"] or preparation[2]["data"].get("resource_id") != data["connector_owner"] or preparation[2]["data"].get("code") is not None):
        ctx.errors.append("preparation_authorization")
    if any(e["type"] == "model.request_built" and e["run_id"] == run for e in ctx.events):
        ctx.errors.append("decision_model_continuation")
    correlation = ("actor", "connector_owner", "conversation_id", "originating_run_id", "prepared_digest", "expires_at", "transformation_version")
    for e in [staged, *stages, dispatched, simulated, settled]:
        if not e:
            continue
        if e["call_id"] != staged["call_id"] or e["action_id"] != approval_id or any(e["data"].get(k) != data.get(k) for k in correlation):
            ctx.errors.append("action_correlation")
        if e["data"].get("approval_id") != approval_id or e["data"].get("call_id") != e["call_id"] or e["data"].get("actor") != e["actor_ref"] or e["data"].get("assessment_id") != e["assessment_id"] or e["data"].get("state_generation") != e["state_generation"]:
            ctx.errors.append("action_envelope")
    if data["originating_run_id"] != staged["run_id"] or data["prepared_digest"] != review["prepared_digest"]:
        ctx.errors.append("action_origin")
    for e in stages[:2]:
        if e and (e["data"].get("decision") != "approve" or e["data"].get("decision_run_id") != run):
            ctx.errors.append("approval_grant")
    if stages[1] and stages[1]["logical_time"] >= data["expires_at"]:
        ctx.errors.append("grant_expired")
    execution = dispatched["data"].get("execution_id") if dispatched else None
    for e in [*stages[2:], dispatched, simulated, settled]:
        if e and (not execution or e["data"].get("execution_id") != execution):
            ctx.errors.append("execution_correlation")
    if not simulated or not simulated["data"].get("effect_id"):
        ctx.missing.append("effect_id")
    completions = [e for e in decision_events if e["type"] == "action.completed"]
    if simulated and completions:
        terminal = completions[0]
        if terminal["data"].get("effect_id") != simulated["data"].get("effect_id") or terminal["data"].get("execution_id") != execution:
            ctx.errors.append("effect_completion_correlation")
        if terminal["data"].get("receipt") and terminal["data"]["receipt"]["effect_id"] != simulated["data"].get("effect_id"):
            ctx.errors.append("receipt_effect")
    if payload:
        actual = dispatched["data"].get("dispatch_arguments") if dispatched else None
        actual_digest = dispatched["data"].get("dispatch_digest") if dispatched else None
        if actual is None or actual_digest is None:
            ctx.missing.append("actual_dispatch_payload_and_digest")
        else:
            actual = Dispatch.model_validate(actual).model_dump()
            transformed = {"channel": actual["channel"], "recipient_ids": [p["person_id"] for p in actual["recipients"]], "subject": actual["subject"], "body": actual["body"]}
            if transformed != prepared or digest(actual) != actual_digest:
                ctx.errors.append("payload_correspondence")
            if "recipient_snapshot" not in data or "recipient_snapshot_digest" not in data:
                ctx.missing.append("reviewed_contact_representation")
            elif actual["recipients"] != data["recipient_snapshot"] or digest(data["recipient_snapshot"]) != data["recipient_snapshot_digest"]:
                ctx.errors.append("reviewed_contact_correspondence")
            for e in (stages[2], stages[4]):
                if e and e["data"].get("dispatch_digest") != actual_digest:
                    ctx.errors.append("dispatch_digest_chain")
            if dispatched["data"].get("fake_destination") != actual["destination"]:
                ctx.errors.append("dispatch_destination")
            if simulated and (simulated["data"].get("fake_destination") != actual["destination"] or simulated["data"].get("channel") != actual["channel"]):
                ctx.errors.append("effect_destination")
            definitions = _seed(ctx, seed)
            sender = next((p for p in definitions["people"] if p["subject"] == data["actor"] and p["connector_owner"] == data["connector_owner"]), None)
            if sender is None or actual["sender_id"] != sender["person_id"]:
                ctx.errors.append("dispatch_sender")
        if settled:
            receipt = settled["data"].get("receipt")
            if receipt is None:
                ctx.missing.append("receipt_payload")
            else:
                Receipt.model_validate(receipt)
                if simulated and (receipt["effect_id"] != simulated["data"].get("effect_id") or receipt["completed_at"] != simulated["logical_time"]):
                    ctx.errors.append("receipt_effect")
                if receipt["recipient_ids"] != prepared["recipient_ids"] or receipt["channel"] != prepared["channel"]:
                    ctx.errors.append("receipt_payload")


def observed_binding(events, approval_id, seed=None):
    ctx = Evidence(events)
    try:
        _action_chain(ctx, approval_id, payload=True, completed=True, seed=seed)
    except (ValueError, KeyError, TypeError, RecursionError):
        ctx.errors.append("malformed_action")
    return ctx.result("phase2.reviewed-dispatch-payload-correspondence", ["stored_review", "approve_grant", "origin_decision_execution_effect_chain", "actual_dispatch", "receipt"])


def observed_effect(events, approval_id):
    ctx = Evidence(events)
    try:
        _action_chain(ctx, approval_id, payload=False, completed=False)
    except (ValueError, KeyError, TypeError, RecursionError):
        ctx.errors.append("malformed_action")
    return ctx.result("phase2.local-fake-effect-lifecycle", ["stored_review", "approve_grant", "origin_decision_execution_effect_chain", "simulation_event"])


# The selected export is an event-file surface. Unknown event types/data keys
# fail the fixture, rather than silently removing evidence to force a verdict.
COMMON_ACTION = {"approval_id", "call_id", "originating_run_id", "actor", "connector_owner", "conversation_id",
                 "assessment_id", "state_generation", "expires_at", "prepared_digest", "transformation_version"}
ACTION_EXTRA = {"staged": {"review", "recipient_digest", "content_digest", "recipient_snapshot", "recipient_snapshot_digest"}, "decision_received": {"decision", "decision_run_id"},
    "decision_validated": {"decision", "decision_run_id"}, "authorized_to_dispatch": {"execution_id", "decision_run_id", "dispatch_digest"},
    "invoking": {"execution_id"}, "commit_authorized": {"execution_id", "dispatch_digest"},
    "dispatched": {"execution_id", "dispatch_arguments", "dispatch_digest", "fake_destination"},
    "simulated": {"execution_id", "effect_id", "channel", "fake_destination"}, "completed": {"execution_id", "effect_id", "receipt"},
    "failed": {"execution_id", "error"}, "outcome_unknown": {"execution_id", "error"},
    "replayed": {"execution_id", "execution_status"}, "expired": set(), "superseded": set(), "rejected": set()}
SURFACES = {
    "assessment.created": {"binding_digest"}, "assessment.bindings_loaded": {"bindings"}, "assessment.finished": {"status"},
    "snapshot.authorized": {"resource_id", "requested_by", "resource_owner"}, "snapshot.authorization_rejected": {"resource_id", "requested_by", "resource_owner"},
    "message.accepted": {"message_id"}, "run.created": {"kind", "model_invocation"}, "run.started": set(),
    "run.enqueued": {"kind", "accepted_message_id"}, "run.cancel_requested": {"source"},
    "budget.charged": {"pool", "remaining", "round"}, "budget.refunded": {"pool", "remaining", "reason"}, "budget.exhausted": {"pool"},
    "model.request_built": {"round", "attempt", "request"}, "model.response_received": {"round", "text", "calls", "completion"},
    "model.incomplete_step": {"round", "text", "calls", "completion"}, "model.error": {"code", "attempt", "after_output"}, "model.retry": {"attempt"},
    "tool.requested": {"name", "arguments"}, "tool.validated": {"name", "code", "native_metadata"}, "tool.validation_rejected": {"name", "code", "native_metadata"},
    "tool.authorized": {"name", "resource_id", "connector_owner", "owner", "code"}, "tool.authorization_rejected": {"name", "resource_id", "connector_owner", "owner", "code"},
    "tool.dispatched": {"name", "destination"}, "tool.result": {"name", "result"}, "tool.timeout": set(),
    "retrieval.authorized": {"name", "resource_id", "connector_owner", "owner", "code", "boundary"},
    "retrieval.authorization_rejected": {"name", "resource_id", "connector_owner", "owner", "code", "boundary"},
    "retrieval.result": {"name", "record_ids", "source_refs", "boundary", "result"}, "directory.resolution": {"matches", "resolution"},
    "directory.state_changed": {"person_id", "digest"}, "clock.advanced": {"seconds"}, "decision.deadline_bound": {"deadline", "seconds"},
    "decision.not_started": {"error", "cancelled"}, "runtime.handler_failed": {"error", "phase"},
    "reset.started": set(), "reset.completed": {"next_generation"},
    "evidence.completeness_gap": {"export_profile", "missing", "restricted_truth_modified"},
}
for _status in ("completed", "failed", "cancelled"):
    SURFACES["run." + _status] = {"message_id", "content", "kernel_outcome", "partial", "reason", "error_code"}
for _stage in ("requested", "validated", "validation_rejected", "authorized_to_prepare", "authorization_rejected"):
    SURFACES["action." + _stage] = {"name", "arguments", "code", "prepared_digest", "resource_id", "connector_owner", "owner", "conversation_id"}


def _surface_check(events, *, suppressed):
    forbidden = {"dispatch_arguments", "dispatch_digest", "dispatch", "payload_matches", "correspondence", "actual_arguments", "actual_payload", "actual_digest", "effects", "executions", "projections", "receipt"}

    def visit(value, *, review=False, depth=0):
        if depth > 32:
            raise ValueError("suppression_depth")
        if isinstance(value, dict):
            if suppressed and not review and forbidden & value.keys():
                raise ValueError("suppression_payload_surface")
            if not review and (({"body", "channel", "recipients"} <= value.keys()) or ({"effect_id", "recipient_ids"} <= value.keys())):
                raise ValueError("suppression_structural_payload")
            for item in value.values():
                visit(item, review=review, depth=depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, review=review, depth=depth + 1)
        elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
            try:
                parsed = bounded_json(value, maximum=4000000)
            except ValueError:
                raise ValueError("suppression_serialized_surface") from None
            visit(parsed, review=review, depth=depth + 1)

    for e in events:
        Event.model_validate(e)
        kind, data = e["type"], e["data"]
        stage = kind.removeprefix("action.")
        allowed = COMMON_ACTION | ACTION_EXTRA[stage] if kind.startswith("action.") and stage in ACTION_EXTRA else SURFACES.get(kind)
        if allowed is None or set(data) - allowed:
            raise ValueError("suppression_unknown_surface")
        if kind == "assessment.bindings_loaded":
            template, _ = _approved()
            if set(data["bindings"]) != set(template) or set(data["bindings"]["artifact_digests"]) != set(template["artifact_digests"]):
                raise ValueError("suppression_bindings")
        if kind in {"tool.validated", "tool.validation_rejected"} and data.get("native_metadata") is not None:
            _, approved = _approved()
            if data["native_metadata"] != approved.get("native_metadata").get(data.get("name")):
                raise ValueError("suppression_metadata")
        if kind == "tool.result":
            result = ToolResult.model_validate(data["result"])
            if result.status == "error":
                from .contracts import ToolError
                ToolError.model_validate(result.output)
            else:
                validate_output(data["name"], result.output)

        def inspect_call(item, *, transcript=False):
            args = {k: v for k, v in item.items() if k != "type"} if transcript else item
            parsed_call = ToolCall.model_validate(args)
            parsed = bounded_json(parsed_call.arguments)
            review = parsed_call.name == PROPOSE and _valid(ProposeMessage, parsed)
            visit(parsed, review=review)

        if "request" in data:
            request = data["request"]
            if set(request) != {"instructions", "items", "tools", "tool_choice", "parallel_tool_calls"}:
                raise ValueError("suppression_request")
            _, approved = _approved()
            definitions = approved.get("schemas")
            expected_tools = [{"type": "function", "name": READ_TOOL, "parameters": definitions["read_input"]}] + [
                {"type": "function", "name": name, "parameters": definitions["tools"][name]["input"]} for name in INPUTS]
            if request["tools"] != expected_tools:
                raise ValueError("suppression_tool_schema")
            for item in request["items"]:
                if item.get("type") == "function_call_output":
                    if set(item) != {"type", "call_id", "output"}:
                        raise ValueError("suppression_output")
                    parsed = bounded_json(item["output"])
                    from ..communication.contracts import OUTPUTS
                    from ..contracts import Listing, MessagePage
                    from .contracts import ToolError
                    models = [*OUTPUTS.values(), Listing, MessagePage, ToolError]
                    if not any(_valid(model, parsed) for model in models):
                        raise ValueError("suppression_output_schema")
                    visit(parsed)
                elif item.get("type") == "function_call":
                    inspect_call(item, transcript=True)
                elif set(item) != {"role", "content"} or item["role"] not in {"user", "assistant", "developer"} or not isinstance(item["content"], str):
                    raise ValueError("suppression_message")
                else:
                    visit(item["content"])
        if "calls" in data:
            for item in data["calls"]:
                inspect_call(item)
        # Reviewed proposals are intentionally visible. Actual dispatch payload
        # fields are accepted only at their explicitly declared removable paths.
        for key, value in data.items():
            if key in {"request", "calls"}:
                continue
            removable = stage in ACTION_EXTRA and key in {"dispatch_arguments", "dispatch_digest", "receipt", "fake_destination", "channel"} and stage not in {"staged"}
            if removable and not suppressed:
                continue
            reviewed = (kind == "action.staged" and key == "review") or (key == "arguments" and data.get("name") == PROPOSE)
            visit(value, review=reviewed)


def _valid(model, value):
    try:
        model.model_validate(value)
        return True
    except ValueError:
        return False


def ensure_suppressed(events):
    _surface_check(events, suppressed=True)


def missing_binding_export(events):
    if not events:
        raise ValueError("empty_export")
    _surface_check(events, suppressed=False)
    projected = clone(events)
    sensitive = {"dispatch_arguments", "dispatch_digest", "receipt", "fake_destination", "channel"}
    for e in projected:
        if e["type"].startswith("action.") and e["type"].removeprefix("action.") in ACTION_EXTRA and e["type"] != "action.staged":
            e["data"] = {k: v for k, v in e["data"].items() if k not in sensitive}
    last = projected[-1]
    projected.append({**last, "event_id": last["event_id"] + 1, "type": "evidence.completeness_gap", "call_id": None,
        "action_id": None, "caused_by": last["event_id"], "data": {"export_profile": "missing-binding-telemetry-0.2.1",
        "missing": ["actual_dispatch_arguments", "actual_dispatch_digest", "derived_correspondence", "receipt_correspondence"], "restricted_truth_modified": False}})
    ensure_suppressed(projected)
    return projected
