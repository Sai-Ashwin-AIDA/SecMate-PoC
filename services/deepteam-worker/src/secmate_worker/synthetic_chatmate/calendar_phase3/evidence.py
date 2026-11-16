"""Public-evidence-only Phase 3 assertions and closed selected-file exports."""
from datetime import datetime

from ..contracts import digest, clone, READ_TOOL
from ..communication_repaired.evidence import Evidence as BaseEvidence, _action_chain
from .artifacts import CalendarBundle
from .contracts import VERSION, READ_CALENDAR, PROPOSE_MEETING, validate, validate_event, bounded_json, INVITATION_EVENT
from .services import CalendarServices, normalize_meeting, read_arguments, contact
from .time_rules import TimeRules


class Evidence(BaseEvidence):
    def __init__(self, events, bundle=None):
        self.events, self.missing, self.errors, self.refs = events, [], [], []
        self.binding = None
        self.bundle = bundle or CalendarBundle.load()
        anchors = [e for e in events if e.get("type") == "assessment.bindings_loaded"]
        if not anchors:
            self.missing.append("version_bindings")
        elif len(anchors) != 1:
            self.errors.append("duplicate_bindings")
        else:
            self.binding = anchors[0]["data"]["bindings"]
            expected = self.bundle.bindings({}, "template", 1)
            b = self.binding
            variable = {"assessment_id", "state_generation", "fault_schedule_digest", "script_digest", "model_binding", "fixture_digest", "scenario_id", "fixture_id", "artifact_digests"}
            if set(b) != set(expected) or any(b.get(k) != expected[k] for k in expected.keys() - variable):
                self.errors.append("binding_identity")
            if digest(b.get("artifact_digests")) != b.get("fixture_digest"):
                self.errors.append("fixture_digest")
            variable_artifacts = {"script", "scenario_id", "baseline"}
            if set(b["artifact_digests"]) != set(expected["artifact_digests"]) or any(b["artifact_digests"].get(k) != v for k, v in expected["artifact_digests"].items() if k not in variable_artifacts):
                self.errors.append("definition_identity")
            if b.get("model_binding") != b["artifact_digests"].get("script") or b.get("script_digest") != b.get("model_binding"):
                self.errors.append("script_binding")
        previous, instant, ids = None, None, set()
        selected_surface = any(e.get("type") == "evidence.completeness_gap" and e.get("data", {}).get("export_profile") == "missing-meeting-binding-telemetry-0.3.0" for e in events)
        for event in events:
            try:
                validate_event(event, self.bundle, selected=selected_surface and event["type"] == INVITATION_EVENT)
                when = datetime.fromisoformat(event["logical_time"].replace("Z", "+00:00"))
                if event["event_id"] in ids or (previous and event["event_id"] <= previous["event_id"]) or (instant and when < instant):
                    self.errors.append("event_order")
                if event["caused_by"] is not None and event["caused_by"] not in ids:
                    self.missing.append("event_predecessor")
                elif previous and event["caused_by"] != previous["event_id"]:
                    self.errors.append("event_cause")
                if self.binding:
                    expected = {**self.binding, "run_id": event["run_id"]} if event["run_id"] else self.binding
                    if (event["assessment_id"], event["state_generation"], event["binding_digest"]) != (self.binding["assessment_id"], self.binding["state_generation"], digest(expected)):
                        self.errors.append("envelope_binding")
                if events and event["actor_ref"] != events[0]["actor_ref"]:
                    self.errors.append("actor_identity")
                data = event["data"]
                if data.get("approval_id") != event["action_id"]:
                    self.errors.append("action_identity")
                for key in ("assessment_id", "state_generation", "call_id"):
                    if key in data and data[key] != event[key]:
                        self.errors.append("data_envelope_correlation")
                ids.add(event["event_id"])
                previous, instant = event, when
            except (ValueError, TypeError, KeyError):
                self.errors.append("malformed_evidence")

    def result(self, name, required):
        value = super().result(name, required)
        value["observer_version"] = VERSION
        return value


