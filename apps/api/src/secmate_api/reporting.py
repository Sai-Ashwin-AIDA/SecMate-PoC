"""Read-only report snapshots. Original captures stay separate from model inputs."""
from . import chatmate_runs as chat, chatmate_critic as critic, deepteam_runs as soc
from .run_store import RunStore, RunStoreError, digest


def chatmate_report_data(run_id):
    run = chat.get_chatmate_run(run_id)
    if run is None:
        return None
    audit = chat.get_chatmate_audit(run_id) if run.artifact_available else None
    if run.artifact_available and audit is None:
        raise RunStoreError("Report evidence failed verification.")
    original = RunStore(chat.CHATMATE_RUN_ROOT).original_evidence(run_id)
    manual = run.manual_evidence
    candidate = next((item for item in run.candidate_batch.candidates if item.candidate_id == run.selected_candidate_id), None) if run.candidate_batch else None
    if original is not None:
        if (manual is None or candidate is None or original.get("candidate_sha256") != run.selected_candidate_sha256
                or original.get("correlation_sha256") != manual.correlation_sha256 or original.get("prompt") != candidate.prompt
                or original.get("response_sha256") != (chat._sha256(original["response_text"]) if original.get("response_text") is not None else None)):
            raise RunStoreError("Original capture differs from accepted evidence.")
    elif manual is not None and candidate is not None and not manual.redaction_applied:
        # Historical unchanged captures can be recovered exactly; masked ones cannot.
        if manual.redacted_response_text is not None and chat._sha256(manual.redacted_response_text) != manual.persisted_response_sha256:
            raise RunStoreError("Historical capture failed verification.")
        original = {"run_id": run_id, "prompt": candidate.prompt, "response_text": manual.redacted_response_text,
                    "candidate_sha256": candidate.prompt_sha256, "correlation_sha256": manual.correlation_sha256,
                    "response_sha256": manual.persisted_response_sha256}
    review, critic_error = None, None
    if audit is not None and run.critic_status == "COMPLETED":
        try:
            review = critic._validated_review(run).model_dump(mode="json")
        except (ValueError, OSError, KeyError, TypeError, chat.ChatMateRunError, RunStoreError):
            critic_error = "Critic verification failed; Judge evidence remains independently verified."
    latest = chat.get_chatmate_run(run_id)
    if latest is None or digest(latest.model_dump(mode="json")) != digest(run.model_dump(mode="json")):
        raise RunStoreError("Saved report changed during verification. Retry the read.")
    return {"source": "ChatMate", "run": run.model_dump(mode="json"),
             "audit": audit.model_dump(mode="json") if audit else None, "original": original, "critic": review,
             "critic_error": critic_error}


def socmate_report_data(run_id):
    run = soc.get_deepteam_run(run_id)
    if run is None:
        return None
    audit = soc.get_deepteam_audit(run_id) if run.artifact_available else None
    if run.artifact_available and audit is None:
        raise RunStoreError("Report evidence failed verification.")
    original = RunStore(soc.RUN_ROOT).original_evidence(run_id)
    if original is not None and (audit is None or digest(soc._redact_payload(original)) != digest(audit.model_dump(mode="json"))):
        raise RunStoreError("Original output differs from the accepted audit.")
    latest = soc.get_deepteam_run(run_id)
    if latest is None or digest(latest.model_dump(mode="json")) != digest(run.model_dump(mode="json")):
        raise RunStoreError("Saved report changed during verification. Retry the read.")
    from .standard_reviews import review_view
    advisory = review_view(run_id) if run.critic_review_id else None
    last = soc.get_deepteam_run(run_id)
    if last is None or digest(last.model_dump(mode="json")) != digest(run.model_dump(mode="json")):
        raise RunStoreError("Saved report changed while loading its advisory. Retry the read.")
    target = {"id": run.target_profile_id, "name": run.target_name or (
        "SocMate" if run.target_profile_id == "synthetic-socmate-tier1" else run.target_profile_id),
        "version": run.target_profile_version, "scenario_id": run.scenario,
        "scenario_version": run.scenario_version}
    source = "SocMate" if run.target_profile_id == "synthetic-socmate-tier1" else (
        "Synthetic ChatMate" if run.target_profile_id == "secmate.synthetic-chatmate.fresh.v1" else run.target_name or run.target_profile_id)
    return {"source": source, "target": target, "run": run.model_dump(mode="json"),
            "audit": audit.model_dump(mode="json") if audit else None, "original": original,
            "standard_review": advisory}
