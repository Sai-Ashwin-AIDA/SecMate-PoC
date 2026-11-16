"""Durable bounded Phase 5 model profile over the accepted Phase 4 runtime."""
from __future__ import annotations

import hashlib
import inspect
import json
import asyncio
import time
import sqlite3
from dataclasses import asdict
from pydantic import ValidationError
from pathlib import Path
from typing import Any, Callable

from ...job_runtime import canonical, require_permission
from ...model_clients import ModelErrorCode, ModelRequestError, StructuredModelClients
from ...model_profiles import OPENROUTER_NEMOTRON_TARGET
from ..contracts import TARGET_ID, SyntheticError, ToolCall, clone, digest
from ..memory_phase4.artifacts import MemoryBundle
from ..memory_phase4.contracts import Phase4FaultPlan
from ..memory_phase4.runtime import MemoryAssessment, validate_repaired
from ..calendar_repaired.runtime import validate_frozen_calendar
from ..communication_repaired.artifacts import validate_predecessor
from .adapter import ADAPTER_VERSION, ModelProtocolError, Phase5ModelAdapter, provider_name
from .onboarding import load_execution_profile
from .attempt_accounting import ACCOUNTING_VERSION, lifecycle
from .model_interface import (
    MODEL_INTERFACE_VERSION, PROMPT_VERSION, TOOL_SCHEMA_VERSION, capability_guidance,
)


VERSION = "0.5.0"
EXECUTION_PROFILE = load_execution_profile()
READ_ONLY_TOOLS = frozenset(tool["name"] for tool in EXECUTION_PROFILE["tools"] if tool["access"] == "read_only")
PROPOSAL_TOOLS = frozenset(tool["name"] for tool in EXECUTION_PROFILE["tools"] if tool["access"] == "staged_only")
DISPATCH_TOOLS = READ_ONLY_TOOLS | PROPOSAL_TOOLS
MODEL_TOOLS = tuple(tool["name"] for tool in EXECUTION_PROFILE["tools"])
PROFILE_BUDGETS = EXECUTION_PROFILE["budgets"]
LOGICAL_TURN_LIMIT = PROFILE_BUDGETS["logical_turn_limit"]
TRANSPORT_RETRY_CODES = frozenset({
    ModelErrorCode.RATE_LIMITED, ModelErrorCode.PROVIDER_UNAVAILABLE,
    ModelErrorCode.REQUEST_TIMEOUT, ModelErrorCode.CONNECT_TIMEOUT,
    ModelErrorCode.READ_TIMEOUT, ModelErrorCode.WRITE_TIMEOUT,
    ModelErrorCode.POOL_TIMEOUT, ModelErrorCode.NETWORK_ERROR,
})


class Phase5Bundle(MemoryBundle):
    def model_interface(self):
        _, tools = Phase5ModelAdapter.render({
            "instructions": self.get("prompt")["instructions"], "items": [],
            "tools": [{"type": "function", "name": name,
                       "parameters": self.get("schemas")["read_input"] if name == "secmate.conversation.history.read"
                       else self.get("schemas")["tools"][name]["input"]}
                      for name in MODEL_TOOLS],
        })
        return {
            "version": MODEL_INTERFACE_VERSION, "prompt_version": PROMPT_VERSION,
            "provider_tool_schema_version": TOOL_SCHEMA_VERSION,
            "execution_profile_digest": digest(EXECUTION_PROFILE),
            "prompt": self.get("prompt"), "provider_tools": tools,
        }

    def bindings(self, faults, assessment_id, generation):
        value = super().bindings(faults, assessment_id, generation)
        value.update(
            target_version=VERSION,
            adapter_version=ADAPTER_VERSION,
            provider_accounting_version=ACCOUNTING_VERSION,
            prompt_version=PROMPT_VERSION,
            model_interface_version=MODEL_INTERFACE_VERSION,
            provider_tool_schema_version=TOOL_SCHEMA_VERSION,
            model_interface_digest=digest(self.model_interface()),
            model_mode="openrouter_nemotron",
            target_profile_id=OPENROUTER_NEMOTRON_TARGET.profile_id,
            provider=OPENROUTER_NEMOTRON_TARGET.provider.value,
            model=OPENROUTER_NEMOTRON_TARGET.model,
            execution_profile=EXECUTION_PROFILE,
            execution_profile_digest=digest(EXECUTION_PROFILE),
            logical_turn_limit=LOGICAL_TURN_LIMIT,
            attempts_per_turn=PROFILE_BUDGETS["attempts_per_turn"],
            attempt_limit=PROFILE_BUDGETS["provider_attempt_limit"],
            output_token_limit=PROFILE_BUDGETS["output_token_limit"],
            provider_token_limit=PROFILE_BUDGETS["provider_token_limit"],
            request_timeout_seconds=PROFILE_BUDGETS["request_timeout_seconds"],
            real_deadline_seconds=PROFILE_BUDGETS["real_deadline_seconds"],
            dispatch_allowlist=sorted(DISPATCH_TOOLS),
        )
        return value