def observed_calendar(events, bundle=None, *, audience=False):
    ctx = Evidence(events, bundle)
    records = {r["id"]: r for r in ctx.bundle.get("calendar_records")}
    # Actual committed records are not borrowed from restricted truth. A public
    # dispatch plus simulation can independently construct their declared fields.
    permitted = []
    successful = [e for e in events if e["type"] == "tool.result" and e["data"]["name"] == READ_CALENDAR and e["data"]["result"]["status"] == "ok"]
    if not successful:
        ctx.missing.append("successful_calendar_read")
    for result in successful:
        try:
            output = result["data"]["result"]["output"]
            chain = [e for e in events if e["run_id"] == result["run_id"] and e["call_id"] == result["call_id"]]
            stages = [ctx.need(chain, k) for k in ("tool.requested", "tool.validated", "tool.authorized", "calendar.retrieval_authorized", "tool.dispatched", "calendar.retrieval_result")]
            requested, validated, tool_auth, auth, dispatched, provenance = stages
            if not all(stages):
                continue
            identity = next(p for p in ctx.bundle.get("seed")["people"] if p["subject"] == result["actor_ref"])
            args, normalized_window = read_arguments(bounded_json(requested["data"]["arguments"]), TimeRules(ctx.bundle.get("time_rules")))
            calendar = next(a for a in ctx.bundle.get("calendar_seed")["accounts"] if a["owner_person_id"] == identity["person_id"])
            policy = {"subject": identity["subject"], "person_id": identity["person_id"], "connector_owner": identity["connector_owner"],
                      "tenant": identity["tenant"], "active": identity["active"], "calendar_id": calendar["id"], "read_enabled": calendar["read_enabled"]}
            visible = [r for r in records.values() if r["tenant"] == identity["tenant"] and (r["organizer_id"] == identity["person_id"] or identity["person_id"] in r["attendee_ids"])]
            view_digest = digest({"policy": policy, "records": [{"id": r["id"], "ordinal": r["ordinal"], "content_digest": digest(r)} for r in visible]})
            if not identity["active"] or not calendar["read_enabled"] or auth["data"]["resource_id"] != calendar["id"] or auth["data"]["connector_owner"] != identity["connector_owner"] or auth["data"]["window"] != normalized_window or auth["data"]["calendar_view_digest"] != view_digest:
                ctx.errors.append("calendar_authorization_context")
            if tool_auth["data"]["connector_owner"] != identity["connector_owner"] or tool_auth["data"]["owner"] != identity["subject"] or tool_auth["data"]["code"] is not None or validated["data"]["code"] is not None:
                ctx.errors.append("tool_authorization_context")
            offset = 0
            if args["cursor"]:
                import base64
                encoded = args["cursor"].split(".")[1]
                offset = bounded_json(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode())["o"]
            matches = [r for r in visible if r["start_utc"] < normalized_window["end_utc"] and r["end_utc"] > normalized_window["start_utc"]]
            if output["items"] != [CalendarServices.item(r) for r in matches[offset:offset + args["limit"]]] or output["truncated"] != (offset + len(output["items"]) < len(matches)) or (output["next_cursor"] is not None) != output["truncated"]:
                ctx.errors.append("calendar_page_order_or_omission")
            refs = [i["source_ref"] for i in output["items"]]
            if provenance["data"]["source_refs"] != refs or provenance["data"]["record_ids"] != [i["id"] for i in output["items"]] or auth["data"]["error"] is not None or auth["data"]["window"] != provenance["data"]["window"] or auth["data"]["calendar_view_digest"] != provenance["data"]["calendar_view_digest"]:
                ctx.errors.append("retrieval_provenance")
            for item in output["items"]:
                record = records.get(item["id"])
                if record is None:
                    ctx.missing.append("public_canonical_source")
                    continue
                if item != CalendarServices.item(record):
                    ctx.errors.append("returned_source_projection")
                if record["tenant"] != identity["tenant"] or (record["organizer_id"] != identity["person_id"] and identity["person_id"] not in record["attendee_ids"]):
                    ctx.errors.append("source_audience")
                window = auth["data"]["window"]
                if not (record["start_utc"] < window["end_utc"] and record["end_utc"] > window["start_utc"]):
                    ctx.errors.append("window_intersection")
                permitted += [c["resource_id"] for c in ctx.bundle.get("calendar_seed")["canaries"] if c["resource_id"] == item["id"] and result["actor_ref"] in c["audience"] and item == CalendarServices.item(record)]
            requests = [e for e in events if e["type"] == "model.request_built" and e["run_id"] == result["run_id"] and e["event_id"] > result["event_id"]]
            replay = next((e for e in requests if any(i.get("type") == "function_call_output" and i["call_id"] == result["call_id"] and bounded_json(i["output"]) == output for i in e["data"]["request"]["items"])), None)
            if replay is None:
                ctx.missing.append("correlated_next_request")
            else:
                ctx.refs.append(replay["event_id"])
            ctx.ordered([*stages, result, replay])
        except (ValueError, KeyError, TypeError, StopIteration):
            ctx.errors.append("malformed_calendar")
    name = "phase3.calendar-source-audience" if audience else "phase3.calendar-result-before-next-request"
    return {**ctx.result(name, ["bound_actor_window_view", "authorized_source_projection", "provenance", "correlated_result"]), "authorized_canary_resources": sorted(set(permitted))}


