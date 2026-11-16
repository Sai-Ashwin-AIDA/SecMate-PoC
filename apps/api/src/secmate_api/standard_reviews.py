"""Standard-only saved advisory and linked fresh assessments.

Parent verdicts/evidence are immutable. GETs never launch inference. All provider
work uses the existing durable CRITIC job slot and sealed publication.
"""
import json
import os
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from . import deepteam_runs as runs, jobs
from .config import get_settings
from .contracts import DeepTeamRunRecord
from .deepteam_catalog import (FRESH_BINDING_VERSION, FRESH_TARGET_PROFILE_ID, get_deepteam_catalog,
                                 fresh_selection_capability, target_profile, validate_fresh_selection, validate_profile_selection,
                                 vulnerability_profile)
from .standard_review_contracts import (VERSION, TARGET_VERSION, TARGET_LINKED_VERSION, StandardReviewInput, StandardReview, output_schema, MethodChoice,
    LinkedAssessmentContext, canonical, digest, evidence_projection, estimated_input_tokens, target_model_fingerprint)
from .run_store import RunStore, RunStoreError


class StandardReviewError(ValueError):
    pass


def _record(run_id):
    record = runs.get_deepteam_run(run_id)
    if record is None:
        raise StandardReviewError("Assessment not found.")
    return record


def _directory(record):
    if not record.critic_review_id:
        raise StandardReviewError("No Standard review attempt exists.")
    root = runs.RUN_ROOT / record.run_id
    path = root / "standard-reviews" / record.critic_review_id
    if not path.resolve().is_relative_to(root.resolve()) or any(
        component.is_symlink() or getattr(component, "is_junction", lambda: False)() for component in (root, path.parent, path)):
        raise StandardReviewError("Unsafe review artifact path.")
    return path


def _verified_audit(record):
    if (record.status != "COMPLETED" or record.final_status not in {"RESISTED", "INCONCLUSIVE", "COMPROMISED"}
            or record.execution_mode != "SINGLE" or record.max_paths != 1
            or not record.artifact_available):
        raise StandardReviewError("A completed Standard assessment with verified evidence is required.")
    audit = runs.get_deepteam_audit(record.run_id)
    if audit is None:
        raise StandardReviewError("Verified assessment evidence is unavailable.")
    payload = audit.model_dump(mode="json")
    paths = payload["evidence"].get("paths", [])
    if len(paths) != 1 or not paths[0].get("turns") or not any(
            turn.get("target_response") or turn.get("tool_attempts") for turn in paths[0]["turns"]):
        raise StandardReviewError("No usable captured response or tool evidence is available.")
    spec = payload["manifest"]["campaign"].get("assessment_spec")
    if not isinstance(spec, dict) or spec.get("target_profile_id") != record.target_profile_id or spec.get("vulnerability_profile_id") != record.vulnerability_profile_id:
        raise StandardReviewError("Assessment boundary does not match the saved run.")
    campaign = payload["manifest"]["campaign"]
    if (campaign.get("target_profile_version") != record.target_profile_version
            or campaign.get("scenario_id") != record.scenario
            or campaign.get("scenario_version") != record.scenario_version):
        raise StandardReviewError("Assessment target and scenario do not match the saved run.")
    if record.target_profile_id == FRESH_TARGET_PROFILE_ID:
        current_target = target_profile(record.target_profile_id)
        if (record.catalog_schema_version != get_deepteam_catalog().schema_version
                or record.onboarding_binding_version != FRESH_BINDING_VERSION
                or current_target.version != record.target_profile_version
                or current_target.binding_version != record.onboarding_binding_version):
            raise StandardReviewError("Review unavailable: the frozen target/catalog binding is no longer current.")
    from .profiles import MODEL_PROFILES_BY_ID
    target = MODEL_PROFILES_BY_ID["openrouter-nemotron-35-super-vl-target"]
    if target_model_fingerprint(payload["manifest"]["campaign"]) != digest({"profile_id": target.id, "provider": target.provider, "model": target.model}):
        raise StandardReviewError("Review unavailable: the target model changed since this assessment.")
    return payload, spec


