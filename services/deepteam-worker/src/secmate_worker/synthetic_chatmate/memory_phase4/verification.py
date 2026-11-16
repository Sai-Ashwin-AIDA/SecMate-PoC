"""Independent read-only reconciliation for saved 0.4.0 evidence."""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .artifacts import MemoryBundle
from .contracts import VERSION, validate_event, validate_root
from .evidence import observations, selected_observation
from .services import active_facts, evaluate, owner_meta, owner_state, fact_ref


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def _inventory(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.rglob("*")) if p.is_file()}


def reconcile(meta):
    directory = Path(meta["evidence_directory"]); before = _inventory(directory)
    version = directory.parent.parent
    if version.name != VERSION: raise ValueError("memory_version")
    definitions = {p.stem: _load(p) for p in (version / "definitions").glob("*.json")}
    bundle = MemoryBundle.from_parts(definitions); registration = _load(version / "registration.json")
    if len(definitions) != 29 or registration["definition_digests"] != {k: _sha(v) for k, v in definitions.items()}: raise ValueError("definition_binding")
    bindings, events = _load(directory / "bindings.json"), _load(directory / "events.json")
    faults = _load(directory / "faults.json")
    restricted = _load(directory / "restricted-truth.json") if (directory / "restricted-truth.json").exists() else None
    if bindings["artifact_digests"] != registration["definition_digests"]: raise ValueError("assessment_binding")
    source = Path(__file__).parents[1]
    for key, expected in definitions["implementation"].items():
        prefix, _, filename = key.partition("/")
        path = source / filename if prefix == "phase1" else source / key
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected: raise ValueError("implementation_binding")
    uri = (directory / "assessment.sqlite3").resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise ValueError("sqlite_integrity")
        if db.execute("PRAGMA foreign_key_check").fetchall(): raise ValueError("sqlite_foreign_key")
        required_triggers = {"memory_facts_no_update", "memory_facts_no_insert", "memory_owners_identity_immutable",
            "memory_context_identity_immutable", "memory_context_sticky", "memory_controls_prepared_immutable",
            "memory_controls_settled_immutable", "memory_controls_transition", "memory_facts_delete_guard", "memory_owner_state_guard",
            "memory_owner_digest_guard", "memory_context_state_guard", "memory_mutation_insert_guard"}
        actual_triggers = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not required_triggers <= actual_triggers: raise ValueError("sqlite_guard_missing")
        ledger = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY id")]
        if ledger != events: raise ValueError("event_export")
        previous = None
        for event in events:
            validate_event(event)
            if event["caused_by"] != (previous["event_id"] if previous else None): raise ValueError("event_cause")
            previous = event
        rows = lambda table: [json.loads(row[0]) for row in db.execute("SELECT payload FROM " + table + " ORDER BY rowid")]
        state = rows("state")[0]
        runs = {run["id"]: run for run in rows("runs")}
        queue = [row[0] for row in db.execute("SELECT run_id FROM queue ORDER BY seq")]
        if state["assessment_id"] != meta["assessment_id"] or state["generation"] != bindings["state_generation"]: raise ValueError("state_identity")
        if queue: raise ValueError("queue_not_terminal")
        if any(run["lease"] is not None or run["status"] not in {"completed", "failed", "cancelled"} for run in runs.values()): raise ValueError("run_not_terminal")
        owner_count = db.execute("SELECT count(*) FROM memory_owners").fetchone()[0]
        fact_count = db.execute("SELECT count(*) FROM memory_facts").fetchone()[0]
        controls = db.execute("SELECT count(*) FROM memory_controls").fetchone()[0]
        snapshots = db.execute("SELECT count(*) FROM memory_snapshots").fetchone()[0]
        for row in db.execute("SELECT conversation_id,assessment_id,state_generation,owner,tenant,revision,memory_disabled,payload FROM memory_contexts"):
            context = json.loads(row[7]); validate_root("Context", context)
            if tuple(context[k] for k in ("conversation_id", "assessment_id", "state_generation", "owner", "tenant", "revision")) != row[:6] or int(context["memory_disabled"]) != row[6]:
                raise ValueError("context_columns")
        seed_owners = [(r[0], r[1], json.loads(r[2])) for r in db.execute("SELECT owner,tenant,payload FROM memory_owner_seed ORDER BY owner")]
        expected_owners = sorted(definitions["memory_seed"]["owners"], key=lambda value: value["owner"])
        if [r[2] for r in seed_owners] != expected_owners: raise ValueError("memory_owner_seed")
        seed_facts = [json.loads(r[0]) for r in db.execute("SELECT payload FROM memory_fact_seed ORDER BY owner,ordinal")]
        if seed_facts != sorted(definitions["memory_seed"]["facts"], key=lambda value: (value["owner"], value["ordinal"])): raise ValueError("memory_fact_seed")
        for owner, tenant, revision, enabled, preferences, cached in db.execute("SELECT * FROM memory_owners"):
            facts = [json.loads(r[0]) for r in db.execute("SELECT payload FROM memory_facts WHERE owner=? ORDER BY ordinal", (owner,))]
            state = owner_state({"owner": owner, "tenant": tenant, "revision": revision, "enabled": bool(enabled), "preferences": json.loads(preferences)}, facts)
            if _sha(state) != cached: raise ValueError("owner_state_digest")
            if restricted:
                exported = next((item for item in restricted["memory"]["owner_states"] if item["owner"] == owner), None)
                if exported != state: raise ValueError("owner_state_export")
        journals = {r[0]: json.loads(r[1]) for r in db.execute("SELECT control_id,payload FROM memory_mutations ORDER BY rowid")}
        chains = {}
        for journal in journals.values():
            validate_root("MutationJournal", journal)
            owner = journal["before_owner"]["owner"]
            if owner in chains and chains[owner] != journal["before_owner"]: raise ValueError("journal_chain")
            chains[owner] = journal["after_owner"]
        controls_by_id = {control["id"]: control for control in _restricted_controls(db)}
        accepted_events = {e["data"]["control_id"]: e for e in events if e["type"] == "memory.control.accepted"}
        finished_events = {e["data"]["control_id"]: e for e in events if e["type"] == "memory.control.finished"}
        for control_id, body, input_digest, result, result_digest, status in db.execute("SELECT id,body,input_digest,result,result_digest,status FROM memory_controls"):
            parsed_body, parsed_result = json.loads(body), json.loads(result) if result else None
            if _sha(parsed_body) != input_digest: raise ValueError("control_input_digest")
            if (parsed_result is None) != (result_digest is None) or parsed_result is not None and _sha(parsed_result) != result_digest: raise ValueError("control_result_digest")
            if status in {"accepted", "applying", "cancel_requested"} and parsed_result is not None: raise ValueError("unsettled_result")
            control = controls_by_id[control_id]
            if control["deadline_seconds"] != control["accepted_seconds"] + 60: raise ValueError("control_deadline")
            accepted = accepted_events.get(control_id)
            finished = finished_events.get(control_id)
            if accepted is None or accepted["data"]["deadline_seconds"] != control["deadline_seconds"] or accepted["logical_time"] != _logical(control["accepted_seconds"]):
                raise ValueError("control_acceptance_time")
            if status not in {"accepted", "applying", "cancel_requested"} and (finished is None or finished["event_id"] <= accepted["event_id"]):
                raise ValueError("control_terminal_order")
            if status not in {"accepted", "applying", "cancel_requested"}: validate_root("ControlRecord", controls_by_id[control_id])
            if status in {"applied", "already_disabled"}:
                journal = journals.get(control_id)
                if not journal or journal["control_id"] != control_id or parsed_result["operation"] != parsed_body["operation"]: raise ValueError("mutation_journal")
                if parsed_result["removed_fact_refs"] != [fact_ref(f) for f in journal["removed_facts"]]: raise ValueError("removed_refs")
                _verify_control(control_id, parsed_body, parsed_result, status, journal, events)
        for run_id, round_number, attempt, payload in db.execute("SELECT run_id,round,attempt,payload FROM memory_snapshots"):
            record = json.loads(payload); snapshot = record["snapshot"]
            if (record["run_id"], snapshot["round"], snapshot["attempt"]) != (run_id, round_number, attempt): raise ValueError("snapshot_key")
            if _sha(record["candidate"]) != snapshot["expected_payload_digest"]: raise ValueError("snapshot_candidate")
            if record["candidate"] is not None and [f["source_ref"] for f in record["candidate"]["facts"]] != snapshot["selected_refs"]: raise ValueError("snapshot_refs")
            _verify_snapshot(record, definitions["memory_seed"], events)
        stored_outputs = [json.loads(r[0]) for r in db.execute("SELECT payload FROM memory_host_outputs ORDER BY id")]
        fault_hits = rows("memory_fault_hits")
        _verify_faults(faults, fault_hits, controls_by_id, accepted_events, finished_events)
        expected_counters = {"checks_remaining": max(0, definitions["budget"]["memory_checks"] - sum(json.loads(r[0])["snapshot"]["status"] != "ineligible" for r in db.execute("SELECT payload FROM memory_snapshots"))),
            "controls_remaining": max(0, definitions["budget"]["memory_controls"] - len(controls_by_id))}
        if restricted and restricted["memory"]["counters"] != expected_counters: raise ValueError("memory_counters")
        fence_rows = db.execute("SELECT control_id,owner,persistence_fenced FROM memory_control_fence").fetchall()
        if len(fence_rows) > 1: raise ValueError("control_fence_count")
        fence = None if not fence_rows else {"control_id": fence_rows[0][0], "owner": fence_rows[0][1], "persistence_fenced": bool(fence_rows[0][2])}
        if fence:
            fenced_control = controls_by_id.get(fence["control_id"])
            if not fenced_control or fenced_control["owner"] != fence["owner"] or not fence["persistence_fenced"] or fenced_control["status"] not in {"applying", "cancel_requested"}:
                raise ValueError("control_fence_state")
        if restricted and restricted["memory"]["fence"] != fence: raise ValueError("control_fence_export")
        inherited_counts = _verify_inherited(db, events, runs, definitions)
        if restricted:
            validate_root("RestrictedMemoryState", restricted["memory"])
            if restricted["memory"]["journals"] != list(journals.values()): raise ValueError("journal_export")
            if restricted["memory"]["snapshots"] != [json.loads(r[0]) for r in db.execute("SELECT payload FROM memory_snapshots ORDER BY rowid")]: raise ValueError("snapshot_export")
            if restricted["memory"]["fault_hits"] != fault_hits: raise ValueError("fault_hit_export")
    host = _load(directory / "memory-host-outputs.json") if (directory / "memory-host-outputs.json").exists() else []
    if host != stored_outputs: raise ValueError("host_output_export")
    for output in host:
        validate_root("HostOutput", output)
        control = controls_by_id.get(output["control_id"])
        if not control: raise ValueError("host_output_control")
        if output["owner"] != control["owner"]: raise ValueError("host_output_owner")
        if output["response"]["status"] != "outcome_unknown" and output["response"] != control["result"]: raise ValueError("host_output_result")
        if output["is_replay"]:
            replay = [e for e in events if e["type"] == "memory.control.replayed" and e["data"]["control_id"] == output["control_id"] and e["data"]["response_digest"] == output["response_digest"]]
            if not replay: raise ValueError("replay_event_output")
    recomputed = observations(events, bundle, host)
    if (directory / "observations.json").exists() and _load(directory / "observations.json") != recomputed: raise ValueError("observation_export")
    if (directory / "missing-memory-request-binding-events.json").exists():
        selected = _load(directory / "missing-memory-request-binding-events.json")
        saved = _load(directory / "missing-memory-request-binding-observation.json")
        if saved != selected_observation(selected, bundle) or saved["result"] != "inconclusive": raise ValueError("selected_export")
    if before != _inventory(directory): raise ValueError("reconciliation_mutated_evidence")
    return {"assessment_id": meta["assessment_id"], "version": VERSION, "sqlite_read_only": True, "owners": owner_count,
            "facts": fact_count, "controls": controls, "snapshots": snapshots, "events": len(events), "queue_terminal": True,
            "runs_terminal": len(runs), "counters": expected_counters, "fence": fence, **inherited_counts}


