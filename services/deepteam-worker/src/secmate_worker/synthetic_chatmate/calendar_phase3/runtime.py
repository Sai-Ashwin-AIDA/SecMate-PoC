"""Scripted Phase 3 host with explicit message/meeting action routing."""
import time
from pathlib import Path

from ...job_runtime import canonical, require_permission
from ..contracts import READ_TOOL, TARGET_ID, ConversationRead, SyntheticError, digest, clone
from ..runtime import Assessment as Phase1Assessment, _id
from ..communication.contracts import INPUTS, PROPOSE, MAIL, TEAMS, DIRECTORY
from ..communication.runtime import CommunicationAssessment as MessageAssessment
from ..communication.services import FakeServices, HostIdentity
from ..communication_repaired.runtime import CommunicationAssessment as CorrectedAssessment
from ..communication_repaired.contracts import CommunicationBudget, validate_output
from ..communication_repaired.artifacts import validate_predecessor
from .artifacts import CalendarBundle
from .contracts import VERSION, READ_CALENDAR, PROPOSE_MEETING, bounded_json, validate, validate_event, Phase3FaultPlan, INVITATION_EVENT, AMENDMENT_VERSION
from .time_rules import TimeRules, TimeError
from .services import CalendarServices, normalize_meeting, read_arguments, account
from .store import CalendarStore

WRITES = {PROPOSE, PROPOSE_MEETING}
NEW_TOOLS = {READ_CALENDAR, PROPOSE_MEETING}


class CalendarTarget:
    def __init__(self, root, bundle=None):
        require_permission()
        supplied = bundle or CalendarBundle.load()
        self.bundle = CalendarBundle.from_parts({k: bounded_json(v, maximum=4000000) for k, v in supplied.artifacts})
        target = Path(root).resolve() / "targets" / TARGET_ID
        if target.exists():
            if (target / VERSION).exists():
                raise SyntheticError("target_version_collision")
            if target.is_symlink() or not target.is_dir() or not list(target.iterdir()):
                raise SyntheticError("unowned_target_namespace")
            for predecessor in target.iterdir():
                if predecessor.name not in {"0.1.1", "0.2.0", "0.2.1"}:
                    raise SyntheticError("unowned_target_namespace")
                validate_predecessor(predecessor)
        else:
            target.mkdir(parents=True, exist_ok=True)
        self.path = target / VERSION
        try:
            self.path.mkdir(exist_ok=False)
        except FileExistsError:
            raise SyntheticError("target_version_collision") from None
        self.assessments = self.path / "assessments"
        self.assessments.mkdir()
        definitions = self.path / "definitions"
        definitions.mkdir()
        for name, text in self.bundle.artifacts:
            with (definitions / (name + ".json")).open("x", encoding="utf-8") as stream:
                stream.write(text)
        with (self.path / "registration.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical({"target_id": TARGET_ID, "target_version": VERSION, "manifesto_version": "0.1.2",
                "phase_scope": [0, 1, 2, 3], "api_registration": False, "deepteam_provider": False,
                "definition_digests": {k: digest(bounded_json(v, maximum=4000000)) for k, v in self.bundle.artifacts}}))

    def fresh(self, *, subject="subject-ada", faults=None, generation=1):
        return CalendarAssessment(self, subject, faults or Phase3FaultPlan(), generation)


