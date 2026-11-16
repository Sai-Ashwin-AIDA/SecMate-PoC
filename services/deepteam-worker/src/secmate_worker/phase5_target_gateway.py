from __future__ import annotations

import json
import time
from tempfile import TemporaryDirectory

from deepeval.test_case import ToolCall
from deepteam.test_case import RTTurn

from .contracts import (
    ConversationTurn,
    InterceptionDecision,
    Phase5TargetEvidence,
    Phase5ToolEvidence,
    ToolAttempt,
    ToolCategory,
    TrustedAuthorizationContext,
)
from .model_clients import StructuredModelClients
from .model_profiles import OPENROUTER_NEMOTRON_TARGET
from .synthetic_chatmate.model_phase5.onboarding import (
    DEEPTEAM_EXECUTION_PROFILE_ID,
    DEEPTEAM_EXECUTION_PROFILE_VERSION,
    ONBOARDING_BINDING_VERSION,
    TARGET_ID,
    TARGET_VERSION,
)
from .synthetic_chatmate.model_phase5.runtime import ModelPhase5Target, PROFILE_BUDGETS
from .synthetic_chatmate.model_phase5.adapter import ADAPTER_VERSION
from .synthetic_chatmate.communication.contracts import PROPOSE
from .synthetic_chatmate.calendar_phase3.contracts import PROPOSE_MEETING
from .synthetic_chatmate.contracts import SyntheticError, clone


class Phase5TargetFailure(RuntimeError):
    def __init__(self, evidence: Phase5TargetEvidence):
        super().__init__(f"Fresh ChatMate target failed: {evidence.terminal_reason or evidence.status}")
        self.evidence = evidence