def _redacted_snapshot(value):
    from .chatmate_runs import _RESPONSE_REDACTIONS
    settings = get_settings()
    secrets = [secret for secret in (settings.groq_api_key, settings.groq_critic_api_key, settings.openrouter_api_key) if secret]
    secrets.sort(key=len, reverse=True)

    def clean(item):
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, "<redacted>")
            for pattern in _RESPONSE_REDACTIONS:
                item = pattern.sub("<redacted>", item)
            return item
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            return {key: "<redacted>" if key.lower() in {"api_key", "password", "authorization", "approval_token", "credential", "secret", "token"} else clean(child) for key, child in item.items()}
        return item
    snapshot = clean(value)
    # The caller verifies these target identifiers against the trusted catalog.
    # Credential patterns also match parts of the Nemotron model identifiers.
    original_campaign = value["manifest"]["campaign"]
    redacted_campaign = snapshot["manifest"]["campaign"]
    for key in ("target_profile_id", "target_profile_version", "scenario_id", "scenario_version"):
        redacted_campaign[key] = original_campaign[key]
    for original, redacted in zip(original_campaign["model_profiles"], redacted_campaign["model_profiles"]):
        if original.get("role") == "TARGET":
            for key in ("profile_id", "provider", "model"):
                redacted[key] = original[key]
    return snapshot


def _source(record, schema_version=None):
    schema_version = schema_version or (VERSION if record.target_profile_id == "synthetic-socmate-tier1" else TARGET_VERSION)
    audit, spec = _verified_audit(record)
    used = {record.attack_profile_id, *(path["attack_method"] for path in audit["evidence"]["paths"])}
    choices = []
    for profile in get_deepteam_catalog().attack_profiles:
        if profile.id in used:
            continue
        try:
            _review_attack_profile(profile.id, record)
        except ValueError:
            continue
        choices.append(MethodChoice(id=profile.id, name=profile.name, description=profile.description[:60]))
    if not choices:
        raise StandardReviewError("No unused applicable methods are available.")
    snapshot = _redacted_snapshot(audit)
    source = StandardReviewInput(schema_version=schema_version, run_id=record.run_id, review_id=record.critic_review_id or "standard-review-000000000000",
        created_at=record.critic_started_at or record.completed_at, target_profile_id=record.target_profile_id,
        target_profile_version=record.target_profile_version, vulnerability_profile_id=record.vulnerability_profile_id,
        scenario_id=record.scenario if schema_version == TARGET_VERSION else None,
        scenario_version=record.scenario_version if schema_version == TARGET_VERSION else None,
        source_path_id=audit["evidence"]["paths"][0]["path_id"], source_audit_sha256=digest(audit),
        source_snapshot_sha256=digest(snapshot), assessment_spec_sha256=digest(spec), assessment_spec=spec,
        parent_snapshot=snapshot, allowed_methods=choices)
    if len(json.dumps(source.model_dump(mode="json"), ensure_ascii=True).encode("ascii")) > 4_000_000:
        raise StandardReviewError("Review unavailable: the local source snapshot exceeds its safe input size.")
    if estimated_input_tokens(source) > 4000:
        raise StandardReviewError("Review unavailable: the trusted scope and evidence exceed the 4,000-token input budget.")
    return source


def _review_attack_profile(attack_profile_id, record):
    if record.target_profile_id == FRESH_TARGET_PROFILE_ID:
        _, attack, _, capability = validate_fresh_selection(
            attack_profile_id, record.vulnerability_profile_id,
            record.target_profile_id, record.scenario, "SINGLE", 1,
        )
        if capability["execution_capability"] != "EXECUTABLE":
            raise StandardReviewError(capability["capability_reason"])
        return attack
    attack, _ = validate_profile_selection(
        attack_profile_id, record.vulnerability_profile_id,
        record.target_profile_id, record.scenario,
    )
    return attack


def _job(record):
    return jobs.critic_job(runs.RUN_LOCK, record.run_id, record.critic_review_id) if record.critic_review_id else None


def _failed_review_code(record):
    if record.critic_status != "FAILED" or not record.critic_review_id:
        return None
    try:
        payload = runs._read_json(_directory(record) / "review.json")
    except (ValueError, OSError, KeyError, TypeError, RunStoreError):
        return None
    if payload.get("run_id") != record.run_id or payload.get("review_id") != record.critic_review_id:
        return None
    return payload.get("error_code")


