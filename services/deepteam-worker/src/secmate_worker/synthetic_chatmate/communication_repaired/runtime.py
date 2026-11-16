"""Corrected 0.2.1 runtime. No monkeypatching of frozen modules or global state."""
import time
from pathlib import Path

from pydantic import ValidationError

from ...job_runtime import canonical, require_permission
from ..contracts import READ_TOOL, TARGET_ID, ConversationRead, SyntheticError, digest, clone
from ..runtime import Assessment as Phase1Assessment, _id
from ..communication.runtime import CommunicationAssessment as LegacyAssessment
from ..communication.contracts import MAIL, TEAMS, DIRECTORY, PROPOSE, INPUTS, ProposeMessage, Dispatch, ToolResult, ToolError
from ..communication.services import HostIdentity
from .artifacts import CommunicationBundle, validate_predecessor
from .contracts import VERSION, Event, bounded_json, validate_output


class CommunicationTarget:
    def __init__(self, root, bundle=None):
        require_permission()
        supplied = bundle or CommunicationBundle.load()
        self.bundle = CommunicationBundle.from_parts({k: bounded_json(v, maximum=4000000) for k, v in supplied.artifacts})
        target = Path(root).resolve() / "targets" / TARGET_ID
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise SyntheticError("unowned_target_namespace")
            if (target / VERSION).exists():
                raise SyntheticError("target_version_collision")
            versions = list(target.iterdir())
            if any(p.name == VERSION for p in versions):
                raise SyntheticError("target_version_collision")
            if not versions or any(p.name not in {"0.1.1", "0.2.0"} for p in versions):
                raise SyntheticError("unowned_target_namespace")
            for predecessor in versions:
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
        for key, value in self.bundle.artifacts:
            with (definitions / f"{key}.json").open("x", encoding="utf-8") as stream:
                stream.write(value)
        with (self.path / "registration.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical({"target_id": TARGET_ID, "target_version": VERSION, "manifesto_version": "0.1.2",
                                    "phase_scope": [0, 1, 2], "api_registration": False, "deepteam_provider": False,
                                    "definition_digests": {k: digest(bounded_json(v, maximum=4000000)) for k, v in self.bundle.artifacts}}))

    def fresh(self, *, subject="subject-ada", faults=None, generation=1):
        from .contracts import CommunicationFaults
        return CommunicationAssessment(self, subject, faults or CommunicationFaults(), generation)


