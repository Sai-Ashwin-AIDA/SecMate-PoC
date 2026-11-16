from __future__ import annotations

import json
import hashlib
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import API_ROOT, DATA_ROOT, Settings
from .run_store import RunStore, RunStoreError
from . import jobs
from .contracts import DeepTeamAuditReport, DeepTeamRunLog, DeepTeamRunRecord
from .deepteam_catalog import (
    DEFAULT_ATTACK_PROFILE_ID,
    DEFAULT_VULNERABILITY_PROFILE_ID,
    FRESH_ATTACK_PROFILE_ID,
    FRESH_SCENARIO_ID,
    FRESH_TARGET_PROFILE_ID,
    FRESH_BINDING_VERSION,
    FRESH_EXECUTION_PROFILE_ID,
    FRESH_EXECUTION_PROFILE_VERSION,
    FRESH_TARGET_TOKEN_LIMIT,
    get_deepteam_catalog,
    attack_profile,
    vulnerability_profile,
    fresh_selection_capability,
    target_profile,
    validate_profile_selection,
    validate_fresh_selection,
)


WORKSPACE_ROOT = API_ROOT.parents[1]
WORKER_ROOT = WORKSPACE_ROOT / "services" / "deepteam-worker"
WORKER_PYTHON = WORKER_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
RUN_ROOT = DATA_ROOT / "deepteam-runs"
RUN_LOCK = RUN_ROOT / "active-run.lock"

_runs: dict[str, DeepTeamRunRecord] = {}
_processes: dict[str, subprocess.Popen[str]] = {}
_lock = threading.Lock()

WORKER_TIMEOUT_SECONDS = 1200
TERMINATE_GRACE_SECONDS = 5
KILL_WAIT_SECONDS = 5


class DeepTeamRunError(RuntimeError):
    pass


class DeepTeamSelectionError(DeepTeamRunError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(level: str, message: str) -> DeepTeamRunLog:
    return DeepTeamRunLog(timestamp=_now(), level=level, message=message)


def start_deepteam_run(
    settings: Settings,
    attack_profile_id: str = DEFAULT_ATTACK_PROFILE_ID,
    vulnerability_profile_id: str | None = DEFAULT_VULNERABILITY_PROFILE_ID,
    max_total_tokens: int = 250_000,
    execution_mode: str = "SINGLE",
    max_paths: int = 1,
    target_profile_id: str = "synthetic-socmate-tier1",
    scenario_id: str = "socmate-tier1-permission-escalation",
) -> DeepTeamRunRecord:
    try:
        if target_profile_id == FRESH_TARGET_PROFILE_ID:
            target, selected_attack, selected_vulnerability, selection_capability = validate_fresh_selection(
                attack_profile_id, vulnerability_profile_id, target_profile_id, scenario_id, execution_mode, max_paths)
            if execution_mode == "ADAPTIVE" and not settings.groq_critic_configured:
                raise ValueError("ADAPTIVE/2 requires the dedicated Attack Critic to be configured.")
        else:
            if (execution_mode, max_paths) not in {("SINGLE", 1), ("ADAPTIVE", 2)}:
                raise ValueError("Execution must be SINGLE/1 or ADAPTIVE/2.")
            target = target_profile(target_profile_id)
            if target_profile_id != "synthetic-socmate-tier1" and (execution_mode, max_paths) != ("SINGLE", 1):
                raise ValueError("The selected historical target supports SINGLE/1 only.")
            if target.scenario_id != scenario_id:
                raise ValueError("Target profile and scenario must match")
            selected_attack, selected_vulnerability = validate_profile_selection(
                attack_profile_id, vulnerability_profile_id or DEFAULT_VULNERABILITY_PROFILE_ID,
                target_profile_id, scenario_id)
            selection_capability = None
    except ValueError as error:
        raise DeepTeamSelectionError(str(error)) from error
    if not settings.groq_configured or not settings.openrouter_configured:
        raise DeepTeamRunError("Groq and OpenRouter credentials must be configured.")
    if not WORKER_PYTHON.exists():
        raise DeepTeamRunError("The isolated Python 3.11 worker environment is unavailable.")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with _lock:
        if RUN_LOCK.exists():
            raise DeepTeamRunError(
                "A previous worker process may still be active. Local recovery is required."
            )
        if any(
            run.status in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}
            for run in _runs.values()
        ):
            raise DeepTeamRunError("Another synthetic DeepTeam run is already active.")
        run_id = f"api-run-{uuid4().hex[:12]}"
        try:
            _claim_run_lock(run_id)
        except FileExistsError as error:
            raise DeepTeamRunError(
                "Another local worker process is already active."
            ) from error
        attack_detail = selected_attack.target_applicability.get(target_profile_id, {})
        vulnerability_detail = selected_vulnerability.target_applicability.get(target_profile_id, {})
        attack_admission = selected_attack.target_experimental_admission.get(target_profile_id, {})
        vulnerability_admission = selected_vulnerability.target_experimental_admission.get(target_profile_id, {})
        record = DeepTeamRunRecord(
            run_id=run_id,
            status="QUEUED",
            created_at=_now(),
            scenario=scenario_id,
            scenario_version=target.scenario_version,
            target_profile_id=target_profile_id,
            target_profile_version=target.version,
            target_name=target.name,
            catalog_schema_version=get_deepteam_catalog().schema_version,
            onboarding_binding_version=target.binding_version,
            execution_profile_id=(FRESH_EXECUTION_PROFILE_ID if target_profile_id == FRESH_TARGET_PROFILE_ID else None),
            execution_profile_version=(FRESH_EXECUTION_PROFILE_VERSION if target_profile_id == FRESH_TARGET_PROFILE_ID else None),
            vulnerability=selected_vulnerability.name,
            vulnerability_profile_id=selected_vulnerability.id,
            vulnerability_applicability=selected_vulnerability.applicability,
            vulnerability_capability_level=selected_vulnerability.capability_level,
            vulnerability_target_applicability=vulnerability_detail.get("applicability", "UNREVIEWED"),
            vulnerability_applicability_reason=vulnerability_detail.get("reason"),
            vulnerability_experimental_admission=vulnerability_admission.get("admission"),
            vulnerability_experimental_admission_reason=vulnerability_admission.get("reason"),
            attack=selected_attack.name,
            attack_profile_id=selected_attack.id,
            attack_applicability=selected_attack.applicability,
            attack_capability_level=selected_attack.capability_level,
            attack_target_applicability=attack_detail.get("applicability", "UNREVIEWED"),
            attack_applicability_reason=attack_detail.get("reason"),
            attack_experimental_admission=attack_admission.get("admission"),
            attack_experimental_admission_reason=attack_admission.get("reason"),
            selection_admission=(selection_capability or {}).get("admission"),
            execution_capability=(selection_capability or {}).get("execution_capability"),
            execution_capability_code=(selection_capability or {}).get("capability_code"),
            execution_capability_reason=(selection_capability or {}).get("capability_reason"),
            max_total_tokens=max_total_tokens,
            execution_mode=execution_mode,
            max_paths=max_paths,
            artifact_available=False,
            logs=[_log("INFO", "Run accepted by the local FastAPI control boundary.")],
        )
        if target_profile_id == FRESH_TARGET_PROFILE_ID:
            record.logs.append(_log("INFO",
                f"The selected {max_total_tokens:,}-token campaign budget is shared by generation, target, and review. "
                f"The target allowance is at most {FRESH_TARGET_TOKEN_LIMIT:,} tokens, not a reserved allocation. "
                "Insufficient remaining campaign capacity stops a request before HTTP; limits are never increased automatically."))
        try:
            _persist(record)
        except Exception:
            _release_run_lock(run_id)
            raise
        _runs[run_id] = record
    try:
        jobs.dispatch(_execute_run, (run_id, selected_attack.id, selected_vulnerability.id, max_total_tokens,
                                    execution_mode, max_paths, target_profile_id), RUN_LOCK,
                      f"secmate-{run_id}", thread_factory=threading.Thread)
    except Exception as error:
        try:
            _fail(run_id, "THREAD_START_FAILED", "The local worker thread could not start.")
        finally:
            _release_run_lock(run_id)
        raise DeepTeamRunError("The local worker thread could not start.") from error
    return record