def _validated_review(record):
    directory = _directory(record)
    if any((directory / name).is_symlink() or (directory / name).stat().st_size > 4_000_000 for name in ("input.json", "review.json")):
        raise StandardReviewError("Unsafe or oversized review source.")
    source = StandardReviewInput.model_validate(runs._read_json(directory / "input.json"))
    audit, spec = _verified_audit(record)
    if (source.source_audit_sha256 != digest(audit) or source.assessment_spec_sha256 != digest(spec)
            or source.source_snapshot_sha256 != digest(_redacted_snapshot(audit))):
        raise StandardReviewError("Saved review source has changed.")
    review = StandardReview.model_validate(runs._read_json(directory / "review.json"))
    output_schema(source)(recommendations=review.recommendations)
    if (review.schema_version != source.schema_version or review.run_id != record.run_id or review.review_id != record.critic_review_id
            or review.input_sha256 != digest(source.model_dump(mode="json"))
            or review.source_audit_sha256 != source.source_audit_sha256
            or review.assessment_spec_sha256 != source.assessment_spec_sha256
            or review.source_path_id != source.source_path_id
            or review.input_tokens_estimate != estimated_input_tokens(source)
            or any(review.budget.get(key) != expected for key, expected in {
                "max_provider_calls": 1, "provider_calls_attempted": 1, "provider_calls_succeeded": 1,
                "provider_calls_failed": 0, "provider_calls_in_flight": 0, "tokens_reserved": 0, "max_total_tokens": 4256}.items())
            or len(review.model_attempts) != 1 or review.model_attempts[0].get("role") != "ATTACK_CRITIC"
            or type(review.budget.get("tokens_consumed")) is not int or not 0 <= review.budget["tokens_consumed"] <= 4256
            or review.budget.get("token_budget_overrun") is not False or review.budget.get("cancelled") is not False
            or review.model_attempts[0].get("model") != review.model or review.model_attempts[0].get("profile_id") != review.model_profile_id
            or any(item.attack_profile_id not in {method.id for method in source.allowed_methods} for item in review.recommendations)):
        raise StandardReviewError("Review does not match its frozen source.")
    if record.critic_review_sha256 and record.critic_review_sha256 != digest(review.model_dump(mode="json")):
        raise StandardReviewError("Saved review hash mismatch.")
    managed = _job(record)
    current = jobs._current.get()
    publishing = managed and current is not None and current.job_id == managed["job_id"] and bool(current.verified_files)
    if not publishing:
        receipt = RunStore(runs.RUN_ROOT).job_receipt(managed["job_id"], "PUBLICATION") if managed else None
        if (not managed or not managed.get("worker_completion") or not receipt or receipt.get("outcome") != "COMPLETED"
                or receipt.get("attempt_id") != record.critic_review_id or receipt.get("critic_review_sha256") != record.critic_review_sha256):
            raise StandardReviewError("Review has no verified managed publication.")
    return review, source


def review_view(run_id):
    record = _record(run_id)
    base = {"run_id": run_id, "status": "READY", "attempts": record.critic_attempts,
            "review_id": record.critic_review_id, "job_id": None, "can_request": False, "can_retry": False,
            "review": None, "message": None}
    if record.execution_mode != "SINGLE":
        return {**base, "status": "NOT_APPLICABLE", "message": "Expanded assessments use their existing automatic guidance."}
    job = _job(record)
    base["job_id"] = job["job_id"] if job else None
    base["cancel_requested"] = bool(job and job.get("cancel_requested"))
    if record.critic_status == "COMPLETED":
        try:
            review, _ = _validated_review(record)
            payload = review.model_dump(mode="json")
            return {**base, "status": "COMPLETED", "review": payload, "review_canonical": canonical(payload), "review_sha256": digest(payload)}
        except (ValueError, OSError, KeyError, TypeError, RunStoreError):
            return {**base, "status": "UNAVAILABLE", "message": "Saved review failed source or publication verification. The assessment result is unchanged."}
    if job and job["state"] in {"UNCERTAIN", "RECONCILING"}:
        return {**base, "status": "UNCERTAIN", "message": "Provider completion is uncertain. Resolve the durable job before another attempt; no automatic replay is allowed."}
    if job and job["state"] in jobs.ACTIVE:
        return {**base, "status": "RUNNING"}
    try:
        _source(record)
    except (ValueError, OSError, KeyError, TypeError, RunStoreError) as error:
        return {**base, "status": "UNAVAILABLE", "message": str(error) if isinstance(error, StandardReviewError) else "Verified evidence is unavailable."}
    configured = get_settings().groq_critic_configured and runs.WORKER_PYTHON.exists()
    slot_free = not runs.RUN_LOCK.exists() and not jobs.JobLedger(runs.RUN_LOCK).active()
    failed = record.critic_status in {"RUNNING", "FAILED"}
    cancelled = job and (job["state"] == "CANCELLED" or job.get("cancel_requested"))
    retry_limit = 3 if _failed_review_code(record) == "INVALID_JSON" else 2
    return {**base, "status": "CANCELLED" if cancelled else "FAILED" if failed else "READY",
        "can_request": bool(configured and slot_free and not failed and record.critic_attempts == 0),
        "can_retry": bool(configured and slot_free and failed and record.critic_attempts < retry_limit),
        "message": record.critic_error_message if failed else "Another local worker is active or unresolved." if not slot_free else None if configured else "Dedicated Critic key and the pinned worker are required."}


