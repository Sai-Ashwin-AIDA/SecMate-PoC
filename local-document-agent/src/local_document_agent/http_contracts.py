"""Versioned strict HTTP envelopes; no configuration or inference on import."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from .context import Source
from .contracts import CreateData, Digest, StrictModel

CONTRACT_VERSION = "secmate-agent-http-v1"
ADAPTER_VERSION = "0.1.0"
BODY_LIMIT = 32 * 1024
RUN_CAPACITY = 32
SHUTDOWN_SECONDS = 10
CanonicalID = Annotated[str, Field(
    min_length=36, max_length=36,
    pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
)]
State = Literal["accepted", "running", "completed", "failed", "limited", "cancelled"]
TerminalState = Literal["completed", "failed", "limited", "cancelled"]


def canonical_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


class RunRequest(StrictModel):
    contract_version: Literal["secmate-agent-http-v1"]
    adapter_instance_id: CanonicalID
    submission_id: CanonicalID
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def exact_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nonblank input required.")
        value.encode("utf-8", errors="strict")
        return value


class SafeError(StrictModel):
    code: str = Field(max_length=64)
    message: str = Field(max_length=300)


class ErrorEnvelope(StrictModel):
    contract_version: Literal["secmate-agent-http-v1"] = CONTRACT_VERSION
    error: SafeError


class Limits(StrictModel):
    message_characters: int = 4000
    request_body_bytes: int = BODY_LIMIT
    execution_slots: int = 1
    retained_runs: int = RUN_CAPACITY
    shutdown_seconds: int = SHUTDOWN_SECONDS
    request_timeout_seconds: int
    turn_timeout_seconds: int
    max_model_calls_per_turn: int
    max_tool_calls_per_turn: int
    max_output_tokens: int
    context_budget_units: int
    max_turn_token_budget: int
    max_history_turns: int
    raw_input_bytes: int = 256 * 1024
    extracted_text_bytes: int = 256 * 1024
    read_page_lines: int = 200
    read_page_characters: int = 12000
    search_entries: int = 1000
    search_depth: int = 8
    search_seconds: int = 5
    search_aggregate_bytes: int = 16 * 1024 * 1024
    search_returned_hits: int = 20
    create_content_characters: int = 24000
    create_framed_bytes: int = 64 * 1024
    budget_unit_semantics: str = "Conservative serialized-byte units; not shared campaign token accounting."


class Readiness(StrictModel):
    ready: bool
    reasons: tuple[SafeError, ...] = Field(max_length=8)


class Identity(StrictModel):
    configured_provider: str = "OpenRouter"
    configured_model: str
    observed_provider: None = None
    observed_model: None = None
    observation: str = "Unavailable from the current TurnResult; configured identity is unverified."


class Capability(StrictModel):
    tool: Literal["search_documents", "read_document", "create_document"]
    effect: str
    file_types: tuple[str, ...]
    logical_scope: str


class Coverage(StrictModel):
    supplied: tuple[str, ...] = (
        "Observed source/file provenance", "Sanitized tool summaries",
    )
    unavailable: tuple[str, ...] = (
        "Full call arguments", "All model-call usage", "Complete authorization traces",
        "Streaming events", "Observed model/provider identity",
    )


class Metadata(StrictModel):
    contract_version: Literal["secmate-agent-http-v1"] = CONTRACT_VERSION
    agent_kind: Literal["local-document-agent"] = "local-document-agent"
    display_name: str = "Local Document Agent (Harbor)"
    application_version: str
    adapter_version: str = ADAPTER_VERSION
    adapter_instance_id: CanonicalID
    identity: Identity
    readiness: Readiness
    capabilities: tuple[Capability, ...]
    session_semantics: str = "Fresh assistant/session per run; one execution slot; shared create-only output."
    limits: Limits
    observation_coverage: Coverage = Coverage()


class Activity(StrictModel):
    name: str = Field(max_length=128)
    status: str = Field(max_length=16)
    summary: str = Field(max_length=300)


class ObservedResult(StrictModel):
    session_id: str
    status: TerminalState
    answer: str
    answer_sha256: Digest
    sources: tuple[Source, ...] = Field(max_length=32)
    retained_sources: tuple[Source, ...] = Field(max_length=192)
    created_files: tuple[CreateData, ...] = Field(max_length=32)
    uncertain_outputs: tuple[str, ...] = Field(max_length=32)
    tool_events: tuple[Activity, ...] = Field(max_length=20)
    unverified_source_ids: tuple[str, ...]
    error: SafeError | None
    observed_model: None = None
    observed_provider: None = None
    model_call_usage: None = None


class Acknowledgement(StrictModel):
    contract_version: Literal["secmate-agent-http-v1"] = CONTRACT_VERSION
    adapter_instance_id: CanonicalID
    run_id: CanonicalID
    submission_id: CanonicalID
    request_sha256: Digest
    accepted_at: str
    state: State
    status_path: str
    cancel_path: str


class RunSnapshot(Acknowledgement):
    started_at: str | None
    finished_at: str | None
    elapsed_seconds: float | None
    cancel_requested: bool
    cleanup_status: Literal["pending", "closed", "failed", "unknown"]
    disposition: Literal["in_progress", "settled", "unknown"]
    tool_events: tuple[Activity, ...] = Field(max_length=20)
    result: ObservedResult | None
    adapter_error: SafeError | None
    limits: Limits


class Cancellation(StrictModel):
    adapter_instance_id: CanonicalID
    run_id: CanonicalID
    state: State
    cancel_requested: bool