class CommunicationAssessment(LegacyAssessment):
    def _action_event(self, db, state, run, stage, approval, **extra):
        if stage == "staged":
            extra.update(recipient_snapshot=approval["recipient_snapshot"], recipient_snapshot_digest=digest(approval["recipient_snapshot"]))
        if stage == "completed" and extra.get("receipt"):
            extra["effect_id"] = extra["receipt"]["effect_id"]
        return super()._action_event(db, state, run, stage, approval, **extra)

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        last = db.execute("SELECT max(id) FROM events").fetchone()[0] or 0
        data = data or {}
        event = Event.model_validate({
            "event_schema_version": VERSION, "target_id": TARGET_ID, "target_version": VERSION,
            "assessment_id": self.id, "state_generation": self.generation,
            "run_id": run["id"] if run else None, "event_id": last + 1,
            "logical_time": self._timestamp(state["seconds"]), "type": kind, "actor_ref": state["owner"],
            "call_id": call_id or data.get("call_id"), "action_id": data.get("approval_id"),
            "caused_by": last or None, "data": data,
            "binding_digest": digest(run["bindings"]) if run else self._binding_digest,
        }).model_dump()
        db.execute("INSERT INTO events (payload) VALUES (?)", (canonical(event),))
        return event["event_id"]

    def _finish(self, db, state, run, status, reason, *, answer=None, outcome=None):
        if run.get("kind") != "decision" and reason == "model_empty_response" and self._pending(db, run):
            status, reason, outcome = "completed", "pending_approval", "Final"
        super()._finish(db, state, run, status, reason, answer=answer, outcome=outcome)

    def _result(self, db, state, run, call_id, output, *, error=False, tool_name=READ_TOOL):
        try:
            if error:
                ToolError.model_validate(output)
            else:
                validate_output(tool_name, output)
                if tool_name == READ_TOOL:
                    call = next(i for i in run["transcript"] if i.get("type") == "function_call" and i["call_id"] == call_id)
                    args = ConversationRead.model_validate(bounded_json(call["arguments"]))
                    if output != Phase1Assessment._read(self, run, args):
                        raise ValueError("read_projection")
            refs = [] if error else [output["source_ref"]] if "source_ref" in output else [i["source_ref"] for i in output.get("items", [])]
            ToolResult(call_id=call_id, status="error" if error else "staged" if tool_name == PROPOSE else "ok", output=output, source_refs=refs)
        except (ValueError, TypeError, KeyError, StopIteration, RecursionError):
            output, error = {"error": "tool_failed"}, True
        super()._result(db, state, run, call_id, output, error=error, tool_name=tool_name)

    def _dispatch(self, db, state, run, calls):
        run.setdefault("provider_remaining", self._budget.fake_provider_read)
        capabilities = self._bundle.get("capabilities")
        if sum(c.name == PROPOSE for c in calls) > 1:
            return super()._dispatch(db, state, run, calls)
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
                    args = model.model_validate(bounded_json(call.arguments, maximum=self._budget.context_characters))
                    if call.name in {MAIL, DIRECTORY} and not args.query.strip():
                        raise ValueError("empty_query")
                except (ValueError, TypeError):
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
                resource = args.space_id if call.name == TEAMS else run["snapshot_id"] if call.name == READ_TOOL else run["identity"]["connector_owner"]
                details = {"name": call.name, "resource_id": resource, "connector_owner": run["identity"]["connector_owner"],
                           "owner": run["owner"], "code": code}
                self._emit(db, state, "tool.authorization_rejected" if code else "tool.authorized", run, details, call.call_id)
                if call.name in {MAIL, TEAMS}:
                    self._emit(db, state, "retrieval.authorization_rejected" if code else "retrieval.authorized", run, details, call.call_id)
                if call.name == PROPOSE:
                    self._emit(db, state, "action.authorization_rejected" if code else "action.authorized_to_prepare", run,
                               {**details, "conversation_id": run["conversation_id"]}, call.call_id)
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
            if not code and halted:
                code = "not_run"
            if code:
                self._result(db, state, run, call.call_id, {"error": code}, error=True, tool_name=call.name)
                if call.name == PROPOSE and code != "budget_exhausted":
                    self._supersede(db, state, run)
                continue
            self._emit(db, state, "tool.dispatched", run, {"name": call.name, "destination": "assessment_fake_service"}, call.call_id)
            fault = next((f for f in self._faults.tools if f.call_id == call.call_id), None)
            elapsed = self._advance(db, state, run, fault.duration if fault else 0.0,
                                    min(run["deadline"], state["seconds"] + self._budget.tool_seconds))
            if elapsed == "cancelled":
                return
            code = "tool_timeout" if elapsed == "timeout" else fault.error if fault else None
            if code == "tool_timeout":
                self._emit(db, state, "tool.timeout", run, {}, call.call_id)
            try:
                if code:
                    raise SyntheticError(code)
                identity = HostIdentity.model_validate(run["identity"])
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
                    approval = self._store.approval(db, output.get("approval_id"))
                    if output.get("status") != "staged_for_approval" or approval is None or approval["originating_run_id"] != run["id"]:
                        raise SyntheticError("write_not_staged")
                if "error" not in output:
                    validate_output(call.name, output)
                if len(canonical(output)) > self._budget.output_characters:
                    output = {"error": "tool_output_limit_exceeded"}
            except SyntheticError as exc:
                output = {"error": exc.code}
            except Exception:
                output = {"error": "tool_failed"}
            if call.name == PROPOSE and "error" in output:
                self._supersede(db, state, run)
                self._emit(db, state, "action.failed", run, {"call_id": call.call_id, "error": output["error"], "stage": "preparation"}, call.call_id)
            if call.name in {MAIL, TEAMS} and "error" not in output:
                self._emit(db, state, "retrieval.result", run, {"name": call.name, "record_ids": [i["id"] for i in output["items"]],
                           "source_refs": [i["source_ref"] for i in output["items"]]}, call.call_id)
            self._result(db, state, run, call.call_id, output, error="error" in output, tool_name=call.name)
            halted = bool(fault and fault.halt)

    def step(self, lease):
        if getattr(self, "_persistence_fenced", False):
            raise SyntheticError("persistence_unavailable")
        with self._store.read() as db:
            _, run = self._leased(db, lease)
        try:
            return self._decision_step(lease) if run.get("kind") == "decision" else Phase1Assessment.step(self, lease)
        except SyntheticError as exc:
            if exc.code in {"stale_generation", "stale_lease", "invalid_session"}:
                raise
            return self._recover_error(lease)
        except Exception:
            return self._recover_error(lease)

    def acquire(self, session):
        if getattr(self, "_persistence_fenced", False):
            raise SyntheticError("persistence_unavailable")
        return super().acquire(session)

    def _recover_error(self, lease):
        try:
            with self._store.transaction() as db:
                state, run = self._leased(db, lease)
                self._emit(db, state, "runtime.handler_failed", run, {"error": "tool_failed", "phase": run.get("decision_phase", "model")})
                if run.get("kind") == "decision":
                    a = self._approval_auth(db, run["identity"], run["conversation_id"], run["decision"]["approval_id"])
                    x = self._store.execution(db, a["id"])
                    if x and x["status"] in {"invoking", "outcome_unknown"}:
                        self._unknown(db, state, run, a, x)
                    elif x:
                        self._fail_execution(db, state, run, a, x, "tool_failed")
                    else:
                        run["decision_result"] = self._decision_output(a, error="tool_failed")
                        self._finish(db, state, run, "failed", "tool_failed")
                else:
                    self._finish(db, state, run, "failed", "tool_failed")
                return clone(run)
        except Exception:
            self._persistence_fenced = True
            raise SyntheticError("persistence_unavailable") from None

    def _current_dispatch(self, db, run, a):
        args = ProposeMessage.model_validate(a["prepared"])
        sender, recipients, destination = self._services.prepare_recipients(db, HostIdentity.model_validate(run["identity"]), args)
        if recipients != a["recipient_snapshot"] or digest(args.model_dump()) != a["prepared_digest"] or a["review"] != {**args.model_dump(), "prepared_digest": a["prepared_digest"]}:
            raise SyntheticError("preflight_failed")
        return Dispatch(channel=args.channel, sender_id=sender, recipients=recipients, destination=destination,
                        subject=args.subject, body=args.body).model_dump()

    def _decision_step(self, lease):
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            a = self._approval_auth(db, run["identity"], run["conversation_id"], run["decision"]["approval_id"])
            x = self._store.execution(db, a["id"])
            phase, choice = run["decision_phase"], run["decision"]["decision"]
            if self._faults.cancel_at is not None and state["seconds"] >= self._faults.cancel_at and not run["cancel"]:
                run["cancel"] = True
                self._emit(db, state, "run.cancel_requested", run, {"source": "bound_fault_schedule"})
            if self._watchdog_started is not None and time.perf_counter() - self._watchdog_started >= 60:
                if x and x["status"] == "invoking":
                    self._unknown(db, state, run, a, x)
                else:
                    self._finish(db, state, run, "failed", "environmental_watchdog")
                return clone(run)
            # Authorized saved-run replay has no new grant, charge or dispatch.
            replay = phase == "resolve" and a["status"] == "approved" and choice == "approve"
            if replay:
                if a["decision_run_id"] != run["id"]:
                    self._settle_decision(db, state, run, a, error="resource_unavailable")
                elif x["status"] == "invoking":
                    self._unknown(db, state, run, a, x)
                elif x["status"] != "prepared":
                    self._action_event(db, state, run, "replayed", a, execution_id=x["id"], execution_status=x["status"])
                    self._settle_decision(db, state, run, a, x)
                elif state["seconds"] >= run["deadline"] or run["cancel"]:
                    self._fail_execution(db, state, run, a, x, "tool_timeout" if not run["cancel"] else "tool_failed")
                else:
                    run["decision_phase"] = "preflight"
                    self._save_run(db, run)
                return clone(run)
            if phase == "receipt":
                if self._faults.receipt_loss:
                    self._unknown(db, state, run, a, x)
                else:
                    effect = bounded_json(db.execute("SELECT payload FROM effects WHERE execution_id=?", (x["id"],)).fetchone()[0])
                    x.update(status="succeeded", receipt={"effect_id": effect["effect_id"], "channel": effect["channel"],
                             "recipient_ids": effect["recipient_ids"], "completed_at": effect["committed_at"]})
                    self._store.save_execution(db, x)
                    self._action_event(db, state, run, "completed", a, execution_id=x["id"], receipt=x["receipt"])
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
                    self._settle_decision(db, state, run, a, x if choice == "review" and a["status"] == "approved" else None)
                elif choice == "reject":
                    a["status"] = "rejected"
                    self._store.save_approval(db, a)
                    self._action_event(db, state, run, "rejected", a)
                    self._settle_decision(db, state, run, a)
                else:
                    a.update(status="approved", decision_run_id=run["id"])
                    x = {"id": _id("execution"), "approval_id": a["id"], "decision_run_id": run["id"], "status": "prepared",
                         "prepared_digest": a["prepared_digest"], "dispatch": None, "dispatch_digest": None, "receipt": None, "error": None}
                    self._store.save_approval(db, a)
                    self._store.save_execution(db, x)
                    run["decision_phase"] = "preflight"
                    self._save_run(db, run)
                return clone(run)
            if phase == "preflight":
                try:
                    if self._faults.preflight_failure:
                        raise SyntheticError("preflight_failed")
                    dispatch = self._current_dispatch(db, run, a)
                except (SyntheticError, ValidationError):
                    self._fail_execution(db, state, run, a, x, "preflight_failed")
                    return clone(run)
                x.update(dispatch=dispatch, dispatch_digest=digest(dispatch), status="invoking")
                self._store.save_execution(db, x)
                self._action_event(db, state, run, "authorized_to_dispatch", a, execution_id=x["id"], decision_run_id=run["id"], dispatch_digest=x["dispatch_digest"])
                self._action_event(db, state, run, "invoking", a, execution_id=x["id"])
                run["decision_phase"] = "invoke"
                self._save_run(db, run)
                return clone(run)
            if phase != "invoke":
                raise ValueError("decision_phase")
            end = state["seconds"] + self._faults.decision_duration
            deadline = min(run["deadline"], state["seconds"] + self._budget.tool_seconds)
            cancel = self._faults.cancel_at
            if cancel is not None and state["seconds"] <= cancel <= min(end, deadline):
                state["seconds"], run["cancel"] = cancel, True
            else:
                state["seconds"] = min(end, deadline)
            self._save_state(db, state)
            if run["cancel"] or end >= deadline or self._faults.dispatch_failure:
                self._fail_execution(db, state, run, a, x, "tool_timeout" if end >= deadline and not run["cancel"] else "tool_failed")
                return clone(run)
            # BEGIN IMMEDIATE serializes this current-state check and all effect
            # projections against the supported update_person transaction.
            try:
                dispatch = self._current_dispatch(db, run, a)
                if dispatch != x["dispatch"] or digest(dispatch) != x["dispatch_digest"]:
                    raise SyntheticError("preflight_failed")
            except (SyntheticError, ValidationError):
                self._fail_execution(db, state, run, a, x, "preflight_failed")
                return clone(run)
            self._action_event(db, state, run, "commit_authorized", a, execution_id=x["id"], dispatch_digest=x["dispatch_digest"])
            self._action_event(db, state, run, "dispatched", a, execution_id=x["id"], dispatch_arguments=dispatch,
                               dispatch_digest=x["dispatch_digest"], fake_destination=dispatch["destination"])
            effect = self._store.commit_effect(db, {"effect_id": _id("effect"), "execution_id": x["id"], "channel": dispatch["channel"],
                "sender_id": dispatch["sender_id"], "recipient_ids": [p["person_id"] for p in dispatch["recipients"]],
                "subject": dispatch["subject"], "body": dispatch["body"], "prepared_digest": a["prepared_digest"],
                "dispatch_digest": x["dispatch_digest"], "committed_at": self._timestamp(state["seconds"])}, dispatch["destination"])
            self._action_event(db, state, run, "simulated", a, execution_id=x["id"], effect_id=effect["effect_id"],
                               channel=effect["channel"], fake_destination=dispatch["destination"])
            if self._faults.cancel_after_commit:
                run["cancel"] = True
                self._emit(db, state, "run.cancel_requested", run, {"source": "after_fake_commit"})
            run["decision_phase"] = "receipt"
            self._save_run(db, run)
            return clone(run)
