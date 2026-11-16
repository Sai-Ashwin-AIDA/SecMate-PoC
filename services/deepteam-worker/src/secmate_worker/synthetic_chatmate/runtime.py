"""Phase 0–1 local state machine. No provider clients or mutable legacy profile imports.

Host controls are Python methods, not model tools. Future managed adapters must
retain job_runtime's permission/fencing gate and use their own publication contract.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from ..job_runtime import canonical, require_permission
from .artifacts import Bundle
from .contracts import (
    Budget, ConversationRead, ErrorOutput, EvidenceEvent, FaultPlan, Lease, Listing, MessageCreate,
    MessagePage, READ_TOOL, Script, Session, SyntheticError, TARGET_ID, TARGET_VERSION,
    ToolCall, ToolResult, clone, digest, strict_json,
)
from .store import Store

TERMINAL = {"completed", "failed", "cancelled"}


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


class SyntheticChatMate:
    """A target-local namespace, not another global SecMate job coordinator."""

    def __init__(self, root: Path, bundle: Bundle | None = None):
        require_permission()
        self.bundle = bundle or Bundle.load()
        self.path = Path(root).resolve() / "targets" / TARGET_ID
        try:
            self.path.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise SyntheticError("target_identity_collision") from exc
        self.path = self.path / TARGET_VERSION
        self.path.mkdir()
        self.assessments = self.path / "assessments"
        self.assessments.mkdir()
        definitions = self.path / "definitions"
        definitions.mkdir()
        for key, value in self.bundle.artifacts:
            with (definitions / f"{key}.json").open("x", encoding="utf-8") as stream:
                stream.write(value)
        with (self.path / "registration.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical({
                "target_id": TARGET_ID, "target_version": TARGET_VERSION, "manifesto_version": "0.1.2",
                "source_revision": self.bundle.get("native_metadata")["source_revision"],
                "mapper_blob_id": self.bundle.get("native_metadata")["mapper_blob_id"],
                "phase_scope": [0, 1], "definition_digests": {
                    key: digest(strict_json(value)) for key, value in self.bundle.artifacts},
                "api_registration": False, "deepteam_provider": False,
            }))

    def fresh(self, *, subject="subject-ada", faults: FaultPlan | None = None,
              generation=1) -> Assessment:
        return Assessment(self, subject, faults or FaultPlan(), generation)


class Assessment:
    def __init__(self, target: SyntheticChatMate, subject: str, faults: FaultPlan, generation: int):
        require_permission()
        self._target, self._bundle = target, target.bundle
        users = {u["subject"]: u for u in self._bundle.get("seed")["users"]}
        if subject not in users:
            raise SyntheticError("invalid_host_identity")
        self.id, self.generation = _id("assessment"), generation
        self._watchdog_started = None
        self.path = target.assessments / self.id
        self.path.mkdir(exist_ok=False)
        self._faults = FaultPlan.model_validate_json(faults.model_dump_json())
        self._binding = self._bundle.bindings(self._faults.model_dump(), self.id, generation)
        self._binding_digest = digest(self._binding)
        with (self.path / "bindings.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical(self._binding))
        with (self.path / "faults.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical(self._faults.model_dump()))
        self._store = Store(self.path / "assessment.sqlite3", {
            "assessment_id": self.id, "generation": generation, "owner": subject,
            "seconds": 0.0, "archived": False, "accepted": False, "sessions": {},
        })
        self.session = self.host_session(subject)
        with self._store.transaction() as db:
            state = self._state(db)
            self._emit(db, state, "assessment.created", None, {"binding_digest": self._binding_digest})
            self._emit(db, state, "assessment.bindings_loaded", None, {"bindings": self._binding})

    @property
    def bindings(self):
        return clone(self._binding)

    def _state(self, db):
        return strict_json(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])

    def _save_state(self, db, state):
        db.execute("UPDATE state SET payload=? WHERE id=1", (canonical(state),))

    def _save_run(self, db, run):
        db.execute("INSERT INTO runs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (run["id"], canonical(run)))

    def _run(self, db, run_id):
        row = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise SyntheticError("resource_unavailable")
        return strict_json(row[0])

    def _timestamp(self, seconds):
        origin = datetime.fromisoformat(self._binding["clock_origin"].replace("Z", "+00:00"))
        return (origin + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        last = db.execute("SELECT max(id) FROM events").fetchone()[0] or 0
        event = {
            "event_schema_version": "0.1.0", "target_id": TARGET_ID, "target_version": TARGET_VERSION,
            "assessment_id": self.id, "state_generation": self.generation,
            "run_id": run["id"] if run else None, "event_id": last + 1,
            "logical_time": self._timestamp(state["seconds"]), "type": kind,
            "actor_ref": state["owner"], "call_id": call_id, "action_id": None,
            "caused_by": last or None, "data": data or {},
            "binding_digest": digest(run["bindings"]) if run else self._binding_digest,
        }
        EvidenceEvent.model_validate(event)
        db.execute("INSERT INTO events (payload) VALUES (?)", (canonical(event),))
        return event["event_id"]

    def _auth(self, db, session, *, owner=True):
        state = self._state(db)
        if state["archived"] or state["generation"] != self.generation:
            raise SyntheticError("stale_generation")
        identity = state["sessions"].get(session.token) if isinstance(session, Session) else None
        if identity is None:
            raise SyntheticError("invalid_session")
        if owner and identity["subject"] != state["owner"]:
            raise SyntheticError("resource_unavailable")
        return state, identity

    def host_session(self, subject: str) -> Session:
        """Trusted harness identity selection; never an argument of MessageCreate."""
        users = {u["subject"]: u for u in self._bundle.get("seed")["users"]}
        if subject not in users:
            raise SyntheticError("invalid_host_identity")
        session = Session(_id("session"))
        with self._store.transaction() as db:
            state = self._state(db)
            if state["archived"]:
                raise SyntheticError("stale_generation")
            state["sessions"][session.token] = users[subject]
            self._save_state(db, state)
        return session

    def submit(self, session: Session, body: dict, *, snapshot_id="snapshot-ada") -> dict:
        """One initial prompt only. Snapshot selector is trusted harness input."""
        error = None
        accepted = None
        with self._store.transaction() as db:
            state, identity = self._auth(db, session)
            if isinstance(body, dict) and "resume_conversation_id" in body:
                raise SyntheticError("continuation_not_supported")
            try:
                message = MessageCreate.model_validate(body)
            except ValidationError as exc:
                raise SyntheticError("invalid_arguments") from exc
            if state["accepted"]:
                raise SyntheticError("continuation_not_supported")
            snapshot = next((s for s in self._bundle.get("seed")["snapshots"] if s["id"] == snapshot_id), None)
            allowed = snapshot is not None and not snapshot["deleted"] and snapshot["owner"] == identity["subject"]
            self._emit(db, state, "snapshot.authorized" if allowed else "snapshot.authorization_rejected", None,
                       {"resource_id": snapshot_id, "requested_by": identity["subject"],
                        "resource_owner": snapshot["owner"] if snapshot else None})
            if not allowed:
                error = SyntheticError("resource_unavailable")
            else:
                prompt = {"id": _id("message"), "conversation_id": _id("conversation"),
                          "role": "user", "content": message.content, "created_at": self._timestamp(state["seconds"])}
                run = {"id": _id("run"), "conversation_id": prompt["conversation_id"],
                       "prompt_message_id": prompt["id"], "status": "queued", "result_message_id": None,
                       "identity": identity, "owner": state["owner"], "prompt": prompt,
                       "snapshot_id": snapshot_id, "snapshot_owner": snapshot["owner"],
                       "snapshot": snapshot["messages"] + [{"message_id": prompt["id"], "role": "user", "content": message.content}],
                       "round": 0, "remaining": self._bundle.get("budget")["execution"],
                       "transcript": [], "seen_calls": [], "oversized": 0, "streak": {},
                       "lease": None, "cancel": False, "outcome": None, "partial": False,
                       "answer": None, "terminal_reason": None}
                run["bindings"] = {**self._binding, "run_id": run["id"]}
                self._save_run(db, run)
                state["accepted"] = True
                self._save_state(db, state)
                self._emit(db, state, "message.accepted", run, {"message_id": prompt["id"]})
                self._emit(db, state, "run.created", run)
                accepted = {"message": prompt, "run": {key: run[key] for key in (
                    "id", "conversation_id", "prompt_message_id", "status", "result_message_id")}}
        if error:
            raise error
        # Deliberately a second transaction: durable acceptance precedes enqueue.
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            run = self._run(db, accepted["run"]["id"])
            if self._faults.enqueue_failure:
                self._finish(db, state, run, "failed", "dispatch_unavailable")
                error = SyntheticError("dispatch_unavailable", run["id"])
            else:
                self._store.enqueue(db, run["id"])
                self._emit(db, state, "run.enqueued", run, {"accepted_message_id": run["prompt_message_id"]})
        if error:
            raise error
        return clone(accepted)

    def acquire(self, session: Session) -> Lease | None:
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            # A held run is not re-enqueued or stolen. This is local CAS, not
            # SecMate's durable process lease protocol.
            for (payload,) in db.execute("SELECT payload FROM runs"):
                if strict_json(payload)["lease"]:
                    return None
            while True:
                next_run = self._store.dequeue(db)
                if next_run is None:
                    return None
                run = self._run(db, next_run)
                if run["status"] in TERMINAL:
                    continue
                token = _id("lease")
                self._watchdog_started = time.perf_counter()
                run.update(status="running", lease=token, deadline=state["seconds"] + self._budget.run_seconds)
                self._save_run(db, run)
                self._emit(db, state, "run.started", run)
                return Lease(self.id, self.generation, run["id"], token)

    @property
    def _budget(self):
        return Budget.model_validate(self._bundle.get("budget"))

    def _leased(self, db, lease):
        state = self._state(db)
        if state["archived"] or lease.assessment_id != self.id or lease.state_generation != self.generation:
            raise SyntheticError("stale_generation")
        run = self._run(db, lease.run_id)
        if run["lease"] != lease.token or run["status"] not in {"running", "cancel_requested"}:
            raise SyntheticError("stale_lease")
        return state, run

    def _finish(self, db, state, run, status, reason, *, answer=None, outcome=None):
        run.update(status=status, terminal_reason=reason, answer=answer, outcome=outcome,
                   partial=outcome == "Partial", lease=None)
        if status == "completed":
            run["result_message_id"] = _id("answer")
        self._save_run(db, run)
        self._emit(db, state, f"run.{status}", run, {
            "message_id": run["result_message_id"], "content": answer,
            "kernel_outcome": outcome, "partial": run["partial"], "reason": reason,
            "error_code": reason if status == "failed" else None})
        self._emit(db, state, "assessment.finished", run, {"status": status})

    def _checkpoint(self, db, state, run):
        if self._watchdog_started is not None and time.perf_counter() - self._watchdog_started >= 60:
            self._finish(db, state, run, "failed", "environmental_watchdog")
            return False
        if self._faults.cancel_at is not None and state["seconds"] >= self._faults.cancel_at and not run["cancel"]:
            run["cancel"] = True
            self._emit(db, state, "run.cancel_requested", run, {"source": "bound_fault_schedule"})
        if run["cancel"]:
            self._finish(db, state, run, "cancelled", "owner_cancelled")
            return False
        return True

    def _advance(self, db, state, run, duration, deadline):
        end = state["seconds"] + duration
        cancel = self._faults.cancel_at
        if cancel is not None and state["seconds"] <= cancel <= min(end, deadline):
            state["seconds"] = cancel
            self._save_state(db, state)
            self._checkpoint(db, state, run)
            return "cancelled"
        state["seconds"] = min(end, deadline)
        self._save_state(db, state)
        return "timeout" if end >= deadline else None

    def _request(self, run, state):
        prompt = self._bundle.get("prompt")
        identity = run["identity"]
        items = [{"role": "developer", "content": prompt["developer_guidance"] + "\n" + canonical({
            "profile": {"display_name": identity["display_name"], "timezone": identity["timezone"]}})}]
        items += [{"role": m["role"], "content": m["content"]} for m in run["snapshot"][:-1]]
        items += [{"role": "developer", "content": canonical({"time": self._timestamp(state["seconds"]),
                                                                "timezone": identity["timezone"]})},
                  {"role": "user", "content": run["prompt"]["content"]}]
        items += run["transcript"]
        return {"instructions": prompt["instructions"], "items": items,
                "tools": [{"type": "function", "name": READ_TOOL,
                           "parameters": self._bundle.get("schemas")["read_input"]}],
                "tool_choice": "auto", "parallel_tool_calls": False}

    def _result(self, db, state, run, call_id, output, *, error=False, tool_name=READ_TOOL):
        if error:
            ErrorOutput.model_validate(output)
        result = ToolResult(call_id=call_id, status="error" if error else "ok", output=output,
                            source_refs=[] if error else [output["source_ref"]]).model_dump()
        self._emit(db, state, "tool.result", run, {"result": result}, call_id)
        run["transcript"].append({"type": "function_call_output", "call_id": call_id, "output": canonical(output)})
        if error and output["error"] != "error_streak_exhausted":
            previous = run["streak"].get(tool_name, {"code": None, "count": 0})
            run["streak"][tool_name] = {"code": output["error"], "count": previous["count"] + 1 if previous["code"] == output["error"] else 1}
        elif not error:
            run["streak"].pop(tool_name, None)

    def _read(self, run, arguments):
        snapshot = run["snapshot"]
        source = {"resource_id": run["snapshot_id"], "source_kind": "conversation_snapshot",
                  "content_digest": digest([{k: m[k] for k in ("role", "content")} for m in snapshot])}
        offset = arguments.offset
        if arguments.message_id is None:
            page = snapshot[offset:offset + 12]
            end = offset + len(page)
            return Listing(kind="listing", messages=[{"message_id": m["message_id"], "role": m["role"]} for m in page],
                           offset=offset, next_offset=end if end < len(snapshot) else None,
                           truncated=end < len(snapshot), source_ref=source).model_dump()
        message = next((m for m in snapshot if m["message_id"] == arguments.message_id), None)
        if message is None:
            return {"error": "resource_unavailable"}
        content = message["content"][offset:offset + 12000]
        end = offset + len(content)
        return MessagePage(kind="message", message_id=message["message_id"], role=message["role"],
                           content=content, offset=offset, next_offset=end if end < len(message["content"]) else None,
                           truncated=end < len(message["content"]), files=[], source_ref=source).model_dump()

    def _dispatch(self, db, state, run, calls):
        decisions = []
        disabled = self._bundle.get("capabilities")["disabled"]
        for call in calls:
            self._emit(db, state, "tool.requested", run, {"name": call.name, "arguments": call.arguments}, call.call_id)
            code, arguments = None, None
            if call.name != READ_TOOL:
                code = "capability_disabled" if call.name in disabled else "unknown_tool"
            else:
                try:
                    arguments = ConversationRead.model_validate(strict_json(call.arguments))
                except (ValueError, TypeError, ValidationError):
                    code = "invalid_arguments"
            self._emit(db, state, "tool.validation_rejected" if code else "tool.validated", run,
                       {"name": call.name, "code": code, "native_label": "conversation_read" if call.name == READ_TOOL else None}, call.call_id)
            if code is None:
                # Missing snapshot IDs are safe lookup errors, not a scope expansion.
                self._emit(db, state, "tool.authorized", run, {"resource_id": run["snapshot_id"],
                           "owner": run["snapshot_owner"], "connector_owner": run["identity"]["connector_owner"]}, call.call_id)
                streak = run["streak"].get(call.name, {})
                if streak.get("count", 0) >= 3:
                    code = "error_streak_exhausted"
                elif run["remaining"] == 0:
                    code = "budget_exhausted"
                    self._emit(db, state, "budget.exhausted", run, {"pool": "execution"}, call.call_id)
                else:
                    run["remaining"] -= 1
                    self._emit(db, state, "budget.charged", run, {"pool": "execution", "remaining": run["remaining"]}, call.call_id)
            decisions.append((call, arguments, code))
        halted = False
        for call, arguments, code in decisions:
            if not self._checkpoint(db, state, run):
                return
            if code is not None:
                self._result(db, state, run, call.call_id, {"error": code}, error=True, tool_name=call.name)
                continue
            if halted:
                self._result(db, state, run, call.call_id, {"error": "not_run"}, error=True)
                continue
            self._emit(db, state, "tool.dispatched", run, {"name": call.name, "destination": "assessment_snapshot"}, call.call_id)
            fault = next((f for f in self._faults.tools if f.call_id == call.call_id), None)
            duration, code = (fault.duration, fault.error) if fault else (0.0, None)
            outcome = self._advance(db, state, run, duration, min(run["deadline"], state["seconds"] + self._budget.tool_seconds))
            if outcome == "cancelled":
                return
            if outcome == "timeout":
                code = "tool_timeout"
                self._emit(db, state, "tool.timeout", run, {}, call.call_id)
            try:
                output = {"error": code} if code else self._read(run, arguments)
            except Exception:
                output = {"error": "tool_failed"}
            if len(canonical(output)) > self._budget.output_characters:
                output = {"error": "tool_output_limit_exceeded"}
            self._result(db, state, run, call.call_id, output, error="error" in output)
            if fault and fault.halt:
                halted = True

    def step(self, lease: Lease) -> dict:
        """One complete model round; cancellation can occur at bound clock barriers."""
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            if not self._checkpoint(db, state, run):
                return clone(run)
            budget = self._budget
            if state["seconds"] >= run["deadline"] or run["round"] >= budget.rounds:
                self._finish(db, state, run, "completed", "time" if state["seconds"] >= run["deadline"] else "rounds", outcome="Partial", answer="")
                return clone(run)
            request = self._request(run, state)
            if len(canonical(request)) > budget.context_characters:
                self._finish(db, state, run, "failed", "context_limit_exceeded")
                return clone(run)
            run["round"] += 1
            self._emit(db, state, "budget.charged", run, {"pool": "rounds", "round": run["round"]})
            script = Script.model_validate(self._bundle.get("script"))
            if run["round"] > len(script.rounds):
                self._finish(db, state, run, "failed", "model_protocol_error")
                return clone(run)
            scripted = script.rounds[run["round"] - 1]
            step_deadline = min(run["deadline"], state["seconds"] + budget.model_seconds)
            for attempt in (1, 2):
                self._emit(db, state, "model.request_built", run, {"round": run["round"], "attempt": attempt, "request": request})
                fault = next((f for f in self._faults.model if f.round == run["round"] and f.attempt == attempt), None)
                outcome = self._advance(db, state, run, fault.duration if fault else 0.0, step_deadline)
                if outcome == "cancelled":
                    return clone(run)
                error = "model_timeout" if outcome == "timeout" else (fault.error if fault else scripted.error)
                if error:
                    if fault and fault.after_output:
                        self._emit(db, state, "model.incomplete_step", run, {
                            "round": run["round"], "text": scripted.text,
                            "calls": scripted.calls, "completion": False})
                    self._emit(db, state, "model.error", run, {"code": error, "attempt": attempt,
                               "after_output": fault.after_output if fault else False})
                    if attempt == 1 and error in {"model_timeout", "model_transport_unavailable"} and not (fault and fault.after_output):
                        result = self._advance(db, state, run, budget.retry_delay, step_deadline)
                        if result == "cancelled":
                            return clone(run)
                        if result is None:
                            self._emit(db, state, "model.retry", run, {"attempt": 2})
                            continue
                    self._finish(db, state, run, "failed", error)
                    return clone(run)
                break
            try:
                calls = [ToolCall.model_validate(c) for c in scripted.calls]
                call_ids = [c.call_id for c in calls]
                if not scripted.completion or len(set(call_ids)) != len(call_ids) or set(call_ids) & set(run["seen_calls"]):
                    raise ValueError("protocol")
            except (ValidationError, ValueError):
                self._emit(db, state, "model.incomplete_step", run, {
                    "round": run["round"], "text": scripted.text,
                    "calls": scripted.calls, "completion": scripted.completion})
                self._finish(db, state, run, "failed", "model_protocol_error")
                return clone(run)
            if len(scripted.text) > budget.output_characters or any(len(c.arguments) > budget.context_characters for c in calls):
                self._finish(db, state, run, "failed", "model_output_limit_exceeded")
                return clone(run)
            self._emit(db, state, "model.response_received", run, {"round": run["round"], "text": scripted.text,
                       "calls": [c.model_dump() for c in calls], "completion": True})
            run["seen_calls"].extend(call_ids)
            if scripted.text:
                run["transcript"].append({"role": "assistant", "content": scripted.text})
            run["transcript"].extend([{"type": "function_call", **c.model_dump()} for c in calls])
            if not calls:
                self._finish(db, state, run, "completed" if scripted.text else "failed",
                             "final" if scripted.text else "model_empty_response", answer=scripted.text or None,
                             outcome="Final" if scripted.text else None)
                return clone(run)
            if len(calls) > budget.calls_per_round:
                run["oversized"] += 1
                for call in calls:
                    self._result(db, state, run, call.call_id, {"error": "call_batch_limit"}, error=True, tool_name=call.name)
                if run["oversized"] >= 2:
                    self._finish(db, state, run, "completed", "call_batch_limit", outcome="Final",
                                 answer="The model exceeded this run's tool-call batch limit.")
                    return clone(run)
            else:
                self._dispatch(db, state, run, calls)
                if run["status"] in TERMINAL:
                    return clone(run)
                if any(item["type"] == "function_call_output" and '"error":"budget_exhausted"' in item["output"] for item in run["transcript"]):
                    self._finish(db, state, run, "completed", "budget", outcome="Partial", answer="")
                    return clone(run)
            self._save_run(db, run)
            return clone(run)

    def execute(self, session: Session) -> dict | None:
        lease = self.acquire(session)
        if lease is None:
            return None
        while True:
            result = self.step(lease)
            if result["status"] in TERMINAL:
                return result

    def cancel(self, session: Session, run_id: str):
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            run = self._run(db, run_id)
            if run["status"] in TERMINAL:
                return clone(run)
            run["cancel"] = True
            run["status"] = "cancel_requested"
            self._emit(db, state, "run.cancel_requested", run, {"source": "owner_control"})
            if not run["lease"]:
                self._finish(db, state, run, "cancelled", "owner_cancelled")
            else:
                self._save_run(db, run)
            return clone(run)

    def run(self, session: Session, run_id: str) -> dict:
        with self._store.read() as db:
            self._auth(db, session)
            return clone(self._run(db, run_id))

    def events(self, session: Session, *, after=0, last_event_id=0) -> list[dict]:
        if type(after) is not int or type(last_event_id) is not int or min(after, last_event_id) < 0:
            raise SyntheticError("invalid_cursor")
        with self._store.read() as db:
            self._auth(db, session)
            return [strict_json(r[0]) for r in db.execute("SELECT payload FROM events WHERE id>? ORDER BY id", (max(after, last_event_id),))]

    def sse(self, session: Session, *, after=0, last_event_id=0) -> str:
        return "".join(f"id: {e['event_id']}\nevent: {e['type']}\ndata: {canonical({'type': e['type'], **e['data']})}\n\n"
                       for e in self.events(session, after=after, last_event_id=last_event_id))

    def reset(self, session: Session) -> Assessment:
        with self._store.transaction() as db:
            state, _ = self._auth(db, session)
            runs = [strict_json(r[0]) for r in db.execute("SELECT payload FROM runs")]
            if any(r["lease"] for r in runs):
                raise SyntheticError("reset_busy")
            self._emit(db, state, "reset.started", None)
            for run in runs:
                if run["status"] not in TERMINAL:
                    self._finish(db, state, run, "cancelled", "reset_fenced")
            db.execute("DELETE FROM queue")
            self._emit(db, state, "reset.completed", None, {"next_generation": self.generation + 1})
            state["archived"] = True
            self._save_state(db, state)
        # A fresh namespace, no deletion or reuse of the archived database.
        return self._target.fresh(subject=state["owner"], generation=self.generation + 1)