def _source_hashes() -> dict[str, str]:
    directory = Path(__file__).parent
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.glob("*.py"))}


class ModelPhase5Target:
    def __init__(self, root: Path, bundle: MemoryBundle | None = None, *, deepteam_onboarding: bool = False):
        require_permission()
        supplied = bundle or MemoryBundle.load()
        inherited = Phase5Bundle.from_parts({key: json.loads(value) for key, value in supplied.artifacts})
        # Validate the frozen predecessor first, then apply an explicitly versioned
        # model-facing prompt overlay. Handler schemas/seeds remain byte-identical.
        parts = {key: json.loads(value) for key, value in inherited.artifacts}
        parts["prompt"] = {
            **parts["prompt"], "version": PROMPT_VERSION,
            "developer_guidance": capability_guidance(EXECUTION_PROFILE),
        }
        self.bundle = Phase5Bundle(tuple((key, canonical(value)) for key, value in sorted(parts.items())))
        target = Path(root).resolve() / "targets" / TARGET_ID
        if target.exists():
            if target.is_symlink() or not target.is_dir() or not list(target.iterdir()):
                raise SyntheticError("unowned_target_namespace")
            if (target / VERSION).exists():
                raise SyntheticError("target_version_collision")
            for predecessor in target.iterdir():
                if predecessor.name in {"0.1.1", "0.2.0", "0.2.1"}:
                    validate_predecessor(predecessor)
                elif predecessor.name == "0.3.0":
                    validate_frozen_calendar(predecessor)
                elif predecessor.name == "0.3.1":
                    validate_repaired(predecessor)
                elif predecessor.name == "0.4.0":
                    self._validate_phase4(predecessor)
                else:
                    raise SyntheticError("unowned_target_namespace")
        else:
            target.mkdir(parents=True, exist_ok=False)
        self.path = target / VERSION
        self.path.mkdir(exist_ok=False)
        self.assessments = self.path / "assessments"
        self.assessments.mkdir()
        definitions = self.path / "definitions"
        definitions.mkdir()
        definition_digests = {}
        for key, value in self.bundle.artifacts:
            parsed = json.loads(value)
            (definitions / f"{key}.json").write_text(canonical(parsed), encoding="ascii")
            definition_digests[key] = digest(parsed)
        enabled = list(self.bundle.get("capabilities")["enabled"])
        if enabled != list(MODEL_TOOLS):
            raise SyntheticError("model_tool_exposure")
        model_interface = self.bundle.model_interface()
        (self.path / "model-interface.json").write_text(canonical(model_interface), encoding="ascii")
        registration = {
            "target_id": TARGET_ID,
            "target_version": VERSION,
            "manifesto_version": "0.1.2",
            "phase_scope": [0, 1, 2, 3, 4, 5],
            "api_registration": deepteam_onboarding,
            "deepteam_provider": deepteam_onboarding,
            "definition_digests": definition_digests,
            "adapter_source_digests": _source_hashes(),
            "adapter_version": ADAPTER_VERSION,
            "provider_accounting_version": ACCOUNTING_VERSION,
            "model_interface_version": MODEL_INTERFACE_VERSION,
            "provider_tool_schema_version": TOOL_SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "model_interface_digest": digest(model_interface),
            "target_profile": {
                "profile_id": OPENROUTER_NEMOTRON_TARGET.profile_id,
                "provider": OPENROUTER_NEMOTRON_TARGET.provider.value,
                "role": OPENROUTER_NEMOTRON_TARGET.role.value,
                "model": OPENROUTER_NEMOTRON_TARGET.model,
            },
            "model_tools": list(MODEL_TOOLS),
            "dispatch_allowlist": sorted(DISPATCH_TOOLS),
            "execution_profile": EXECUTION_PROFILE,
            "execution_profile_digest": digest(EXECUTION_PROFILE),
        }
        if deepteam_onboarding:
            from .onboarding import onboarding_binding
            registration["deepteam_onboarding"] = onboarding_binding()
        (self.path / "registration.json").write_text(canonical(registration), encoding="ascii")

    @staticmethod
    def _validate_phase4(path: Path) -> None:
        try:
            registration = json.loads((path / "registration.json").read_text(encoding="utf-8"))
            definitions = {item.stem: json.loads(item.read_text(encoding="utf-8")) for item in (path / "definitions").glob("*.json")}
            if registration["target_version"] != "0.4.0" or len(definitions) != 29:
                raise ValueError
            if registration["definition_digests"] != {key: digest(value) for key, value in definitions.items()}:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            raise SyntheticError("unowned_target_namespace") from None

    def fresh(self, *, subject="subject-ada", faults=None, generation=1, context_profile="private", selected_tool=None):
        return ModelPhase5Assessment(
            self, subject, faults or Phase4FaultPlan(), generation, context_profile,
            selected_tool=selected_tool,
        )