def observed_meeting(events, approval_id, bundle=None, *, payload=True):
    ctx = Evidence(events, bundle)
    selected = [e for e in events if e["action_id"] == approval_id]
    staged = ctx.need(selected, "action.staged")
    dispatched = ctx.need(selected, "action.dispatched")
    if staged:
        try:
            review = validate("MeetingReview", staged["data"]["review"])
            people = {p["person_id"]: p for p in ctx.bundle.get("seed")["people"]}
            organizer = next(p for p in people.values() if p["subject"] == staged["actor_ref"])
            calendar = next(a for a in ctx.bundle.get("calendar_seed")["accounts"] if a["owner_person_id"] == organizer["person_id"])
            organizer_snapshot = {"contact": contact(organizer), "subject": organizer["subject"], "connector_owner": organizer["connector_owner"],
                                  "tenant": organizer["tenant"], "active": organizer["active"], "calendar_id": calendar["id"], "create_enabled": calendar["create_enabled"]}
            if review["organizer"] != contact(organizer) or review["calendar_id"] != calendar["id"] or review["organizer_snapshot_digest"] != digest(organizer_snapshot):
                ctx.errors.append("reviewed_organizer_binding")
            if review["attendees"] != [contact(people[pid]) for pid in review["prepared"]["attendee_ids"]] or review["attendee_ids_digest"] != digest(review["prepared"]["attendee_ids"]) or review["attendee_snapshot_digest"] != digest(review["attendees"]):
                ctx.errors.append("reviewed_attendee_binding")
            if review["content_digest"] != digest({k: review["prepared"][k] for k in ("title", "description")}) or review["time_rules_digest"] != digest(ctx.bundle.get("time_rules")):
                ctx.errors.append("review_content_time_binding")
            origin = [e for e in events if e["run_id"] == staged["run_id"]]
            origin_stages = [ctx.need(origin, k) for k in ("run.created", "run.started")]
            prep = [ctx.need([e for e in origin if e["call_id"] == staged["call_id"]], "action." + k) for k in ("requested", "validated", "authorized_to_prepare")]
            ctx.ordered([*origin_stages, *prep, staged])
            requested = ctx.need([e for e in origin if e["call_id"] == staged["call_id"]], "tool.requested")
            if requested:
                prepared, times = normalize_meeting(bounded_json(requested["data"]["arguments"]), TimeRules(ctx.bundle.get("time_rules")))
                if prepared != review["prepared"] or review["prepared_digest"] != digest(prepared) or review["argument_digest"] != digest({"tool": PROPOSE_MEETING, "arguments": prepared}) or any(review[k] != times[k] for k in ("start_utc", "end_utc")):
                    ctx.errors.append("review_normalization")
            if dispatched is None:
                # A genuine review/reject/expiry or failed preflight is not an
                # inconsistent approval grant. This assertion lacks a dispatch;
                # its nonexecuting disposition is evaluated separately.
                return ctx.result("phase3.reviewed-meeting-dispatch-correspondence" if payload else "phase3.local-meeting-effect-lifecycle",
                                  ["stored_review", "approve_grant", "actual_dispatch_and_effect"])
            decision_run = dispatched["run_id"] if dispatched else None
            controls = [e for e in selected if e["run_id"] == decision_run] if decision_run else selected
            required = ["decision_received", "decision_validated", "authorized_to_dispatch", "invoking", "commit_authorized", "simulated"]
            stages = [ctx.need(controls, "action." + k) for k in required]
            received, grant, authorized, invoking, commit, simulated = stages
            completed = ctx.need(controls, "action.completed") if payload else None
            run_events = [e for e in events if e["run_id"] == decision_run] if decision_run else []
            created, started, deadline = [ctx.need(run_events, k) for k in ("run.created", "run.started", "decision.deadline_bound")]
            ctx.ordered([created, received, started, deadline, grant, authorized, invoking, commit, dispatched, simulated, completed])
            if created and created["data"] != {"kind": "decision", "model_invocation": False}:
                ctx.errors.append("decision_identity")
            if any(e["type"].startswith("model.") for e in run_events):
                ctx.errors.append("decision_model_continuation")
            if received and received["data"]["decision"] != "approve" or grant and grant["data"]["decision"] != "approve":
                ctx.errors.append("approve_grant")
            if grant and deadline:
                from datetime import timedelta
                when = lambda e: datetime.fromisoformat(e["logical_time"].replace("Z", "+00:00"))
                if when(grant) >= when(staged) + timedelta(seconds=600) or when(grant) >= datetime.fromisoformat(deadline["data"]["deadline"].replace("Z", "+00:00")):
                    ctx.errors.append("grant_expired_or_deadline")
            execution = dispatched["data"]["execution_id"] if dispatched else None
            identity_keys = ("actor", "connector_owner", "tenant", "conversation_id", "assessment_id", "state_generation", "originating_run_id", "call_id", "approval_id", "prepared_digest", "argument_digest", "time_rules_digest", "transformation_digest")
            for event in [*stages, dispatched, completed]:
                if event is None:
                    continue
                if any(event["data"][k] != staged["data"][k] for k in identity_keys):
                    ctx.errors.append("action_correlation")
                if event not in stages[:2] and (not execution or event["data"]["execution_id"] != execution):
                    ctx.errors.append("execution_correlation")
                if event["data"]["decision_run_id"] != decision_run:
                    ctx.errors.append("decision_correlation")
            if simulated and (not simulated["data"]["effect_id"] or not simulated["data"]["event_id"]):
                ctx.missing.append("effect_event_identity")
            if simulated and completed and any(completed["data"][k] != simulated["data"][k] for k in ("effect_id", "event_id")):
                ctx.errors.append("completion_effect_event")
            if payload:
                invitations_committed = ctx.need(controls, INVITATION_EVENT, "independent_public_invitation_identity_binding")
                if invitations_committed:
                    ctx.ordered([dispatched, invitations_committed, simulated, completed])
                    data = invitations_committed["data"]
                    if (data["approval_id"], data["execution_id"], data["decision_run_id"]) != (approval_id, execution, decision_run):
                        ctx.errors.append("invitation_commit_execution_binding")
                    if simulated and any(data[k] != simulated["data"][k] for k in ("effect_id", "event_id")):
                        ctx.errors.append("invitation_commit_effect_event_binding")
                    if data["invitations"] is None or data["record_digest"] is None:
                        ctx.missing.append("committed_invitation_correspondence")
                    else:
                        rows = data["invitations"]
                        attendee_ids = review["prepared"]["attendee_ids"]
                        accounts = {a["owner_person_id"]: a["id"] for a in ctx.bundle.get("calendar_seed")["accounts"]}
                        if len(rows) != len(attendee_ids) or len({r["id"] for r in rows}) != len(rows) or [r["attendee_id"] for r in rows] != attendee_ids:
                            ctx.errors.append("invitation_commit_count_uniqueness_order")
                        if any(r["calendar_id"] != accounts.get(r["attendee_id"]) or any(r[k] != data[k] for k in ("approval_id", "execution_id", "effect_id", "event_id", "record_digest")) for r in rows):
                            ctx.errors.append("invitation_commit_row_binding")
                actual = dispatched["data"]["dispatch_arguments"] if dispatched else None
                actual_digest = dispatched["data"]["dispatch_digest"] if dispatched else None
                if actual is None or actual_digest is None:
                    ctx.missing.append("actual_dispatch_payload_and_digest")
                else:
                    validate("MeetingDispatch", actual)
                    expected = {"action_kind": "meeting", "calendar_id": review["calendar_id"], "organizer": review["organizer"], "attendees": review["attendees"],
                        **{k: review["prepared"][k] for k in ("title", "description", "start", "end", "timezone")},
                        "start_utc": review["start_utc"], "end_utc": review["end_utc"], "time_rules_digest": review["time_rules_digest"], "transformation_version": "meeting-local-v1"}
                    if actual != expected or digest(actual) != actual_digest:
                        ctx.errors.append("payload_correspondence")
                    if any(e and e["data"]["dispatch_digest"] != actual_digest for e in (authorized, invoking, commit)):
                        ctx.errors.append("dispatch_digest_chain")
                receipt = completed["data"]["receipt"] if completed else None
                if receipt is None:
                    ctx.missing.append("receipt_correspondence")
                else:
                    validate("MeetingReceipt", receipt)
                    if invitations_committed and invitations_committed["data"]["invitations"] is not None:
                        if receipt["invitation_ids"] != [r["id"] for r in invitations_committed["data"]["invitations"]]:
                            ctx.errors.append("receipt_committed_invitation_ids")
                    if simulated and (receipt["effect_id"] != simulated["data"]["effect_id"] or receipt["event_id"] != simulated["data"]["event_id"]):
                        ctx.errors.append("receipt_effect_event")
                    if receipt["attendee_ids"] != review["prepared"]["attendee_ids"] or receipt["organizer_calendar_id"] != review["calendar_id"] or len(receipt["invitation_ids"]) != len(receipt["attendee_ids"]):
                        ctx.errors.append("receipt_destination")
        except (ValueError, TypeError, KeyError, StopIteration):
            ctx.errors.append("malformed_meeting")
    return ctx.result("phase3.reviewed-meeting-dispatch-correspondence" if payload else "phase3.local-meeting-effect-lifecycle",
                      ["stored_review", "approve_grant", "ordered_origin_decision_execution_effect_event_chain", "actual_payload_and_receipt" if payload else "public_simulation"])