class Phase5TargetGateway:
    """One authoritative linear conversation and target budget per attack path."""

    def __init__(self, clients: StructuredModelClients, path_id: str):
        self.clients = clients
        self.path_id = path_id
        self.turns: list[ConversationTurn] = []
        self.oracle_results = []
        self.phase5_assessments: list[Phase5TargetEvidence] = []
        self.retrieval_redactions = {}
        self._temporary = TemporaryDirectory(prefix="secmate-phase5-")
        self._target: ModelPhase5Target | None = None
        self._target_attempts = 0
        self._target_tokens = 0
        self._started_at = time.monotonic()
        self._responses: list[RTTurn] = []
        self._pending_assessments = {}

    def close(self) -> None:
        self._temporary.cleanup()

    async def invoke(self, probe: str, turns=None) -> RTTurn:
        self._validate_history(probe, turns)
        if (self._target_attempts >= PROFILE_BUDGETS["provider_attempt_limit"]
                or self._target_tokens >= PROFILE_BUDGETS["provider_token_limit"]):
            raise Phase5TargetFailure(self._failure_evidence("target_budget_exhausted"))
        target_deadline = PROFILE_BUDGETS["real_deadline_seconds"] - (time.monotonic() - self._started_at)
        if target_deadline <= 0:
            raise Phase5TargetFailure(self._failure_evidence("target_deadline_exhausted"))
        if self._target is None:
            self._target = ModelPhase5Target(self._temporary.name, deepteam_onboarding=True)
        assessment = self._target.fresh()
        turn_id = f"{self.path_id}-turn-{len(self.turns) + 1}"
        trusted_history = [
            message
            for turn in self.turns
            for message in (
                {"role": "user", "content": turn.probe},
                {"role": "assistant", "content": turn.target_response},
            )
        ]
        run = await assessment.invoke(self.clients, probe, close_client=False,
            target_attempt_limit=PROFILE_BUDGETS["provider_attempt_limit"] - self._target_attempts,
            target_token_limit=PROFILE_BUDGETS["provider_token_limit"] - self._target_tokens,
            target_deadline_seconds=target_deadline,
            trusted_conversation_history=trusted_history)
        events = assessment.events(assessment.session)
        evidence = self._evidence(assessment, run, events, turn_id=turn_id)
        self.phase5_assessments.append(evidence)
        self._target_attempts += evidence.provider_attempts
        self._target_tokens += evidence.target_tokens
        if run.get("status") != "completed" or not isinstance(run.get("answer"), str) or not run["answer"].strip():
            raise Phase5TargetFailure(evidence)
        with assessment._store.read() as db:
            for payload, in db.execute("SELECT payload FROM approvals"):
                approval = json.loads(payload)
                if approval["status"] == "pending":
                    self._pending_assessments[approval["id"]] = assessment

        tool_attempts = self._tool_attempts(turn_id, events)
        turn = ConversationTurn(
            turn_id=turn_id,
            turn_number=len(self.turns) + 1,
            probe=probe,
            target_response=run["answer"],
            tool_attempts=tool_attempts,
            latency_ms=sum(
                int((item.get("data") or {}).get("latency_ms") or 0)
                for item in events if item.get("type") == "model.attempt_accepted"
            ),
            usage=None,
        )
        self.turns.append(turn)
        response = RTTurn(
            role="assistant",
            content=run["answer"],
            tools_called=[
                ToolCall(name=item.tool_name, input_parameters=item.redacted_arguments, output=item.simulated_result)
                for item in tool_attempts
            ] or None,
            additional_metadata={
                "secmate_turn_id": turn_id,
                "phase5_assessment_id": assessment.id,
                "target_profile_id": TARGET_ID,
                "target_version": TARGET_VERSION,
            },
        )
        self._responses.append(response.model_copy(deep=True))
        return response

    def review(self, approval_id: str) -> dict:
        """Return a copy of retained trusted review state, never mutable storage."""
        assessment = self._pending_assessments.get(approval_id)
        if assessment is None:
            raise SyntheticError("resource_unavailable")
        with assessment._store.read() as db:
            approval = assessment._store.approval(db, approval_id)
        if approval is None:
            raise SyntheticError("resource_unavailable")
        return clone({
            "approval_id": approval["id"], "approval_status": approval["status"],
            "action_kind": approval["action_kind"], "review": approval["review"],
            "expires_at": approval["expires_at"],
        })

    def submit_decision(self, approval_id: str, decision: str) -> dict:
        """Apply a trusted host decision using only identity retained by the gateway."""
        assessment = self._pending_assessments.get(approval_id)
        if assessment is None:
            raise SyntheticError("resource_unavailable")
        with assessment._store.read() as db:
            approval = assessment._store.approval(db, approval_id)
        if approval is None:
            raise SyntheticError("resource_unavailable")
        saved = assessment.submit_decision(
            assessment.session,
            {"approval_id": approval_id, "decision": decision},
            conversation_id=approval["conversation_id"],
        )
        lease = assessment.acquire(assessment.session)
        if lease is None or lease.run_id != saved["id"]:
            raise SyntheticError("dispatch_unavailable")
        for _ in range(12):
            settled = assessment.step(lease)
            if settled["lease"] is None:
                self._pending_assessments.pop(approval_id, None)
                return clone(settled["decision_result"])
        raise SyntheticError("model_timeout")

    def _validate_history(self, probe: str, turns) -> None:
        if not isinstance(probe, str) or not probe.strip():
            raise Phase5TargetFailure(self._failure_evidence("malformed_conversation_history"))
        if turns is None:
            if self.turns:
                raise Phase5TargetFailure(self._failure_evidence("conversation_history_missing"))
            return
        if not isinstance(turns, (list, tuple)):
            raise Phase5TargetFailure(self._failure_evidence("malformed_conversation_history"))
        expected = []
        for recorded, response in zip(self.turns, self._responses, strict=True):
            expected.extend([
                ("user", recorded.probe, None),
                ("assistant", recorded.target_response, response),
            ])
        supplied = list(turns)
        allowed_lengths = {len(expected)}
        if supplied and len(supplied) == len(expected) + 1:
            allowed_lengths.add(len(expected) + 1)
        if len(supplied) not in allowed_lengths:
            raise Phase5TargetFailure(self._failure_evidence("conversation_history_diverged"))
        if len(supplied) == len(expected) + 1:
            expected.append(("user", probe, None))
        for supplied_turn, (role, content, response) in zip(supplied, expected, strict=True):
            if (
                not isinstance(supplied_turn, RTTurn)
                or supplied_turn.role != role
                or supplied_turn.content != content
                or supplied_turn.user_id is not None
                or supplied_turn.mcp_tools_called is not None
                or supplied_turn.mcp_resources_called is not None
                or supplied_turn.mcp_prompts_called is not None
            ):
                raise Phase5TargetFailure(self._failure_evidence("conversation_history_diverged"))
            if role == "user" and any((
                supplied_turn.retrieval_context is not None,
                supplied_turn.tools_called is not None,
                supplied_turn.additional_metadata is not None,
            )):
                raise Phase5TargetFailure(self._failure_evidence("conversation_identity_injection"))
            if role == "assistant" and (
                supplied_turn.retrieval_context != response.retrieval_context
                or supplied_turn.tools_called != response.tools_called
                or supplied_turn.additional_metadata != response.additional_metadata
            ):
                raise Phase5TargetFailure(self._failure_evidence("conversation_history_diverged"))

    def _failure_evidence(self, reason: str) -> Phase5TargetEvidence:
        return Phase5TargetEvidence(
            evidence_id=f"{self.path_id}-phase5-unstarted",
            parent_path_id=self.path_id,
            target_id=TARGET_ID,
            target_version=TARGET_VERSION,
            onboarding_binding_version=ONBOARDING_BINDING_VERSION,
            assessment_id=f"unstarted-{self.path_id}",
            target_run_id=f"unstarted-{self.path_id}",
            status="failed",
            terminal_reason=reason,
            model_profile_id=OPENROUTER_NEMOTRON_TARGET.profile_id,
            provider=OPENROUTER_NEMOTRON_TARGET.provider,
            model=OPENROUTER_NEMOTRON_TARGET.model,
            provider_attempts=0,
            target_tokens=0,
            logical_turns=0,
            answer_present=False,
            evidence_gaps=[reason],
        )

    def _evidence(self, assessment, run: dict, events: list[dict], *, turn_id: str) -> Phase5TargetEvidence:
        with assessment._store.read() as db:
            attempts = [
                {"status": status, **json.loads(payload)}
                for status, payload in db.execute("SELECT status,payload FROM phase5_attempts ORDER BY id")
            ]
        provider_events = [event for attempt in attempts for event in attempt.get("provider_attempts", [])]
        tokens = sum(
            ((event.get("usage") or {}).get("total_tokens")
             if (event.get("usage") or {}).get("total_tokens") is not None
             else event.get("estimated_tokens") or 0)
            for event in provider_events
        )
        requested = [event for event in events if event.get("type") == "tool.requested"]
        tools = []
        for event in requested:
            call_id = event.get("call_id")
            correlated = [item for item in events if item.get("call_id") == call_id]
            by_type = {item["type"]: item for item in correlated}
            result = by_type.get("retrieval.result")
            authorization = by_type.get("tool.authorized")
            validation = by_type.get("tool.validated") or by_type.get("tool.validation_rejected")
            denied = by_type.get("tool.authorization_rejected")
            dispatch = by_type.get("tool.dispatched")
            tool_result = by_type.get("tool.result")
            result_envelope = (tool_result or {}).get("data", {}).get("result")
            call = next((call for attempt in attempts for call in ((attempt.get("response") or {}).get("calls") or [])
                         if call.get("call_id") == call_id), {})
            replay = call.get("replay") or {}
            function = replay.get("function") if isinstance(replay, dict) else None
            arguments = event.get("data", {}).get("arguments", {})
            if isinstance(arguments, str):
                try: arguments = json.loads(arguments)
                except ValueError: arguments = {}
            tools.append(Phase5ToolEvidence(
                evidence_id=f"{run['id']}-phase5-tool-{len(tools) + 1}",
                call_id=call_id,
                tool_name=event["data"]["name"],
                provider_tool_name=function.get("name") if isinstance(function, dict) else None,
                proposed_arguments=arguments,
                requested_event_id=event["event_id"],
                validation_status="REJECTED" if validation and validation["type"] == "tool.validation_rejected" else "VALIDATED" if validation else "UNAVAILABLE",
                validation_code=(validation or {}).get("data", {}).get("code"),
                authorized_event_id=(by_type.get("tool.authorized") or {}).get("event_id"),
                authorization_status="ALLOWED" if authorization else "DENIED" if denied else "UNAVAILABLE",
                authorization_code=(authorization or denied or {}).get("data", {}).get("code"),
                dispatched_event_id=(dispatch or {}).get("event_id"),
                dispatch_destination=(dispatch or {}).get("data", {}).get("destination"),
                result_event_id=(result or tool_result or {}).get("event_id"),
                result_status=(result_envelope or {}).get("status", "ok" if result else "unavailable"),
                result_output=(result_envelope or {}).get("output") or (result or {}).get("data", {}).get("output"),
                execution_error=((result_envelope or {}).get("output") or {}).get("error") if isinstance((result_envelope or {}).get("output"), dict) else None,
                authorization=(authorization or denied or {}).get("data"),
                source_refs=(result_envelope or {}).get("source_refs") or (result or {}).get("data", {}).get("source_refs", []),
            ))
        accepted = [item for item in attempts if item.get("status") == "accepted"]
        request_history = [{"turn": item["turn"], "attempt": item["attempt"],
            "request_digest": item["request_digest"], "rendered_payload_digest": item["rendered_payload_digest"],
            "roles": [message.get("role") for message in item["rendered_payload"]["messages"]],
            "response": item.get("response"), "error_code": item.get("error_code")}
            for item in attempts]
        gaps = []
        if not provider_events: gaps.append("provider_attempt_metadata_unavailable")
        if not run.get("answer"): gaps.append("final_response_absent")
        return Phase5TargetEvidence(
            evidence_id=f"{run['id']}-phase5-assessment",
            parent_path_id=self.path_id,
            parent_turn_id=turn_id if run.get("status") == "completed" and run.get("answer") else None,
            turn_binding_version=(
                "phase5-turn-binding-v1"
                if run.get("status") == "completed" and run.get("answer")
                else None
            ),
            target_id=TARGET_ID,
            target_version=TARGET_VERSION,
            onboarding_binding_version=ONBOARDING_BINDING_VERSION,
            assessment_id=assessment.id,
            target_run_id=run["id"],
            status=run.get("status", "failed"),
            terminal_reason=run.get("terminal_reason"),
            model_profile_id=OPENROUTER_NEMOTRON_TARGET.profile_id,
            provider=OPENROUTER_NEMOTRON_TARGET.provider,
            model=OPENROUTER_NEMOTRON_TARGET.model,
            provider_attempts=min(PROFILE_BUDGETS["provider_attempt_limit"], len(provider_events)),
            target_tokens=min(PROFILE_BUDGETS["provider_token_limit"], tokens),
            logical_turns=len(accepted),
            answer_present=bool(run.get("answer")),
            tools=tools,
            request_history=request_history,
            provider_attempt_metadata=provider_events,
            target_budget=assessment._budget_snapshot,
            binding_metadata={
                **assessment._binding,
                "adapter_version": ADAPTER_VERSION,
                "execution_profile_id": DEEPTEAM_EXECUTION_PROFILE_ID,
                "execution_profile_version": DEEPTEAM_EXECUTION_PROFILE_VERSION,
            },
            evidence_gaps=gaps,
            duration_ms=sum(int(event.get("latency_ms") or 0) for event in provider_events),
            response_model_verified=bool(provider_events),
        )

    @staticmethod
    def _tool_attempts(turn_id: str, events: list[dict]) -> list[ToolAttempt]:
        attempts = []
        for index, requested in enumerate((item for item in events if item.get("type") == "tool.requested"), 1):
            call_id = requested["call_id"]
            correlated = [item for item in events if item.get("call_id") == call_id]
            result = next((item for item in correlated if item.get("type") == "tool.result"), None)
            arguments = requested.get("data", {}).get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            proposal = requested["data"]["name"] in {PROPOSE, PROPOSE_MEETING}
            attempts.append(ToolAttempt(
                evidence_id=f"{turn_id}-phase5-tool-{index}",
                tool_name=requested["data"]["name"],
                tool_version=TARGET_VERSION,
                category=ToolCategory.MUTATION if proposal else ToolCategory.READ_ONLY,
                original_arguments=arguments,
                redacted_arguments=arguments,
                authorization=TrustedAuthorizationContext(
                    caller_role="SYNTHETIC_CHATMATE_SUBJECT",
                    approval_source="NONE",
                    approval_valid=False,
                ),
                destination=f"synthetic://chatmate/{requested['data']['name']}",
                decision=InterceptionDecision.INTERCEPTED_NOT_EXECUTED if proposal else InterceptionDecision.SIMULATED,
                simulated_result=(result or {}).get("data", {}).get("result"),
            ))
        return attempts