class CalendarAssessment(CorrectedAssessment):
    def __init__(self, target, subject, faults, generation):
        require_permission()
        self._target, self._bundle = target, target.bundle
        if subject not in {u["subject"] for u in self._bundle.get("seed")["users"]}:
            raise SyntheticError("invalid_host_identity")
        self.id, self.generation = _id("assessment"), generation
        self._watchdog_started = None
        self._fault_hits = {}
        self.path = target.assessments / self.id
        self.path.mkdir(exist_ok=False)
        self._faults = Phase3FaultPlan.model_validate_json(faults.model_dump_json())
        validate("Phase3FaultPlan", self._faults.model_dump())
        self._binding = self._bundle.bindings(self._faults.model_dump(), self.id, generation)
        self._binding_digest = digest(self._binding)
        self._rules = TimeRules(self._bundle.get("time_rules"))
        self._store = CalendarStore(self.path / "assessment.sqlite3", {
            "assessment_id": self.id, "generation": generation, "owner": subject, "seconds": 0.0,
            "archived": False, "accepted": False, "sessions": {}}, self._bundle.get("seed"),
            self._bundle.get("calendar_seed"), self._bundle.get("calendar_records"))
        for name, value in (("bindings", self._binding), ("faults", self._faults.model_dump())):
            with (self.path / (name + ".json")).open("x", encoding="utf-8") as stream:
                stream.write(canonical(value))
        self._services = FakeServices(self.id, generation, self._binding["artifact_digests"]["seed"], self._binding_digest)
        self._calendar = CalendarServices(self._binding, self._bundle.get("calendar_seed"), self._rules)
        self.session = self.host_session(subject)
        with self._store.transaction() as db:
            state = self._state(db)
            self._emit(db, state, "assessment.created", None, {"binding_digest": self._binding_digest})
            self._emit(db, state, "assessment.bindings_loaded", None, {"bindings": self._binding})
            self._emit(db, state, "time.rules_loaded", None, {"time_rules_digest": self._rules.digest,
                "package_version": "2026.6", "iana_version": "2026f", "resource_digests": self._binding["timezone_resources"]})

    @property
    def _budget(self):
        return CommunicationBudget.model_validate(self._bundle.get("budget"))

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        data = data or {}
        last = db.execute("SELECT max(id) FROM events").fetchone()[0] or 0
        event = {"event_schema_version": VERSION, "target_id": TARGET_ID, "target_version": VERSION,
                 "assessment_id": self.id, "state_generation": self.generation, "run_id": run["id"] if run else None,
                 "event_id": last + 1, "logical_time": self._timestamp(state["seconds"]), "type": kind,
                 "actor_ref": state["owner"], "call_id": call_id or data.get("call_id"), "action_id": data.get("approval_id"),
                 "caused_by": last or None, "data": data, "binding_digest": digest(run["bindings"]) if run else self._binding_digest,
                 "production_claim": False}
        validate_event(event, self._bundle)
        roots = {"time.rules_loaded": "TimeRulesLoadedData", "calendar.account_changed": "CalendarAccountChangedData", "meeting.normalized": "MeetingNormalizedData"}
        if kind in roots:
            validate(roots[kind], data)
        elif kind.startswith("calendar.retrieval_"):
            validate("CalendarRetrievalData", data)
        elif kind.startswith("action.") and data.get("action_kind") == "meeting":
            validate("MeetingActionData", data)
        db.execute("INSERT INTO events (payload) VALUES (?)", (canonical(event),))
        return event["event_id"]

    def _request(self, run, state):
        request = Phase1Assessment._request(self, run, state)
        request["tools"] += [{"type": "function", "name": name, "parameters": self._bundle.get("schemas")["tools"][name]["input"]}
                             for name in self._bundle.get("capabilities")["enabled"] if name != READ_TOOL]
        return request

    @staticmethod
    def _summary(prepared):
        if "attendee_ids" in prepared:
            return f"Review {prepared['title'][:180]} with {', '.join(prepared['attendee_ids'])[:100]} at {prepared['start']} {prepared['timezone']}; approval required."
        return MessageAssessment._summary(prepared)

    def _meeting_event(self, db, state, run, stage, *, approval=None, call_id=None, **extra):
        a = approval
        fields = ("approval_id", "decision_run_id", "execution_id", "effect_id", "event_id", "decision", "approval_status",
                  "execution_status", "prepared_digest", "argument_digest", "dispatch_digest", "review", "dispatch_arguments", "receipt", "fake_destination", "error", "field")
        data = {k: None for k in fields}
        data.update(action_kind="meeting", tool_name=PROPOSE_MEETING, actor=run["owner"], connector_owner=run["identity"]["connector_owner"],
                    tenant=run["identity"]["tenant"], conversation_id=run["conversation_id"], assessment_id=self.id,
                    state_generation=self.generation, originating_run_id=a["originating_run_id"] if a else run["id"],
                    call_id=a["call_id"] if a else call_id, transformation_digest=digest(self._bundle.get("transformation")), time_rules_digest=self._rules.digest)
        if a:
            data.update(approval_id=a["id"], approval_status=a["status"], prepared_digest=a["prepared_digest"], argument_digest=a["argument_digest"],
                        decision_run_id=a["decision_run_id"])
        data.update(extra)
        return self._emit(db, state, "action." + stage, run, data, data["call_id"])

    def _action_event(self, db, state, run, stage, approval, **extra):
        if approval["action_kind"] == "message":
            return CorrectedAssessment._action_event(self, db, state, run, stage, approval, **extra)
        if approval["action_kind"] != "meeting":
            raise ValueError("action_kind")
        x = self._store.execution(db, approval["id"])
        if x:
            extra.setdefault("execution_id", x["id"])
            extra.setdefault("execution_status", x["status"])
        receipt = extra.get("receipt")
        if receipt:
            extra.update(effect_id=receipt["effect_id"], event_id=receipt["event_id"])
        return self._meeting_event(db, state, run, stage, approval=approval, **extra)

    def _result(self, db, state, run, call_id, output, *, error=False, tool_name=READ_TOOL):
        if tool_name not in NEW_TOOLS:
            return CorrectedAssessment._result(self, db, state, run, call_id, output, error=error, tool_name=tool_name)
        try:
            if error:
                output = {"error": output["error"], "field": output.get("field")}
                validate("CalendarError", output)
            else:
                validate("CalendarPage" if tool_name == READ_CALENDAR else "Staged", output)
                if tool_name == READ_CALENDAR:
                    call = next(i for i in run["transcript"] if i.get("type") == "function_call" and i["call_id"] == call_id)
                    args, window = read_arguments(bounded_json(call["arguments"]), self._rules)
                    expected = CalendarServices.read(self._calendar, db, run["identity"], args, window)[0]
                    if output != expected:
                        raise ValueError("calendar_projection")
            result = {"call_id": call_id, "status": "error" if error else "staged" if tool_name == PROPOSE_MEETING else "ok",
                      "output": output, "source_refs": [i["source_ref"] for i in output.get("items", [])] if not error else []}
            validate("CalendarToolResult", result)
        except (ValueError, KeyError, TypeError):
            error, output = True, {"error": "tool_failed", "field": None}
            result = {"call_id": call_id, "status": "error", "output": output, "source_refs": []}
        self._emit(db, state, "tool.result", run, {"name": tool_name, "result": result}, call_id)
        run["transcript"].append({"type": "function_call_output", "call_id": call_id, "output": canonical(output)})
        if error and output["error"] != "error_streak_exhausted":
            old = run["streak"].get(tool_name, {})
            run["streak"][tool_name] = {"code": output["error"], "count": old.get("count", 0) + 1 if old.get("code") == output["error"] else 1}
        elif not error:
            run["streak"].pop(tool_name, None)

    def _stage(self, db, state, run, call, args):
        if call.name == PROPOSE_MEETING:
            self._fault_point(db, state, run, "meeting_prepare", call.call_id)
        prepared = args if call.name == PROPOSE_MEETING else args.model_dump()
        fingerprint = digest({"tool": call.name, "arguments": prepared})
        same = next((a for a in self._pending(db, run) if a["action_kind"] == ("meeting" if call.name == PROPOSE_MEETING else "message") and
                     digest({"tool": call.name, "arguments": a["prepared"]}) == fingerprint), None)
        if same:
            run["remaining"] += 1
            self._emit(db, state, "budget.refunded", run, {"pool": "execution", "reason": "already_staged", "remaining": run["remaining"]}, call.call_id)
            return {"status": "staged_for_approval", "approval_id": same["id"], "summary": self._summary(prepared), "expires_at": same["expires_at"]}
        if self._faults.preparation_failure:
            raise SyntheticError("tool_failed")
        self._supersede(db, state, run)
        expiry = state["seconds"] + 600
        approval = {"id": _id("approval"), "status": "pending", "actor": run["owner"], "connector_owner": run["identity"]["connector_owner"],
                    "tenant": run["identity"]["tenant"], "conversation_id": run["conversation_id"], "assessment_id": self.id,
                    "state_generation": self.generation, "originating_run_id": run["id"], "call_id": call.call_id,
                    "prepared": prepared, "prepared_digest": digest(prepared), "expires_seconds": expiry,
                    "expires_at": self._timestamp(expiry), "decision_run_id": None}
        if call.name == PROPOSE_MEETING:
            _, times = normalize_meeting(prepared, self._rules)
            snapshot, review, _ = self._calendar.prepare(db, run["identity"], prepared, times, digest(self._bundle.get("transformation")))
            approval.update(action_kind="meeting", tool_name=PROPOSE_MEETING, review=review, organizer_snapshot=snapshot,
                            attendee_snapshot=review["attendees"], argument_digest=fingerprint, transformation_version="meeting-local-v1",
                            transformation_digest=digest(self._bundle.get("transformation")))
        elif call.name == PROPOSE:
            _, recipients, _ = self._services.prepare_recipients(db, HostIdentity.model_validate(run["identity"]), args)
            approval.update(action_kind="message", recipient_snapshot=recipients, review={**prepared, "prepared_digest": digest(prepared)},
                            recipient_digest=digest(prepared["recipient_ids"]), content_digest=digest({k: prepared[k] for k in ("subject", "body")}),
                            transformation_version="message-local-v1")
        else:
            raise ValueError("write_kind")
        self._store.save_approval(db, approval)
        extra = {} if call.name == PROPOSE_MEETING else {"recipient_digest": approval["recipient_digest"], "content_digest": approval["content_digest"]}
        self._action_event(db, state, run, "staged", approval, review=approval["review"], **extra)
        return {"status": "staged_for_approval", "approval_id": approval["id"], "summary": self._summary(prepared), "expires_at": approval["expires_at"]}

    def _dispatch(self, db, state, run, calls):
        run.setdefault("provider_remaining", self._budget.fake_provider_read)
        capabilities = self._bundle.get("capabilities")
        multi = sum(c.name in WRITES for c in calls) > 1
        decisions = []
        for call in calls:
            self._emit(db, state, "tool.requested", run, {"name": call.name, "arguments": call.arguments}, call.call_id)
            if call.name == PROPOSE_MEETING:
                self._meeting_event(db, state, run, "requested", call_id=call.call_id)
            elif call.name == PROPOSE:
                self._emit(db, state, "action.requested", run, {"name": call.name, "arguments": call.arguments}, call.call_id)
            args, code, field, window = None, None, None, None
            if multi:
                code = "unsupported_write_batch"
            elif call.name not in capabilities["enabled"]:
                code = "capability_disabled" if call.name in capabilities["disabled"] else "unknown_tool"
            else:
                try:
                    raw = bounded_json(call.arguments)
                    if call.name == PROPOSE_MEETING:
                        args, times = normalize_meeting(raw, self._rules)
                        timing = {k: times[k] for k in ("start", "end", "start_utc", "end_utc")}
                        timing.update(timezone=args["timezone"], time_rules_digest=self._rules.digest)
                        db.execute("INSERT INTO normalizations VALUES (?,?)", (call.call_id, canonical({
                            "run_id": run["id"], "call_id": call.call_id, "prepared_digest": digest(args),
                            "time_rules_digest": self._rules.digest, "times": times})))
                        self._emit(db, state, "meeting.normalized", run, {"call_id": call.call_id, "prepared_digest": digest(args),
                            "argument_digest": digest({"tool": call.name, "arguments": args}), "timing_digest": digest(timing),
                            "time_rules_digest": self._rules.digest, "transformation_digest": digest(self._bundle.get("transformation"))}, call.call_id)
                    elif call.name == READ_CALENDAR:
                        args, window = read_arguments(raw, self._rules)
                    else:
                        args = (ConversationRead if call.name == READ_TOOL else INPUTS[call.name]).model_validate(raw)
                        if call.name in {MAIL, DIRECTORY} and not args.query.strip():
                            raise ValueError("empty_query")
                except TimeError as exc:
                    code, field = exc.code, exc.field
                except (ValueError, TypeError):
                    code = "invalid_arguments"
            self._emit(db, state, "tool.validation_rejected" if code else "tool.validated", run,
                       {"name": call.name, "code": code, "native_metadata": self._bundle.get("native_metadata").get(call.name)}, call.call_id)
            if call.name == PROPOSE_MEETING:
                self._meeting_event(db, state, run, "validation_rejected" if code else "validated", call_id=call.call_id,
                    prepared_digest=digest(args) if args else None,
                    argument_digest=digest({"tool": call.name, "arguments": args}) if args else None, error=code, field=field)
            elif call.name == PROPOSE:
                self._emit(db, state, "action.validation_rejected" if code else "action.validated", run,
                           {"code": code, "prepared_digest": digest(args.model_dump()) if args else None}, call.call_id)
            if code is None:
                try:
                    if call.name == PROPOSE_MEETING:
                        self._calendar.prepare(db, run["identity"], args, times, digest(self._bundle.get("transformation")))
                    elif call.name == READ_CALENDAR:
                        calendar, _, view = self._calendar.view(db, run["identity"])
                    else:
                        self._authorize(db, run, call.name, args)
                except TimeError as exc:
                    code, field = exc.code, exc.field
                except SyntheticError as exc:
                    code = exc.code
                resource = args.space_id if call.name == TEAMS else run["snapshot_id"] if call.name == READ_TOOL else run["identity"]["connector_owner"]
                details = {"name": call.name, "resource_id": resource, "connector_owner": run["identity"]["connector_owner"], "owner": run["owner"], "code": code}
                self._emit(db, state, "tool.authorization_rejected" if code else "tool.authorized", run, details, call.call_id)
                if call.name == READ_CALENDAR:
                    self._emit(db, state, "calendar.retrieval_rejected" if code else "calendar.retrieval_authorized", run,
                        {"tool_name": READ_CALENDAR, "resource_id": calendar["id"] if not code else run["identity"]["connector_owner"],
                         "connector_owner": run["identity"]["connector_owner"], "window": window,
                         "calendar_view_digest": view if not code else None, "record_ids": [], "source_refs": [], "error": code}, call.call_id)
                if call.name in {MAIL, TEAMS}:
                    self._emit(db, state, "retrieval.authorization_rejected" if code else "retrieval.authorized", run, details, call.call_id)
                if call.name == PROPOSE_MEETING:
                    self._meeting_event(db, state, run, "authorization_rejected" if code else "authorized_to_prepare", call_id=call.call_id,
                                        prepared_digest=digest(args), argument_digest=digest({"tool": call.name, "arguments": args}), error=code, field=field)
                elif call.name == PROPOSE:
                    self._emit(db, state, "action.authorization_rejected" if code else "action.authorized_to_prepare", run, {**details, "conversation_id": run["conversation_id"]}, call.call_id)
            if code is None:
                pool = capabilities["enabled"][call.name]["pool"]
                key = "remaining" if pool == "execution" else "provider_remaining"
                if run["streak"].get(call.name, {}).get("count", 0) >= 3:
                    code = "error_streak_exhausted"
                elif run[key] <= 0:
                    code = "budget_exhausted"
                    self._emit(db, state, "budget.exhausted", run, {"pool": pool}, call.call_id)
                else:
                    run[key] -= 1
                    self._emit(db, state, "budget.charged", run, {"pool": pool, "remaining": run[key]}, call.call_id)
            decisions.append((call, args, window, code, field))
        halted = False
        for call, args, window, code, field in decisions:
            if not self._checkpoint(db, state, run):
                return
            if not code and halted:
                code = "not_run"
            if not code:
                self._emit(db, state, "tool.dispatched", run, {"name": call.name, "destination": "assessment_fake_service"}, call.call_id)
                fault = next((f for f in self._faults.tools if f.call_id == call.call_id), None)
                elapsed = self._advance(db, state, run, fault.duration if fault else 0, min(run["deadline"], state["seconds"] + self._budget.tool_seconds))
                if elapsed == "cancelled":
                    return
                code = "tool_timeout" if elapsed else fault.error if fault else None
                try:
                    if code:
                        raise SyntheticError(code)
                    identity = HostIdentity.model_validate(run["identity"])
                    if call.name == READ_CALENDAR:
                        self._fault_point(db, state, run, "calendar_read", call.call_id)
                        if self._faults.calendar_read_unavailable:
                            raise SyntheticError("resource_unavailable")
                        output, view, calendar = self._calendar.read(db, run["identity"], args, window)
                    elif call.name in WRITES:
                        output = self._stage(db, state, run, call, args)
                    elif call.name == READ_TOOL:
                        output = self._read(run, args)
                    elif call.name == MAIL:
                        output = self._services.mailbox(db, identity, identity.connector_owner, args)
                    elif call.name == TEAMS:
                        output = self._services.teams(db, identity, args)
                    elif call.name == DIRECTORY:
                        if self._faults.directory_unavailable:
                            raise SyntheticError("resource_unavailable")
                        output = self._services.directory(db, identity, args)
                        self._emit(db, state, "directory.resolution", run, output, call.call_id)
                    else:
                        raise ValueError("handler")
                    if "error" not in output:
                        if call.name in NEW_TOOLS:
                            validate("CalendarPage" if call.name == READ_CALENDAR else "Staged", output)
                        else:
                            validate_output(call.name, output)
                        if call.name in WRITES:
                            approval = self._store.approval(db, output["approval_id"])
                            prepared = args if call.name == PROPOSE_MEETING else args.model_dump()
                            if approval is None or approval["status"] != "pending" or approval["originating_run_id"] != run["id"] or approval["prepared"] != prepared:
                                raise SyntheticError("write_not_staged")
                            if output != {"status": "staged_for_approval", "approval_id": approval["id"], "summary": self._summary(prepared), "expires_at": approval["expires_at"]}:
                                raise SyntheticError("tool_failed")
                        if call.name == READ_CALENDAR and output != CalendarServices.read(self._calendar, db, run["identity"], args, window)[0]:
                            raise SyntheticError("tool_failed")
                    if len(canonical(output)) > self._budget.output_characters:
                        code = "tool_output_limit_exceeded"
                    elif "error" in output:
                        code = output["error"]
                except TimeError as exc:
                    code, field = exc.code, exc.field
                except SyntheticError as exc:
                    code = exc.code
                except Exception:
                    code = "tool_failed"
                halted = bool(fault and fault.halt)
            if code:
                output = {"error": code, **({"field": field} if call.name in NEW_TOOLS else {})}
                if call.name in WRITES and code != "budget_exhausted":
                    self._supersede(db, state, run)
            elif call.name in {MAIL, TEAMS}:
                self._emit(db, state, "retrieval.result", run, {"name": call.name, "record_ids": [i["id"] for i in output["items"]], "source_refs": [i["source_ref"] for i in output["items"]]}, call.call_id)
            elif call.name == READ_CALENDAR:
                self._emit(db, state, "calendar.retrieval_result", run,
                    {"tool_name": READ_CALENDAR, "resource_id": calendar, "connector_owner": run["identity"]["connector_owner"], "window": window,
                     "calendar_view_digest": view, "record_ids": [i["id"] for i in output["items"]],
                     "source_refs": [i["source_ref"] for i in output["items"]], "error": None}, call.call_id)
            self._result(db, state, run, call.call_id, output, error=bool(code), tool_name=call.name)

    def _current_dispatch(self, db, run, a):
        if a["action_kind"] == "message":
            return CorrectedAssessment._current_dispatch(self, db, run, a)
        if a["action_kind"] != "meeting":
            raise ValueError("action_kind")
        TimeRules(self._bundle.get("time_rules"))
        if db.execute("SELECT count(*) FROM calendar_records").fetchone()[0] >= 10000:
            raise SyntheticError("preflight_failed")
        prepared, times = normalize_meeting(a["prepared"], self._rules)
        snapshot, review, dispatch = self._calendar.prepare(db, run["identity"], prepared, times, a["transformation_digest"])
        if snapshot != a["organizer_snapshot"] or review != a["review"] or review["attendees"] != a["attendee_snapshot"] or digest(prepared) != a["prepared_digest"]:
            raise SyntheticError("preflight_failed")
        return dispatch

    def _decision_output(self, a, execution=None, *, error=None):
        if a["action_kind"] == "message":
            return MessageAssessment._decision_output(self, a, execution, error=error)
        if a["action_kind"] != "meeting":
            raise ValueError("action_kind")
        value = {"action_kind": "meeting", "approval_id": a["id"], "approval_status": a["status"],
                 "execution_id": execution["id"] if execution else None, "execution_status": execution["status"] if execution else None,
                 "review": a["review"], "expires_at": a["expires_at"], "receipt": execution["receipt"] if execution else None,
                 "error": error or (execution["error"] if execution else None)}
        return validate("MeetingDecisionOutput", value)

    def _commit_meeting(self, db, state, run, a, x, dispatch):
        existing = db.execute("SELECT payload FROM meeting_effects WHERE execution_id=?", (x["id"],)).fetchone()
        if existing:
            saved = bounded_json(existing[0])
            if saved["dispatch_digest"] != digest(dispatch) or saved["prepared_digest"] != a["prepared_digest"]:
                raise ValueError("idempotence_payload_mismatch")
            return saved
        event_id, effect_id = _id("event"), _id("effect")
        ordinal = db.execute("SELECT coalesce(max(ordinal),0)+1 FROM calendar_records").fetchone()[0]
        record = {"id": event_id, "tenant": a["tenant"], "organizer_id": dispatch["organizer"]["person_id"],
                  "organizer_calendar_id": dispatch["calendar_id"], "attendee_ids": a["prepared"]["attendee_ids"],
                  **{k: dispatch[k] for k in ("title", "description", "start", "end", "start_utc", "end_utc", "timezone", "time_rules_digest")},
                  "origin": "simulated", "effect_id": effect_id, "execution_id": x["id"], "ordinal": ordinal}
        effect = {"effect_id": effect_id, "execution_id": x["id"], "approval_id": a["id"], "event_id": event_id,
                  "calendar_record": record, "prepared_digest": a["prepared_digest"], "dispatch_digest": x["dispatch_digest"], "committed_at": self._timestamp(state["seconds"])}
        projections, invitations = [], []
        people = {p["person_id"]: p for p in self._store.people(db)}
        for pid, role in [(record["organizer_id"], "organizer")] + [(p, "attendee") for p in record["attendee_ids"]]:
            cal = account(db, people[pid])
            projections.append({"effect_id": effect_id, "event_id": event_id, "calendar_id": cal["id"], "owner_person_id": pid, "role": role, "record_digest": digest(record)})
            if role == "attendee":
                invitations.append({"id": _id("invitation"), "effect_id": effect_id, "event_id": event_id, "attendee_id": pid,
                                    "calendar_id": cal["id"], "record_digest": digest(record), "created_at": effect["committed_at"]})
        self._fault_point(db, state, run, "projection", a["call_id"])
        self._store.commit_meeting(db, a, x, record, effect, projections, invitations)
        # Read the rows actually inserted, not the planned list or a receipt.
        committed = [bounded_json(r[0]) for r in db.execute(
            "SELECT payload FROM invitations WHERE effect_id=? ORDER BY rowid", (effect_id,))]
        self._emit(db, state, INVITATION_EVENT, run, {
            "amendment_version": AMENDMENT_VERSION, "action_kind": "meeting", "approval_id": a["id"],
            "execution_id": x["id"], "decision_run_id": run["id"], "effect_id": effect_id,
            "event_id": event_id, "record_digest": digest(record),
            "invitations": [{**{k: row[k] for k in ("id", "effect_id", "event_id", "attendee_id", "calendar_id", "record_digest")},
                             "approval_id": a["id"], "execution_id": x["id"]} for row in committed],
        }, a["call_id"])
        return effect

    def _decision_step(self, lease):
        with self._store.read() as db:
            _, before = self._leased(db, lease)
            if before.get("held_barrier") and not before["cancel"] and not (self._watchdog_started and time.perf_counter() - self._watchdog_started >= 60):
                return clone(before)
        result = self._decision_phase(lease)
        checkpoint = {"preflight": "after_resolve", "invoke": "after_preflight", "receipt": "after_commit"}.get(result.get("decision_phase"))
        if checkpoint and result["lease"] and result.get("decision_phase") != before.get("decision_phase"):
            with self._store.transaction() as db:
                state, run = self._leased(db, lease)
                a = self._store.approval(db, run["decision"]["approval_id"])
                if a["action_kind"] == "meeting":
                    self._fault_point(db, state, run, checkpoint, a["call_id"])
                    self._save_run(db, run)
                    result = clone(run)
        return result

    def _decision_phase(self, lease):
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            a = self._approval_auth(db, run["identity"], run["conversation_id"], run["decision"]["approval_id"])
            x = self._store.execution(db, a["id"])
            phase, choice = run["decision_phase"], run["decision"]["decision"]
            if self._faults.cancel_at is not None and state["seconds"] >= self._faults.cancel_at:
                run["cancel"] = True
            if self._watchdog_started is not None and time.perf_counter() - self._watchdog_started >= 60:
                if x and x["status"] == "invoking":
                    self._unknown(db, state, run, a, x)
                else:
                    self._finish(db, state, run, "failed", "environmental_watchdog")
                return clone(run)
            if phase == "resolve" and a["status"] == "approved":
                if a["decision_run_id"] != run["id"]:
                    self._settle_decision(db, state, run, a, error="resource_unavailable")
                elif x["status"] == "invoking":
                    self._unknown(db, state, run, a, x)
                elif x["status"] != "prepared":
                    self._action_event(db, state, run, "replayed", a, execution_id=x["id"], execution_status=x["status"])
                    self._settle_decision(db, state, run, a, x)
                elif run["cancel"] or state["seconds"] >= run["deadline"]:
                    self._fail_execution(db, state, run, a, x, "tool_failed" if run["cancel"] else "tool_timeout")
                else:
                    run["decision_phase"] = "preflight"
                    self._save_run(db, run)
                return clone(run)
            if phase == "receipt":
                if a["action_kind"] == "meeting":
                    self._fault_point(db, state, run, "receipt", a["call_id"])
                if self._faults.receipt_loss or run.get("fault_receipt_loss"):
                    self._unknown(db, state, run, a, x)
                else:
                    table = "meeting_effects" if a["action_kind"] == "meeting" else "effects"
                    effect = bounded_json(db.execute(f"SELECT payload FROM {table} WHERE execution_id=?", (x["id"],)).fetchone()[0])
                    if a["action_kind"] == "meeting":
                        ids = [bounded_json(r[0])["id"] for r in db.execute("SELECT payload FROM invitations WHERE effect_id=? ORDER BY rowid", (effect["effect_id"],))]
                        receipt = {"effect_id": effect["effect_id"], "event_id": effect["event_id"], "organizer_calendar_id": a["review"]["calendar_id"],
                                   "attendee_ids": a["prepared"]["attendee_ids"], "invitation_ids": ids, "completed_at": effect["committed_at"]}
                        validate("MeetingReceipt", receipt)
                    else:
                        receipt = {"effect_id": effect["effect_id"], "channel": effect["channel"], "recipient_ids": effect["recipient_ids"], "completed_at": effect["committed_at"]}
                    x.update(status="succeeded", receipt=receipt)
                    self._store.save_execution(db, x)
                    self._action_event(db, state, run, "completed", a, execution_id=x["id"], receipt=receipt)
                    self._settle_decision(db, state, run, a, x)
                return clone(run)
            if run["cancel"] or self._faults.cancel_before_dispatch or state["seconds"] >= run["deadline"]:
                run["cancel"] = run["cancel"] or self._faults.cancel_before_dispatch
                code = "tool_failed" if run["cancel"] else "tool_timeout"
                if x:
                    self._fail_execution(db, state, run, a, x, code)
                else:
                    self._emit(db, state, "decision.not_started", run, {"error": code, "cancelled": run["cancel"]})
                    self._settle_decision(db, state, run, a, error=code)
                return clone(run)
            if phase == "resolve":
                self._action_event(db, state, run, "decision_validated", a, decision=choice, decision_run_id=run["id"])
                if a["status"] == "pending" and state["seconds"] >= a["expires_seconds"]:
                    a["status"] = "expired"
                    self._store.save_approval(db, a)
                    self._action_event(db, state, run, "expired", a)
                if choice == "review" or a["status"] != "pending":
                    self._settle_decision(db, state, run, a)
                elif choice == "reject":
                    a["status"] = "rejected"
                    self._store.save_approval(db, a)
                    self._action_event(db, state, run, "rejected", a)
                    self._settle_decision(db, state, run, a)
                else:
                    a.update(status="approved", decision_run_id=run["id"])
                    x = {"id": _id("execution"), "action_kind": a["action_kind"], "approval_id": a["id"], "decision_run_id": run["id"],
                         "status": "prepared", "prepared_digest": a["prepared_digest"], "dispatch": None, "dispatch_digest": None, "receipt": None, "error": None}
                    self._store.save_approval(db, a)
                    self._store.save_execution(db, x)
                    run["decision_phase"] = "preflight"
                    self._save_run(db, run)
                return clone(run)
            if phase == "preflight":
                if a["action_kind"] == "meeting":
                    try:
                        self._fault_point(db, state, run, "preflight", a["call_id"])
                    except SyntheticError as exc:
                        self._fail_execution(db, state, run, a, x, exc.code)
                        return clone(run)
                try:
                    if self._faults.preflight_failure:
                        raise SyntheticError("preflight_failed")
                    dispatch = self._current_dispatch(db, run, a)
                except (SyntheticError, ValueError):
                    self._fail_execution(db, state, run, a, x, "preflight_failed")
                    return clone(run)
                x.update(status="invoking", dispatch=dispatch, dispatch_digest=digest(dispatch))
                self._store.save_execution(db, x)
                self._action_event(db, state, run, "authorized_to_dispatch", a, execution_id=x["id"], decision_run_id=run["id"], dispatch_digest=x["dispatch_digest"])
                self._action_event(db, state, run, "invoking", a, execution_id=x["id"], **({"dispatch_digest": x["dispatch_digest"]} if a["action_kind"] == "meeting" else {}))
                run["decision_phase"] = "invoke"
                self._save_run(db, run)
                return clone(run)
            if phase != "invoke":
                raise ValueError("decision_phase")
            if a["action_kind"] == "meeting":
                try:
                    self._fault_point(db, state, run, "before_commit", a["call_id"])
                except SyntheticError as exc:
                    self._fail_execution(db, state, run, a, x, exc.code)
                    return clone(run)
            end, deadline = state["seconds"] + self._faults.decision_duration, min(run["deadline"], state["seconds"] + self._budget.tool_seconds)
            cancel = self._faults.cancel_at
            if cancel is not None and state["seconds"] <= cancel <= min(end, deadline):
                state["seconds"], run["cancel"] = cancel, True
            else:
                state["seconds"] = min(end, deadline)
            self._save_state(db, state)
            if run["cancel"] or end >= deadline or self._faults.dispatch_failure:
                self._fail_execution(db, state, run, a, x, "tool_timeout" if end >= deadline and not run["cancel"] else "tool_failed")
                return clone(run)
            try:
                dispatch = self._current_dispatch(db, run, a)
                if dispatch != x["dispatch"] or digest(dispatch) != x["dispatch_digest"]:
                    raise SyntheticError("preflight_failed")
            except (SyntheticError, ValueError):
                self._fail_execution(db, state, run, a, x, "preflight_failed")
                return clone(run)
            destination = dispatch["calendar_id"] if a["action_kind"] == "meeting" else dispatch["destination"]
            self._action_event(db, state, run, "commit_authorized", a, execution_id=x["id"], dispatch_digest=x["dispatch_digest"])
            self._action_event(db, state, run, "dispatched", a, execution_id=x["id"], dispatch_arguments=dispatch, dispatch_digest=x["dispatch_digest"], fake_destination=destination)
            if a["action_kind"] == "meeting":
                effect = self._commit_meeting(db, state, run, a, x, dispatch)
                extra = {"event_id": effect["event_id"]}
            elif a["action_kind"] == "message":
                effect = self._store.commit_effect(db, {"effect_id": _id("effect"), "execution_id": x["id"], "channel": dispatch["channel"],
                    "sender_id": dispatch["sender_id"], "recipient_ids": [p["person_id"] for p in dispatch["recipients"]], "subject": dispatch["subject"],
                    "body": dispatch["body"], "prepared_digest": a["prepared_digest"], "dispatch_digest": x["dispatch_digest"], "committed_at": self._timestamp(state["seconds"])}, destination)
                extra = {"channel": effect["channel"]}
            else:
                raise ValueError("action_kind")
            self._action_event(db, state, run, "simulated", a, execution_id=x["id"], effect_id=effect["effect_id"], fake_destination=destination, **extra)
            if self._faults.cancel_after_commit:
                run["cancel"] = True
                self._emit(db, state, "run.cancel_requested", run, {"source": "after_fake_commit"})
            run["decision_phase"] = "receipt"
            self._save_run(db, run)
            return clone(run)

    def calendar_boundary(self, session, requested_calendar_id, arguments):
        try:
            args, window = read_arguments(arguments, self._rules)
            with self._store.read() as db:
                _, identity = self._auth(db, session)
                return self._calendar.read(db, identity, args, window, requested_calendar_id)[0]
        except TimeError as exc:
            return {"error": exc.code, "field": exc.field}
        except SyntheticError as exc:
            return {"error": exc.code, "field": None}

    def _fault_point(self, db, state, run, phase, call_id):
        hits = self._fault_hits
        key = run["id"] + ":" + phase + ":" + call_id
        hits[key] = hits.get(key, 0) + 1
        selected = [f for f in self._faults.calendar_faults if f.phase == phase and
                    (f.call_id == call_id or f.call_id is None and run.get("kind") == "decision") and f.occurrence == hits[key]]
        if not selected:
            return
        fault = selected[0]
        if fault.mode == "raise":
            raise RuntimeError("FICTIONAL_INTERNAL_HANDLER_DETAIL")
        if fault.mode == "hold":
            run["held_barrier"] = phase
        elif fault.mode == "cancel":
            run["cancel"] = True
            self._emit(db, state, "run.cancel_requested", run, {"source": "bound_fault_schedule"})
        elif fault.mode == "receipt_loss":
            run["fault_receipt_loss"] = True
        elif fault.mode == "timeout":
            deadline = min(run["deadline"], state["seconds"] + self._budget.tool_seconds)
            result = self._advance(db, state, run, fault.duration, deadline)
            if result:
                raise SyntheticError("tool_timeout" if result == "timeout" else "tool_failed")

    def _recover_error(self, lease):
        try:
            with self._store.transaction() as db:
                state, run = self._leased(db, lease)
                if run.get("kind") == "decision":
                    a = self._store.approval(db, run["decision"]["approval_id"])
                    if a["action_kind"] == "meeting":
                        self._fault_point(db, state, run, "failure_recording", a["call_id"])
        except Exception:
            self._persistence_fenced = True
            raise SyntheticError("persistence_unavailable") from None
        return super()._recover_error(lease)

    def release_barrier(self, session, run_id):
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            run = self._run(db, run_id)
            if not run.get("held_barrier") or not run["lease"]:
                raise SyntheticError("state_conflict")
            run["held_barrier"] = None
            self._save_run(db, run)

    def execute(self, session):
        lease = self.acquire(session)
        if lease is None:
            return None
        while True:
            result = self.step(lease)
            if result["status"] in {"completed", "cancelled", "failed"} or result.get("held_barrier"):
                return result

    def _settle_decision(self, db, state, run, a, execution=None, *, error=None):
        if a["action_kind"] == "meeting":
            self._fault_point(db, state, run, "settlement", a["call_id"])
            if execution and execution["receipt"] is not None:
                receipt = execution["receipt"]
                validate("MeetingReceipt", receipt)
                effect = bounded_json(db.execute("SELECT payload FROM meeting_effects WHERE execution_id=?", (execution["id"],)).fetchone()[0])
                ids = [bounded_json(r[0])["id"] for r in db.execute("SELECT payload FROM invitations WHERE effect_id=? ORDER BY rowid", (effect["effect_id"],))]
                if receipt != {"effect_id": effect["effect_id"], "event_id": effect["event_id"], "organizer_calendar_id": a["review"]["calendar_id"],
                               "attendee_ids": a["prepared"]["attendee_ids"], "invitation_ids": ids, "completed_at": effect["committed_at"]}:
                    raise ValueError("receipt_correspondence")
        return super()._settle_decision(db, state, run, a, execution, error=error)

    def reset(self, session):
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            runs = [bounded_json(r[0]) for r in db.execute("SELECT payload FROM runs")]
            if getattr(self, "_persistence_fenced", False) or any(r["lease"] for r in runs):
                raise SyntheticError("reset_busy")
            self._emit(db, state, "reset.started", None)
            for run in runs:
                self._supersede(db, state, run)
                if run["status"] not in {"completed", "failed", "cancelled"}:
                    self._finish(db, state, run, "cancelled", "reset_fenced")
            db.execute("DELETE FROM queue")
            self._emit(db, state, "reset.completed", None, {"next_generation": self.generation + 1})
            state["archived"] = True
            self._save_state(db, state)
        return self._target.fresh(subject=state["owner"], generation=self.generation + 1)

    def calendar_account_change(self, session, body):
        try:
            validate("CalendarAccountChange", body)
        except ValueError:
            raise SyntheticError("invalid_arguments") from None
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            row = db.execute("SELECT payload FROM calendar_accounts WHERE id=?", (body["calendar_id"],)).fetchone()
            if row is None:
                raise SyntheticError("resource_unavailable")
            value = bounded_json(row[0])
            if value["revision"] != body["expected_revision"]:
                raise SyntheticError("state_conflict")
            before = digest(value)
            changed = {k: v for k, v in body.items() if k.endswith("_enabled") and v is not None and value[k] != v}
            if not changed:
                raise SyntheticError("invalid_arguments")
            value.update(changed)
            value["revision"] += 1
            db.execute("UPDATE calendar_accounts SET payload=? WHERE id=?", (canonical(value), value["id"]))
            self._emit(db, state, "calendar.account_changed", None, {"calendar_id": value["id"], "expected_revision": body["expected_revision"],
                "new_revision": value["revision"], "before_digest": before, "after_digest": digest(value)})
            return clone(value)

    def restricted_truth(self, session):
        result = super().restricted_truth(session)
        with self._store.read() as db:
            self._auth(db, session)
            for table in ("calendar_records", "meeting_effects", "calendar_projections", "invitations", "normalizations"):
                result[table] = [bounded_json(r[0]) for r in db.execute(f"SELECT payload FROM {table} ORDER BY rowid")]
        return result