def _restricted_controls(db):
    for row in db.execute("SELECT * FROM memory_controls ORDER BY ordinal"):
        yield {"id": row[0], "ordinal": row[1], "assessment_id": row[2], "state_generation": row[3], "owner": row[4], "tenant": row[5],
            "body": json.loads(row[6]), "input_digest": row[7], "status": row[8], "result": json.loads(row[9]) if row[9] else None,
            "result_digest": row[10], "accepted_seconds": row[11], "deadline_seconds": row[12]}


def _restricted_controls_from_file(restricted):
    return restricted["memory"]["controls"] if restricted else []


def _logical(seconds):
    value = datetime(2030, 1, 7, 9, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z").replace(".000000Z", "Z")


def _verify_faults(plan, hits, controls, accepted, finished):
    scheduled = {(item["ordinal"], item["phase"]): item for item in plan["memory"]["controls"]}
    scheduled.update({(item["round"], item["attempt"], "load"): item for item in plan["memory"]["loads"]})
    for hit in hits:
        validate_root("MemoryFaultHit", hit)
        key = (hit["round"], hit["attempt"], "load") if hit["kind"] == "load" else (hit["ordinal"], hit["phase"])
        if key not in scheduled: raise ValueError("unscheduled_fault_hit")
        if hit["kind"] == "control":
            control = controls.get(hit["control_id"])
            if not control or control["ordinal"] != hit["ordinal"]: raise ValueError("fault_control_identity")
            if hit["status"] != "not_reached" and not (control["accepted_seconds"] <= hit["before_seconds"] <= hit["after_seconds"] <= hit["deadline_seconds"]):
                raise ValueError("fault_control_time")
            if hit["control_id"] in finished and finished[hit["control_id"]]["event_id"] <= accepted[hit["control_id"]]["event_id"]:
                raise ValueError("fault_terminal_order")


def _verify_inherited(db, events, runs, definitions):
    rows = lambda table: [json.loads(row[0]) for row in db.execute("SELECT payload FROM " + table + " ORDER BY rowid")]
    approvals = {item["id"]: item for item in rows("approvals")}
    executions = {item["id"]: item for item in rows("executions")}
    effects = rows("effects")
    meeting_effects = rows("meeting_effects")
    records = {item["id"]: item for item in rows("calendar_records")}
    invitations = rows("invitations")
    projections = rows("calendar_projections")
    for execution in executions.values():
        approval = approvals.get(execution["approval_id"])
        if not approval or execution["decision_run_id"] != approval["decision_run_id"] or execution["prepared_digest"] != approval["prepared_digest"]:
            raise ValueError("inherited_execution_binding")
        run = runs.get(execution["decision_run_id"])
        if not run or run.get("decision_result", {}).get("execution_status") != execution["status"]: raise ValueError("inherited_run_result")
        if execution["dispatch"] is not None and _sha(execution["dispatch"]) != execution["dispatch_digest"]: raise ValueError("inherited_dispatch_digest")
    for effect in effects:
        execution = executions.get(effect["execution_id"])
        if not execution or execution["status"] != "succeeded" or effect["dispatch_digest"] != execution["dispatch_digest"]: raise ValueError("message_effect_binding")
        completed = [e for e in events if e["type"] == "action.completed" and e["data"].get("execution_id") == execution["id"]]
        if len(completed) != 1 or completed[0]["data"].get("receipt") != execution["receipt"]: raise ValueError("message_receipt_binding")
    for effect in meeting_effects:
        execution, approval = executions.get(effect["execution_id"]), approvals.get(effect["approval_id"])
        record = records.get(effect["event_id"])
        if not execution or not approval or not record or effect["calendar_record"] != record or effect["dispatch_digest"] != execution["dispatch_digest"] or effect["prepared_digest"] != approval["prepared_digest"]:
            raise ValueError("meeting_effect_binding")
        actual_invitations = [item for item in invitations if item["effect_id"] == effect["effect_id"]]
        actual_projections = [item for item in projections if item["effect_id"] == effect["effect_id"]]
        if [item["attendee_id"] for item in actual_invitations] != record["attendee_ids"] or len(actual_projections) != len(record["attendee_ids"]) + 1: raise ValueError("meeting_projection_binding")
        witness = [e for e in events if e["type"] == "meeting.record_committed" and e["data"]["execution_id"] == execution["id"]]
        committed = [e for e in events if e["type"] == "meeting.invitations_committed" and e["data"]["execution_id"] == execution["id"]]
        if len(witness) != 1 or len(committed) != 1 or witness[0]["data"]["record"] != record or witness[0]["data"]["record_digest"] != _sha(record): raise ValueError("meeting_public_witness")
        if committed[0]["data"]["record_digest"] != _sha(record) or execution["receipt"]["invitation_ids"] != [item["id"] for item in actual_invitations]: raise ValueError("meeting_receipt_binding")
    return {"approvals": len(approvals), "executions": len(executions), "message_effects": len(effects), "meeting_effects": len(meeting_effects), "invitations": len(invitations)}


def _verify_control(control_id, body, result, status, journal, events):
    accepted = next((e for e in events if e["type"] == "memory.control.accepted" and e["data"]["control_id"] == control_id), None)
    committed = next((e for e in events if e["type"] == "memory.control.committed" and e["data"]["control_id"] == control_id), None)
    if not accepted or not committed or accepted["event_id"] >= committed["event_id"]: raise ValueError("control_event_order")
    if accepted["data"]["body"] != body or accepted["data"]["input_digest"] != journal["input_digest"]: raise ValueError("control_event_identity")
    operation, before, after = body["operation"], journal["before_owner"], journal["after_owner"]
    if before["owner"] != after["owner"] or before["tenant"] != after["tenant"]: raise ValueError("control_scope")
    if operation != "fixture_context_change" and body["expected_revision"] != before["revision"]: raise ValueError("control_cas")
    if operation in {"forget", "clear", "fixture_set_enabled"} and after["revision"] != before["revision"] + 1: raise ValueError("control_revision")
    if operation in {"disable_conversation", "fixture_context_change"} and after != before: raise ValueError("context_changed_owner")
    if operation == "forget" and (len(journal["removed_facts"]) != 1 or journal["removed_facts"][0]["id"] != body["fact_id"]): raise ValueError("forget_rows")
    if operation == "clear" and len(journal["removed_facts"]) != len(before["facts"]): raise ValueError("clear_rows")
    if operation in {"disable_conversation", "fixture_context_change"}:
        cb, ca = journal["before_context"], journal["after_context"]
        if cb is None or ca is None or body["expected_context_revision"] != cb["revision"]: raise ValueError("context_cas")
        if operation == "disable_conversation" and (not ca["memory_disabled"] or ca["revision"] not in {cb["revision"], cb["revision"] + 1}): raise ValueError("disable_transition")
        if operation == "fixture_context_change" and ca["revision"] != cb["revision"] + 1: raise ValueError("fixture_context_transition")
    expected_event = {"control_id": control_id, "operation": operation, "input_digest": journal["input_digest"],
        "owner_before": owner_meta({k: before[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}, before["facts"]),
        "owner_after": owner_meta({k: after[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}, after["facts"]),
        "context_before": journal["before_context"], "context_after": journal["after_context"], "affected_run_ids": journal["affected_run_ids"],
        "removed_fact_refs": [fact_ref(f) for f in journal["removed_facts"]], "commit_seconds": journal["commit_seconds"], "committed_at": _logical(journal["commit_seconds"])}
    if committed["data"] != expected_event: raise ValueError("committed_event_journal")
    if result["operation"] != operation or result["removed_fact_refs"] != expected_event["removed_fact_refs"] or result["state_digest"] != expected_event["owner_after"]["state_digest"]:
        raise ValueError("control_result_journal")


def _verify_snapshot(record, seed, events):
    snapshot, candidate = record["snapshot"], record["candidate"]
    if snapshot["read_at"] != _logical(snapshot["read_seconds"]): raise ValueError("snapshot_time")
    if snapshot["status"] == "unavailable":
        if candidate is not None or snapshot["selected_refs"]: raise ValueError("unavailable_snapshot_payload")
        return
    owner = snapshot["eligibility"]["context"]["owner"]
    header = next(o for o in seed["owners"] if o["owner"] == owner)
    facts = [f for f in seed["facts"] if f["owner"] == owner]
    snapshot_event = next(e for e in events if e["type"] in {"memory.context_loaded", "memory.context_refreshed"} and e["data"]["snapshot_id"] == snapshot["snapshot_id"])
    for event in events:
        if event["event_id"] >= snapshot_event["event_id"]: break
        if event["type"] != "memory.control.committed" or event["data"]["owner_before"]["owner"] != owner: continue
        data = event["data"]; operation = data["operation"]
        facts = [f for f in facts if f["id"] not in {r["resource_id"] for r in data["removed_fact_refs"]}]
        header = {**header, "revision": data["owner_after"]["revision"], "enabled": data["owner_after"]["enabled"]}
    expected_status, expected_reason, expected_candidate = evaluate(snapshot["eligibility"], header, facts, snapshot["read_seconds"])
    if (snapshot["status"], snapshot["reason"], candidate) != (expected_status, expected_reason, expected_candidate): raise ValueError("snapshot_selection")


def reconcile_report(path):
    report = _load(path)
    return {name: reconcile(meta) for name, meta in report["scenarios"].items()}
