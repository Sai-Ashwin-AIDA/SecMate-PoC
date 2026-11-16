from __future__ import annotations

import json
import hashlib
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from . import jobs
from .config import API_ROOT, DATA_ROOT
from .contracts import SyntheticChatMateSmokeEvidence, SyntheticChatMateSmokeRun
from .run_store import RunStore, RunStoreError

WORKSPACE_ROOT = API_ROOT.parents[1]
WORKER_ROOT = WORKSPACE_ROOT / "services" / "deepteam-worker"
WORKER_PYTHON = WORKER_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
RUN_ROOT = DATA_ROOT / "synthetic-chatmate-smoke-runs"
RUN_LOCK = DATA_ROOT / "deepteam-runs" / "active-run.lock"
REPORT_NAME = "demo.json"
REQUEST_TEXT = "Summarize my fictional lunch-planning mail."
WORKER_TIMEOUT_SECONDS = 130

_runs: dict[str, SyntheticChatMateSmokeRun] = {}
_processes: dict[str, subprocess.Popen[str]] = {}
_lock = threading.RLock()


class SyntheticChatMateSmokeError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worker_environment() -> dict[str, str]:
    environment = {
        name: os.environ[name]
        for name in ("APPDATA", "LOCALAPPDATA", "PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "WINDIR")
        if os.environ.get(name)
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def load_records() -> None:
    records = RunStore(RUN_ROOT).records()
    loaded = {}
    for run_id, payload in records.items():
        try:
            loaded[run_id] = SyntheticChatMateSmokeRun.model_validate(payload)
        except ValidationError as error:
            raise RunStoreError("Synthetic ChatMate smoke history failed validation.") from error
    with _lock:
        _runs.clear()
        _runs.update(loaded)


def get_run(run_id: str) -> SyntheticChatMateSmokeRun | None:
    with _lock:
        return _runs.get(run_id)


def list_runs(limit: int = 100) -> list[SyntheticChatMateSmokeRun]:
    with _lock:
        return sorted(_runs.values(), key=lambda item: item.created_at, reverse=True)[:limit]


def snapshot_runs() -> list[SyntheticChatMateSmokeRun]:
    """Copy every retained smoke record without touching durable state."""
    with _lock:
        return [record.model_copy(deep=True) for record in _runs.values()]


def _persist(record: SyntheticChatMateSmokeRun, evidence: SyntheticChatMateSmokeEvidence | None = None) -> None:
    payload = record.model_dump(mode="json")
    bundle = (f"{record.run_id}/{REPORT_NAME}", evidence.model_dump(mode="json")) if evidence else None
    jobs.persist(RunStore(RUN_ROOT), RUN_LOCK, payload, bundle)
    _runs[record.run_id] = record


def _load_json(path: Path):
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise SyntheticChatMateSmokeError("Required Phase5 evidence is absent or oversized.")
    return json.loads(path.read_text(encoding="utf-8"))


def _validated_evidence(output: Path) -> SyntheticChatMateSmokeEvidence:
    output = jobs.filesystem_path(output)
    meta = _load_json(output / "demo.json")
    verification = _load_json(output / "verification.json")
    if not isinstance(meta, dict) or not isinstance(verification, dict):
        raise SyntheticChatMateSmokeError("Phase5 evidence objects are invalid.")
    assessment_id = meta.get("assessment_id")
    if not isinstance(assessment_id, str) or not assessment_id:
        raise SyntheticChatMateSmokeError("Phase5 assessment identity is invalid.")
    evidence_directory = output / "targets" / "secmate.synthetic-chatmate.fresh.v1" / "0.5.0" / "assessments" / assessment_id
    final = _load_json(evidence_directory / "final-output.json")
    events = _load_json(evidence_directory / "events.json")
    if not all(isinstance(value, dict) for value in (meta, verification, final)):
        raise SyntheticChatMateSmokeError("Phase5 evidence objects are invalid.")
    if not isinstance(events, list) or any(not isinstance(event, dict) or not isinstance(event.get("data"), dict) for event in events):
        raise SyntheticChatMateSmokeError("Phase5 event envelopes are invalid.")
    expected_meta = {
        "target_id": "secmate.synthetic-chatmate.fresh.v1", "target_version": "0.5.0",
        "model_mode": "openrouter_nemotron", "compatibility_claim": "OpenRouter/Nemotron-profile-shaped and mock-verified",
        "live_call_performed": False,
    }
    if any(meta.get(name) != value for name, value in expected_meta.items()):
        raise SyntheticChatMateSmokeError("Phase5 mock/live provenance is invalid.")
    expected_verification = {"assessment_id": assessment_id, "version": "0.5.0", "sqlite_read_only": True,
        "logical_turns": 2, "authorized_reads": 1, "fake_writes": 0, "fake_effects": 0,
        "model_tools": 7, "mock_verified": True}
    expected_verification["terminal_status"] = "completed"
    if any(verification.get(name) != value for name, value in expected_verification.items()):
        raise SyntheticChatMateSmokeError("Phase5 read-only reconciliation is invalid.")
    if any(final.get(name) != value for name, value in {"logical_turns": 2, "model_mode": "openrouter_nemotron", "mock_verified": True}.items()):
        raise SyntheticChatMateSmokeError("Phase5 final output binding is invalid.")
    requested = [event for event in events if event.get("type") == "tool.requested"]
    if len(requested) != 1 or not isinstance(final.get("final_text"), str) or not final["final_text"].strip():
        raise SyntheticChatMateSmokeError("Phase5 completion evidence is incomplete.")
    tool = requested[0]
    arguments = tool.get("data", {}).get("arguments")
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise SyntheticChatMateSmokeError("Phase5 tool arguments are invalid.")
    artifacts = {}
    for path in output.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
            raise SyntheticChatMateSmokeError("Phase5 evidence contains an unsafe path.")
        if path.is_file():
            artifacts[path.relative_to(output).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return SyntheticChatMateSmokeEvidence.model_validate({
        "schema_version": "synthetic-chatmate-phase5-smoke-v1", "target_id": "secmate.synthetic-chatmate.fresh.v1",
        "target_version": "0.5.0", "mode": "MOCKED", "provider_profile": "openrouter-nemotron-35-super-vl-target",
        "model": "nvidia/nemotron-3.5-super-vl:free", "request_text": REQUEST_TEXT,
        "limits": {"max_model_turns": 2, "max_tool_calls": 1, "max_output_tokens_per_turn": 500,
                   "deadline_seconds": 120, "permitted_effect": "READ_ONLY_RETRIEVAL"},
        "model_turns_completed": 2, "tool_activity": [{"tool_call_id": tool.get("call_id"),
            "name": tool.get("data", {}).get("name"), "arguments": arguments, "authorization": "ALLOWED",
            "execution": "FICTIONAL_READ_COMPLETED", "source_refs": verification.get("source_refs")}],
        "final_response": final["final_text"], "terminal_outcome": "COMPLETED",
        "fake_write_count": 0, "fake_effect_count": 0, "reconciled": True,
        "artifacts_sha256": artifacts,
    })


def start_run() -> SyntheticChatMateSmokeRun:
    if not WORKER_PYTHON.exists():
        raise SyntheticChatMateSmokeError("The isolated worker environment is unavailable.")
    run_id = f"target-smoke-{uuid4().hex[:12]}"
    record = SyntheticChatMateSmokeRun(
        run_id=run_id, target_id="secmate.synthetic-chatmate.fresh.v1", target_name="Synthetic ChatMate",
        mode="MOCKED", status="QUEUED", verification="UNVERIFIED", progress=5,
        stage="Accepted; waiting for the bounded mocked worker.", created_at=_now(),
    )
    try:
        session = jobs.prepare(RUN_LOCK, run_id, "TARGET_SMOKE", RUN_ROOT)
    except FileExistsError as error:
        raise SyntheticChatMateSmokeError("Another local worker job is active or unresolved.") from error
    token = jobs._current.set(session)
    try:
        _persist(record.model_copy(update={"job_id": session.job_id}))
        jobs.claim_projection(session)
    except Exception:
        session.finish()
        raise
    finally:
        jobs._current.reset(token)
    record = _runs[run_id]
    try:
        jobs.dispatch(_execute_run, (run_id,), RUN_LOCK, f"secmate-{run_id}", thread_factory=threading.Thread)
    except Exception as error:
        _fail(run_id, "DISPATCH_FAILED", "The bounded mocked worker could not be dispatched.")
        raise SyntheticChatMateSmokeError("The bounded mocked worker could not be dispatched.") from error
    return record


@jobs.execution("TARGET_SMOKE", lambda: RUN_LOCK, lambda: RUN_ROOT, lambda: _runs)
def _execute_run(run_id: str) -> None:
    process = None
    output = RUN_ROOT / run_id / "worker-output"
    try:
        with _lock:
            current = _runs[run_id]
            if current.status == "CANCEL_REQUESTED":
                _cancelled(run_id)
                return
            updated = current.model_copy(update={"status": "RUNNING", "progress": 35,
                "stage": "Running the bounded mocked retrieval loop.", "started_at": _now()})
            _persist(updated)
        command = [str(WORKER_PYTHON), "-m", "secmate_worker.synthetic_chatmate.model_phase5",
                   "--output", str(output), "--mode", "mocked", "--tool", "secmate.search_mail",
                   "--prompt", REQUEST_TEXT]
        process = jobs.launch(command, cwd=WORKER_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=_worker_environment())
        with _lock:
            _processes[run_id] = process
        _, stderr = process.communicate(timeout=WORKER_TIMEOUT_SECONDS)
        if get_run(run_id).status == "CANCEL_REQUESTED":
            _cancelled(run_id)
            return
        if process.returncode != 0:
            raise SyntheticChatMateSmokeError("The mocked worker exited without a valid completion.")
        evidence = _validated_evidence(output)
        with _lock:
            if get_run(run_id).status == "CANCEL_REQUESTED":
                _cancelled(run_id)
                return
            completed = get_run(run_id).model_copy(update={"status": "COMPLETED", "verification": "MOCK_VERIFIED",
                "progress": 100, "stage": "Mocked retrieval protocol completed and evidence validated.",
                "completed_at": _now(), "final_response": evidence.final_response, "evidence_available": True})
            _persist(completed, evidence)
    except subprocess.TimeoutExpired:
        if process is not None:
            process.session.terminate()
        _fail(run_id, "WORKER_TIMEOUT", "The bounded mocked worker exceeded 130 seconds.")
    except (OSError, ValueError, TypeError, AttributeError, ValidationError, RunStoreError, SyntheticChatMateSmokeError):
        if get_run(run_id).status == "CANCEL_REQUESTED":
            _cancelled(run_id)
        else:
            _fail(run_id, "EVIDENCE_INVALID", "The mocked worker did not produce valid Phase5 smoke evidence.")
    finally:
        with _lock:
            if _processes.get(run_id) is process:
                _processes.pop(run_id, None)
        # Durable JobSession owns releasing the global slot and lock projection.


def _fail(run_id: str, code: str, message: str) -> None:
    with _lock:
        current = _runs.get(run_id)
        if current is None or current.status in {"COMPLETED", "CANCELLED"}:
            return
        _persist(current.model_copy(update={"status": "FAILED", "progress": 100, "stage": "Smoke test failed.",
            "completed_at": _now(), "error_code": code, "error_message": message}))


def _cancelled(run_id: str) -> SyntheticChatMateSmokeRun:
    with _lock:
        current = _runs[run_id]
        cancelled = current.model_copy(update={"status": "CANCELLED", "progress": 100,
            "stage": "Bounded smoke test cancelled.", "completed_at": _now()})
        _persist(cancelled)
        return cancelled


def cancel_run(run_id: str) -> SyntheticChatMateSmokeRun:
    with _lock:
        current = _runs.get(run_id)
        if current is None:
            raise SyntheticChatMateSmokeError("Synthetic ChatMate smoke run not found.")
        if current.status in {"CANCEL_REQUESTED", "CANCELLED"}:
            return current
        if current.status in {"COMPLETED", "FAILED"}:
            raise SyntheticChatMateSmokeError("The smoke test has already finished.")
        session = jobs.session_for(RUN_LOCK, run_id)
        if session is not None:
            session.ledger.update(session.job_id, session.token, cancel_requested=True, authorized=False,
                                  reason="OPERATOR_CANCELLED")
        requested = current.model_copy(update={"status": "CANCEL_REQUESTED", "stage": "Cancellation requested; stopping the worker."})
        _persist(requested)
        process = _processes.get(run_id)
    if process is not None:
        process.session.terminate()
    return get_run(run_id)


def get_evidence(run_id: str) -> SyntheticChatMateSmokeEvidence:
    record = get_run(run_id)
    if record is None:
        raise KeyError(run_id)
    if not record.evidence_available:
        raise SyntheticChatMateSmokeError("Validated smoke evidence is not available.")
    try:
        report = _validated_evidence(RUN_ROOT / run_id / "worker-output")
        RunStore(RUN_ROOT).verify_evidence(run_id, f"{run_id}/{REPORT_NAME}", report.model_dump(mode="json"), allow_baseline=False)
        return report
    except (OSError, ValueError, ValidationError, RunStoreError) as error:
        raise SyntheticChatMateSmokeError("Saved smoke evidence failed validation.") from error
