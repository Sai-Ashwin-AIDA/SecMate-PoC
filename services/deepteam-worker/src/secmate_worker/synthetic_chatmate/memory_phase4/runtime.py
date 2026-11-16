"""Facts-only Phase 4 runtime, host controls, and fresh request adapter."""
from pathlib import Path
import tempfile
import time

from pydantic import ValidationError
from ...job_runtime import canonical, require_permission
from ..contracts import TARGET_ID, SyntheticError, clone, digest, MessageCreate, Script, ToolCall
from ..runtime import Assessment as Phase1Assessment, _id, TERMINAL
from ..calendar_repaired.runtime import CalendarAssessment as BaseAssessment
from ..calendar_phase3.services import CalendarServices
from ..calendar_phase3.time_rules import TimeRules
from ..communication.services import FakeServices
from ..communication_repaired.contracts import CommunicationBudget
from ..calendar_repaired.runtime import validate_frozen_calendar
from ..calendar_repaired.artifacts import parts as predecessor_parts
from ..communication_repaired.artifacts import validate_predecessor
from ..calendar_repaired.contracts import bounded_json
from .artifacts import MemoryBundle
from .contracts import VERSION, MAX_REVISION, MemorySeed, Phase4FaultPlan, fixture_control_input, strict_control_json, validate_event
from .context import render_request, binding
from .services import active_facts, evaluate, fact_ref, owner_meta
from .store import MemoryStore

_PORTABLE_ROOTS = {}


def _portable_root(root):
    requested = Path(root).resolve()
    projected = requested / "targets" / TARGET_ID / VERSION / "assessments" / ("assessment-" + "0" * 32) / "assessment.sqlite3"
    if len(str(projected)) < 240:
        return requested
    key = str(requested)
    if key not in _PORTABLE_ROOTS:
        parent = Path(tempfile.gettempdir()) / "opencode"; parent.mkdir(exist_ok=True)
        _PORTABLE_ROOTS[key] = Path(tempfile.mkdtemp(prefix="m4t-", dir=parent)).resolve()
    return _PORTABLE_ROOTS[key]


def validate_repaired(path):
    try:
        if path.is_symlink() or any(p.is_symlink() for p in path.rglob("*")): raise ValueError("link")
        reg = bounded_json((path / "registration.json").read_text(encoding="utf-8"), maximum=4_000_000)
        files = {p.stem: bounded_json(p.read_text(encoding="utf-8"), maximum=4_000_000) for p in (path / "definitions").glob("*.json")}
        expected = predecessor_parts()
        if set(files) != set(expected) or len(files) != 24 or reg["target_version"] != "0.3.1": raise ValueError("set")
        if {k: digest(v) for k, v in files.items()} != reg["definition_digests"]: raise ValueError("digest")
        if files != expected: raise ValueError("definition")
    except (OSError, ValueError, KeyError, TypeError):
        raise SyntheticError("unowned_target_namespace") from None


class MemoryTarget:
    def __init__(self, root, bundle=None):
        require_permission()
        supplied = bundle or MemoryBundle.load()
        self.bundle = MemoryBundle.from_parts({k: bounded_json(v, maximum=4_000_000) for k, v in supplied.artifacts})
        target = _portable_root(root) / "targets" / TARGET_ID
        if target.exists():
            if (target / VERSION).exists(): raise SyntheticError("target_version_collision")
            if target.is_symlink() or not target.is_dir() or not list(target.iterdir()): raise SyntheticError("unowned_target_namespace")
            for previous in target.iterdir():
                if previous.name == "0.3.0": validate_frozen_calendar(previous)
                elif previous.name == "0.3.1": validate_repaired(previous)
                elif previous.name in {"0.1.1", "0.2.0", "0.2.1"}: validate_predecessor(previous)
                else: raise SyntheticError("unowned_target_namespace")
        else:
            target.mkdir(parents=True, exist_ok=True)
        self.path = target / VERSION
        try: self.path.mkdir(exist_ok=False)
        except FileExistsError: raise SyntheticError("target_version_collision") from None
        self.assessments = self.path / "assessments"; self.assessments.mkdir()
        definitions = self.path / "definitions"; definitions.mkdir()
        for key, value in self.bundle.artifacts:
            with (definitions / (key + ".json")).open("x", encoding="utf-8") as stream: stream.write(value)
        registration = {"target_id": TARGET_ID, "target_version": VERSION, "manifesto_version": "0.1.2", "phase_scope": [0, 1, 2, 3, 4],
            "api_registration": False, "deepteam_provider": False,
            "definition_digests": {k: digest(bounded_json(v, maximum=4_000_000)) for k, v in self.bundle.artifacts}}
        with (self.path / "registration.json").open("x", encoding="utf-8") as stream: stream.write(canonical(registration))

    def fresh(self, *, subject="subject-ada", faults=None, generation=1, context_profile="private"):
        return MemoryAssessment(self, subject, faults or Phase4FaultPlan(), generation, context_profile)


