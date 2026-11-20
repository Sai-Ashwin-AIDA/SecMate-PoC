"""Authenticated single-loop/single-slot adapter around the unchanged core."""

import asyncio
import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from .agent import DocumentAssistant, ToolActivity, TurnResult
from .http_config import AdapterSettings
from .http_contracts import (
    Acknowledgement, Activity, BODY_LIMIT, CONTRACT_VERSION, Cancellation, Capability,
    ErrorEnvelope, Identity, Metadata, ObservedResult, RUN_CAPACITY, RunRequest,
    RunSnapshot, SHUTDOWN_SECONDS, SafeError, canonical_id,
)
from .provider import create_provider

TERMINAL = {"completed", "failed", "limited", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def wire(model, status: int = 200) -> Response:
    return Response(model.model_dump_json().encode("utf-8"), status_code=status, media_type="application/json")


def error_response(status: int, code: str, message: str) -> Response:
    response = wire(ErrorEnvelope(error=SafeError(code=code, message=message)), status)
    if status == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


def activity(event: ToolActivity) -> Activity:
    # Unknown model-selected tool names are not trusted metadata.
    name = event.name if event.name in {"search_documents", "read_document", "create_document"} else "unknown"
    return Activity(name=name, status=event.status, summary=event.summary)


def observed(result: TurnResult) -> ObservedResult:
    return ObservedResult(
        session_id=result.session_id, status=result.status, answer=result.answer,
        answer_sha256=hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
        sources=result.sources, retained_sources=result.retained_sources,
        created_files=result.created_files, uncertain_outputs=result.uncertain_outputs,
        tool_events=tuple(activity(event) for event in result.tool_events),
        unverified_source_ids=result.unverified_source_ids,
        error=SafeError(code=result.error.code, message=result.error.message) if result.error else None,
    )


@dataclass
class Run:
    request: RunRequest
    request_sha256: str
    run_id: str = field(default_factory=lambda: str(uuid4()))
    accepted_at: str = field(default_factory=utc_now)
    state: str = "accepted"
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float | None = None
    cancel_requested: bool = False
    cleanup_status: str = "pending"
    disposition: str = "in_progress"
    tool_events: list[Activity] = field(default_factory=list)
    result: ObservedResult | None = None
    adapter_error: SafeError | None = None
    owner: asyncio.Task | None = None
    chat_task: asyncio.Task | None = None
    final_bytes: bytes | None = None


class RunManager:
    def __init__(
        self, settings: AdapterSettings, *,
        provider_factory: Callable = create_provider,
        assistant_factory: Callable = DocumentAssistant,
        diagnostics=None,
    ) -> None:
        settings.require_token()
        self.settings = settings
        self.instance_id = str(uuid4())
        self.provider_factory = provider_factory
        self.assistant_factory = assistant_factory
        self.diagnostics = diagnostics
        self.runs: dict[str, Run] = {}
        self.submissions: dict[str, Run] = {}
        self.active: Run | None = None
        self.stopping = False
        self.shutdown_timed_out = False

    def diagnostic(self, code: str) -> None:
        if self.diagnostics:
            self.diagnostics.record("shutdown" if code.startswith("SHUTDOWN") else "turn", code)

    def ack(self, run: Run) -> Acknowledgement:
        return Acknowledgement(
            adapter_instance_id=self.instance_id, run_id=run.run_id,
            submission_id=run.request.submission_id, request_sha256=run.request_sha256,
            accepted_at=run.accepted_at, state=run.state,
            status_path=f"/v1/runs/{run.run_id}", cancel_path=f"/v1/runs/{run.run_id}/cancel",
        )

    def snapshot(self, run: Run) -> bytes:
        if run.final_bytes is not None:
            return run.final_bytes
        return RunSnapshot(
            **self.ack(run).model_dump(), started_at=run.started_at,
            finished_at=run.finished_at, elapsed_seconds=run.elapsed_seconds,
            cancel_requested=run.cancel_requested, cleanup_status=run.cleanup_status,
            disposition=run.disposition, tool_events=tuple(run.tool_events),
            result=run.result, adapter_error=run.adapter_error, limits=self.settings.limits(),
        ).model_dump_json().encode("utf-8")

    def metadata(self) -> Metadata:
        return Metadata(
            application_version=version("local-document-agent"),
            adapter_instance_id=self.instance_id,
            identity=Identity(configured_model=self.settings.configuration.model),
            readiness=self.settings.readiness(), limits=self.settings.limits(),
            capabilities=(
                Capability(tool="search_documents", effect="Read-only discovery; not source registration.",
                           file_types=(".txt", ".md", ".eml"), logical_scope="Harbor input"),
                Capability(tool="read_document", effect="Bounded read-only source registration.",
                           file_types=(".txt", ".md", ".eml"), logical_scope="Harbor input"),
                Capability(tool="create_document", effect="Exclusive new local file; no overwrite. Email drafts are NOT SENT.",
                           file_types=(".txt", ".md"), logical_scope="Shared create-only output"),
            ),
        )

    def submit(self, request: RunRequest) -> Response:
        # No await between identity checks, receipt creation and slot acquisition.
        if request.adapter_instance_id != self.instance_id:
            return error_response(409, "ADAPTER_INSTANCE_CHANGED", "Fetch metadata; old-instance disposition is unknown. Do not automatically resubmit.")
        digest = hashlib.sha256(request.message.encode("utf-8")).hexdigest()
        previous = self.submissions.get(request.submission_id)
        if previous:
            if previous.request_sha256 != digest:
                return error_response(409, "SUBMISSION_CONFLICT", "The submission ID is already bound to different input.")
            return wire(self.ack(previous), 202)
        if self.stopping:
            return error_response(503, "SERVICE_STOPPING", "The adapter is shutting down; no new run was accepted.")
        if len(self.runs) >= RUN_CAPACITY:
            return error_response(503, "RUN_CAPACITY_REACHED", "All 32 receipts are retained. Collect results before a deliberate restart; never automatically resubmit.")
        if self.active is not None:
            return error_response(409, "TARGET_BUSY", "The single execution slot is occupied; no run was queued.")
        readiness = self.settings.readiness()
        if not readiness.ready:
            return error_response(503, "TARGET_NOT_READY", "Inference settings, disabled tracing and valid Harbor roots are required; inspect metadata.")
        run = Run(request, digest)
        self.runs[run.run_id] = run
        self.submissions[request.submission_id] = run
        self.active = run
        run.owner = asyncio.create_task(self.execute(run))
        return wire(self.ack(run), 202)

    def cancel(self, run: Run) -> None:
        if run.state in TERMINAL or run.cancel_requested:
            return
        run.cancel_requested = True
        # Only chat receives cancellation. Provider closure is never cancelled by
        # repeated requests; the strongly referenced owner retains the slot.
        if run.chat_task is not None and not run.chat_task.done():
            run.chat_task.cancel()

    async def execute(self, run: Run) -> None:
        provider = None
        started = time.monotonic()
        run.state, run.started_at = "running", utc_now()
        try:
            configuration = self.settings.configuration
            roots = self.settings.roots()
            provider = self.provider_factory(configuration)

            def observe(event: ToolActivity) -> None:
                if len(run.tool_events) < configuration.max_tool_calls_per_turn:
                    run.tool_events.append(activity(event))

            assistant = self.assistant_factory(
                configuration, provider.model, roots=roots, observer=observe,
                diagnostics=self.diagnostics,
            )
            if run.cancel_requested:
                # No chat has begun and therefore no tool effect can exist.
                result = TurnResult(assistant.session_id, "cancelled")
            else:
                run.chat_task = asyncio.create_task(assistant.chat(run.request.message))
                try:
                    result = await run.chat_task
                except asyncio.CancelledError:
                    # Covers cancellation before the core coroutine first enters.
                    result = TurnResult(assistant.session_id, "cancelled")
            run.result = observed(result)
        except Exception:
            run.adapter_error = SafeError(code="ADAPTER_RUN_ERROR", message="The accepted run failed at the adapter boundary; no retry was made.")
            self.diagnostic("ADAPTER_RUN_ERROR")
        finally:
            if provider is not None:
                try:
                    await provider.aclose()
                    run.cleanup_status = "closed"
                except Exception:
                    run.cleanup_status = "failed"
                    run.adapter_error = SafeError(code="PROVIDER_CLOSE_ERROR", message="Provider cleanup failed; closure is not confirmed. Observed effects remain.")
                    self.diagnostic("PROVIDER_CLOSE_ERROR")
            else:
                run.cleanup_status = "closed"  # No resource was returned to own.
            run.state = "failed" if run.adapter_error else run.result.status
            run.finished_at = utc_now()
            run.elapsed_seconds = float(time.monotonic() - started)
            run.disposition = "settled"
            run.final_bytes = self.snapshot(run)
            # Retain only receipts/results, not user messages after settlement.
            run.request = run.request.model_copy(update={"message": ""})
            if run.cleanup_status == "closed":
                self.active = None

    async def shutdown(self) -> None:
        self.stopping = True
        run = self.active
        if run is None or run.owner is None:
            return
        self.cancel(run)
        done, _ = await asyncio.wait({run.owner}, timeout=SHUTDOWN_SECONDS)
        if not done:
            self.shutdown_timed_out = True
            run.cleanup_status = "unknown"
            run.disposition = "unknown"
            run.adapter_error = SafeError(
                code="SHUTDOWN_TIMEOUT",
                message="Cooperative shutdown deadline expired; execution/cleanup disposition is unknown. File effects are not rolled back.",
            )
            self.diagnostic("SHUTDOWN_TIMEOUT")


class Authentication:
    """Authenticate before reading any body, including unknown routes."""

    def __init__(self, app, token: bytes):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            values = [value for key, value in scope["headers"] if key.lower() == b"authorization"]
            if len(values) != 1 or not hmac.compare_digest(values[0], b"Bearer " + self.token):
                await error_response(401, "UNAUTHORIZED", "A valid adapter bearer token is required.")(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(
    settings: AdapterSettings, *, provider_factory: Callable = create_provider,
    assistant_factory: Callable = DocumentAssistant, diagnostics=None,
) -> FastAPI:
    """Trusted injection only; never load environment or construct a provider here."""
    manager = RunManager(
        settings, provider_factory=provider_factory,
        assistant_factory=assistant_factory, diagnostics=diagnostics,
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        await manager.shutdown()

    app = FastAPI(
        lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None,
        redirect_slashes=False,
    )
    app.state.runs = manager
    app.add_middleware(Authentication, token=settings.token.get_secret_value().encode("ascii"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exception):
        return error_response(422, "INVALID_REQUEST", "The request must match the strict wire contract.")

    @app.exception_handler(HTTPException)
    async def http_error(request, exception):
        return error_response(exception.status_code, "NOT_FOUND" if exception.status_code == 404 else "HTTP_ERROR", "The requested HTTP operation is unavailable.")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exception):
        manager.diagnostic("ADAPTER_HTTP_ERROR")
        return error_response(500, "ADAPTER_HTTP_ERROR", "An internal adapter operation failed.")

    @app.get("/v1/metadata")
    async def metadata():
        return wire(manager.metadata())

    @app.post("/v1/runs")
    async def submit(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > BODY_LIMIT:
                return error_response(413, "BODY_TOO_LARGE", "The request body exceeds 32 KiB.")
            body.extend(chunk)
        try:
            # Decode explicitly: no BOM/UTF-16 guessing or non-UTF-8 bodies.
            value = json.loads(body.decode("utf-8"))
            parsed = RunRequest.model_validate(value, strict=True)
        except (ValueError, UnicodeError, ValidationError, RecursionError):
            return error_response(422, "INVALID_REQUEST", "The request must match the strict UTF-8 wire contract.")
        return manager.submit(parsed)

    def find(run_id: str) -> Run | None:
        return manager.runs.get(run_id) if canonical_id(run_id) else None

    @app.get("/v1/runs/{run_id}")
    async def status(run_id: str):
        run = find(run_id)
        if run is None:
            return error_response(404, "RUN_NOT_FOUND", "No run with that ID exists in this adapter instance.")
        return Response(manager.snapshot(run), media_type="application/json")

    @app.post("/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        run = find(run_id)
        if run is None:
            return error_response(404, "RUN_NOT_FOUND", "No run with that ID exists in this adapter instance.")
        manager.cancel(run)
        return wire(Cancellation(
            adapter_instance_id=manager.instance_id, run_id=run.run_id,
            state=run.state, cancel_requested=run.cancel_requested,
        ))

    return app