class ModelPhase5Assessment(MemoryAssessment):
    def __init__(self, target, subject, faults, generation, context_profile, *, selected_tool=None):
        if selected_tool not in {None, *DISPATCH_TOOLS}:
            raise SyntheticError("capability_disabled")
        self._selected_tool = selected_tool
        self._clients = None
        self._budget_snapshot = None
        self._trusted_conversation_history = []
        super().__init__(target, subject, faults, generation, context_profile)
        with self._store.transaction() as db:
            db.executescript(f"""
                CREATE TABLE phase5_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    turn INTEGER NOT NULL CHECK(turn BETWEEN 1 AND {LOGICAL_TURN_LIMIT}),
                    attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND {PROFILE_BUDGETS['attempts_per_turn']}),
                    status TEXT NOT NULL CHECK(status IN ('pending','accepted','failed','discarded')),
                    payload TEXT NOT NULL,
                    UNIQUE(run_id,turn,attempt)
                );
                CREATE TABLE phase5_result (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL);
            """)

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        last = db.execute("SELECT max(id) FROM events").fetchone()[0] or 0
        event = {
            "event_schema_version": VERSION, "target_id": TARGET_ID, "target_version": VERSION,
            "assessment_id": self.id, "state_generation": self.generation,
            "run_id": run["id"] if run else None, "event_id": last + 1,
            "logical_time": self._timestamp(state["seconds"]), "type": kind,
            "actor_ref": state["owner"], "call_id": call_id or (data or {}).get("call_id"),
            "action_id": (data or {}).get("approval_id"), "caused_by": last or None,
            "data": clone(data or {}), "binding_digest": digest(run["bindings"]) if run else self._binding_digest,
            "production_claim": False,
        }
        db.execute("INSERT INTO events (payload) VALUES (?)", (canonical(event),))
        return event["event_id"]

    def _attempt_payload(self, run, turn, attempt, request, rendered, started, deadline):
        return {
            "adapter_version": ADAPTER_VERSION,
            "run_id": run["id"], "assessment_id": self.id, "state_generation": self.generation,
            "lease_token_digest": digest(run["lease"]), "turn": turn, "attempt": attempt,
            "request": request, "request_digest": digest(request), "rendered_payload": rendered,
            "rendered_payload_digest": digest(rendered), "started_elapsed_seconds": started,
            "real_deadline_seconds": deadline, "response": None, "error_code": None,
            "provider_attempts": [], "settled_elapsed_seconds": None,
        }

    def _prepare_attempt(self, lease, adapter, turn, attempt, replay, started, deadline):
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            if not self._checkpoint(db, state, run):
                raise SyntheticError("model_timeout" if run.get("terminal_reason") == "model_timeout" else "owner_cancelled")
            if started >= deadline:
                self._finish(db, state, run, "failed", "model_timeout")
                raise SyntheticError("model_timeout")
            run["round"] = turn
            request = self._prepare_memory(
                db, state, run, turn, attempt,
                min(run["deadline"], state["seconds"] + PROFILE_BUDGETS["request_timeout_seconds"]),
            )
            if self._trusted_conversation_history:
                request["trusted_conversation_history"] = clone(self._trusted_conversation_history)
                if len(canonical(request)) > self._budget.context_characters:
                    raise SyntheticError("context_limit_exceeded")
            messages, tools = adapter.render(request, replay)
            rendered = {
                "model": OPENROUTER_NEMOTRON_TARGET.model, "messages": messages,
                "temperature": 0, "max_tokens": PROFILE_BUDGETS["output_token_limit"], "reasoning": {"enabled": False},
                "tools": tools, "tool_choice": "auto",
                "provider": {**adapter.clients._openrouter_provider_policy(), "allow_fallbacks": False},
            }
            payload = self._attempt_payload(run, turn, attempt, request, rendered, started, deadline)
            db.execute("INSERT INTO phase5_attempts(run_id,turn,attempt,status,payload) VALUES (?,?,?,?,?)",
                       (run["id"], turn, attempt, "pending", canonical(payload)))
            self._save_run(db, run)
            self._emit(db, state, "model.attempt_prepared", run, {
                "turn": turn, "attempt": attempt, "request_digest": payload["request_digest"],
                "rendered_payload_digest": payload["rendered_payload_digest"], "deadline_seconds": deadline,
            })
            return request

    def _settle_attempt(self, lease, turn, attempt, status, response=None, error_code=None, *, elapsed=None, provider_attempts=()):
        with self._store.transaction() as db:
            state = self._state(db)
            if state["archived"] or lease.assessment_id != self.id or lease.state_generation != self.generation:
                raise SyntheticError("stale_generation")
            run = self._run(db, lease.run_id)
            if run["lease"] not in {lease.token, None}:
                raise SyntheticError("stale_lease")
            row = db.execute("SELECT payload FROM phase5_attempts WHERE run_id=? AND turn=? AND attempt=?",
                             (run["id"], turn, attempt)).fetchone()
            if row is None:
                raise SyntheticError("persistence_failed")
            payload = json.loads(row[0])
            if payload["lease_token_digest"] != digest(lease.token):
                raise SyntheticError("stale_lease")
            if status == "accepted" and (run["status"] in {"completed", "failed", "cancelled"} or elapsed is None or elapsed >= payload["real_deadline_seconds"] or not self._checkpoint(db, state, run)):
                status, response, error_code = "discarded", None, "DEADLINE_EXCEEDED"
                if run["status"] not in {"completed", "failed", "cancelled"}:
                    self._finish(db, state, run, "failed", "model_timeout")
            if status == "accepted":
                previous = 0
                for (raw,) in db.execute("SELECT payload FROM phase5_attempts WHERE status='accepted'"):
                    usage = (json.loads(raw).get("response") or {}).get("metadata", {}).get("usage")
                    previous += (usage or {}).get("total_tokens") or 0
                current_usage = (response or {}).get("metadata", {}).get("usage")
                if previous + ((current_usage or {}).get("total_tokens") or 0) > PROFILE_BUDGETS["provider_token_limit"]:
                    status, response, error_code = "failed", None, "BUDGET_EXHAUSTED"
            payload.update(response=response, error_code=error_code, provider_attempts=list(provider_attempts),
                           settled_elapsed_seconds=elapsed)
            db.execute("UPDATE phase5_attempts SET status=?,payload=? WHERE run_id=? AND turn=? AND attempt=? AND status='pending'",
                       (status, canonical(payload), run["id"], turn, attempt))
            self._emit(db, state, "model.attempt_" + status, run, {
                "turn": turn, "attempt": attempt, "error_code": error_code,
                "provider_request_id": (response or {}).get("metadata", {}).get("provider_request_id"),
                "finish_reason": (response or {}).get("metadata", {}).get("finish_reason"),
            })
            return status

    @staticmethod
    def _normalized(turn):
        return {
            "kind": turn.kind, "content": turn.content,
            "calls": [{"call_id": call.call_id, "name": call.name, "arguments": call.arguments, "replay": call.replay}
                      for call in turn.calls],
            "metadata": turn.metadata,
        }

    def _fail(self, lease, reason):
        with self._store.transaction() as db:
            state = self._state(db)
            run = self._run(db, lease.run_id)
            if state["archived"] or lease.state_generation != self.generation:
                raise SyntheticError("stale_generation")
            if run["status"] in {"completed", "failed", "cancelled"}:
                return clone(run)
            self._leased(db, lease)
            if run["status"] not in {"completed", "failed", "cancelled"}:
                self._finish(db, state, run, "cancelled" if reason == "owner_cancelled" else "failed", reason)
            return clone(run)

    def _checkpoint(self, db, state, run):
        if not super()._checkpoint(db, state, run):
            return False
        require_permission()
        if self._clients is not None and self._clients.budget_manager.remaining_seconds <= 0:
            self._finish(db, state, run, "failed", "model_timeout")
            return False
        return True

    def _accept_tool(self, lease, accepted):
        call = accepted.calls[0]
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            if not self._checkpoint(db, state, run):
                return None
            tool_call = ToolCall(call_id=call.call_id, name=call.name, arguments=canonical(call.arguments))
            run["seen_calls"].append(call.call_id)
            run["transcript"].append({"type": "function_call", **tool_call.model_dump()})
            if call.name not in DISPATCH_TOOLS or self._selected_tool is not None and call.name != self._selected_tool:
                self._emit(db, state, "tool.requested", run, {"name": call.name, "arguments": tool_call.arguments}, call.call_id)
                code = "capability_disabled" if call.name in self._bundle.get("capabilities")["enabled"] else "unknown_tool"
                self._emit(db, state, "tool.validation_rejected", run, {"name": call.name, "code": code, "native_metadata": None}, call.call_id)
                self._result(db, state, run, call.call_id, {"error": code}, error=True, tool_name=call.name)
                self._finish(db, state, run, "failed", "tool_denied" if code == "capability_disabled" else "model_protocol_error")
                return None
            self._dispatch(db, state, run, [tool_call])
            if not self._checkpoint(db, state, run):
                return None
            output_item = next((item for item in reversed(run["transcript"])
                                if item.get("type") == "function_call_output" and item.get("call_id") == call.call_id), None)
            if output_item is None:
                self._finish(db, state, run, "failed", "tool_denied")
                return None
            output = json.loads(output_item["output"])
            if "error" in output:
                self._finish(db, state, run, "failed", "tool_denied")
                return None
            run["memory_checkpoint"] = True
            self._save_run(db, run)
            self._emit(db, state, "memory.checkpoint", run, {"conversation_id": run["conversation_id"], "after_round": run["round"]})
            return {"call": call.replay, "output": output, "proposal": call.name in PROPOSAL_TOOLS}

    def _accept_pending(self, lease, logical_turns):
        text = "Awaiting approval"
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            if not self._checkpoint(db, state, run):
                return clone(run)
            run["transcript"].append({"role": "assistant", "content": text})
            self._finish(db, state, run, "completed", "pending_approval", answer=text, outcome="AwaitingApproval")
            result = {"final_text": text, "logical_turns": logical_turns, "model_mode": "openrouter_nemotron",
                      "mock_verified": None, "pending_approval": True}
            db.execute("INSERT INTO phase5_result VALUES (1,?)", (canonical(result),))
            return clone(run)

    def _accept_final(self, lease, text, logical_turns):
        with self._store.transaction() as db:
            state, run = self._leased(db, lease)
            if not self._checkpoint(db, state, run):
                return clone(run)
            run["transcript"].append({"role": "assistant", "content": text})
            self._finish(db, state, run, "completed", "final", answer=text, outcome="Final")
            result = {"final_text": text, "logical_turns": logical_turns, "model_mode": "openrouter_nemotron",
                      "mock_verified": None}
            db.execute("INSERT INTO phase5_result VALUES (1,?)", (canonical(result),))
            require_permission()
            if self._clients.budget_manager.remaining_seconds <= 0:
                raise SyntheticError("model_timeout")
            return clone(run)

    async def invoke(self, clients: StructuredModelClients, prompt: str, *, close_client: bool = True,
                     target_attempt_limit: int = PROFILE_BUDGETS["provider_attempt_limit"],
                     target_token_limit: int = PROFILE_BUDGETS["provider_token_limit"],
                     target_deadline_seconds: float | None = None,
                     trusted_conversation_history: list[dict[str, str]] | None = None):
        if (not 1 <= target_attempt_limit <= PROFILE_BUDGETS["provider_attempt_limit"]
                or not 1 <= target_token_limit <= PROFILE_BUDGETS["provider_token_limit"]):
            raise SyntheticError("target_budget_exhausted")
        self._clients = clients
        self._trusted_conversation_history = clone(trusted_conversation_history or [])
        accepted = self.submit(self.session, {"content": prompt})
        lease = self.acquire(self.session)
        if lease is None:
            raise SyntheticError("dispatch_unavailable")
        self._watchdog_started = None  # Phase 5 uses the shared 120s real deadline.
        adapter = Phase5ModelAdapter(clients)
        clock_start = time.monotonic()
        deadline = min(
            PROFILE_BUDGETS["real_deadline_seconds"] if target_deadline_seconds is None else target_deadline_seconds,
            clients.budget_manager.remaining_seconds,
        )
        if deadline <= 0:
            return self._fail(lease, "model_timeout")
        replay = []
        previous_sink = clients.event_sink
        attempt_events = []
        target_accounting = {"attempts": 0, "tokens": 0}
        def sink(event):
            value = asdict(event)
            value["usage"] = event.usage.model_dump() if event.usage else None
            attempt_events.append(json.loads(canonical(value)))
            state = lifecycle(value, required=True)
            if state["reservation_accepted"]:
                target_accounting["attempts"] += 1
                usage = event.usage.total_tokens if event.usage else None
                target_accounting["tokens"] += usage if usage is not None else (event.estimated_tokens or 0)
            if previous_sink:
                previous_sink(event)
        clients.event_sink = sink
        try:
            return await self._invoke_turns(clients, accepted, lease, adapter, clock_start, deadline, replay,
                                            attempt_events, target_accounting, target_attempt_limit, target_token_limit)
        except (SyntheticError, ValidationError, sqlite3.Error, OSError, RuntimeError) as error:
            reason = "model_timeout" if isinstance(error, TimeoutError) else "persistence_failed" if isinstance(error, (sqlite3.Error, OSError)) else (
                "owner_cancelled" if "cancel" in str(getattr(error, "code", "")) else
                "model_timeout" if isinstance(error, TimeoutError) or getattr(error, "code", None) == "model_timeout" else "model_protocol_error")
            try:
                return self._fail(lease, reason)
            except SyntheticError:
                # Stale generation/lease: never acquire authority to mutate a new run.
                with self._store.read() as db:
                    return clone(self._run(db, accepted["run"]["id"]))
        finally:
            clients.event_sink = previous_sink
            if close_client:
                try:
                    await asyncio.wait_for(clients.close(), timeout=max(.001, clients.budget_manager.remaining_seconds))
                except TimeoutError:
                    pass
            self._budget_snapshot = asdict(await clients.budget_manager.snapshot())

    async def _provider_turn(self, adapter, request, replay, lease, timeout):
        task = asyncio.create_task(adapter.turn(request, timeout_seconds=timeout, replay=replay))
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=min(.05, timeout))
                with self._store.transaction() as db:
                    state, run = self._leased(db, lease)
                    if not self._checkpoint(db, state, run):
                        raise SyntheticError("owner_cancelled" if run["status"] == "cancelled" else "model_timeout")
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _invoke_turns(self, clients, accepted, lease, adapter, clock_start, deadline, replay,
                            attempt_events, target_accounting, target_attempt_limit, target_token_limit):
        proposal_pending = False
        for turn_number in range(1, LOGICAL_TURN_LIMIT + 1):
            accepted_turn = None
            for attempt in range(1, PROFILE_BUDGETS["attempts_per_turn"] + 1):
                elapsed = time.monotonic() - clock_start
                attempt_events.clear()
                try:
                    if target_accounting["attempts"] >= target_attempt_limit or target_accounting["tokens"] >= target_token_limit:
                        if proposal_pending:
                            return self._accept_pending(lease, turn_number - 1)
                        return self._fail(lease, "model_failed")
                    request = self._prepare_attempt(lease, adapter, turn_number, attempt, replay, elapsed, deadline)
                    remaining = deadline - (time.monotonic() - clock_start)
                    if remaining <= 0:
                        raise ModelProtocolError("model_timeout")
                    accepted_turn = await self._provider_turn(adapter, request, replay, lease,
                                                               min(PROFILE_BUDGETS["request_timeout_seconds"], remaining))
                    if accepted_turn.kind == "tool_call" and len(accepted_turn.calls) != 1:
                        raise ModelProtocolError("invalid_tool_turn")
                    if proposal_pending and accepted_turn.kind != "final":
                        raise ModelProtocolError("tool_after_pending_approval")
                    if turn_number == LOGICAL_TURN_LIMIT and accepted_turn.kind != "final":
                        raise ModelProtocolError("logical_turn_limit")
                    if target_accounting["attempts"] > target_attempt_limit or target_accounting["tokens"] > target_token_limit:
                        raise ModelProtocolError("target_budget_exhausted")
                    if (accepted_turn.kind == "tool_call" and accepted_turn.calls[0].name in PROPOSAL_TOOLS
                            and (turn_number >= LOGICAL_TURN_LIMIT
                                 or target_accounting["attempts"] >= target_attempt_limit
                                 or target_accounting["tokens"] >= target_token_limit)):
                        raise ModelProtocolError("proposal_final_turn_unavailable")
                    normalized = self._normalized(accepted_turn)
                    settled = self._settle_attempt(
                        lease, turn_number, attempt, "accepted", response=normalized,
                        elapsed=time.monotonic() - clock_start,
                        provider_attempts=attempt_events,
                    )
                    if settled != "accepted":
                        if settled == "failed":
                            return self._fail(lease, "model_failed")
                        with self._store.read() as db:
                            return clone(self._run(db, accepted["run"]["id"]))
                    break
                except ModelRequestError as error:
                    self._settle_attempt(lease, turn_number, attempt, "failed", error_code=error.code.value,
                        elapsed=time.monotonic() - clock_start, provider_attempts=attempt_events)
                    if attempt == 1 and error.retryable and error.code in TRANSPORT_RETRY_CODES:
                        continue
                    if proposal_pending:
                        return self._accept_pending(lease, turn_number - 1)
                    reason = {ModelErrorCode.MALFORMED_RESPONSE: "model_protocol_error", ModelErrorCode.CAMPAIGN_CANCELLED: "owner_cancelled",
                              ModelErrorCode.DEADLINE_EXCEEDED: "model_timeout"}.get(error.code, "model_failed")
                    return self._fail(lease, reason)
                except ModelProtocolError as error:
                    self._settle_attempt(lease, turn_number, attempt, "failed", error_code=str(error),
                        elapsed=time.monotonic() - clock_start, provider_attempts=attempt_events)
                    if proposal_pending:
                        return self._accept_pending(lease, turn_number - 1)
                    if attempt == 1 and str(error) == "model_timeout":
                        continue
                    return self._fail(lease, "model_protocol_error" if str(error) != "model_timeout" else "model_timeout")
                except asyncio.CancelledError:
                    self._settle_attempt(lease, turn_number, attempt, "discarded", error_code="CANCELLED",
                        elapsed=time.monotonic() - clock_start, provider_attempts=attempt_events)
                    with self._store.transaction() as db:
                        state, run = self._leased(db, lease)
                        self._finish(db, state, run, "cancelled", "owner_cancelled")
                        return clone(run)
                except SyntheticError as error:
                    try:
                        self._settle_attempt(lease, turn_number, attempt, "discarded", error_code=error.code,
                            elapsed=time.monotonic() - clock_start, provider_attempts=attempt_events)
                    except SyntheticError:
                        pass
                    if error.code in {"stale_generation", "stale_lease"}:
                        raise
                    return self._fail(lease, "model_timeout" if error.code == "model_timeout" else "owner_cancelled")
            if accepted_turn is None:
                return self._fail(lease, "model_failed")
            if accepted_turn.kind == "final":
                if proposal_pending:
                    return self._accept_pending(lease, turn_number)
                return self._accept_final(lease, accepted_turn.content, turn_number)
            result = self._accept_tool(lease, accepted_turn)
            if result is None:
                with self._store.read() as db:
                    return clone(self._run(db, accepted["run"]["id"]))
            proposal_pending = result.pop("proposal")
            replay.append(result)
        raise RuntimeError("unreachable")

    def export(self, *, mock_verified: bool):
        require_permission()
        events = self.events(self.session)
        truth = self.restricted_truth(self.session)
        with self._store.read() as db:
            attempts = [{"status": row[0], **json.loads(row[1])}
                        for row in db.execute("SELECT status,payload FROM phase5_attempts ORDER BY turn,attempt")]
            result_row = db.execute("SELECT payload FROM phase5_result WHERE singleton=1").fetchone()
            result = json.loads(result_row[0]) if result_row else None
        if result is not None:
            result["mock_verified"] = mock_verified
        for name, value in (("events.json", events), ("restricted-truth.json", truth),
                            ("model-attempts.json", attempts), ("final-output.json", result),
                            ("provider-budget.json", self._budget_snapshot)):
            (self.path / name).write_text(canonical(value), encoding="ascii")
        return {
            "target_id": TARGET_ID, "target_version": VERSION, "assessment_id": self.id,
            "evidence_directory": str(self.path), "model_mode": "openrouter_nemotron",
            "compatibility_claim": "OpenRouter/Nemotron-profile-shaped and mock-verified" if mock_verified else "authorized live observation",
            "live_call_performed": not mock_verified,
            "evidence_schema": "phase5-repair-1",
            "provider_accounting_version": ACCOUNTING_VERSION,
            "provider_tool_names": {provider_name(name): name for name in self._bundle.get("capabilities")["enabled"]},
        }


async def invoke_fresh(root, prompt, clients_factory: Callable[[], Any], *, history=None, selected_tool=None):
    """Fresh-invoke seam for one ordinary probe; no supplied history or session reuse."""
    if history is not None:
        raise SyntheticError("continuation_not_supported")
    target = ModelPhase5Target(root)
    assessment = target.fresh(selected_tool=selected_tool)
    clients = clients_factory()
    if inspect.isawaitable(clients):
        clients = await clients
    if not isinstance(clients, StructuredModelClients):
        raise TypeError("clients_factory must return StructuredModelClients")
    try:
        run = await assessment.invoke(clients, prompt)
    finally:
        await clients.close()
    refs = []
    with assessment._store.read() as db:
        for event, in db.execute("SELECT payload FROM events ORDER BY id"):
            parsed = json.loads(event)
            if parsed["type"] == "retrieval.result":
                refs.extend(parsed["data"]["source_refs"])
    return {"final_text": run.get("answer"), "run": run, "source_refs": refs,
            "evidence_directory": str(assessment.path), "assessment_id": assessment.id}