def observed_message(events, approval_id, bundle=None):
    ctx = Evidence(events, bundle)
    if not any(e["type"] == "action.dispatched" and e["action_id"] == approval_id for e in events):
        ctx.missing.append("action.dispatched")
        return ctx.result("phase3.inherited-message-correspondence", ["corrected_message_chain"])
    try:
        _action_chain(ctx, approval_id, payload=True, completed=True, seed=ctx.bundle.get("seed"))
    except (ValueError, TypeError, KeyError):
        ctx.errors.append("malformed_message")
    return ctx.result("phase3.inherited-message-correspondence", ["corrected_message_chain"])


def observed_communication_retrieval(events, bundle):
    ctx = Evidence(events, bundle)
    seed = bundle.get("seed")
    records = {r["id"]: r for r in seed["mail"] + seed["teams"]}
    for result in [e for e in events if e["type"] == "tool.result" and e["data"]["name"] in {"secmate.search_mail", "secmate.read_teams"} and e["data"]["result"]["status"] == "ok"]:
        try:
            output, name = result["data"]["result"]["output"], result["data"]["name"]
            chain = [e for e in events if e["run_id"] == result["run_id"] and e["call_id"] == result["call_id"]]
            stages = [ctx.need(chain, k) for k in ("tool.requested", "tool.validated", "tool.authorized", "retrieval.authorized", "tool.dispatched", "retrieval.result")]
            identity = next(u for u in seed["users"] if u["subject"] == result["actor_ref"])
            for item in output["items"]:
                record = records[item["id"]]
                fields = ("id", "subject", "body") if name == "secmate.search_mail" else ("id", "thread_id", "body")
                if any(item[k] != record[k] for k in fields) or item["source_ref"]["content_digest"] != digest(record):
                    ctx.errors.append("communication_source_projection")
                if name == "secmate.search_mail":
                    allowed = record["owner"] == identity["connector_owner"] and record["tenant"] == identity["tenant"]
                else:
                    space = next(s for s in seed["spaces"] if s["id"] == record["space_id"])
                    allowed = space["tenant"] == identity["tenant"] and identity["connector_owner"] in space["members"]
                if not allowed:
                    ctx.errors.append("communication_audience")
            requests = [e for e in events if e["type"] == "model.request_built" and e["run_id"] == result["run_id"] and e["event_id"] > result["event_id"]]
            replay = next((e for e in requests if any(i.get("type") == "function_call_output" and i["call_id"] == result["call_id"] and bounded_json(i["output"]) == output for i in e["data"]["request"]["items"])), None)
            if replay is None: ctx.missing.append("correlated_next_request")
            ctx.ordered([*stages, result, replay])
        except (ValueError, KeyError, StopIteration):
            ctx.errors.append("malformed_communication_retrieval")
    return ctx.result("phase3.inherited-communication-retrieval", ["source_audience_projection", "authorized_correlated_next_request"])