class MemoryAssessment(BaseAssessment):
    def __init__(self, target, subject, faults, generation, context_profile):
        require_permission()
        self._target, self._bundle = target, target.bundle
        users = {u["subject"]: u for u in self._bundle.get("seed")["users"]}
        if subject not in users: raise SyntheticError("invalid_host_identity")
        self.id, self.generation, self._watchdog_started, self._fault_hits = _id("assessment"), generation, None, {}
        self._operation_deadline = None
        self.path = target.assessments / self.id; self.path.mkdir(exist_ok=False)
        self._faults = Phase4FaultPlan.model_validate(faults.model_dump() if hasattr(faults, "model_dump") else faults)
        self._binding = self._bundle.bindings(self._faults.model_dump(), self.id, generation)
        self._binding_digest, self._rules = digest(self._binding), TimeRules(self._bundle.get("time_rules"))
        memory_seed = MemorySeed.model_validate(self._bundle.get("memory_seed")).model_dump()
        self._store = MemoryStore(self.path / "assessment.sqlite3", {"assessment_id": self.id, "generation": generation, "owner": subject,
            "seconds": 0.0, "archived": False, "accepted": False, "sessions": {}}, self._bundle.get("seed"), self._bundle.get("calendar_seed"),
            self._bundle.get("calendar_records"), memory_seed)
        for name, value in (("bindings", self._binding), ("faults", self._faults.model_dump())):
            with (self.path / (name + ".json")).open("x", encoding="utf-8") as stream: stream.write(canonical(value))
        self._services = FakeServices(self.id, generation, self._binding["artifact_digests"]["seed"], self._binding_digest)
        self._calendar = CalendarServices(self._binding, self._bundle.get("calendar_seed"), self._rules)
        profiles = {p["id"]: p for p in self._bundle.get("memory_contexts")["profiles"]}
        if context_profile not in profiles or context_profile == "multiparticipant" and subject == "subject-cyra": raise SyntheticError("invalid_fixture")
        self._context_profile, self._memory_payload = profiles[context_profile], None
        self._persistence_fenced = False
        self.session = self.host_session(subject)
        with self._store.transaction() as db:
            state = self._state(db)
            self._emit(db, state, "assessment.created", None, {"binding_digest": self._binding_digest})
            self._emit(db, state, "assessment.bindings_loaded", None, {"bindings": self._binding})
            self._emit(db, state, "time.rules_loaded", None, {"time_rules_digest": self._rules.digest, "package_version": "2026.6", "iana_version": "2026f", "resource_digests": self._binding["timezone_resources"]})
            self._emit(db, state, "memory.seed_bound", None, {"seed_digest": digest(memory_seed), "owner_ids": [o["owner"] for o in memory_seed["owners"]], "fact_count": len(memory_seed["facts"])})

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        last = db.execute("SELECT max(id) FROM events").fetchone()[0] or 0
        event = {"event_schema_version": VERSION, "target_id": TARGET_ID, "target_version": VERSION, "assessment_id": self.id,
            "state_generation": self.generation, "run_id": run["id"] if run else None, "event_id": last + 1,
            "logical_time": self._timestamp(state["seconds"]), "type": kind, "actor_ref": state["owner"], "call_id": call_id or (data or {}).get("call_id"),
            "action_id": (data or {}).get("approval_id"), "caused_by": last or None, "data": clone(data or {}),
            "binding_digest": digest(run["bindings"]) if run else self._binding_digest, "production_claim": False}
        validate_event(event)
        db.execute("INSERT INTO events (payload) VALUES (?)", (canonical(event),))
        return event["event_id"]

    @property
    def _budget(self):
        value = clone(self._bundle.get("budget"))
        for key in ("memory_checks", "memory_load_seconds", "memory_controls", "memory_control_seconds", "memory_control_output_characters"):
            value.pop(key)
        return CommunicationBudget.model_validate(value)

    def submit(self, session, body, *, snapshot_id="snapshot-ada"):
        error, accepted = None, None
        with self._store.transaction() as db:
            state, identity = self._auth(db, session)
            if isinstance(body, dict) and "resume_conversation_id" in body: raise SyntheticError("continuation_not_supported")
            try: message = MessageCreate.model_validate(body)
            except ValidationError as exc: raise SyntheticError("invalid_arguments") from exc
            if state["accepted"]: raise SyntheticError("continuation_not_supported")
            snapshot = next((s for s in self._bundle.get("seed")["snapshots"] if s["id"] == snapshot_id), None)
            allowed = snapshot is not None and not snapshot["deleted"] and snapshot["owner"] == identity["subject"]
            self._emit(db, state, "snapshot.authorized" if allowed else "snapshot.authorization_rejected", None,
                {"resource_id": snapshot_id, "requested_by": identity["subject"], "resource_owner": snapshot["owner"] if snapshot else None})
            if not allowed: raise SyntheticError("resource_unavailable")
            prompt = {"id": _id("message"), "conversation_id": _id("conversation"), "role": "user", "content": message.content,
                "created_at": self._timestamp(state["seconds"])}
            run = {"id": _id("run"), "conversation_id": prompt["conversation_id"], "prompt_message_id": prompt["id"], "status": "queued",
                "result_message_id": None, "identity": identity, "owner": state["owner"], "prompt": prompt, "snapshot_id": snapshot_id,
                "snapshot_owner": snapshot["owner"], "snapshot": snapshot["messages"] + [{"message_id": prompt["id"], "role": "user", "content": message.content}],
                "round": 0, "remaining": self._bundle.get("budget")["execution"], "transcript": [], "seen_calls": [], "oversized": 0,
                "streak": {}, "lease": None, "cancel": False, "outcome": None, "partial": False, "answer": None, "terminal_reason": None,
                "memory_checkpoint": False}
            run["bindings"] = {**self._binding, "run_id": run["id"]}
            profile, owner = self._context_profile, state["owner"]
            peer = "subject-bram" if owner == "subject-ada" else "subject-ada"
            context = {"assessment_id": self.id, "state_generation": self.generation, "conversation_id": run["conversation_id"], "owner": owner,
                "tenant": run["identity"]["tenant"], "revision": 1, "shared": profile["shared"],
                "participant_ids": [owner, peer] if profile["participant_mode"] == "owner_plus_peer" else [owner], "project_id": profile["project_id"],
                "deleted": profile["deleted"], "memory_disabled": profile["memory_disabled"]}
            db.execute("INSERT INTO memory_contexts VALUES (?,?,?,?,?,?,?,?)", (run["conversation_id"], self.id, self.generation,
                owner, context["tenant"], context["revision"], context["memory_disabled"], canonical(context)))
            run["memory_disabled"] = profile["memory_disabled"]
            self._save_run(db, run); state["accepted"] = True; self._save_state(db, state)
            self._emit(db, state, "message.accepted", run, {"message_id": prompt["id"]})
            self._emit(db, state, "run.created", run)
            self._emit(db, state, "memory.context_created", run, {"context": context, "profile_id": profile["id"], "context_digest": digest(context)})
            accepted = {"message": prompt, "run": {key: run[key] for key in ("id", "conversation_id", "prompt_message_id", "status", "result_message_id")}}
        with self._store.transaction() as db:
            state, _ = self._auth(db, session); run = self._run(db, accepted["run"]["id"])
            if self._faults.enqueue_failure:
                self._finish(db, state, run, "failed", "dispatch_unavailable"); error = SyntheticError("dispatch_unavailable", run["id"])
            else:
                self._store.enqueue(db, run["id"]); self._emit(db, state, "run.enqueued", run, {"accepted_message_id": run["prompt_message_id"]})
        if error: raise error
        return accepted

    def _request(self, run, state):
        base = Phase1Assessment._request(self, run, state)
        base["tools"] += [{"type": "function", "name": name, "parameters": self._bundle.get("schemas")["tools"][name]["input"]}
            for name in self._bundle.get("capabilities")["enabled"] if name != "secmate.conversation.history.read"]
        return render_request(base, self._bundle.get("prompt")["developer_guidance"], self._memory_payload)

    def _prepare_memory(self, db, state, run, round_number, attempt, step_deadline):
            row = db.execute("SELECT payload FROM memory_contexts WHERE conversation_id=?", (run["conversation_id"],)).fetchone()
            context = bounded_json(row[0])
            eligibility = {"context": context, "memory_owner": context["owner"], "requested_by": run["owner"],
                "run_memory_disabled": run.get("memory_disabled", False), "subsystem_enabled": self._context_profile["subsystem_enabled"]}
            basic = evaluate(eligibility)
            header = clean_header = fault = None
            if basic[0] == "ineligible":
                status, reason, candidate = basic
            elif db.execute("SELECT count(*) FROM memory_snapshots").fetchone()[0] >= 8:
                status, reason, candidate = "unavailable", "memory_budget_exhausted", None
            else:
                fault = next((f for f in self._faults.memory.loads if (f.round, f.attempt) == (round_number, attempt)), None)
                deadline = min(step_deadline, run["deadline"], state["seconds"] + self._bundle.get("budget")["memory_load_seconds"])
                before = state["seconds"]
                outcome = self._advance(db, state, run, fault.duration if fault else 0.0, deadline)
                if outcome == "cancelled": raise SyntheticError("memory_cancelled")
                if outcome == "timeout": status, reason, candidate = "unavailable", "memory_timeout", None
                elif fault and fault.mode != "none":
                    if fault.mode == "cancel_before_read": raise SyntheticError("memory_cancelled")
                    status, reason, candidate = "unavailable", "memory_unavailable" if fault.mode == "unavailable" else "memory_failed", None
                else: status = reason = candidate = None
                if fault:
                    hit = {"kind": "load", "phase": "load", "round": round_number, "attempt": attempt, "ordinal": None, "control_id": None,
                        "status": "failed" if reason else "completed", "before_seconds": before, "after_seconds": state["seconds"],
                        "deadline_seconds": deadline, "error": reason}
                    db.execute("INSERT INTO memory_fault_hits(payload) VALUES (?)", (canonical(hit),))
            if status is None:
                header = self._store.header(db, state["owner"])
                clean_header = {k: header[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}
                status, reason, candidate = evaluate(eligibility, clean_header, self._store.facts(db, state["owner"]), state["seconds"])
            elif header is None and status != "ineligible":
                header = self._store.header(db, state["owner"])
                clean_header = {k: header[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}
            self._memory_payload = candidate
            snapshot_id = _id("memory-snapshot")
            previous = db.execute("SELECT payload FROM memory_snapshots WHERE run_id=? ORDER BY rowid DESC LIMIT 1", (run["id"],)).fetchone()
            previous_id = bounded_json(previous[0])["snapshot"]["snapshot_id"] if previous else None
            snapshot = {"snapshot_id": snapshot_id, "previous_snapshot_id": previous_id, "round": round_number, "attempt": attempt,
                "read_seconds": state["seconds"], "read_at": self._timestamp(state["seconds"]), "eligibility": eligibility, "status": status, "reason": reason,
                "owner_revision": clean_header["revision"] if status in {"loaded", "empty", "disabled"} else None,
                "owner_enabled": clean_header["enabled"] if status in {"loaded", "empty", "disabled"} else None,
                "owner_state_digest": header["state_digest"] if status in {"loaded", "empty", "disabled"} else None,
                "selected_refs": [item["source_ref"] for item in candidate["facts"]] if candidate else [], "expected_payload_digest": digest(candidate)}
            db.execute("INSERT INTO memory_snapshots VALUES (?,?,?,?,?)", (snapshot_id, run["id"], round_number, attempt, canonical({"run_id": run["id"], "snapshot": snapshot, "candidate": candidate})))
            self._emit(db, state, "memory.context_loaded" if previous is None else "memory.context_refreshed", run, snapshot)
            request = self._request(run, state)
            if fault and fault.mode == "cancel_before_publication":
                run["cancel"] = True
                raise SyntheticError("memory_cancelled")
            if len(canonical(request)) > self._budget.context_characters: raise SyntheticError("context_limit_exceeded")
            request_event_id = self._emit(db, state, "model.request_built", run, {"round": round_number, "attempt": attempt, "request": request})
            present, value_digest = binding(request, self._bundle.get("prompt")["developer_guidance"])
            self._emit(db, state, "memory.request_bound", run, {"snapshot_id": snapshot_id, "round": round_number, "attempt": attempt,
                "request_event_id": request_event_id, "request_seconds": snapshot["read_seconds"], "actual_present": present, "actual_payload_digest": value_digest})
            return request

    def step(self, lease):
        with self._store.read() as db:
            _, selected_run = self._leased(db, lease)
        if selected_run.get("kind") == "decision": return super().step(lease)
        with self._store.transaction() as db:
            state, run = self._leased(db, lease); run["memory_checkpoint"] = False
            if not self._checkpoint(db, state, run): return clone(run)
            budget = self._budget
            if state["seconds"] >= run["deadline"] or run["round"] >= budget.rounds:
                self._finish(db, state, run, "completed", "time" if state["seconds"] >= run["deadline"] else "rounds", outcome="Partial", answer=""); return clone(run)
            round_number = run["round"] + 1; script = Script.model_validate(self._bundle.get("script"))
            if round_number > len(script.rounds): self._finish(db, state, run, "failed", "model_protocol_error"); return clone(run)
            scripted = script.rounds[round_number - 1]; step_deadline = min(run["deadline"], state["seconds"] + budget.model_seconds)
            run["round"] = round_number; self._emit(db, state, "budget.charged", run, {"pool": "rounds", "round": round_number})
            for attempt in (1, 2):
                try: self._prepare_memory(db, state, run, round_number, attempt, step_deadline)
                except SyntheticError as exc:
                    self._finish(db, state, run, "failed", exc.code); return clone(run)
                fault = next((f for f in self._faults.model if f.round == round_number and f.attempt == attempt), None)
                outcome = self._advance(db, state, run, fault.duration if fault else 0.0, step_deadline)
                if outcome == "cancelled": return clone(run)
                error = "model_timeout" if outcome == "timeout" else (fault.error if fault else scripted.error)
                if error:
                    self._emit(db, state, "model.error", run, {"code": error, "attempt": attempt, "after_output": fault.after_output if fault else False})
                    if attempt == 1 and error in {"model_timeout", "model_transport_unavailable"} and not (fault and fault.after_output):
                        if self._advance(db, state, run, budget.retry_delay, step_deadline) is None:
                            self._emit(db, state, "model.retry", run, {"attempt": 2}); continue
                    self._finish(db, state, run, "failed", error); return clone(run)
                break
            try:
                calls = [ToolCall.model_validate(c) for c in scripted.calls]; call_ids = [c.call_id for c in calls]
                if not scripted.completion or len(set(call_ids)) != len(call_ids) or set(call_ids) & set(run["seen_calls"]): raise ValueError("protocol")
            except (ValidationError, ValueError):
                self._emit(db, state, "model.incomplete_step", run, {"round": round_number, "text": scripted.text, "calls": scripted.calls, "completion": scripted.completion})
                self._finish(db, state, run, "failed", "model_protocol_error"); return clone(run)
            self._emit(db, state, "model.response_received", run, {"round": round_number, "text": scripted.text, "calls": [c.model_dump() for c in calls], "completion": True})
            run["seen_calls"].extend(call_ids)
            if scripted.text: run["transcript"].append({"role": "assistant", "content": scripted.text})
            run["transcript"].extend([{"type": "function_call", **c.model_dump()} for c in calls])
            if not calls:
                self._finish(db, state, run, "completed" if scripted.text else "failed", "final" if scripted.text else "model_empty_response",
                    answer=scripted.text or None, outcome="Final" if scripted.text else None); return clone(run)
            if len(calls) > budget.calls_per_round:
                for call in calls: self._result(db, state, run, call.call_id, {"error": "call_batch_limit"}, error=True, tool_name=call.name)
            else: self._dispatch(db, state, run, calls)
            if run["status"] in TERMINAL: return clone(run)
            run["memory_checkpoint"] = True; self._save_run(db, run)
            self._emit(db, state, "memory.checkpoint", run, {"conversation_id": run["conversation_id"], "after_round": round_number})
            return clone(run)

    def memory_control(self, session, body):
        try: body = strict_control_json(body)
        except ValueError: return self._error(None, "invalid_arguments")
        return self._execute_memory_control(session, body)

    def _accept_memory_control(self, session, body):
        # Acceptance is intentionally committed before any apply work. The durable
        # fence is the process-boundary source of truth, not an in-memory flag.
        with self._store.transaction() as db:
            try: state, _ = self._auth(db, session)
            except SyntheticError as exc: return self._error(None, exc.code)
            fence = db.execute("SELECT persistence_fenced FROM memory_control_fence WHERE singleton=1").fetchone()
            if fence: return self._error(None, "persistence_unavailable" if fence[0] else "memory_control_busy")
            owner, seconds = state["owner"], state["seconds"]
            ordinal = db.execute("SELECT count(*) FROM memory_controls").fetchone()[0] + 1
            if ordinal > 32: return self._error(None, "memory_budget_exhausted")
            control_id, input_digest = _id("memory-control"), digest(body)
            header = self._store.header(db, owner)
            db.execute("INSERT INTO memory_controls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (control_id, ordinal, self.id, self.generation,
                owner, header["tenant"], canonical(body), input_digest, "accepted", None, None, seconds, seconds + 60))
            db.execute("INSERT INTO memory_control_fence VALUES (1,?,?,0)", (control_id, owner))
            self._emit(db, state, "memory.control.accepted", None, {"control_id": control_id, "ordinal": ordinal, "owner": owner, "body": body, "input_digest": input_digest, "deadline_seconds": seconds + 60})
        return {"control_id": control_id, "ordinal": ordinal, "input_digest": input_digest}

    def _execute_memory_control(self, session, body, accepted=None):
        accepted = accepted or self._accept_memory_control(session, body)
        if "error" in accepted: return accepted
        control_id, ordinal, input_digest = accepted["control_id"], accepted["ordinal"], accepted["input_digest"]
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            owner, seconds = state["owner"], state["seconds"]
            record = db.execute("SELECT status,deadline_seconds FROM memory_controls WHERE id=? AND owner=?", (control_id, owner)).fetchone()
            if not record: return self._error(None, "resource_unavailable")
            if record[0] == "cancel_requested" or state["seconds"] >= record[1]:
                return self._fail_control(db, state, control_id, "memory_cancelled" if record[0] == "cancel_requested" else "memory_timeout")
            if db.execute("UPDATE memory_controls SET status='applying' WHERE id=? AND status='accepted'", (control_id,)).rowcount != 1:
                return self._error(control_id, "memory_control_busy")
            before_fault = next((f for f in self._faults.memory.controls if (f.ordinal, f.phase) == (ordinal, "before_commit")), None)
            if before_fault:
                deadline = seconds + 60; state["seconds"] = min(deadline, state["seconds"] + before_fault.duration); self._save_state(db, state)
                error = "memory_cancelled" if before_fault.mode in {"cancel", "cancel_before_apply"} else "memory_failed" if before_fault.mode in {"raise", "journal_insert_failure", "witness_insert_failure"} else None
                db.execute("INSERT INTO memory_fault_hits(payload) VALUES (?)", (canonical({"kind": "control", "phase": "before_commit", "round": None,
                    "attempt": None, "ordinal": ordinal, "control_id": control_id, "status": "failed" if error else "completed",
                    "before_seconds": seconds, "after_seconds": state["seconds"], "deadline_seconds": deadline, "error": error}),))
                if error is None and state["seconds"] >= deadline: error = "memory_timeout"
                if error:
                    if self._faults.memory.failure_recording_unavailable:
                        db.execute("UPDATE memory_control_fence SET persistence_fenced=1 WHERE control_id=?", (control_id,))
                        return self._error(control_id, "persistence_unavailable")
                    return self._fail_control(db, state, control_id, error)
            header = self._store.header(db, owner); facts = self._store.facts(db, owner)
            clean = {k: header[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}
            operation = body["operation"]
            if operation == "inspect":
                active = active_facts(facts, seconds)
                context_row = db.execute("SELECT payload FROM memory_contexts LIMIT 1").fetchone()
                response = {"control_id": control_id, "operation": "inspect", "status": "inspected", "owner_state": clean, "active_facts": active,
                    "stored_count": len(facts), "expired_count": len(facts) - len(active), "context": bounded_json(context_row[0]) if context_row else None,
                    "read_seconds": seconds, "read_at": self._timestamp(seconds)}
                if len(canonical(response)) > self._bundle.get("budget")["memory_control_output_characters"]:
                    return self._fail_control(db, state, control_id, "memory_output_limit_exceeded")
                self._settle(db, control_id, "inspected", response)
                self._emit(db, state, "memory.control.inspected", None, {"control_id": control_id, "owner_meta": owner_meta(clean, facts),
                    "active_refs": [fact_ref(f) for f in active], "expired_count": len(facts) - len(active), "read_seconds": seconds, "read_at": self._timestamp(seconds)})
                return self._host_output(db, state, control_id, False, response)
            if operation != "fixture_context_change" and body["expected_revision"] != header["revision"]: return self._fail_control(db, state, control_id, "memory_revision_conflict", header["revision"])
            if header["revision"] == MAX_REVISION and operation in {"forget", "clear", "fixture_set_enabled"}: return self._fail_control(db, state, control_id, "memory_revision_exhausted", header["revision"])
            before, removed, context_before, context_after, affected = {**clean, "facts": facts}, [], None, None, []
            if operation == "forget":
                fact = next((f for f in facts if f["id"] == body["fact_id"]), None)
                if fact is None: return self._fail_control(db, state, control_id, "resource_unavailable", header["revision"])
                db.execute("DELETE FROM memory_facts WHERE id=? AND owner=?", (fact["id"], owner)); removed = [fact]
                db.execute("UPDATE memory_owners SET revision=revision+1 WHERE owner=? AND revision=?", (owner, header["revision"]))
            elif operation == "clear":
                removed = facts; db.execute("DELETE FROM memory_facts WHERE owner=?", (owner,))
                db.execute("UPDATE memory_owners SET revision=revision+1,enabled=0 WHERE owner=? AND revision=?", (owner, header["revision"]))
            elif operation == "fixture_set_enabled":
                if header["enabled"] == body["enabled"]: return self._fail_control(db, state, control_id, "invalid_arguments", header["revision"])
                db.execute("UPDATE memory_owners SET revision=revision+1,enabled=? WHERE owner=? AND revision=?", (body["enabled"], owner, header["revision"]))
            else:
                row = db.execute("SELECT payload FROM memory_contexts WHERE conversation_id=?", (body["conversation_id"],)).fetchone()
                if not row: return self._fail_control(db, state, control_id, "resource_unavailable", header["revision"])
                context_before = bounded_json(row[0])
                if body["expected_context_revision"] != context_before["revision"]: return self._fail_control(db, state, control_id, "memory_revision_conflict", header["revision"], context_before["revision"])
                context_after = clone(context_before)
                if operation == "fixture_context_change":
                    mutable = body["context"]
                    known = {u["subject"] for u in self._bundle.get("seed")["users"]}
                    if any(p not in known for p in mutable["participant_ids"]): return self._fail_control(db, state, control_id, "resource_unavailable", header["revision"], context_before["revision"])
                    if all(context_before[k] == mutable[k] for k in mutable): return self._fail_control(db, state, control_id, "invalid_arguments", header["revision"], context_before["revision"])
                    context_after.update(mutable, revision=context_after["revision"] + 1)
                    db.execute("UPDATE memory_contexts SET revision=?,payload=? WHERE conversation_id=?", (context_after["revision"], canonical(context_after), body["conversation_id"]))
                    status = "applied"
                else:
                    status = "already_disabled" if context_after["memory_disabled"] else "applied"
                if operation == "disable_conversation" and not context_after["memory_disabled"]:
                    context_after.update(memory_disabled=True, revision=context_after["revision"] + 1)
                    db.execute("UPDATE memory_contexts SET revision=?,memory_disabled=1,payload=? WHERE conversation_id=?",
                        (context_after["revision"], canonical(context_after), body["conversation_id"]))
                    for (raw,) in db.execute("SELECT payload FROM runs"):
                        run = bounded_json(raw)
                        if run["conversation_id"] == body["conversation_id"]:
                            run["memory_disabled"] = True; self._save_run(db, run); affected.append(run["id"])
                after = before
            if operation in {"forget", "clear", "fixture_set_enabled"}:
                self._store.rehash(db, owner); current = self._store.header(db, owner)
                after_header = {k: current[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}; after = {**after_header, "facts": self._store.facts(db, owner)}; status = "applied"
            elif operation == "fixture_context_change":
                after = before
            current = self._store.header(db, owner); current_header = {k: current[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}
            journal = {"control_id": control_id, "input_digest": input_digest, "before_owner": before, "after_owner": after,
                "before_context": context_before, "after_context": context_after, "removed_facts": removed, "affected_run_ids": affected, "commit_seconds": seconds}
            db.execute("INSERT INTO memory_mutations VALUES (?,?)", (control_id, canonical(journal)))
            response = {"control_id": control_id, "operation": operation, "status": status, "owner": owner, "before_revision": header["revision"],
                "revision": current_header["revision"], "enabled": current_header["enabled"], "conversation_id": body.get("conversation_id"),
                "before_context_revision": context_before["revision"] if context_before else None, "context_revision": context_after["revision"] if context_after else None,
                "removed_fact_refs": [fact_ref(f) for f in removed], "state_digest": current["state_digest"],
                "context_digest": digest(context_after) if context_after else None, "commit_seconds": seconds, "committed_at": self._timestamp(seconds)}
            self._settle(db, control_id, status, response)
            self._emit(db, state, "memory.control.committed", None, {"control_id": control_id, "operation": operation, "input_digest": input_digest,
                "owner_before": owner_meta({k: before[k] for k in clean}, before["facts"]), "owner_after": owner_meta(current_header, after["facts"]),
                "context_before": context_before, "context_after": context_after, "affected_run_ids": affected, "removed_fact_refs": response["removed_fact_refs"],
                "commit_seconds": seconds, "committed_at": self._timestamp(seconds)})
            uncertain = False
            for post in (f for phase in ("after_commit", "return") for f in self._faults.memory.controls if f.ordinal == ordinal and f.phase == phase):
                before_post = state["seconds"]
                state["seconds"] += post.duration; self._save_state(db, state)
                failed = post.mode in {"raise", "response_loss"}
                db.execute("INSERT INTO memory_fault_hits(payload) VALUES (?)", (canonical({"kind": "control", "phase": post.phase, "round": None,
                    "attempt": None, "ordinal": ordinal, "control_id": control_id, "status": "failed" if failed else "completed", "before_seconds": before_post,
                    "after_seconds": state["seconds"], "deadline_seconds": seconds + 60, "error": "memory_outcome_unknown" if failed else None}),))
                # Disconnect is transport loss only; cancellation after commit
                # cannot roll back the already durable mutation.
                uncertain = uncertain or failed
            if uncertain:
                unknown = {"control_id": control_id, "status": "outcome_unknown", "error": "memory_outcome_unknown", "field": None,
                    "current_revision": None, "current_context_revision": None}
                return self._host_output(db, state, control_id, False, unknown)
            return self._host_output(db, state, control_id, False, response)

    @staticmethod
    def _error(control_id, code, revision=None, context_revision=None):
        return {"control_id": control_id, "status": "error", "error": code, "field": None, "current_revision": revision, "current_context_revision": context_revision}

    def _fail_control(self, db, state, control_id, code, revision=None, context_revision=None):
        response = self._error(control_id, code, revision, context_revision); self._settle(db, control_id, "failed", response)
        return self._host_output(db, state, control_id, False, response)

    def _settle(self, db, control_id, status, response):
        raw = canonical(response)
        db.execute("UPDATE memory_controls SET status=?,result=?,result_digest=? WHERE id=?", (status, raw, digest(response), control_id))
        db.execute("DELETE FROM memory_control_fence WHERE control_id=? AND persistence_fenced=0", (control_id,))

    def _host_output(self, db, state, control_id, replay, response):
        output = {"target_id": TARGET_ID, "target_version": VERSION, "assessment_id": self.id, "state_generation": self.generation,
            "owner": state["owner"], "control_id": control_id, "is_replay": replay, "returned_at": self._timestamp(state["seconds"]),
            "response": response, "response_digest": digest(response)}
        if len(canonical(output)) > self._bundle.get("budget")["memory_control_output_characters"]:
            response = self._error(control_id, "memory_output_limit_exceeded")
            output.update(response=response, response_digest=digest(response))
        db.execute("INSERT INTO memory_host_outputs(control_id,payload) VALUES (?,?)", (control_id, canonical(output)))
        row = db.execute("SELECT body FROM memory_controls WHERE id=?", (control_id,)).fetchone()
        operation = bounded_json(row[0])["operation"] if row else response.get("operation", "inspect")
        boundary_status = response["status"]
        if boundary_status == "error": boundary_status = "cancelled" if response.get("error") == "memory_cancelled" else "failed"
        self._emit(db, state, "memory.control.replayed" if replay else "memory.control.finished", None,
            {"control_id": control_id, "operation": operation, "status": "replayed" if replay else boundary_status,
             "error": response.get("error"), "response_digest": digest(response)})
        return output

    def replay_memory_control(self, session, body):
        control_id = body.get("control_id") if isinstance(body, dict) and set(body) == {"control_id"} else None
        with self._store.transaction() as db:
            try: state, _ = self._auth(db, session)
            except SyntheticError as exc: return self._error(None, exc.code)
            row = db.execute("SELECT owner,result FROM memory_controls WHERE id=?", (control_id,)).fetchone()
            if not row or row[0] != state["owner"] or row[1] is None: return self._error(None, "resource_unavailable")
            return self._host_output(db, state, control_id, True, bounded_json(row[1]))

    def memory_boundary(self, session, body):
        required = {"requested_owner", "eligibility"}
        if not isinstance(body, dict) or set(body) != required or not isinstance(body["requested_owner"], str) or not isinstance(body["eligibility"], dict):
            return self._error(None, "invalid_arguments")
        with self._store.read() as db:
            try: state, _ = self._auth(db, session)
            except SyntheticError as exc: return self._error(None, exc.code)
            # A selector is never authority. Reject unknown and foreign owners
            # identically before reading either owner's header or facts.
            if body["requested_owner"] != state["owner"]: return self._error(None, "resource_unavailable")
            supplied = body["eligibility"]
            context = supplied.get("context")
            if not isinstance(context, dict): return self._error(None, "invalid_arguments")
            row = db.execute("SELECT payload FROM memory_contexts WHERE conversation_id=?", (context.get("conversation_id"),)).fetchone()
            if not row: return self._error(None, "resource_unavailable")
            actual_context = bounded_json(row[0])
            run_row = db.execute("SELECT payload FROM runs WHERE json_extract(payload,'$.conversation_id')=?", (actual_context["conversation_id"],)).fetchone()
            if not run_row: return self._error(None, "resource_unavailable")
            run = bounded_json(run_row[0])
            actual = {"context": actual_context, "memory_owner": state["owner"], "requested_by": run["owner"],
                "run_memory_disabled": run.get("memory_disabled", False), "subsystem_enabled": self._context_profile["subsystem_enabled"]}
            if supplied != actual: return self._error(None, "resource_unavailable")
            header = self._store.header(db, state["owner"])
            clean = {k: header[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}
            status, reason, value = evaluate(actual, clean, self._store.facts(db, state["owner"]), state["seconds"])
            return {"status": status, "reason": reason, "read_seconds": state["seconds"], "payload": value}

    def cancel_memory_control(self, session, body):
        control_id = body.get("control_id") if isinstance(body, dict) and set(body) == {"control_id"} else None
        with self._store.transaction() as db:
            try: state, _ = self._auth(db, session)
            except SyntheticError as exc: return self._error(None, exc.code)
            row = db.execute("SELECT owner,status,result FROM memory_controls WHERE id=?", (control_id,)).fetchone()
            if not row or row[0] != state["owner"]: return self._error(None, "resource_unavailable")
            if row[2] is not None: return self._host_output(db, state, control_id, True, bounded_json(row[2]))
            if row[1] == "accepted":
                db.execute("UPDATE memory_controls SET status='cancel_requested' WHERE id=?", (control_id,))
                self._emit(db, state, "memory.control.cancel_requested", None, {"control_id": control_id})
            response = self._error(control_id, "memory_cancelled")
            self._settle(db, control_id, "cancelled", response)
            return self._host_output(db, state, control_id, False, response)

    def advance_at_memory_checkpoint(self, session, lease, body):
        if not isinstance(body, dict) or set(body) != {"seconds"} or type(body["seconds"]) not in {int, float} or not 0 <= body["seconds"] <= 60:
            raise SyntheticError("invalid_arguments")
        with self._store.transaction() as db:
            state, _ = self._auth(db, session); leased_state, run = self._leased(db, lease)
            if state != leased_state or not run.get("memory_checkpoint"): raise SyntheticError("memory_control_busy")
            before = state["seconds"]; state["seconds"] += body["seconds"]; self._save_state(db, state)
            data = {"after_round": run["round"], "before_seconds": before, "after_seconds": state["seconds"]}
            self._emit(db, state, "memory.checkpoint_clock_advanced", run, data); return data

    def fixture_set_enabled(self, session, body):
        if self._bundle.get("baseline")["fixture_id"] != "memory-conformance-0.4.0": return self._error(None, "capability_disabled")
        try: body = fixture_control_input(body)
        except ValueError: return self._error(None, "invalid_arguments")
        return self._execute_memory_control(session, body)

    def fixture_context_change(self, session, body):
        if self._bundle.get("baseline")["fixture_id"] != "memory-conformance-0.4.0": return self._error(None, "capability_disabled")
        try: body = fixture_control_input(body)
        except ValueError: return self._error(None, "invalid_arguments")
        return self._execute_memory_control(session, body)

    def reset(self, session):
        with self._store.read() as db:
            if db.execute("SELECT 1 FROM memory_control_fence").fetchone(): raise SyntheticError("reset_busy")
        return super().reset(session)

    def restricted_truth(self, session):
        inherited = super().restricted_truth(session)
        with self._store.read() as db:
            self._auth(db, session)
            rows = lambda table: [bounded_json(r[0]) for r in db.execute(f"SELECT payload FROM {table} ORDER BY rowid")]
            inherited["memory"] = {"owner_states": [{**{k: h[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}, "facts": self._store.facts(db, h["owner"])}
                for h in (self._store.header(db, o[0]) for o in db.execute("SELECT owner FROM memory_owners ORDER BY owner"))],
                "contexts": rows("memory_contexts"), "controls": [], "journals": rows("memory_mutations"), "snapshots": rows("memory_snapshots"),
                "host_outputs": rows("memory_host_outputs"), "fault_hits": rows("memory_fault_hits"),
                "counters": {"checks_remaining": max(0, 8 - sum(bounded_json(r[0])["snapshot"]["status"] != "ineligible" for r in db.execute("SELECT payload FROM memory_snapshots"))),
                    "controls_remaining": max(0, 32 - db.execute("SELECT count(*) FROM memory_controls").fetchone()[0])}, "fence": None}
            fence = db.execute("SELECT control_id,owner,persistence_fenced FROM memory_control_fence WHERE singleton=1").fetchone()
            if fence: inherited["memory"]["fence"] = {"control_id": fence[0], "owner": fence[1], "persistence_fenced": bool(fence[2])}
            inherited["memory"]["controls"] = [{"id": r[0], "ordinal": r[1], "assessment_id": r[2], "state_generation": r[3], "owner": r[4], "tenant": r[5],
                "body": bounded_json(r[6]), "input_digest": r[7], "status": r[8], "result": bounded_json(r[9]) if r[9] else None,
                "result_digest": r[10], "accepted_seconds": r[11], "deadline_seconds": r[12]}
                for r in db.execute("SELECT * FROM memory_controls ORDER BY ordinal")]
        return inherited