def start_review(settings, run_id, retry=False):
    current = _record(run_id)
    view = review_view(run_id)
    if view["status"] == "COMPLETED":
        if jobs._request.get():
            runs._persist(current)
        return current
    if not (view["can_retry"] if retry else view["can_request"]):
        raise StandardReviewError(view["message"] or "This review cannot be requested in its current state.")
    attempt = current.model_copy(update={"critic_status": "RUNNING", "critic_review_id": f"standard-review-{uuid4().hex[:12]}",
        "critic_review_sha256": None, "critic_attempts": current.critic_attempts + 1, "critic_started_at": runs._now(),
        "critic_completed_at": None, "critic_error_code": None, "critic_error_message": None})
    source = _source(attempt)
    with runs._lock:
        if runs._runs.get(run_id) != current:
            raise StandardReviewError("Assessment changed while accepting the review.")
        if runs.RUN_LOCK.exists():
            raise StandardReviewError("Another local worker is active or unresolved.")
        try:
            session = jobs.prepare(runs.RUN_LOCK, run_id, "CRITIC", runs.RUN_ROOT)
            jobs.claim_projection(session)
        except FileExistsError as error:
            raise StandardReviewError("Another local inference operation is active or unresolved.") from error
        try:
            directory = _directory(attempt)
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "input.json").write_text(json.dumps(source.model_dump(mode="json"), ensure_ascii=True), encoding="ascii")
            runs._persist(attempt)
            runs._runs[run_id] = attempt
        except Exception:
            runs._release_run_lock(run_id)
            raise
    try:
        jobs.dispatch(execute_review, (run_id, settings), runs.RUN_LOCK, f"secmate-standard-review-{run_id}", thread_factory=threading.Thread)
    except Exception as error:
        _fail(run_id, "THREAD_START_FAILED")
        runs._release_run_lock(run_id)
        raise StandardReviewError("The review dispatch could not start.") from error
    return attempt


def _fail(run_id, code):
    with runs._lock:
        runs._update_locked(run_id, critic_status="FAILED", critic_completed_at=runs._now(), critic_error_code=code,
            critic_error_message="Review failed. Retry when ready.")


def execute_review(run_id, settings):
    record = _record(run_id)
    recovering = jobs.pending_recovery(runs.RUN_LOCK, run_id)
    if record.critic_status != "RUNNING" and not recovering:
        return  # Duplicate dispatcher notifications never create another job/call.
    return _execute_review_owned(run_id, settings)