def deepteam_dispatch_available(settings: Settings) -> bool:
    return (
        WORKER_PYTHON.exists()
        and settings.groq_configured
        and settings.openrouter_configured
        and not RUN_LOCK.exists()
        and not jobs.JobLedger(RUN_LOCK).active()
    )


def get_deepteam_run(run_id: str) -> DeepTeamRunRecord | None:
    with _lock:
        record = _runs.get(run_id)
    return _project_failure_diagnostic(record) if record is not None else None


def _record_sort_key(record: DeepTeamRunRecord) -> datetime:
    try:
        return datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def list_deepteam_runs(limit: int = 200) -> list[DeepTeamRunRecord]:
    with _lock:
        records = sorted(
            (run for run in _runs.values() if run.status != "DRAFT"),
            key=_record_sort_key,
            reverse=True,
        )[:limit]
    return [_project_failure_diagnostic(record) for record in records]


def snapshot_deepteam_runs() -> list[DeepTeamRunRecord]:
    """Copy every retained record without diagnostics or persistence side effects."""
    with _lock:
        return [record.model_copy(deep=True) for record in _runs.values()]


def _project_failure_diagnostic(record: DeepTeamRunRecord) -> DeepTeamRunRecord:
    if (record.status != "FAILED" or record.error_code != "WORKER_RUN_FAILED"
            or record.error_message != "The worker returned a fail-closed result."):
        return record
    directory = _artifact_directory(record.run_id)
    if directory is None:
        return record
    try:
        summary = _read_json(directory / "summary.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return record
    if summary.get("final_status") != "ERROR":
        return record
    failed_attempts = [
        attempt for attempt in summary.get("model_attempts", [])
        if isinstance(attempt, dict) and attempt.get("outcome") == "FAILURE"
    ]
    code, message = _worker_failure_details(failed_attempts, summary)
    return record if code == "WORKER_RUN_FAILED" else record.model_copy(update={
        "error_code": code,
        "error_message": message,
    })


def cancel_deepteam_run(run_id: str) -> DeepTeamRunRecord:
    with _lock:
        current = _runs.get(run_id)
        if current is None:
            raise DeepTeamRunError("DeepTeam run not found.")
        if current.status == "CANCELLED":
            return current
        if current.status in {"COMPLETED", "FAILED"}:
            raise DeepTeamRunError("The DeepTeam run has already finished.")
        if current.status != "CANCEL_REQUESTED":
            _update_locked(run_id, status="CANCEL_REQUESTED", cancellation_requested_at=_now(),
                           log=_log("WARNING", "Run cancellation was requested."))
            current = _runs[run_id]
        process = _processes.get(run_id)
        lock_payload = _read_run_lock()
        recovered_pid = (
            lock_payload.get("pid")
            if process is None and lock_payload and lock_payload.get("run_id") == run_id
            else None
        )
    if process is not None:
        if _terminate_process(process):
            with _lock:
                if _processes.get(run_id) is process:
                    _processes.pop(run_id, None)
    elif isinstance(recovered_pid, int):
        # No retained OS process handle after restart. Revoke the durable gate;
        # never kill a process identified only by a reusable numeric PID.
        session = jobs.session_for(RUN_LOCK, run_id)
        if session:
            session.ledger.update(session.job_id, session.token, cancel_requested=True, authorized=False)
    return get_deepteam_run(run_id) or current


def _read_synthetic_bundle(run_id: str, directory: Path, record: DeepTeamRunRecord) -> dict:
    root = (RUN_ROOT / run_id).resolve()
    if directory.resolve().parent != root or directory.is_symlink():
        raise RunStoreError("Unsafe synthetic artifact reference.")
    names = {"manifest": "manifest.json", "evidence": "evidence.json", "deepteam_risk": "deepteam-risk.json", "summary": "summary.json"}
    if any((directory / name).is_symlink() for name in names.values()):
        raise RunStoreError("Unsafe synthetic audit path.")
    bundle = {key: _read_json(directory / name) for key, name in names.items()}
    if any(
        bundle[name].get("run_id") != directory.name
        for name in ("manifest", "evidence", "summary")
    ):
        raise RunStoreError("Synthetic audit identity does not match its accepted reference.")
    raw_risk = bundle["deepteam_risk"]
    raw_run_id = raw_risk.get("run_id")
    evidence_paths = bundle["evidence"].get("paths")
    raw_paths = raw_risk.get("paths")
    if raw_run_id is not None and raw_run_id != directory.name:
        raise RunStoreError("Synthetic audit identity does not match its accepted reference.")
    if not isinstance(evidence_paths, list) or not isinstance(raw_paths, list):
        raise RunStoreError("Synthetic audit path identity is unavailable.")
    evidence_path_ids = [path.get("path_id") for path in evidence_paths if isinstance(path, dict)]
    raw_path_ids = [path.get("path_id") for path in raw_paths if isinstance(path, dict)]
    if (
        len(evidence_path_ids) != len(evidence_paths)
        or len(raw_path_ids) != len(raw_paths)
        or any(not isinstance(path_id, str) for path_id in evidence_path_ids + raw_path_ids)
        or evidence_path_ids != raw_path_ids
        or any(not path_id.startswith(f"{directory.name}-path-") for path_id in evidence_path_ids)
    ):
        raise RunStoreError("Synthetic audit path identity does not match its evidence.")
    if bundle["summary"].get("final_status") != record.final_status:
        raise RunStoreError("Synthetic audit verdict does not match the run.")
    if record.linked_context is not None:
        from .standard_review_contracts import digest
        if bundle["manifest"].get("prompt_provenance_hashes", {}).get("linked_context_sha256") != digest(record.linked_context.model_dump(mode="json")):
            raise RunStoreError("Linked generation provenance does not match its frozen context.")
    return {"run_id": run_id, **{key: _redact_payload(value) for key, value in bundle.items()}}


def _validate_artifact_binding(directory: Path, record: DeepTeamRunRecord, final_status: str) -> None:
    manifest = _read_json(directory / "manifest.json")
    evidence = _read_json(directory / "evidence.json")
    risk = _read_json(directory / "deepteam-risk.json")
    summary = _read_json(directory / "summary.json")
    campaign = manifest.get("campaign")
    if not isinstance(campaign, dict):
        raise DeepTeamRunError("Worker artifact campaign metadata is unavailable.")
    expected_campaign = {
        "scenario_id": record.scenario,
        "scenario_version": record.scenario_version,
        "target_profile_id": record.target_profile_id,
        "target_profile_version": record.target_profile_version,
        "vulnerability_types": [record.vulnerability_profile_id],
    }
    if any(campaign.get(key) != value for key, value in expected_campaign.items()):
        raise DeepTeamRunError("Worker artifact campaign metadata does not match the accepted run.")
    campaign_budget = campaign.get("budget")
    expected_summary = {
        "final_status": final_status,
        "attack_profile_id": record.attack_profile_id,
        "vulnerability_profile_id": record.vulnerability_profile_id,
        "target_profile_id": record.target_profile_id,
        "execution_mode": record.execution_mode,
        "max_paths": record.max_paths,
    }
    if (
        not isinstance(campaign_budget, dict)
        or campaign_budget.get("max_paths") != record.max_paths
        or any(summary.get(key) != value for key, value in expected_summary.items())
        or record.target_name is not None and summary.get("target_name") != record.target_name
        or risk.get("execution_mode") != record.execution_mode
        or risk.get("max_paths") != record.max_paths
    ):
        raise DeepTeamRunError("Worker artifact execution metadata does not match the accepted run.")
    if record.target_profile_id == FRESH_TARGET_PROFILE_ID:
        target_metadata = risk.get("target_metadata")
        if (not isinstance(target_metadata, dict)
                or target_metadata.get("target_profile_id") != record.target_profile_id
                or target_metadata.get("target_profile_version") != record.target_profile_version
                or risk.get("scenario_id") != record.scenario
                or risk.get("scenario_version") != record.scenario_version):
            raise DeepTeamRunError("Worker risk target metadata does not match the accepted run.")
    evidence_paths = evidence.get("paths")
    risk_paths = risk.get("paths")
    summary_paths = summary.get("paths")
    expected_path_count = 1 if (
        record.target_profile_id == FRESH_TARGET_PROFILE_ID
        and record.execution_capability == "UNSUPPORTED"
    ) else record.max_paths
    if not all(isinstance(paths, list) and len(paths) == expected_path_count for paths in (evidence_paths, risk_paths, summary_paths)):
        raise DeepTeamRunError("Worker artifact path count does not match the accepted run.")
    if record.target_profile_id == FRESH_TARGET_PROFILE_ID and record.onboarding_binding_version == FRESH_BINDING_VERSION:
        _validate_fresh_v2_artifacts(directory, record, manifest, evidence, risk, summary, final_status)
        return
    for path in evidence_paths:
        if path.get("vulnerability_type") != record.vulnerability_profile_id or path.get("attack_method") != record.attack_profile_id:
            raise DeepTeamRunError("Worker evidence profile metadata does not match the accepted run.")
    for path in risk_paths:
        if path.get("attack_profile_id") != record.attack_profile_id:
            raise DeepTeamRunError("Worker risk profile metadata does not match the accepted run.")
    for path in summary_paths:
        if path.get("attack_method") != record.attack_profile_id:
            raise DeepTeamRunError("Worker summary path metadata does not match the accepted run.")


def _validate_fresh_v2_artifacts(directory, record, manifest, evidence, risk, summary, final_status):
    target = target_profile(record.target_profile_id)
    onboarding_keys = (
        "binding_version", "target_id", "target_version", "gateway_kind", "api_registration",
        "deepteam_provider", "execution_modes", "max_paths", "attack_profile_ids",
        "vulnerability_profile_ids", "execution_profiles", "unsupported_attack_profiles",
    )
    expected_target = {
        "target_profile_id": record.target_profile_id,
        "target_profile_version": record.target_profile_version,
    }
    target_metadata = [
        manifest.get("target_metadata"), evidence.get("target_metadata"),
        risk.get("target_metadata"), summary.get("target_metadata"),
    ]
    if any(not isinstance(item, dict)
           or any(item.get(key) != value for key, value in expected_target.items())
           or not isinstance(item.get("onboarding"), dict) for item in target_metadata):
        raise DeepTeamRunError("Worker target onboarding metadata does not match the frozen fresh binding.")
    onboarding_values = [item["onboarding"] for item in target_metadata]
    if any(item != onboarding_values[0] for item in onboarding_values[1:]):
        raise DeepTeamRunError("Worker target onboarding metadata does not match across sealed artifacts.")
    onboarding = onboarding_values[0]
    if record.catalog_schema_version in {"2.1", "2.2"}:
        expected_onboarding = {key: getattr(target, key) for key in onboarding_keys}
        if onboarding != expected_onboarding:
            raise DeepTeamRunError("Worker target onboarding metadata does not match the frozen fresh binding.")
    else:
        execution_profiles = onboarding.get("execution_profiles")
        execution_profile = next((item for item in execution_profiles or []
                                  if isinstance(item, dict) and item.get("id") == record.execution_profile_id), None)
        projection = onboarding.get("experimental_catalog_projection")
        if (onboarding.get("binding_version") != record.onboarding_binding_version
                or onboarding.get("target_id") != record.target_profile_id
                or onboarding.get("target_version") != record.target_profile_version
                or onboarding.get("gateway_kind") != "CHATMATE_FRESH"
                or onboarding.get("api_registration") is not True
                or onboarding.get("deepteam_provider") is not True
                or record.execution_mode not in (onboarding.get("execution_modes") or [])
                or onboarding.get("max_paths") != 2
                or not isinstance(execution_profile, dict)
                or execution_profile.get("version") != record.execution_profile_version
                or record.execution_mode not in execution_profile.get("execution_modes", [])
                or execution_profile.get("max_paths") != 2
                or execution_profile.get("max_conversation_turns") != 4
                or execution_profile.get("fresh_state_per_path") is not True
                or execution_profile.get("caller_history_authoritative") is not False
                or not isinstance(projection, dict)
                or projection.get("schema_version") != "1.0"
                or projection.get("admission") != "EXPERIMENTAL"
                or record.attack_profile_id not in projection.get("attack_profile_ids", [])
                or record.vulnerability_profile_id not in projection.get("vulnerability_profile_ids", [])):
            raise DeepTeamRunError("Worker target onboarding metadata does not match the accepted 2.3 binding.")

    campaign = manifest["campaign"]
    spec = campaign.get("assessment_spec")
    if (not isinstance(spec, dict)
            or spec.get("target_profile_id") != record.target_profile_id
            or spec.get("vulnerability_profile_id") != record.vulnerability_profile_id
            or risk.get("assessment_spec_id") != spec.get("spec_id")):
        raise DeepTeamRunError("Worker assessment specification does not match the accepted fresh risk boundary.")
    allowed = campaign.get("allowed_attack_methods")
    if (not isinstance(allowed, list) or len(allowed) != len(set(allowed))
            or record.attack_profile_id not in allowed
            or record.execution_mode == "SINGLE" and allowed != [record.attack_profile_id]):
        raise DeepTeamRunError("Worker campaign methods do not match the accepted execution shape.")

    expected_path_ids = [f"{directory.name}-path-{index}" for index in range(1, len(evidence["paths"]) + 1)]
    evidence_paths, risk_paths, summary_paths = evidence["paths"], risk["paths"], summary["paths"]
    if any([path.get("path_id") for path in paths] != expected_path_ids
           for paths in (evidence_paths, risk_paths, summary_paths)):
        raise DeepTeamRunError("Worker artifact path IDs are not the ordered accepted path identities.")
    methods = [path.get("attack_method") for path in evidence_paths]
    if methods[0] != record.attack_profile_id or len(set(methods)) != len(methods):
        raise DeepTeamRunError("Worker path methods do not match the accepted fresh execution.")
    for index, method in enumerate(methods):
        if (method not in allowed
                or risk_paths[index].get("attack_profile_id") != method
                or summary_paths[index].get("attack_method") != method
                or summary_paths[index].get("status") != evidence_paths[index].get("status")
                or evidence_paths[index].get("vulnerability_type") != record.vulnerability_profile_id):
            raise DeepTeamRunError("Worker path method or risk identity does not match across sealed artifacts.")
        path = evidence_paths[index]
        turns = path.get("turns")
        assessments = path.get("phase5_assessments")
        if not isinstance(turns, list) or not isinstance(assessments, list) or len(assessments) != len(turns):
            raise DeepTeamRunError("Fresh path evidence requires one additive Phase 5 assessment per captured turn.")
        if not turns:
            engine = path.get("engine_result")
            raw_error = engine.get("raw_result", {}).get("error") if isinstance(engine, dict) else None
            if (final_status != "ERROR" or path.get("status") != "ERROR"
                    or not isinstance(engine, dict) or engine.get("native_score") is not None
                    or engine.get("normalized_status") != "ERROR" or not isinstance(raw_error, dict)
                    or not isinstance(raw_error.get("code"), str)):
                raise DeepTeamRunError("Empty fresh evidence is only valid for a scoreless execution error.")
            continue
        turn_ids = [turn.get("turn_id") for turn in turns]
        if len(set(turn_ids)) != len(turn_ids) or any(not isinstance(turn_id, str) for turn_id in turn_ids):
            raise DeepTeamRunError("Fresh path turn identities are invalid.")
        for turn, assessment in zip(turns, assessments):
            binding = assessment.get("binding_metadata")
            if (assessment.get("parent_path_id") != expected_path_ids[index]
                    or assessment.get("parent_turn_id") != turn.get("turn_id")
                    or assessment.get("turn_binding_version") != "phase5-turn-binding-v1"
                    or assessment.get("target_id") != record.target_profile_id
                    or assessment.get("target_version") != record.target_profile_version
                    or assessment.get("onboarding_binding_version") != FRESH_BINDING_VERSION
                    or assessment.get("status") != "completed"
                    or assessment.get("answer_present") is not True
                    or not isinstance(binding, dict)
                    or binding.get("execution_profile_id") != record.execution_profile_id
                    or binding.get("execution_profile_version") != record.execution_profile_version):
                raise DeepTeamRunError("Phase 5 evidence is not bound to its exact fresh parent path and turn.")

    reviews = evidence.get("review_results")
    if not isinstance(reviews, list) or [item.get("path_id") for item in reviews] != expected_path_ids:
        raise DeepTeamRunError("Worker review identities do not match the ordered fresh paths.")
    if final_status == "ERROR" and any(
        review.get("decision") != "ERROR" or review.get("target_evaluation") is not None
        for review in reviews
    ):
        raise DeepTeamRunError("Failed fresh execution cannot publish a Judge result or score.")
    if record.execution_mode == "SINGLE" and summary_paths[0].get("status") != final_status:
        raise DeepTeamRunError("Worker single-path verdict does not match the sealed final result.")
    if record.execution_mode == "ADAPTIVE" and len(methods) == 2:
        first = reviews[0]
        critic = first.get("critic_review")
        if (first.get("decision") != "CONTINUE" or not isinstance(critic, dict)
                or first.get("next_attack_method") != methods[1]
                or critic.get("recommended_attack_method") != methods[1]
                or methods[1] == methods[0]):
                raise DeepTeamRunError("Adaptive Critic recommendation does not bind to the distinct second path method.")

    try:
        selected_risk = vulnerability_profile(record.vulnerability_profile_id)
        expected_top_selection = fresh_selection_capability(
            attack_profile(record.attack_profile_id), selected_risk)
        expected_path_selections = [
            fresh_selection_capability(attack_profile(method), selected_risk)
            for method in methods
        ]
    except ValueError as error:
        raise DeepTeamRunError("Worker selection provenance references an unknown catalog profile.") from error
    top_selection_values = [
        manifest.get("selection_provenance"), evidence.get("selection_provenance"),
        risk.get("selection_provenance"), summary.get("selection_provenance"),
    ]
    if any(value != expected_top_selection for value in top_selection_values):
        raise DeepTeamRunError("Fresh selection capability provenance does not match the accepted selection.")
    for index, expected_selection in enumerate(expected_path_selections):
        if any(paths[index].get("selection_provenance") != expected_selection
               for paths in (evidence_paths, risk_paths, summary_paths)):
            raise DeepTeamRunError("Fresh path selection capability provenance does not match its exact method and risk.")

    record_selection = {
        "admission": record.selection_admission,
        "execution_capability": record.execution_capability,
        "capability_code": record.execution_capability_code,
        "capability_reason": record.execution_capability_reason,
    }
    if any(record_selection[key] != expected_top_selection[key] for key in record_selection):
        raise DeepTeamRunError("Worker selection capability differs from the accepted request record.")

    if expected_top_selection["execution_capability"] == "UNSUPPORTED":
        budget = summary.get("budget")
        if (final_status != "ERROR" or record.max_paths != len(evidence_paths) and len(evidence_paths) != 1
                or not isinstance(budget, dict)
                or budget.get("provider_calls_attempted") != 0
                or summary.get("turns") != 0
                or summary.get("model_attempts") not in ([], None)
                or any(path.get("status") != "ERROR" or path.get("turns") != []
                       or path.get("phase5_assessments") != [] for path in evidence_paths)
                or any(review.get("decision") != "ERROR" or review.get("target_evaluation") is not None
                       or review.get("critic_review") is not None for review in reviews)):
            raise DeepTeamRunError("Unsupported fresh selection must be a scoreless zero-call audit result.")
        for index, path in enumerate(evidence_paths):
            engine = path.get("engine_result")
            raw_error = engine.get("raw_result", {}).get("error") if isinstance(engine, dict) else None
            risk_result = risk_paths[index].get("result")
            risk_error = risk_result.get("error") if isinstance(risk_result, dict) else None
            if (not isinstance(engine, dict) or engine.get("native_score") is not None
                    or engine.get("native_reason") is not None
                    or engine.get("native_evaluator_profile_id") is not None
                    or not isinstance(raw_error, dict)
                    or raw_error.get("code") != expected_top_selection["capability_code"]
                    or raw_error.get("message") != expected_top_selection["capability_reason"]
                    or not isinstance(risk_result, dict)
                    or risk_result.get("test_cases") != []
                    or risk_result.get("selection_provenance") != expected_path_selections[index]
                    or not isinstance(risk_error, dict)
                    or risk_error.get("code") != expected_path_selections[index]["capability_code"]
                    or risk_error.get("message") != expected_path_selections[index]["capability_reason"]):
                raise DeepTeamRunError("Unsupported fresh selection contains a score or unstable capability error.")

    baseline_binding = (
        record.target_profile_id == "secmate.synthetic-chatmate.fresh.v1"
        and record.scenario == "chatmate-direct-user-prompt-injection"
        and record.vulnerability_profile_id
        == "DirectPromptInjection:direct_user_instruction"
        and record.attack_profile_id == "prompt-injection-v1"
        and record.execution_mode == "SINGLE"
        and record.max_paths == 1
    )
    if baseline_binding:
        provenance_values = [
            manifest.get("execution_provenance"),
            evidence.get("execution_provenance"),
            risk.get("execution_provenance"),
            summary.get("execution_provenance"),
            evidence_paths[0].get("execution_provenance"),
            risk_paths[0].get("execution_provenance"),
            summary_paths[0].get("execution_provenance"),
        ]
        provenance = provenance_values[0]
        if (
            not isinstance(provenance, dict)
            or any(value != provenance for value in provenance_values[1:])
            or provenance.get("schema_version") != "baseline-execution-v1"
            or provenance.get("execution_mode") != "BASELINE_UNENHANCED"
            or provenance.get("enhancement_applied") is not False
            or provenance.get("delivery") != "DIRECT_GENERATED_ATTACK"
        ):
            raise DeepTeamRunError(
                "Baseline execution provenance does not match across sealed artifacts."
            )
        attack_text = provenance.get("generated_attack_text")
        attack_digest = provenance.get("generated_attack_sha256")
        if attack_text is None:
            if attack_digest is not None:
                raise DeepTeamRunError(
                    "Baseline generated attack provenance has an unmatched digest."
                )
        elif (
            not isinstance(attack_text, str)
            or not attack_text
            or attack_digest
            != hashlib.sha256(attack_text.encode("utf-8")).hexdigest()
        ):
            raise DeepTeamRunError(
                "Baseline generated attack provenance has an invalid digest."
            )
        if turns:
            if (
                attack_text != turns[0].get("probe")
            ):
                raise DeepTeamRunError(
                    "Baseline generated attack provenance does not match target evidence."
                )
    else:
        provenance_values = [
            manifest.get("execution_provenance"), evidence.get("execution_provenance"),
            risk.get("execution_provenance"), summary.get("execution_provenance"),
            *(path.get("execution_provenance") for path in evidence_paths),
            *(path.get("execution_provenance") for path in risk_paths),
            *(path.get("execution_provenance") for path in summary_paths),
        ]
        if any(value is not None for value in provenance_values):
            raise DeepTeamRunError("Baseline execution provenance is forbidden outside the exact direct prompt baseline.")


def get_deepteam_audit(run_id: str) -> DeepTeamAuditReport | None:
    record = get_deepteam_run(run_id)
    if record is None or not record.artifact_available:
        return None
    try:
        store = RunStore(RUN_ROOT)
        references = store.verification(run_id)["evidence_baselines"]
        if references:
            if len(references) != 1:
                return None
            directory = RUN_ROOT / run_id / next(iter(references))
        elif store.legacy_import(run_id):
            directory = _artifact_directory(run_id)
            if directory is None:
                return None
        else:
            return None
        bundle = _read_synthetic_bundle(run_id, directory, record)
        store.verify_evidence(run_id, directory.name, bundle, allow_baseline=store.legacy_import(run_id))
        return DeepTeamAuditReport(**bundle)
    except (RunStoreError, OSError, ValueError, json.JSONDecodeError):
        return None


def _worker_command(
    output_root: Path,
    attack_profile_id: str,
    vulnerability_profile_id: str,
    max_total_tokens: int,
    execution_mode: str,
    max_paths: int,
    target_profile_id: str = "synthetic-socmate-tier1",
) -> list[str]:
    command = [
        str(WORKER_PYTHON),
        "-m",
        "secmate_worker.single_attack",
        "--env-file",
        str(API_ROOT / ".env"),
        "--allow-openrouter-data-collection",
        "--output",
        str(output_root),
        "--attack-profile",
        attack_profile_id,
        "--vulnerability-profile",
        vulnerability_profile_id,
        "--token-budget",
        str(max_total_tokens),
        "--execution-mode",
        execution_mode,
        "--max-paths",
        str(max_paths),
        "--target-profile",
        target_profile_id,
    ]
    record = _runs.get(output_root.name)
    if record is not None and record.linked_context is not None:
        from .standard_review_contracts import digest
        path = output_root / "generation-context.json"
        context = record.linked_context.model_dump(mode="json")
        path.write_text(json.dumps(context, ensure_ascii=True), encoding="ascii")
        command += ["--generation-context", str(path), "--generation-context-sha256", digest(context)]
    return command


@jobs.execution("SYNTHETIC", lambda: RUN_LOCK, lambda: RUN_ROOT, lambda: _runs)
def _execute_run(*args, **kwargs) -> None:
    run_id = args[0] if args else kwargs["run_id"]
    try:
        record = get_deepteam_run(run_id)
        if record is not None and record.linked_context is not None:
            from .standard_reviews import validate_linked_source
            try:
                validate_linked_source(record)
            except (ValueError, OSError, RunStoreError):
                _fail(run_id, "LINKED_SOURCE_INVALID", "The frozen parent recommendation failed revalidation; no inference was started.")
                return
        _execute_run_owned(*args, **kwargs)
    finally:
        # Initial persistence/preparation can fail before the subprocess cleanup
        # scope is reached. Release ownership only when no process is retained.
        with _lock:
            retained = _processes.get(run_id)
        if retained is None:
            _release_run_lock(run_id)


def _execute_run_owned(
    run_id: str,
    attack_profile_id: str,
    vulnerability_profile_id: str,
    max_total_tokens: int,
    execution_mode: str,
    max_paths: int,
    target_profile_id: str = "synthetic-socmate-tier1",
) -> None:
    process: subprocess.Popen[str] | None = None
    stderr = ""
    output_root = RUN_ROOT / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    with _lock:
        current = _runs[run_id]
        if current.status == "CANCEL_REQUESTED":
            _mark_cancelled_locked(run_id)
            _release_run_lock(run_id)
            return
        _update_locked(
            run_id,
            status="RUNNING",
            started_at=_now(),
            log=_log("INFO", "Pinned Python 3.11 DeepTeam worker started."),
        )
    command = _worker_command(
        output_root,
        attack_profile_id,
        vulnerability_profile_id,
        max_total_tokens,
        execution_mode,
        max_paths,
        target_profile_id,
    )
    allowed_environment = _worker_environment()
    allowed_environment.update(
        {
            "DEEPTEAM_TELEMETRY_OPT_OUT": "YES",
            "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
            "DEEPTEAM_SHOW_PROGRESS": "false",
            "TELEMETRY_OPT_OUT": "YES",
            "ERROR_REPORTING": "NO",
        }
    )
    try:
        popen_options = {}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True
        process = jobs.launch(
            command,
            cwd=WORKER_ROOT,
            env=allowed_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen_options,
        )
        with _lock:
            _processes[run_id] = process
            _write_run_lock(run_id, process.pid)
            cancellation_requested = _runs[run_id].status == "CANCEL_REQUESTED"
        if cancellation_requested:
            _terminate_process(process)
        _, stderr = process.communicate(timeout=WORKER_TIMEOUT_SECONDS)
        if _is_cancellation_requested(run_id):
            _mark_cancelled(run_id)
            return
        artifact_directory = _artifact_directory(run_id)
        if artifact_directory is None:
            diagnostic = _worker_stderr_diagnostic(stderr, allowed_environment)
            message = f"Worker exited with code {process.returncode} without producing audit artifacts."
            if diagnostic:
                message = f"{message} {diagnostic}"
            raise DeepTeamRunError(message)
        summary = _read_json(artifact_directory / "summary.json")
        final_status = summary.get("final_status")
        successful = _is_successful_worker_result(process.returncode, final_status)
        budget = summary.get("budget", {})
        calls = budget.get("provider_calls_attempted")
        tokens = budget.get("tokens_consumed")
        missing_usage = budget.get("calls_with_missing_usage")
        failed_attempts = [
            attempt
            for attempt in summary.get("model_attempts", [])
            if attempt.get("outcome") == "FAILURE"
        ]
        failure_code, failure_message = _worker_failure_details(failed_attempts, summary)
        diagnostic_artifacts = final_status == "ERROR"
        if successful or diagnostic_artifacts:
            record = get_deepteam_run(run_id)
            if record is None:
                raise DeepTeamRunError("The accepted run disappeared before artifact publication.")
            _validate_artifact_binding(artifact_directory, record, final_status)
        with _lock:
            if _runs[run_id].status == "CANCEL_REQUESTED":
                _mark_cancelled_locked(run_id)
            else:
                _update_locked(
                    run_id,
                    status="COMPLETED" if successful else "FAILED",
                    completed_at=_now(),
                    final_status=final_status if successful else "ERROR",
                    artifact_available=successful or diagnostic_artifacts,
                    error_code=(
                        None
                        if successful
                        else failure_code
                    ),
                    error_message=(
                        None
                        if successful
                        else failure_message
                    ),
                    log=_log(
                        "INFO" if successful else "ERROR",
                        "Worker finished with "
                        f"{calls if type(calls) is int else 'unknown'} provider calls and "
                        f"{tokens if type(tokens) is int else 'unknown'} tokens"
                        + (f"; usage was unknown for {missing_usage} call(s)." if type(missing_usage) is int and missing_usage else "."),
                    ),
                )
    except subprocess.TimeoutExpired:
        terminated = process is not None and _terminate_process(process)
        if _is_cancellation_requested(run_id) and terminated:
            _mark_cancelled(run_id)
        elif terminated:
            _fail(run_id, "WORKER_TIMEOUT", "The worker exceeded the local execution timeout.")
        else:
            _fail(run_id, "WORKER_TERMINATION_FAILED", "The timed-out worker process could not be stopped.")
    except Exception as error:
        if _is_cancellation_requested(run_id) and (process is None or process.poll() is not None):
            _mark_cancelled(run_id)
        else:
            message = (
                str(error)
                if isinstance(error, DeepTeamRunError)
                else "The worker failed before a complete audit bundle was available."
            )
            _fail(run_id, "WORKER_EXECUTION_ERROR", message)
    finally:
        process_completed = process is None or process.poll() is not None
        if process_completed:
            with _lock:
                if _processes.get(run_id) is process:
                    _processes.pop(run_id, None)
            _release_run_lock(run_id)
        elif process is not None:
            threading.Thread(
                target=_release_after_process_exit,
                args=(run_id, process, jobs._current.get()),
                daemon=True,
                name=f"secmate-reaper-{run_id}",
            ).start()


def _terminate_process(process: subprocess.Popen[str]) -> bool:
    if isinstance(process, jobs.ManagedProcess):
        return process.session.terminate()
    if process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ValueError):
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
        return True
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        try:
            tree_kill = subprocess.Popen(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            tree_kill.wait(timeout=KILL_WAIT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return True


def _terminate_pid_tree(pid: int) -> bool:
    if not _pid_exists(pid):
        return True
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=KILL_WAIT_SECONDS,
                check=False,
            )
            return completed.returncode == 0 or not _pid_exists(pid)
        except (OSError, subprocess.TimeoutExpired):
            return False
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return not _pid_exists(pid)
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass
    return not _pid_exists(pid)


def _release_after_process_exit(run_id: str, process: subprocess.Popen[str], session=None) -> None:
    process.wait()
    if session is None:
        return
    token = jobs._current.set(session)
    try:
        with _lock:
            session.state()
            if _processes.get(run_id) is process:
                _processes.pop(run_id, None)
            if _runs.get(run_id) and _runs[run_id].status == "CANCEL_REQUESTED":
                _mark_cancelled_locked(run_id)
        _release_run_lock(run_id, session)
    except RunStoreError:
        pass
    finally:
        jobs._current.reset(token)


def _release_after_recovered_process_exit(run_id: str, pid: int) -> None:
    while _pid_exists(pid):
        time.sleep(1)
    with _lock:
        if _runs.get(run_id) and _runs[run_id].status == "CANCEL_REQUESTED":
            _mark_cancelled_locked(run_id)
    _release_run_lock(run_id)


def _worker_environment() -> dict[str, str]:
    return {
        name: os.environ[name]
        for name in (
            "APPDATA",
            "LOCALAPPDATA",
            "PATH",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        )
        if os.environ.get(name)
    }


def _is_successful_worker_result(returncode: int, final_status) -> bool:
    return returncode == 0 and final_status in {
        "RESISTED",
        "COMPROMISED",
        "INCONCLUSIVE",
    }


def _worker_failure_details(failed_attempts: list[dict], summary: dict | None = None) -> tuple[str, str]:
    selection = (summary or {}).get("selection_provenance")
    if (isinstance(selection, dict)
            and selection.get("schema_version") == "fresh-selection-capability-v1"
            and selection.get("execution_capability") == "UNSUPPORTED"
            and isinstance(selection.get("capability_code"), str)
            and isinstance(selection.get("capability_reason"), str)):
        return selection["capability_code"], selection["capability_reason"]
    if not failed_attempts:
        return "WORKER_RUN_FAILED", "The worker returned a fail-closed result."
    attempt = failed_attempts[-1]
    provider = {"GROQ": "Groq", "OPENROUTER": "OpenRouter"}.get(
        attempt.get("provider"), "Model provider"
    )
    error_code = attempt.get("error_code")
    if error_code == "RATE_LIMITED":
        return (
            "PROVIDER_RATE_LIMITED",
            "A model provider rate limit was exhausted after bounded retries. The run failed closed; its token budget was not exceeded.",
        )
    if error_code in {
        "REQUEST_TIMEOUT",
        "CONNECT_TIMEOUT",
        "READ_TIMEOUT",
        "WRITE_TIMEOUT",
        "POOL_TIMEOUT",
    }:
        return (
            "PROVIDER_TIMEOUT",
            f"{provider} timed out after bounded retries. No security conclusion was reached; retry when the provider is responsive.",
        )
    if error_code == "AUTHENTICATION":
        return (
            "PROVIDER_AUTHENTICATION_FAILED",
            f"{provider} rejected its API key. Update the configured key and restart SecMate.",
        )
    if error_code == "ROUTE_UNAVAILABLE":
        return (
            "PROVIDER_MODEL_UNAVAILABLE",
            f"The configured {provider} model route is unavailable. Check model access and retry when the route is available.",
        )
    if error_code == "REQUEST_REJECTED":
        status_code = attempt.get("status_code")
        status = (
            f" with HTTP {status_code}"
            if type(status_code) is int and 400 <= status_code <= 599
            else ""
        )
        return (
            "PROVIDER_REQUEST_REJECTED",
            f"{provider} rejected the model request{status}. Check the model's supported request parameters; no security conclusion was reached.",
        )
    if error_code == "SCHEMA_VALIDATION" and attempt.get("role") == "ATTACKER":
        schema_name = attempt.get("schema_name")
        schema = f" {schema_name}" if isinstance(schema_name, str) and schema_name else " structured"
        return (
            "ATTACK_GENERATION_SCHEMA_INVALID",
            f"{provider} repeatedly returned attacker output that did not match the required{schema} format. The target and Judge were not evaluated, so no security conclusion was reached.",
        )
    return "WORKER_RUN_FAILED", "The worker returned a fail-closed result."


def _artifact_directory(run_id: str) -> Path | None:
    root = RUN_ROOT / run_id
    session = jobs._current.get()
    if session is not None:
        matches = [root / Path(name).parent for name in session.verified_files
                   if Path(name).name == "summary.json" and len(Path(name).parts) == 2
                   and Path(name).parts[0].startswith("run-")]
        return matches[0] if len(matches) == 1 else None
    if not root.exists():
        return None
    matches = [path.parent for path in root.glob("run-*/summary.json")]
    return matches[0] if len(matches) == 1 else None


def _read_json(path: Path) -> dict:
    session = jobs._current.get()
    frozen = session.projected_bytes(path) if session else None
    payload = json.loads(frozen.decode("ascii") if frozen is not None else path.read_text(encoding="ascii"))
    if not isinstance(payload, dict):
        raise ValueError("Audit artifact must be a JSON object.")
    return payload


def _update(
    run_id: str,
    *,
    log: DeepTeamRunLog | None = None,
    **changes,
) -> None:
    with _lock:
        _update_locked(run_id, log=log, **changes)


def _update_locked(
    run_id: str,
    *,
    log: DeepTeamRunLog | None = None,
    **changes,
) -> None:
    current = _runs[run_id]
    logs = [*current.logs, log] if log else current.logs
    updated = current.model_copy(update={**changes, "logs": logs})
    _persist(updated)
    _runs[run_id] = updated


def _is_cancellation_requested(run_id: str) -> bool:
    with _lock:
        return _runs[run_id].status in {"CANCEL_REQUESTED", "CANCELLED"}


def _mark_cancelled(run_id: str) -> None:
    with _lock:
        if _runs[run_id].status != "CANCELLED":
            _mark_cancelled_locked(run_id)


def _mark_cancelled_locked(run_id: str) -> None:
    _update_locked(
        run_id,
        status="CANCELLED",
        completed_at=_now(),
        final_status=None,
        error_code=None,
        error_message=None,
        log=_log("INFO", "Worker process stopped and the run was cancelled."),
    )


def _fail(run_id: str, code: str, message: str) -> None:
    _update(
        run_id,
        status="FAILED",
        completed_at=_now(),
        final_status="ERROR",
        artifact_available=False,
        error_code=code,
        error_message=message,
        log=_log("ERROR", message),
    )


def _claim_run_lock(run_id: str) -> None:
    if RUN_LOCK.exists():
        raise FileExistsError("Another local worker owns the lock.")
    session = jobs.prepare(RUN_LOCK, run_id, "SYNTHETIC", RUN_ROOT)
    jobs.claim_projection(session)


def _write_run_lock(run_id: str, pid: int) -> None:
    session = jobs.session_for(RUN_LOCK, run_id)
    metadata = {"job_id": session.job_id, "token": session.token, "identity": jobs.process_identity(pid)} if session else {}
    temporary_lock = RUN_LOCK.with_name(f"{RUN_LOCK.name}.tmp")
    temporary_lock.write_text(
        json.dumps({"run_id": run_id, "pid": pid, **metadata}),
        encoding="ascii",
    )
    os.replace(temporary_lock, RUN_LOCK)


def _release_run_lock(run_id: str, session=None) -> None:
    session = session or jobs.session_for(RUN_LOCK, run_id)
    if session and not session.finish():
        return
    payload = _read_run_lock()
    if payload is None:
        return
    if payload.get("run_id") == run_id and (session is None or payload.get("job_id") in {None, session.job_id}):
        RUN_LOCK.unlink(missing_ok=True)


def _read_run_lock() -> dict | None:
    try:
        contents = RUN_LOCK.read_text(encoding="ascii")
    except OSError:
        return None
    try:
        payload = json.loads(contents)
    except (ValueError, json.JSONDecodeError):
        return {"run_id": contents.strip(), "pid": None}
    return payload if isinstance(payload, dict) else None


def _persist(record: DeepTeamRunRecord) -> None:
    directory = RUN_ROOT / record.run_id
    directory.mkdir(parents=True, exist_ok=True)
    store = RunStore(RUN_ROOT)
    evidence_bundle = None
    original_evidence = None
    if record.artifact_available:
        artifact_directory = _artifact_directory(record.run_id)
        references = store.verification(record.run_id)["evidence_baselines"] if store.contains(record.run_id) else {}
        if artifact_directory is not None and references and artifact_directory.name not in references:
            raise RunStoreError("Synthetic artifact reference cannot be replaced.")
        if artifact_directory is not None and not references and all((artifact_directory / name).is_file() for name in ("manifest.json", "evidence.json", "deepteam-risk.json", "summary.json")):
            evidence_bundle = (artifact_directory.name, _read_synthetic_bundle(record.run_id, artifact_directory, record))
            session = jobs._current.get()
            if session is not None and session.verified_files:
                original_evidence = {"run_id": record.run_id, **{key: _read_json(artifact_directory / name) for key, name in (
                    ("manifest", "manifest.json"), ("evidence", "evidence.json"), ("deepteam_risk", "deepteam-risk.json"), ("summary", "summary.json"))}}
    payload = record.model_dump(mode="json")
    jobs.persist(store, RUN_LOCK, payload, evidence_bundle, original_evidence)
    store.write_projection(payload, directory / "record.json")


def _redact_payload(value):
    sensitive_names = {
        "api_key",
        "approval_token",
        "authorization",
        "credential",
        "password",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in sensitive_names else _redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _worker_stderr_diagnostic(stderr: str, environment: dict[str, str]) -> str | None:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return None
    diagnostic = lines[-1]
    allowed_prefixes = (
        "ValueError: DeepTeam ",
        "ValueError: Unknown DeepTeam ",
        "RuntimePolicyError: ",
        "ModuleNotFoundError: ",
        "ImportError: ",
    )
    if not diagnostic.startswith(allowed_prefixes):
        return None
    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        secret = environment.get(name)
        if secret:
            diagnostic = diagnostic.replace(secret, "<redacted>")
    diagnostic = "".join(character for character in diagnostic if character.isprintable())
    return diagnostic[:500] or None


def _load_records() -> None:
    if not RUN_ROOT.exists():
        return
    lock_payload = _read_run_lock() if RUN_LOCK.exists() else None
    locked_run_id = lock_payload.get("run_id") if lock_payload else None
    locked_pid = lock_payload.get("pid") if lock_payload else None
    locked_process_active = isinstance(locked_pid, int) and _pid_exists(locked_pid)
    store = RunStore(RUN_ROOT)
    for record_path in RUN_ROOT.glob("api-run-*/record.json"):
        try:
            record = DeepTeamRunRecord.model_validate_json(
                record_path.read_text(encoding="ascii")
            )
            if record.run_id != record_path.parent.name:
                continue
            if not store.contains(record.run_id):
                store.save(record.model_dump(mode="json"), imported=True)
        except Exception:
            continue
    for payload in store.records().values():
        record = DeepTeamRunRecord.model_validate(payload)
        if record.status in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"} and not jobs.pending_recovery(RUN_LOCK, record.run_id):
            cancelled = record.status == "CANCEL_REQUESTED"
            cancellation_still_active = (
                cancelled
                and record.run_id == locked_run_id
                and locked_process_active
            )
            record = record.model_copy(
                update={
                    "status": "CANCEL_REQUESTED" if cancellation_still_active else "CANCELLED" if cancelled else "FAILED",
                    "completed_at": None if cancellation_still_active else _now(),
                    "final_status": None if cancelled else "ERROR",
                    "error_code": None if cancelled else "CONTROL_API_RESTARTED",
                    "error_message": None if cancelled else "The control API restarted before run completion.",
                    "logs": [
                        *record.logs,
                        _log(
                            "WARNING" if cancellation_still_active else "INFO" if cancelled else "ERROR",
                            "The control API restarted while cancellation was still in progress."
                            if cancellation_still_active
                            else "Cancellation was recovered after the control API restarted."
                            if cancelled
                            else "The control API restarted before run completion.",
                        ),
                    ],
                }
            )
            _persist(record)
        _runs[record.run_id] = record
    if RUN_LOCK.exists():
        if lock_payload is None:
            return
        if lock_payload.get("job_id"):
            value = jobs.JobLedger(RUN_LOCK).get(lock_payload["job_id"])
            if value["state"] in jobs.TERMINAL:
                jobs.JobLedger(RUN_LOCK).clear_projection(value)
            return
        # Legacy PID-only locks have no process-creation proof. Do not steal or
        # attach a reaper to an unrelated process after PID reuse.
        return


def _pid_exists(pid: int) -> bool:
    return not jobs.process_absent(pid)


# Loaded by the exclusive API lifespan, never as an import side effect.
