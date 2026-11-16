"""Complete synthetic DTOs. These are not Microsoft/ConnectorMate wire schemas."""
from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from ..contracts import Budget, EvidenceEvent, FaultPlan, StrictModel

VERSION = "0.2.0"
MAIL = "secmate.search_mail"
TEAMS = "secmate.read_teams"
DIRECTORY = "secmate.search_directory"
PROPOSE = "secmate.propose_message"
DECIDE = "secmate.action.decide"
ID = Annotated[StrictStr, Field(min_length=1, max_length=128)]
SHA = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
UTC = Annotated[StrictStr, Field(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")]
Cursor = Annotated[StrictStr, Field(min_length=1, max_length=65536)]
Recipients = Annotated[list[ID], Field(min_length=1, max_length=4)]
Channel = Literal["mail", "teams"]
ApprovalStatus = Literal["pending", "expired", "superseded", "approved", "rejected"]
ExecutionStatus = Literal["prepared", "invoking", "succeeded", "failed", "outcome_unknown"]
ErrorCode = Literal[
    "invalid_arguments", "invalid_cursor", "resource_unavailable", "ambiguous_recipient",
    "capability_disabled", "budget_exhausted", "tool_failed", "tool_timeout",
    "unsupported_write_batch", "write_not_staged", "preflight_failed", "outcome_unknown",
    "unknown_tool", "not_run", "error_streak_exhausted", "call_batch_limit",
    "tool_output_limit_exceeded",
]


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


class CommunicationBudget(Budget):
    profile_id: StrictStr = "communication-small-0.2.0"
    fake_provider_read: Annotated[StrictInt, Field(ge=1, le=64)] = 8


class CommunicationFaults(FaultPlan):
    directory_unavailable: StrictBool = False
    preparation_failure: StrictBool = False
    preflight_failure: StrictBool = False
    dispatch_failure: StrictBool = False
    receipt_loss: StrictBool = False
    cancel_before_dispatch: StrictBool = False
    cancel_after_commit: StrictBool = False
    decision_duration: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0


class SearchMail(StrictModel):
    query: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    limit: Annotated[StrictInt, Field(ge=1, le=20)]
    cursor: Cursor | None


class ReadTeams(StrictModel):
    space_id: ID
    query: Annotated[StrictStr, Field(max_length=2000)]
    limit: Annotated[StrictInt, Field(ge=1, le=20)]
    cursor: Cursor | None


class SearchDirectory(StrictModel):
    query: Annotated[StrictStr, Field(min_length=1, max_length=200)]


class ProposeMessage(StrictModel):
    channel: Channel
    recipient_ids: Recipients
    subject: Annotated[StrictStr, Field(min_length=1, max_length=240)] | None
    body: Annotated[StrictStr, Field(min_length=1, max_length=8000)]

    @field_validator("subject", "body", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def channel_fields(self):
        if len(set(self.recipient_ids)) != len(self.recipient_ids):
            raise ValueError("duplicate_recipient")
        if self.channel == "mail" and self.subject is None:
            raise ValueError("mail_subject_required")
        if self.channel == "teams" and (self.subject is not None or len(self.recipient_ids) != 1):
            raise ValueError("invalid_teams_shape")
        return self


class ActionDecision(StrictModel):
    approval_id: ID
    decision: Literal["approve", "reject", "review"]


class SourceRef(StrictModel):
    resource_id: ID
    source_kind: Literal["synthetic_mail", "synthetic_teams", "conversation_snapshot"]
    content_digest: SHA


class MailItem(StrictModel):
    id: ID
    subject: Annotated[StrictStr, Field(max_length=240)]
    body: Annotated[StrictStr, Field(max_length=12000)]
    source_ref: SourceRef


class TeamsItem(StrictModel):
    id: ID
    thread_id: ID
    body: Annotated[StrictStr, Field(max_length=12000)]
    source_ref: SourceRef


class MailPage(StrictModel):
    items: list[MailItem]
    next_cursor: Cursor | None
    truncated: StrictBool


class TeamsPage(StrictModel):
    items: list[TeamsItem]
    next_cursor: Cursor | None
    truncated: StrictBool


class DirectoryMatch(StrictModel):
    person_id: ID
    display_name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    address: Annotated[StrictStr, Field(min_length=1, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.invalid$")]


class DirectoryResult(StrictModel):
    matches: list[DirectoryMatch]
    resolution: Literal["exact", "ambiguous", "none"]


class Staged(StrictModel):
    status: Literal["staged_for_approval"]
    approval_id: ID
    summary: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    expires_at: UTC


class Review(ProposeMessage):
    prepared_digest: SHA


class Receipt(StrictModel):
    effect_id: ID
    channel: Channel
    recipient_ids: Recipients
    completed_at: UTC


class DecisionOutput(StrictModel):
    approval_id: ID
    approval_status: ApprovalStatus
    execution_id: ID | None
    execution_status: ExecutionStatus | None
    review: Review
    expires_at: UTC
    receipt: Receipt | None
    error: ErrorCode | None


class ToolError(StrictModel):
    error: ErrorCode


class ToolResult(StrictModel):
    call_id: ID
    status: Literal["ok", "error", "staged", "interrupt"]
    output: dict
    source_refs: list[SourceRef]


class Event(EvidenceEvent):
    event_schema_version: Literal["0.2.0"]
    target_version: Literal["0.2.0"]
    action_id: ID | None


class Person(DirectoryMatch):
    tenant: ID
    subject: ID
    connector_owner: ID
    active: StrictBool


class MailRecord(StrictModel):
    id: ID
    owner: ID
    tenant: ID
    subject: Annotated[StrictStr, Field(max_length=240)]
    body: Annotated[StrictStr, Field(max_length=12000)]


class Space(StrictModel):
    id: ID
    tenant: ID
    members: list[ID]


class TeamsRecord(StrictModel):
    id: ID
    space_id: ID
    thread_id: ID
    body: Annotated[StrictStr, Field(max_length=12000)]


class DirectChat(Space):
    pass


class Approval(StrictModel):
    id: ID
    status: ApprovalStatus
    actor: ID
    connector_owner: ID
    tenant: ID
    conversation_id: ID
    assessment_id: ID
    state_generation: StrictInt
    originating_run_id: ID
    call_id: ID
    transformation_version: Literal["message-local-v1"]
    prepared: ProposeMessage
    prepared_digest: SHA
    recipient_digest: SHA
    content_digest: SHA
    review: Review
    recipient_snapshot: list[DirectoryMatch]
    expires_seconds: float
    expires_at: UTC
    decision_run_id: ID | None


class Dispatch(StrictModel):
    channel: Channel
    sender_id: ID
    recipients: list[DirectoryMatch]
    destination: ID
    subject: Annotated[StrictStr, Field(min_length=1, max_length=240)] | None
    body: Annotated[StrictStr, Field(min_length=1, max_length=8000)]


class Execution(StrictModel):
    id: ID
    approval_id: ID
    decision_run_id: ID
    status: ExecutionStatus
    prepared_digest: SHA
    dispatch: Dispatch | None
    dispatch_digest: SHA | None
    receipt: Receipt | None
    error: ErrorCode | None


class Effect(StrictModel):
    effect_id: ID
    execution_id: ID
    channel: Channel
    sender_id: ID
    recipient_ids: Recipients
    subject: Annotated[StrictStr, Field(min_length=1, max_length=240)] | None
    body: Annotated[StrictStr, Field(min_length=1, max_length=8000)]
    prepared_digest: SHA
    dispatch_digest: SHA
    committed_at: UTC


INPUTS = {MAIL: SearchMail, TEAMS: ReadTeams, DIRECTORY: SearchDirectory, PROPOSE: ProposeMessage}
OUTPUTS = {MAIL: MailPage, TEAMS: TeamsPage, DIRECTORY: DirectoryResult, PROPOSE: Staged}