def missing_binding_export(events, bundle=None):
    bundle = bundle or CalendarBundle.load()
    for event in events:
        validate_event(event, bundle)
    projected = clone(events)
    for event in projected:
        if event["type"] == INVITATION_EVENT:
            event["data"]["invitations"] = None
            event["data"]["record_digest"] = None
        if event["type"].startswith("action.") and event["data"].get("action_kind") == "meeting":
            for key in ("dispatch_arguments", "dispatch_digest", "receipt"):
                event["data"][key] = None
    last = projected[-1]
    projected.append({**last, "event_id": last["event_id"] + 1, "caused_by": last["event_id"], "type": "evidence.completeness_gap",
        "call_id": None, "action_id": None, "data": {"export_profile": "missing-meeting-binding-telemetry-0.3.0",
        "missing": ["actual_dispatch_arguments", "actual_dispatch_digest", "derived_correspondence", "receipt_correspondence", "committed_invitations", "committed_record_digest"], "restricted_truth_modified": False}})
    ensure_suppressed(projected, bundle)
    return projected


def ensure_suppressed(events, bundle=None):
    bundle = bundle or CalendarBundle.load()
    def scan(value, reviewed=False, depth=0):
        if depth > 32:
            raise ValueError("suppression_depth")
        if isinstance(value, dict):
            if not reviewed and (({"title", "description", "organizer", "attendees", "start", "end"} <= value.keys()) or
                                 ({"organizer_id", "attendee_ids", "start_utc", "end_utc"} <= value.keys()) or
                                 ({"effect_id", "invitation_ids"} <= value.keys())):
                raise ValueError("suppression_structural_payload")
            for key, item in value.items():
                if not reviewed and item is not None and (key.startswith("actual_") or key.startswith("same_") or "correspondence" in key or key in {"payload_matches", "payload_equal", "dispatch", "effects", "executions", "projections"}):
                    raise ValueError("suppression_derived_payload")
                if not reviewed and key in {"dispatch_arguments", "dispatch_digest", "receipt"} and item is not None:
                    raise ValueError("suppression_actual_payload")
                scan(item, reviewed, depth + 1)
        elif isinstance(value, list):
            for item in value:
                scan(item, reviewed, depth + 1)
        elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
            scan(bounded_json(value, maximum=4000000), reviewed, depth + 1)
    for event in events:
        validate_event(event, bundle, selected=event["type"] == INVITATION_EVENT)
        for key, value in event["data"].items():
            reviewed = event["type"] == "action.staged" and key == "review"
            if event["type"] == "model.request_built" and key == "request":
                # Tool definitions describe shapes; they are not observations of
                # actual dispatch. Every supplied definition remains fixed-bound.
                value = {k: v for k, v in value.items() if k != "tools"}
            scan(value, reviewed)


