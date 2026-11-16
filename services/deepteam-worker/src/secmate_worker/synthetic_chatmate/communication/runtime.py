"""Scripted communication with persisted host-only decisions and local fake effects."""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import ValidationError

from ...job_runtime import canonical, require_permission
from ..contracts import READ_TOOL, TARGET_ID, ConversationRead, Lease, SyntheticError, clone, digest, strict_json
from ..runtime import Assessment, TERMINAL, _id
from .artifacts import CommunicationBundle
from .contracts import (
    DECIDE, DIRECTORY, MAIL, PROPOSE, TEAMS, VERSION, ActionDecision, CommunicationBudget,
    CommunicationFaults, DecisionOutput, Dispatch, Event, INPUTS, OUTPUTS, ProposeMessage,
    SearchMail, ToolError, ToolResult, normalize,
)
from .services import FakeServices, HostIdentity
from .store import CommunicationStore


class CommunicationTarget:
    def __init__(self, root: Path, bundle=None):
        require_permission()
        self.bundle = bundle or CommunicationBundle.load()
        # Revalidate schemas/capabilities before publishing any enabled definition.
        CommunicationBundle.from_parts({k: strict_json(v) for k, v in self.bundle.artifacts})
        target = Path(root).resolve() / "targets" / TARGET_ID
        if target.exists():
            if (target / VERSION).exists():
                raise SyntheticError("target_version_collision")
            old = target / "0.1.1"
            try:
                registration = strict_json((old / "registration.json").read_text(encoding="utf-8"))
                if registration["target_id"] != TARGET_ID or registration["target_version"] != "0.1.1":
                    raise ValueError("identity")
                for key, expected in registration["definition_digests"].items():
                    if not key.isidentifier() or digest(strict_json((old / "definitions" / f"{key}.json").read_text(encoding="utf-8"))) != expected:
                        raise ValueError("definition")
            except (OSError, ValueError, KeyError):
                raise SyntheticError("unowned_target_namespace") from None
        else:
            target.mkdir(parents=True, exist_ok=False)
        self.path = target / VERSION
        try:
            self.path.mkdir(exist_ok=False)
        except FileExistsError:
            raise SyntheticError("target_version_collision") from None
        self.assessments = self.path / "assessments"
        self.assessments.mkdir()
        definitions = self.path / "definitions"
        definitions.mkdir()
        for key, value in self.bundle.artifacts:
            with (definitions / f"{key}.json").open("x", encoding="utf-8") as stream:
                stream.write(value)
        with (self.path / "registration.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical({"target_id": TARGET_ID, "target_version": VERSION,
                                    "manifesto_version": "0.1.2", "phase_scope": [0, 1, 2],
                                    "api_registration": False, "deepteam_provider": False,
                                    "definition_digests": {k: digest(strict_json(v)) for k, v in self.bundle.artifacts}}))

    def fresh(self, *, subject="subject-ada", faults=None, generation=1):
        return CommunicationAssessment(self, subject, faults or CommunicationFaults(), generation)


