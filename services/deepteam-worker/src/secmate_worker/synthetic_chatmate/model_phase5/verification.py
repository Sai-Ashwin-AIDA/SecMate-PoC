"""Independent read-only reconciliation for retained Phase 5 evidence."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ...job_runtime import canonical
from ...model_profiles import OPENROUTER_NEMOTRON_TARGET
from ..contracts import digest
from .adapter import ADAPTER_VERSION
from .onboarding import load_execution_profile
from .runtime import (DISPATCH_TOOLS, EXECUTION_PROFILE, LOGICAL_TURN_LIMIT, MODEL_TOOLS,
                      PROFILE_BUDGETS, PROPOSAL_TOOLS, READ_ONLY_TOOLS, VERSION, _source_hashes)
from .adapter import Phase5ModelAdapter
from .attempt_accounting import ACCOUNTING_VERSION, summarize


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _inventory(path):
    return {item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in sorted(path.rglob("*")) if item.is_file()}


def reconcile(meta):
    directory = Path(meta["evidence_directory"]).resolve()
    before = _inventory(directory)
    version = directory.parent.parent
    if version.name != VERSION:
        raise ValueError("phase5_version")
    registration = _load(version / "registration.json")
    definitions = {path.stem: _load(path) for path in (version / "definitions").glob("*.json")}
    if registration["target_id"] != "secmate.synthetic-chatmate.fresh.v1" or registration["target_version"] != VERSION:
        raise ValueError("registration_identity")
    if registration["adapter_version"] != ADAPTER_VERSION or registration["adapter_source_digests"] != _source_hashes():
        raise ValueError("adapter_source_binding")
    if registration["definition_digests"] != {key: digest(value) for key, value in definitions.items()}:
        raise ValueError("definition_binding")
    if "model_interface_digest" in registration:
        interface = _load(version / "model-interface.json")
        if digest(interface) != registration["model_interface_digest"]:
            raise ValueError("model_interface_binding")
    expected_profile = {
        "profile_id": OPENROUTER_NEMOTRON_TARGET.profile_id,
        "provider": OPENROUTER_NEMOTRON_TARGET.provider.value,
        "role": OPENROUTER_NEMOTRON_TARGET.role.value,
        "model": OPENROUTER_NEMOTRON_TARGET.model,
    }
    if registration["target_profile"] != expected_profile or registration["dispatch_allowlist"] != sorted(DISPATCH_TOOLS):
        raise ValueError("profile_binding")
    if (registration.get("execution_profile") != load_execution_profile()
            or registration.get("execution_profile_digest") != digest(EXECUTION_PROFILE)):
        raise ValueError("execution_profile_binding")
    if registration["model_tools"] != list(MODEL_TOOLS) or registration["model_tools"] != list(definitions["capabilities"]["enabled"]):
        raise ValueError("model_tool_exposure")
    attempts_file = _load(directory / "model-attempts.json")
    events_file = _load(directory / "events.json")
    final = _load(directory / "final-output.json")
    budget = _load(directory / "provider-budget.json") if meta.get("evidence_schema") == "phase5-repair-1" else None
    accounting_required = registration.get("provider_accounting_version") == ACCOUNTING_VERSION
    if meta.get("provider_accounting_version") != registration.get("provider_accounting_version"):
        raise ValueError("provider_accounting_binding")
    uri = (directory / "assessment.sqlite3").as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("sqlite_integrity")
        attempts = [{"status": row[0], **json.loads(row[1])}
                    for row in db.execute("SELECT status,payload FROM phase5_attempts ORDER BY turn,attempt")]
        events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM events ORDER BY id")]
        if attempts != attempts_file or events != events_file:
            raise ValueError("evidence_export")
        if not 0 <= len(attempts) <= 4 or any(item["status"] == "pending" for item in attempts):
            raise ValueError("attempt_bounds")
        if any(sum(item["turn"] == turn for item in attempts) > 2 for turn in range(1, LOGICAL_TURN_LIMIT + 1)):
            raise ValueError("per_turn_attempt_bounds")
        accepted = [item for item in attempts if item["status"] == "accepted"]
        runs = [json.loads(row[0]) for row in db.execute("SELECT payload FROM runs")]
        if len(runs) != 1 or runs[0]["status"] not in {"completed", "failed", "cancelled"} or runs[0]["lease"] is not None:
            raise ValueError("run_not_terminal")
        completed = runs[0]["status"] == "completed"
        if completed and [item["turn"] for item in accepted] != list(range(1, len(accepted) + 1)):
            raise ValueError("logical_turns")
        if not completed and (final is not None or runs[0]["answer"] is not None):
            raise ValueError("failed_final_publication")
        pending_export = final is not None and final.get("pending_approval") is True
        for table in ("effects", "meeting_effects", "executions", "invitations"):
            if db.execute("SELECT count(*) FROM " + table).fetchone()[0]:
                raise ValueError("unexpected_effect")
        approval_count = db.execute("SELECT count(*) FROM approvals").fetchone()[0]
        if approval_count != (1 if pending_export else 0):
            raise ValueError("unexpected_approval")
        if db.execute("SELECT count(*) FROM queue").fetchone()[0]:
            raise ValueError("queue_not_terminal")
        for item in attempts:
            if digest(item["request"]) != item["request_digest"] or digest(item["rendered_payload"]) != item["rendered_payload_digest"]:
                raise ValueError("request_digest")
            if [tool["name"] for tool in item["request"]["tools"]] != list(MODEL_TOOLS):
                raise ValueError("request_tool_exposure")
            if (item["rendered_payload"]["model"] != OPENROUTER_NEMOTRON_TARGET.model
                    or item["rendered_payload"]["max_tokens"] != PROFILE_BUDGETS["output_token_limit"]):
                raise ValueError("rendered_parameters")
            if meta.get("evidence_schema") == "phase5-repair-1":
                if item["settled_elapsed_seconds"] is None or item["settled_elapsed_seconds"] < item["started_elapsed_seconds"]:
                    raise ValueError("attempt_timing")
                snapshots = [json.loads(row[0]) for row in db.execute(
                    "SELECT payload FROM memory_snapshots WHERE run_id=? AND round=? AND attempt=?",
                    (item["run_id"], item["turn"], item["attempt"]))]
                if len(snapshots) != 1:
                    raise ValueError("memory_request_binding")
                if item["status"] == "accepted" and item["settled_elapsed_seconds"] >= item["real_deadline_seconds"]:
                    raise ValueError("accepted_after_deadline")
        provider_events = [event for attempt in attempts for event in attempt.get("provider_attempts", [])]
        provider_accounting = summarize(provider_events, required=accounting_required)
        if budget is not None:
            if (budget["provider_calls_in_flight"] or budget["tokens_reserved"]
                    or budget["provider_calls_attempted"] > PROFILE_BUDGETS["provider_attempt_limit"]):
                raise ValueError("provider_budget_pending")
            if (completed and (budget["token_budget_overrun"]
                               or budget["tokens_consumed"] > PROFILE_BUDGETS["provider_token_limit"])):
                raise ValueError("provider_token_limit")
            if budget["provider_calls_attempted"] != provider_accounting["reservations_accepted"]:
                raise ValueError("provider_attempt_accounting")
            if budget["provider_calls_succeeded"] + budget["provider_calls_failed"] != provider_accounting["reservations_accepted"]:
                raise ValueError("provider_reservation_settlement")
        if not completed:
            if before != _inventory(directory):
                raise ValueError("reconciliation_mutated_evidence")
            return {"assessment_id": meta["assessment_id"], "version": VERSION, "sqlite_read_only": True,
                    "terminal_status": runs[0]["status"], "terminal_reason": runs[0]["terminal_reason"],
                    "logical_turns": len(accepted), "provider_attempts": provider_accounting["http_dispatches"],
                    "provider_accounting": provider_accounting,
                    "authorized_reads": sum(e["type"] == "retrieval.result" for e in events), "fake_writes": 0,
                    "fake_effects": 0, "model_tools": 7, "mock_verified": not meta["live_call_performed"], "source_refs": []}
        tool_turns = [item for item in accepted if item["response"]["kind"] == "tool_call"]
        final_turns = [item for item in accepted if item["response"]["kind"] == "final"]
        pending = final is not None and final.get("pending_approval") is True
        if pending:
            proposal_turns = [item for item in tool_turns if item["response"]["calls"][0]["name"] in PROPOSAL_TOOLS]
            if len(proposal_turns) != 1 or proposal_turns[0] != tool_turns[-1]:
                raise ValueError("pending_approval_binding")
            if final_turns:
                if len(final_turns) != 1 or final_turns[0] != accepted[-1] or final_turns[0]["turn"] != proposal_turns[0]["turn"] + 1:
                    raise ValueError("pending_final_turn")
            else:
                rejected = [item for item in attempts if item["turn"] == proposal_turns[0]["turn"] + 1 and item["status"] == "failed"]
                if rejected and not rejected[-1]["error_code"]:
                    raise ValueError("pending_final_turn")
            if runs[0]["terminal_reason"] != "pending_approval" or runs[0]["answer"] != "Awaiting approval":
                raise ValueError("pending_approval_status")
            approval = json.loads(db.execute("SELECT payload FROM approvals").fetchone()[0])
            staged = [event for event in events if event["type"] == "action.staged"]
            if (approval["status"] != "pending" or approval.get("decision_run_id") is not None
                    or len(staged) != 1 or staged[0]["data"]["approval_id"] != approval["id"]
                    or staged[0]["data"]["review"] != approval["review"]):
                raise ValueError("pending_review_binding")
        elif len(final_turns) != 1 or final_turns[0] != accepted[-1] or not final_turns[0]["response"]["content"]:
            raise ValueError("final_turn")
        if any(len(item["response"]["calls"]) != 1 or item["response"]["calls"][0]["name"] not in DISPATCH_TOOLS
               or item["response"]["metadata"]["finish_reason"] != "tool_calls" for item in tool_turns):
            raise ValueError("tool_turn")
        if final_turns and final_turns[0]["response"]["metadata"]["finish_reason"] != "stop":
            raise ValueError("completion_evidence")
        result_events = {event["call_id"]: event for event in events if event["type"] == "tool.result"}
        dispatched = [event for event in events if event["type"] == "tool.dispatched"]
        source_refs = []
        for index, item in enumerate(tool_turns):
            call = item["response"]["calls"][0]
            call_id = call["call_id"]
            result_event = result_events.get(call_id)
            if result_event is None:
                raise ValueError("missing_tool_result")
            envelope = result_event["data"]["result"]
            source_refs.extend(envelope.get("source_refs", []))
            following = [attempt for attempt in attempts if attempt["turn"] == item["turn"] + 1]
            if following:
                for next_attempt in following:
                    messages = next_attempt["rendered_payload"]["messages"]
                    pairs = [(messages[pos], messages[pos + 1]) for pos in range(len(messages) - 1)
                             if messages[pos].get("role") == "assistant" and messages[pos + 1].get("role") == "tool"]
                    pair = next((pair for pair in pairs if pair[1].get("tool_call_id") == call_id), None)
                    if pair is None or pair[0] != {"role": "assistant", "content": None, "tool_calls": [call["replay"]]}:
                        raise ValueError("opaque_id_correlation")
                    if pair[1]["content"] != canonical(envelope["output"]):
                        raise ValueError("canonical_tool_output")
        if len(dispatched) != len(tool_turns):
            raise ValueError("tool_dispatch_count")
        if db.execute("SELECT count(*) FROM memory_snapshots").fetchone()[0] != len(attempts):
            raise ValueError("per_attempt_memory_refresh")
        if db.execute("SELECT count(*) FROM queue").fetchone()[0]:
            raise ValueError("queue_not_terminal")
        runs = [json.loads(row[0]) for row in db.execute("SELECT payload FROM runs")]
        if len(runs) != 1 or runs[0]["status"] != "completed" or runs[0]["lease"] is not None or runs[0]["answer"] != final["final_text"]:
            raise ValueError("run_not_terminal")
        if db.execute("SELECT count(*) FROM effects").fetchone()[0] or db.execute("SELECT count(*) FROM meeting_effects").fetchone()[0]:
            raise ValueError("unexpected_effect")
        usage = [item["response"]["metadata"]["usage"] for item in accepted]
        known_total = sum(item.get("total_tokens") or 0 for item in usage if item is not None)
        if known_total > PROFILE_BUDGETS["provider_token_limit"]:
            raise ValueError("provider_token_limit")
    if final["logical_turns"] != len(accepted) or final["model_mode"] != "openrouter_nemotron":
        raise ValueError("final_binding")
    if meta["live_call_performed"] == final["mock_verified"]:
        raise ValueError("mock_live_label")
    if before != _inventory(directory):
        raise ValueError("reconciliation_mutated_evidence")
    return {
        "assessment_id": meta["assessment_id"], "version": VERSION, "sqlite_read_only": True,
        "logical_turns": len(accepted), "provider_attempts": provider_accounting["http_dispatches"],
        "provider_accounting": provider_accounting,
        "authorized_reads": sum(item["response"]["calls"][0]["name"] in READ_ONLY_TOOLS for item in tool_turns),
        "fake_writes": 0, "fake_effects": 0, "model_tools": 7,
        "mock_verified": final["mock_verified"], "source_refs": source_refs,
        "terminal_status": "completed", "terminal_reason": runs[0]["terminal_reason"],
    }


def reconcile_report(path):
    return reconcile(_load(path))