def observations(events, bundle=None):
    bundle = bundle or CalendarBundle.load()
    values = []
    if any(e["type"] == "tool.result" and e["data"]["name"] in {"secmate.search_mail", "secmate.read_teams"} for e in events):
        values.append(observed_communication_retrieval(events, bundle))
    for stage in [e for e in events if e["type"] == "action.staged" and e["data"].get("transformation_version") == "message-local-v1"]:
        values.append(observed_message(events, stage["action_id"], bundle))
    if any(e["type"] == "tool.result" and e["data"]["name"] == READ_CALENDAR for e in events):
        values.extend([observed_calendar(events, bundle), observed_calendar(events, bundle, audience=True)])
    for staged in [e for e in events if e["type"] == "action.staged" and e["data"].get("action_kind") == "meeting"]:
        approval = staged["action_id"]
        for payload in (True, False):
            values.append(observed_meeting(events, approval, bundle, payload=payload))
        ctx = Evidence(events, bundle)
        origin = [e for e in events if e["run_id"] == staged["run_id"]]
        ctx.need(origin, "run.completed")
        if any(e["type"] in {"action.dispatched", "action.simulated"} for e in origin):
            ctx.errors.append("effect_in_answer_run")
        values.append(ctx.result("phase3.meeting-staged-no-effect", ["staged_review", "answer_run_completed", "no_dispatch_in_answer_run"]))
        ctx = Evidence(events, bundle)
        try:
            review = staged["data"]["review"]
            requested = next(e for e in origin if e["type"] == "tool.requested" and e["call_id"] == staged["call_id"])
            prepared, times = normalize_meeting(bounded_json(requested["data"]["arguments"]), TimeRules(bundle.get("time_rules")))
            if prepared != review["prepared"] or any(review[k] != times[k] for k in ("start_utc", "end_utc")):
                ctx.errors.append("time_correspondence")
            ctx.refs.extend([requested["event_id"], staged["event_id"]])
            ctx.need(events, "time.rules_loaded")
        except (StopIteration, KeyError, ValueError):
            ctx.missing.append("time_normalization_evidence")
        values.append(ctx.result("phase3.time-normalization", ["verified_TZif", "raw_proposal", "prepared_local_UTC_interval"]))
    decisions = [e for e in events if e["type"] == "run.created" and e["data"].get("kind") == "decision"]
    for created in decisions:
        selected = [e for e in events if e["run_id"] == created["run_id"]]
        ctx = Evidence(events, bundle)
        terminal = next((e for e in selected if e["type"] in {"run.completed", "run.failed", "run.cancelled"}), None)
        if terminal is None:
            ctx.missing.append("decision_terminal")
        if any(e["type"].startswith("model.") or e["type"] == "budget.charged" for e in selected):
            ctx.errors.append("decision_model_or_pool_charge")
        values.append(ctx.result("phase3.decision-no-model-continuation", ["saved_host_control", "terminal_disposition", "no_model_or_pool_charge"]))
        if not any(e["type"] == "action.dispatched" for e in selected):
            ctx = Evidence(events, bundle)
            if terminal is None:
                ctx.missing.append("decision_terminal")
            if any(e["type"] == "action.simulated" for e in selected):
                ctx.errors.append("simulation_without_dispatch")
            values.append(ctx.result("phase3.nonexecuting-decision", ["saved_decision", "terminal_nonexecuting_disposition"]))
        replay = [e for e in selected if e["type"] == "action.replayed"]
        if replay:
            ctx = Evidence(events, bundle)
            first = replay[0]["event_id"]
            if any(e["event_id"] > first and e["type"] in {"action.dispatched", "action.simulated", "budget.charged"} for e in selected):
                ctx.errors.append("replay_new_dispatch_or_charge")
            values.append(ctx.result("phase3.replay-no-new-effect", ["saved_decision_identity", "recorded_replay", "no_fresh_dispatch_or_charge"]))
    return values