class CommunicationAssessment(Assessment):
    def __init__(self, target, subject, faults, generation):
        require_permission()
        self._target, self._bundle = target, target.bundle
        if subject not in {u["subject"] for u in self._bundle.get("seed")["users"]}:
            raise SyntheticError("invalid_host_identity")
        self.id, self.generation = _id("assessment"), generation
        self._watchdog_started = None
        self.path = target.assessments / self.id
        self.path.mkdir(exist_ok=False)
        self._faults = CommunicationFaults.model_validate_json(faults.model_dump_json())
        self._binding = self._bundle.bindings(self._faults.model_dump(), self.id, generation)
        self._binding_digest = digest(self._binding)
        for name, value in (("bindings", self._binding), ("faults", self._faults.model_dump())):
            with (self.path / f"{name}.json").open("x", encoding="utf-8") as stream:
                stream.write(canonical(value))
        self._store = CommunicationStore(self.path / "assessment.sqlite3", {
            "assessment_id": self.id, "generation": generation, "owner": subject,
            "seconds": 0.0, "archived": False, "accepted": False, "sessions": {},
        }, self._bundle.get("seed"))
        self._services = FakeServices(self.id, generation, self._binding["artifact_digests"]["seed"], self._binding_digest)
        self.session = self.host_session(subject)
        with self._store.transaction() as db:
            state = self._state(db)
            self._emit(db, state, "assessment.created", None, {"binding_digest": self._binding_digest})
            self._emit(db, state, "assessment.bindings_loaded", None, {"bindings": self._binding})

    @property
    def _budget(self):
        return CommunicationBudget.model_validate(self._bundle.get("budget"))

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        last = db.execute("SELECT max(id) FROM events").fetchone()[0] or 0
        data = data or {}
        event = Event.model_validate({
            "event_schema_version": VERSION, "target_id": TARGET_ID, "target_version": VERSION,
            "assessment_id": self.id, "state_generation": self.generation,
            "run_id": run["id"] if run else None, "event_id": last + 1,
            "logical_time": self._timestamp(state["seconds"]), "type": kind,
            "actor_ref": state["owner"], "call_id": call_id or data.get("call_id"),
            "action_id": data.get("approval_id"), "caused_by": last or None, "data": data,
            "binding_digest": digest(run["bindings"]) if run else self._binding_digest,
        }).model_dump()
        db.execute("INSERT INTO events (payload) VALUES (?)", (canonical(event),))
        return event["event_id"]

    def _request(self, run, state):
        request = super()._request(run, state)
        request["tools"] += [{"type": "function", "name": name,
                              "parameters": self._bundle.get("schemas")["tools"][name]["input"]} for name in INPUTS]
        return request

    def _result(self, db, state, run, call_id, output, *, error=False, tool_name=READ_TOOL):
        if error:
            ToolError.model_validate(output)
        elif tool_name in OUTPUTS:
            OUTPUTS[tool_name].model_validate(output)
        refs = []
        if not error:
            refs = [output["source_ref"]] if "source_ref" in output else [item["source_ref"] for item in output.get("items", [])]
        status = "error" if error else "staged" if output.get("status") == "staged_for_approval" else "ok"
        result = ToolResult(call_id=call_id, status=status, output=output, source_refs=refs).model_dump()
        self._emit(db, state, "tool.result", run, {"name": tool_name, "result": result}, call_id)
        run["transcript"].append({"type": "function_call_output", "call_id": call_id, "output": canonical(output)})
        if error and output["error"] != "error_streak_exhausted":
            previous = run["streak"].get(tool_name, {"code": None, "count": 0})
            run["streak"][tool_name] = {"code": output["error"], "count": previous["count"] + 1 if previous["code"] == output["error"] else 1}
        elif not error:
            run["streak"].pop(tool_name, None)

    def _pending(self, db, run):
        return [strict_json(row[0]) for row in db.execute("SELECT payload FROM approvals")
                if strict_json(row[0])["originating_run_id"] == run["id"] and strict_json(row[0])["status"] == "pending"]

    def _supersede(self, db, state, run):
        for approval in self._pending(db, run):
            approval["status"] = "superseded"
            self._store.save_approval(db, approval)
            self._action_event(db, state, run, "superseded", approval)

    def _finish(self, db, state, run, status, reason, *, answer=None, outcome=None):
        if run.get("kind") != "decision":
            pending = self._pending(db, run)
            if status == "completed" and pending and outcome in {"Final", "Partial"}:
                outcome = "AwaitingApproval"
                answer = self._summary(pending[-1]["prepared"])
                run["approval_id"] = pending[-1]["id"]
            elif status in {"cancelled", "failed"}:
                self._supersede(db, state, run)
        super()._finish(db, state, run, status, reason, answer=answer, outcome=outcome)

    @staticmethod
    def _summary(prepared):
        return f"Review {prepared['channel']} message to {', '.join(prepared['recipient_ids'])}; approval required."

    def _action_event(self, db, state, run, stage, approval, **extra):
        return self._emit(db, state, f"action.{stage}", run, {
            "approval_id": approval["id"], "call_id": approval["call_id"],
            "originating_run_id": approval["originating_run_id"], "actor": approval["actor"],
            "connector_owner": approval["connector_owner"], "conversation_id": approval["conversation_id"],
            "assessment_id": self.id, "state_generation": self.generation,
            "expires_at": approval["expires_at"], "prepared_digest": approval["prepared_digest"],
            "transformation_version": approval["transformation_version"], **extra,
        }, approval["call_id"])

    def _stage(self, db, state, run, call, args):
        prepared = args.model_dump()
        identity = HostIdentity.model_validate(run["identity"])
        _, recipients, _ = self._services.prepare_recipients(db, identity, args)
        same = next((a for a in self._pending(db, run) if a["prepared_digest"] == digest(prepared)), None)
        if same:
            run["remaining"] += 1
            self._emit(db, state, "budget.refunded", run, {"pool": "execution", "reason": "already_staged", "remaining": run["remaining"]}, call.call_id)
            return {"status": "staged_for_approval", "approval_id": same["id"],
                    "summary": self._summary(prepared), "expires_at": same["expires_at"]}
        if self._faults.preparation_failure:
            raise SyntheticError("tool_failed")
        self._supersede(db, state, run)
        expiry = state["seconds"] + 600.0
        approval = {
            "id": _id("approval"), "status": "pending", "actor": identity.subject,
            "connector_owner": identity.connector_owner, "tenant": identity.tenant,
            "conversation_id": run["conversation_id"], "assessment_id": self.id, "state_generation": self.generation,
            "originating_run_id": run["id"], "call_id": call.call_id, "transformation_version": "message-local-v1",
            "prepared": prepared, "prepared_digest": digest(prepared),
            "recipient_digest": digest(prepared["recipient_ids"]),
            "content_digest": digest({k: prepared[k] for k in ("subject", "body")}),
            "review": {**prepared, "prepared_digest": digest(prepared)}, "recipient_snapshot": recipients,
            "expires_seconds": expiry, "expires_at": self._timestamp(expiry), "decision_run_id": None,
        }
        self._store.save_approval(db, approval)
        self._action_event(db, state, run, "staged", approval, review=approval["review"],
                           recipient_digest=approval["recipient_digest"], content_digest=approval["content_digest"])
        return {"status": "staged_for_approval", "approval_id": approval["id"],
                "summary": self._summary(prepared), "expires_at": approval["expires_at"]}

    def _authorize(self, db, run, name, args):
        identity = HostIdentity.model_validate(run["identity"])
        if name == PROPOSE:
            self._services.prepare_recipients(db, identity, args)
        elif name == TEAMS:
            # Authorization only: content/paging happens after charge and dispatch.
            spaces = self._store.records(db, "spaces")
            if not any(s["id"] == args.space_id and s["tenant"] == identity.tenant and
                       identity.connector_owner in s["members"] for s in spaces):
                raise SyntheticError("resource_unavailable")
        elif name in {MAIL, DIRECTORY} and not normalize(args.query):
            raise SyntheticError("invalid_arguments")

    def _dispatch(self, db, state, run, calls):
        run.setdefault("provider_remaining", self._budget.fake_provider_read)
        capabilities = self._bundle.get("capabilities")
        # Manifesto 6.4: reject the entire multi-write batch before any pool charge.
        if sum(c.name == PROPOSE for c in calls) > 1:
            for call in calls:
                self._emit(db, state, "tool.requested", run, {"name": call.name, "arguments": call.arguments}, call.call_id)
                if call.name == PROPOSE:
                    self._emit(db, state, "action.requested", run, {"name": call.name}, call.call_id)
                    self._emit(db, state, "action.validation_rejected", run, {"code": "unsupported_write_batch"}, call.call_id)
                self._emit(db, state, "tool.validation_rejected", run, {"code": "unsupported_write_batch"}, call.call_id)
                self._result(db, state, run, call.call_id, {"error": "unsupported_write_batch"}, error=True, tool_name=call.name)
            self._supersede(db, state, run)
            return
        decisions = []
        for call in calls:
            self._emit(db, state, "tool.requested", run, {"name": call.name, "arguments": call.arguments}, call.call_id)
            if call.name == PROPOSE:
                self._emit(db, state, "action.requested", run, {"name": call.name, "arguments": call.arguments}, call.call_id)
            args, code = None, None
            if call.name not in capabilities["enabled"]:
                code = "capability_disabled" if call.name in capabilities["disabled"] else "unknown_tool"
            else:
                try:
                    model = ConversationRead if call.name == READ_TOOL else INPUTS[call.name]
                    args = model.model_validate(strict_json(call.arguments))
                    if call.name in {MAIL, DIRECTORY} and not normalize(args.query):
                        raise ValueError("empty_query")
                except (ValidationError, ValueError, TypeError):
                    code = "invalid_arguments"
            self._emit(db, state, "tool.validation_rejected" if code else "tool.validated", run,
                       {"name": call.name, "code": code, "native_metadata": self._bundle.get("native_metadata").get(call.name)}, call.call_id)
            if call.name == PROPOSE:
                self._emit(db, state, "action.validation_rejected" if code else "action.validated", run,
                           {"code": code, "prepared_digest": digest(args.model_dump()) if args else None}, call.call_id)
            if code is None:
                try:
                    self._authorize(db, run, call.name, args)
                except SyntheticError as exc:
                    code = exc.code
                self._emit(db, state, "tool.authorization_rejected" if code else "tool.authorized", run,
                           {"name": call.name, "connector_owner": run["identity"]["connector_owner"],
                            "resource_id": args.space_id if call.name == TEAMS else run["identity"]["connector_owner"],
                            "owner": run["owner"], "code": code}, call.call_id)
                if call.name in {MAIL, TEAMS}:
                    self._emit(db, state, "retrieval.authorization_rejected" if code else "retrieval.authorized", run,
                               {"name": call.name, "resource_id": args.space_id if call.name == TEAMS else run["identity"]["connector_owner"],
                                "connector_owner": run["identity"]["connector_owner"], "code": code}, call.call_id)
                if call.name == PROPOSE:
                    self._emit(db, state, "action.authorization_rejected" if code else "action.authorized_to_prepare", run,
                               {"connector_owner": run["identity"]["connector_owner"], "conversation_id": run["conversation_id"], "code": code}, call.call_id)
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
            decisions.append((call, args, code))
        halted = False
        for call, args, code in decisions:
            if not self._checkpoint(db, state, run):
                return
            if code is None and halted:
                code = "not_run"
            if code:
                self._result(db, state, run, call.call_id, {"error": code}, error=True, tool_name=call.name)
                if call.name == PROPOSE and code != "budget_exhausted":
                    self._supersede(db, state, run)
                continue
            self._emit(db, state, "tool.dispatched", run, {"name": call.name, "destination": "assessment_fake_service"}, call.call_id)
            fault = next((f for f in self._faults.tools if f.call_id == call.call_id), None)
            result = self._advance(db, state, run, fault.duration if fault else 0.0,
                                   min(run["deadline"], state["seconds"] + self._budget.tool_seconds))
            if result == "cancelled":
                return
            code = "tool_timeout" if result == "timeout" else fault.error if fault else None
            if code == "tool_timeout":
                self._emit(db, state, "tool.timeout", run, {}, call.call_id)
            identity = HostIdentity.model_validate(run["identity"])
            try:
                if code:
                    raise SyntheticError(code)
                if call.name == READ_TOOL:
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
                    output = self._stage(db, state, run, call, args)
                    staged_record = self._store.approval(db, output.get("approval_id"))
                    if output.get("status") != "staged_for_approval" or staged_record is None or staged_record["originating_run_id"] != run["id"]:
                        raise SyntheticError("write_not_staged")
                if call.name in OUTPUTS and "error" not in output:
                    OUTPUTS[call.name].model_validate(output)
            except SyntheticError as exc:
                output = {"error": exc.code}
            except Exception:
                output = {"error": "tool_failed"}
            if len(canonical(output)) > self._budget.output_characters:
                output = {"error": "tool_output_limit_exceeded"}
            if call.name == PROPOSE and "error" in output:
                self._supersede(db, state, run)
                self._emit(db, state, "action.failed", run, {"call_id": call.call_id, "error": output["error"],
                           "stage": "preparation", "connector_owner": identity.connector_owner}, call.call_id)
            if call.name in {MAIL, TEAMS} and "error" not in output:
                self._emit(db, state, "retrieval.result", run, {"name": call.name,
                           "record_ids": [i["id"] for i in output["items"]],
                           "source_refs": [i["source_ref"] for i in output["items"]]}, call.call_id)
            self._result(db, state, run, call.call_id, output, error="error" in output, tool_name=call.name)
            halted = bool(fault and fault.halt)

    def mailbox_boundary(self, session, resource, arguments):
        """Trusted host-only direct ACL conformance seam; no mailbox model argument."""
        args = SearchMail.model_validate(arguments)
        error = None
        with self._store.transaction() as db:
            state, identity = self._auth(db, session)
            try:
                output = self._services.mailbox(db, HostIdentity.model_validate(identity), resource, args)
            except SyntheticError as exc:
                error = exc.code
                output = {"error": error}
            self._emit(db, state, "retrieval.authorization_rejected" if error else "retrieval.authorized", None,
                       {"boundary": "typed_mailbox", "resource_id": resource,
                        "connector_owner": identity["connector_owner"], "code": error})
            if not error:
                self._emit(db, state, "retrieval.result", None, {"boundary": "typed_mailbox", "result": output})
        return output

    def advance_clock(self, session, seconds):
        if type(seconds) not in {int, float} or not 0 <= seconds < 1e9:
            raise SyntheticError("invalid_arguments")
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            if any(strict_json(r[0])["lease"] for r in db.execute("SELECT payload FROM runs")):
                raise SyntheticError("clock_busy")
            state["seconds"] += seconds
            self._save_state(db, state)
            self._emit(db, state, "clock.advanced", None, {"seconds": seconds})

    def update_person(self, session, person):
        """Trusted conformance control for relevant/unrelated current-directory changes."""
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            self._store.update_person(db, person)
            self._emit(db, state, "directory.state_changed", None, {"person_id": person["person_id"], "digest": digest(person)})

    def _approval_auth(self, db, identity, conversation_id, approval_id):
        a = self._store.approval(db, approval_id)
        if a is None or (a["actor"], a["connector_owner"], a["tenant"], a["conversation_id"], a["assessment_id"], a["state_generation"]) != (
            identity["subject"], identity["connector_owner"], identity["tenant"], conversation_id, self.id, self.generation
        ):
            raise SyntheticError("resource_unavailable")
        return a

    def submit_decision(self, session, body, *, conversation_id):
        try:
            decision = ActionDecision.model_validate(body).model_dump()
        except ValidationError:
            raise SyntheticError("invalid_arguments") from None
        with self._store.transaction() as db:
            state, identity = self._auth(db, session)
            a = self._approval_auth(db, identity, conversation_id, decision["approval_id"])
            run = {"id": _id("decision"), "kind": "decision", "conversation_id": conversation_id,
                   "identity": identity, "owner": identity["subject"], "decision": decision,
                   "decision_phase": "resolve", "decision_result": None,
                   "status": "queued", "lease": None, "cancel": False, "result_message_id": None,
                   "round": 0, "remaining": 0, "outcome": None, "partial": False,
                   "answer": None, "terminal_reason": None}
            run["bindings"] = {**self._binding, "run_id": run["id"]}
            self._save_run(db, run)
            self._emit(db, state, "run.created", run, {"kind": "decision", "model_invocation": False})
            self._action_event(db, state, run, "decision_received", a, decision=decision["decision"], decision_run_id=run["id"])
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            run = self._run(db, run["id"])
            if self._faults.enqueue_failure:
                self._finish(db, state, run, "failed", "dispatch_unavailable")
                raise_error = True
            else:
                self._store.enqueue(db, run["id"])
                self._emit(db, state, "run.enqueued", run, {"kind": "decision"})
                raise_error = False
        if raise_error:
            raise SyntheticError("dispatch_unavailable", run["id"])
        return clone(run)

    def acquire(self, session):
        lease = super().acquire(session)
        if lease:
            with self._store.transaction() as db:
                state, run = self._leased(db, lease)
                if run.get("kind") == "decision":
                    run.setdefault("control_deadline", state["seconds"] + 60)
                    run["deadline"] = run["control_deadline"]
                    self._save_run(db, run)
                    self._emit(db, state, "decision.deadline_bound", run, {"deadline": self._timestamp(run["deadline"]), "seconds": 60})
        return lease

    def step(self, lease):
        with self._store.read() as db:
            _, run = self._leased(db, lease)
        if run.get("kind") != "decision":
            return super().step(lease)
        return self._decision_step(lease)

    def _decision_output(self, a, execution=None, *, error=None):
        return DecisionOutput.model_validate({
            "approval_id": a["id"], "approval_status": a["status"],
            "execution_id": execution["id"] if execution else None,
            "execution_status": execution["status"] if execution else None,
            "review": a["review"], "expires_at": a["expires_at"],
            "receipt": execution["receipt"] if execution else None,
            "error": error or (execution["error"] if execution else None),
        }).model_dump()

    def _settle_decision(self, db, state, run, a, execution=None, *, error=None):
        run["decision_result"] = self._decision_output(a, execution, error=error)
        self._finish(db, state, run, "cancelled" if run["cancel"] else "completed",
                     "owner_cancelled" if run["cancel"] else "decision_resolved", answer=None, outcome=None)

    def _decision_step(self, lease):
        # Each phase is its own durable transaction. In particular, invoking is
        # committed before fake effect commit, and receipt export is another phase.
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            a = self._approval_auth(db, run["identity"], run["conversation_id"], run["decision"]["approval_id"])
            x = self._store.execution(db, a["id"])
            if self._faults.cancel_at is not None and state["seconds"] >= self._faults.cancel_at and not run["cancel"]:
                run["cancel"] = True
                self._emit(db, state, "run.cancel_requested", run, {"source": "bound_fault_schedule"})
            if self._watchdog_started is not None and time.perf_counter() - self._watchdog_started >= 60:
                if x and x["status"] == "invoking":
                    self._unknown(db, state, run, a, x)
                else:
                    self._finish(db, state, run, "failed", "environmental_watchdog")
                return clone(run)
            phase = run["decision_phase"]
            if phase == "resolve":
                decision = run["decision"]["decision"]
                self._action_event(db, state, run, "decision_validated", a, decision=decision, decision_run_id=run["id"])
                # Authorization precedes replay; consumed replay precedes expiry.
                if a["status"] == "approved" and decision == "approve":
                    if a["decision_run_id"] != run["id"]:
                        self._settle_decision(db, state, run, a, error="resource_unavailable")
                    else:
                        self._action_event(db, state, run, "replayed", a, execution_id=x["id"], execution_status=x["status"])
                        if x["status"] == "prepared":
                            run["decision_phase"] = "preflight"
                            self._save_run(db, run)
                        elif x["status"] == "invoking":
                            self._unknown(db, state, run, a, x)
                        else:
                            self._settle_decision(db, state, run, a, x)
                    return clone(run)
                if a["status"] == "pending" and state["seconds"] >= a["expires_seconds"]:
                    a["status"] = "expired"
                    self._store.save_approval(db, a)
                    self._action_event(db, state, run, "expired", a)
                if decision == "review" or a["status"] != "pending":
                    self._settle_decision(db, state, run, a, x if decision == "review" and a["status"] == "approved" else None)
                elif run["cancel"] or self._faults.cancel_before_dispatch:
                    run["cancel"] = True
                    self._settle_decision(db, state, run, a)
                elif decision == "reject":
                    a["status"] = "rejected"
                    self._store.save_approval(db, a)
                    self._action_event(db, state, run, "rejected", a)
                    self._settle_decision(db, state, run, a)
                else:
                    a.update(status="approved", decision_run_id=run["id"])
                    x = {"id": _id("execution"), "approval_id": a["id"], "decision_run_id": run["id"],
                         "status": "prepared", "prepared_digest": a["prepared_digest"], "dispatch": None,
                         "dispatch_digest": None, "receipt": None, "error": None}
                    self._store.save_approval(db, a)
                    self._store.save_execution(db, x)
                    run["decision_phase"] = "preflight"
                    self._save_run(db, run)
                return clone(run)
            if phase == "receipt":
                # A committed effect survives cancellation and the decision deadline.
                if self._faults.receipt_loss:
                    self._unknown(db, state, run, a, x)
                else:
                    effect = strict_json(db.execute("SELECT payload FROM effects WHERE execution_id=?", (x["id"],)).fetchone()[0])
                    x.update(status="succeeded", receipt={"effect_id": effect["effect_id"], "channel": effect["channel"],
                             "recipient_ids": effect["recipient_ids"], "completed_at": effect["committed_at"]})
                    self._store.save_execution(db, x)
                    self._action_event(db, state, run, "completed", a, execution_id=x["id"], receipt=x["receipt"])
                    self._settle_decision(db, state, run, a, x)
                return clone(run)
            if run["cancel"] or self._faults.cancel_before_dispatch or state["seconds"] >= run["deadline"]:
                # This leased local run has not entered commit. An abandoned
                # invoking record instead takes the uncertain replay branch above.
                run["cancel"] = run["cancel"] or self._faults.cancel_before_dispatch
                self._fail_execution(db, state, run, a, x, "tool_timeout" if state["seconds"] >= run["deadline"] else "tool_failed")
                return clone(run)
            if phase == "preflight":
                try:
                    if self._faults.preflight_failure:
                        raise SyntheticError("preflight_failed")
                    args = ProposeMessage.model_validate(a["prepared"])
                    sender, recipients, destination = self._services.prepare_recipients(db, HostIdentity.model_validate(run["identity"]), args)
                    if recipients != a["recipient_snapshot"] or digest(args.model_dump()) != a["prepared_digest"]:
                        raise SyntheticError("preflight_failed")
                    dispatch = Dispatch(channel=args.channel, sender_id=sender, recipients=recipients,
                                        destination=destination, subject=args.subject, body=args.body).model_dump()
                    x.update(dispatch=dispatch, dispatch_digest=digest(dispatch), status="invoking")
                    self._store.save_execution(db, x)
                    self._action_event(db, state, run, "authorized_to_dispatch", a, execution_id=x["id"],
                                       decision_run_id=run["id"], dispatch_digest=x["dispatch_digest"])
                    self._action_event(db, state, run, "invoking", a, execution_id=x["id"])
                    run["decision_phase"] = "invoke"
                    self._save_run(db, run)
                except (SyntheticError, ValidationError):
                    self._fail_execution(db, state, run, a, x, "preflight_failed")
                return clone(run)
            end = state["seconds"] + self._faults.decision_duration
            deadline = min(run["deadline"], state["seconds"] + self._budget.tool_seconds)
            cancel_at = self._faults.cancel_at
            if cancel_at is not None and state["seconds"] <= cancel_at <= min(end, deadline):
                state["seconds"], run["cancel"] = cancel_at, True
                outcome = "cancelled"
                self._emit(db, state, "run.cancel_requested", run, {"source": "bound_fault_schedule"})
            else:
                state["seconds"] = min(end, deadline)
                outcome = "timeout" if end >= deadline else None
            self._save_state(db, state)
            if outcome:
                # This runner knows the local dispatch has not yet reached commit.
                self._fail_execution(db, state, run, a, x, "tool_timeout" if outcome == "timeout" else "tool_failed")
                return clone(run)
            if self._faults.dispatch_failure:
                self._fail_execution(db, state, run, a, x, "tool_failed")
                return clone(run)
            dispatch = x["dispatch"]
            self._action_event(db, state, run, "dispatched", a, execution_id=x["id"],
                               dispatch_arguments=dispatch, dispatch_digest=x["dispatch_digest"],
                               fake_destination=dispatch["destination"])
            effect = self._store.commit_effect(db, {
                "effect_id": _id("effect"), "execution_id": x["id"], "channel": dispatch["channel"],
                "sender_id": dispatch["sender_id"], "recipient_ids": [p["person_id"] for p in dispatch["recipients"]],
                "subject": dispatch["subject"], "body": dispatch["body"], "prepared_digest": a["prepared_digest"],
                "dispatch_digest": x["dispatch_digest"], "committed_at": self._timestamp(state["seconds"]),
            }, dispatch["destination"])
            self._action_event(db, state, run, "simulated", a, execution_id=x["id"], effect_id=effect["effect_id"],
                               channel=effect["channel"], fake_destination=dispatch["destination"])
            if self._faults.cancel_after_commit:
                run["cancel"] = True
                self._emit(db, state, "run.cancel_requested", run, {"source": "after_fake_commit"})
            run["decision_phase"] = "receipt"
            self._save_run(db, run)
            return clone(run)

    def _fail_execution(self, db, state, run, a, x, code):
        x.update(status="failed", error=code)
        self._store.save_execution(db, x)
        self._action_event(db, state, run, "failed", a, execution_id=x["id"], error=code)
        self._settle_decision(db, state, run, a, x)

    def _unknown(self, db, state, run, a, x):
        x.update(status="outcome_unknown", error="outcome_unknown", receipt=None)
        self._store.save_execution(db, x)
        self._action_event(db, state, run, "outcome_unknown", a, execution_id=x["id"], error="outcome_unknown")
        self._settle_decision(db, state, run, a, x)

    def redeliver_decision(self, session, run_id):
        """Trusted delivery of a persisted run, never replacement decision arguments."""
        with self._store.transaction() as db:
            state, identity = self._auth(db, session)
            run = self._run(db, run_id)
            if run.get("kind") != "decision" or run["lease"]:
                raise SyntheticError("decision_busy")
            a = self._approval_auth(db, identity, run["conversation_id"], run["decision"]["approval_id"])
            if run["decision_result"] is not None:
                self._action_event(db, state, run, "replayed", a, execution_status=run["decision_result"]["execution_status"])
                return clone(run["decision_result"])
            run.update(status="queued", decision_phase="resolve")
            self._save_run(db, run)
            if not db.execute("SELECT 1 FROM queue WHERE run_id=?", (run_id,)).fetchone():
                self._store.enqueue(db, run_id)
        return None

    def cancel(self, session, run_id):
        result = super().cancel(session, run_id)
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            run = self._run(db, run_id)
            if run.get("kind") != "decision":
                self._supersede(db, state, run)
        return result

    def restricted_truth(self, session):
        """Explicit observer-only surface; never used by exported-observation assertions."""
        with self._store.read() as db:
            self._auth(db, session)
            return {"evidence_surface": "restricted_fixture_truth",
                    "effects": [strict_json(r[0]) for r in db.execute("SELECT payload FROM effects ORDER BY rowid")],
                    "executions": [strict_json(r[0]) for r in db.execute("SELECT payload FROM executions ORDER BY rowid")],
                    "projections": [{"kind": r[0], "destination": r[1], "effect": strict_json(r[2])}
                                    for r in db.execute("SELECT kind,destination,payload FROM projections ORDER BY rowid")]}