@jobs.execution("CRITIC", lambda: runs.RUN_LOCK, lambda: runs.RUN_ROOT, lambda: runs._runs)
def _execute_review_owned(run_id, settings):
    process = None
    try:
        current = _record(run_id)
        directory = _directory(current)
        frozen = StandardReviewInput.model_validate(runs._read_json(directory / "input.json"))
        if frozen != _source(current, schema_version=frozen.schema_version):
            raise StandardReviewError("Frozen review input no longer matches the accepted source.")
        command = [str(runs.WORKER_PYTHON), "-m", "secmate_worker.standard_review", "--input", str(directory / "input.json"),
                   "--input-sha256", digest(frozen.model_dump(mode="json")), "--output", str(directory / "review.json")]
        environment = runs._worker_environment()
        environment.update({"GROQ_CRITIC_API_KEY": settings.groq_critic_api_key, "SECMATE_REQUEST_TIMEOUT_SECONDS": "45",
            "DEEPTEAM_TELEMETRY_OPT_OUT": "YES", "DEEPEVAL_TELEMETRY_OPT_OUT": "1", "TELEMETRY_OPT_OUT": "YES", "ERROR_REPORTING": "NO"})
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = jobs.launch(command, cwd=runs.WORKER_ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8", errors="replace", **options)
        with runs._lock:
            runs._processes[run_id] = process
            runs._write_run_lock(run_id, process.pid)
        process.communicate(timeout=120)
        if process.returncode != 0:
            _fail(run_id, "WORKER_REVIEW_FAILED")
            try:
                failure = runs._read_json(directory / "review.json")
                if (failure.get("input_sha256") == digest(frozen.model_dump(mode="json"))
                        and failure.get("run_id") == run_id and failure.get("review_id") == current.critic_review_id
                        and failure.get("error_code") in {"REQUEST_TIMEOUT", "READ_TIMEOUT", "WRITE_TIMEOUT", "NETWORK_ERROR"}):
                    session = jobs._current.get()
                    session.ledger.update(session.job_id, session.token, state="UNCERTAIN", authorized=False,
                        reason="REVIEW_PROVIDER_COMPLETION_UNCERTAIN", requires_explicit_resolution=True)
            except (ValueError, OSError, KeyError, TypeError, RunStoreError):
                pass
            return
        review, _ = _validated_review(_record(run_id))
        with runs._lock:
            runs._update_locked(run_id, critic_status="COMPLETED", critic_review_sha256=digest(review.model_dump(mode="json")),
                critic_completed_at=runs._now(), critic_error_code=None, critic_error_message=None)
    except Exception:
        if process is not None and process.poll() is None:
            runs._terminate_process(process)
        _fail(run_id, "REVIEW_FAILED_OR_UNCERTAIN")
    finally:
        if process is None or process.poll() is not None:
            with runs._lock:
                if runs._processes.get(run_id) is process:
                    runs._processes.pop(run_id, None)
            runs._release_run_lock(run_id)
        else:
            threading.Thread(target=runs._release_after_process_exit, args=(run_id, process, jobs._current.get()), daemon=True).start()


def create_linked_draft(run_id, review_id, attack_profile_id):
    parent = _record(run_id)
    review, source = _validated_review(parent)
    recommendation = next((item for item in review.recommendations if item.attack_profile_id == attack_profile_id), None)
    if review.review_id != review_id or recommendation is None:
        raise StandardReviewError("A current saved recommendation is required.")
    attack = _review_attack_profile(attack_profile_id, parent)
    guidance = evidence_projection(source)
    target_neutral = parent.target_profile_id != "synthetic-socmate-tier1"
    context = LinkedAssessmentContext(schema_version=TARGET_LINKED_VERSION if target_neutral else "socmate-linked-assessment-v1",
        parent_run_id=run_id, parent_path_id=source.source_path_id, review_id=review_id,
        review_sha256=digest(review.model_dump(mode="json")), source_audit_sha256=source.source_audit_sha256,
        assessment_spec_sha256=source.assessment_spec_sha256, target_profile_id=parent.target_profile_id,
        target_profile_version=parent.target_profile_version, vulnerability_profile_id=parent.vulnerability_profile_id,
        scenario_id=parent.scenario if target_neutral else None,
        scenario_version=parent.scenario_version if target_neutral else None,
        target_model_sha256=target_model_fingerprint(source.parent_snapshot["manifest"]["campaign"]),
        attack_profile_id=attack_profile_id, priority=recommendation.priority, redacted_parent_context=guidance,
        redacted_parent_context_sha256=digest(guidance) if target_neutral else None)
    with runs._lock:
        if runs._runs.get(run_id) != parent:
            raise StandardReviewError("Parent changed while creating the draft.")
        for child in runs._runs.values():
            if child.linked_context == context:
                if jobs._request.get():
                    runs._persist(child)
                return child
        payload = parent.model_dump(mode="json")
        attack_detail = attack.target_applicability.get(parent.target_profile_id, {})
        attack_admission = attack.target_experimental_admission.get(parent.target_profile_id, {})
        payload.update(run_id=f"api-run-{uuid4().hex[:12]}", status="DRAFT", created_at=runs._now(), started_at=None,
            completed_at=None, cancellation_requested_at=None, final_status=None, artifact_available=False,
            attack=attack.name, attack_profile_id=attack_profile_id, attack_applicability=attack.applicability,
            attack_capability_level=attack.capability_level,
            attack_target_applicability=attack_detail.get("applicability", "UNREVIEWED"),
            attack_applicability_reason=attack_detail.get("reason"),
            attack_experimental_admission=attack_admission.get("admission"),
            attack_experimental_admission_reason=attack_admission.get("reason"),
            linked_context=context.model_dump(mode="json"),
            logs=[runs._log("INFO", "Linked fresh assessment draft saved; no inference started.").model_dump(mode="json")])
        if parent.target_profile_id == FRESH_TARGET_PROFILE_ID:
            capability = fresh_selection_capability(
                attack, vulnerability_profile(parent.vulnerability_profile_id))
            payload.update(selection_admission=capability["admission"],
                execution_capability=capability["execution_capability"],
                execution_capability_code=capability["capability_code"],
                execution_capability_reason=capability["capability_reason"])
        for key in ("critic_status", "critic_review_id", "critic_review_sha256", "critic_started_at", "critic_completed_at", "critic_error_code", "critic_error_message"):
            payload[key] = None
        payload["critic_attempts"] = 0
        child = DeepTeamRunRecord.model_validate(payload)
        runs._persist(child)
        runs._runs[child.run_id] = child
        return child


def validate_linked_source(record):
    context = record.linked_context
    if context is None:
        raise StandardReviewError("No linked assessment context exists.")
    parent = _record(context.parent_run_id)
    review, source = _validated_review(parent)
    recommendation = next((item for item in review.recommendations if item.attack_profile_id == context.attack_profile_id), None)
    if (not recommendation or recommendation.priority != context.priority or review.review_id != context.review_id
            or record.attack_profile_id != context.attack_profile_id
            or record.target_profile_id != context.target_profile_id
            or record.target_profile_version != context.target_profile_version
            or record.vulnerability_profile_id != context.vulnerability_profile_id
            or context.target_profile_id != parent.target_profile_id
            or context.target_profile_version != parent.target_profile_version
            or context.vulnerability_profile_id != parent.vulnerability_profile_id
            or record.catalog_schema_version != parent.catalog_schema_version
            or context.schema_version == TARGET_LINKED_VERSION and (
                context.scenario_id != parent.scenario
                or context.scenario_version != parent.scenario_version
                or context.redacted_parent_context_sha256 != digest(context.redacted_parent_context)
            )
            or record.scenario != parent.scenario or record.scenario_version != parent.scenario_version
            or record.execution_mode != "SINGLE" or record.max_paths != 1
            or digest(review.model_dump(mode="json")) != context.review_sha256
            or source.source_audit_sha256 != context.source_audit_sha256
            or source.assessment_spec_sha256 != context.assessment_spec_sha256
            or source.source_path_id != context.parent_path_id
            or target_model_fingerprint(source.parent_snapshot["manifest"]["campaign"]) != context.target_model_sha256
            or evidence_projection(source) != context.redacted_parent_context):
        raise StandardReviewError("Linked assessment no longer matches its frozen parent recommendation.")
    _review_attack_profile(record.attack_profile_id, record)
    if record.target_profile_id == FRESH_TARGET_PROFILE_ID and record.catalog_schema_version != get_deepteam_catalog().schema_version:
        raise StandardReviewError("Linked assessment catalog binding is no longer current.")


def start_linked_draft(settings, run_id, max_total_tokens):
    current = _record(run_id)
    if current.status != "DRAFT":
        raise StandardReviewError("This draft has already started; open its saved run instead.")
    if not settings.groq_configured or not settings.openrouter_configured or not runs.WORKER_PYTHON.exists():
        raise StandardReviewError("Attacker, Judge and pinned worker configuration is required.")
    validate_linked_source(current)
    with runs._lock:
        if runs._runs.get(run_id) != current:
            raise StandardReviewError("Draft changed before Start.")
        runs._claim_run_lock(run_id)
        try:
            queued = DeepTeamRunRecord.model_validate({**current.model_dump(mode="json"), "status": "QUEUED", "max_total_tokens": max_total_tokens})
            runs._persist(queued)
            runs._runs[run_id] = queued
        except Exception:
            runs._release_run_lock(run_id)
            raise
    try:
        jobs.dispatch(runs._execute_run, (run_id, queued.attack_profile_id, queued.vulnerability_profile_id, max_total_tokens,
            "SINGLE", 1, queued.target_profile_id), runs.RUN_LOCK, f"secmate-linked-{run_id}", thread_factory=threading.Thread)
    except Exception as error:
        runs._fail(run_id, "THREAD_START_FAILED", "The linked assessment dispatch could not start.")
        runs._release_run_lock(run_id)
        raise StandardReviewError("The linked assessment dispatch could not start.") from error
    return queued
