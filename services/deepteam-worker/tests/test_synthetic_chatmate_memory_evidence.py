"""Phase 4 evidence suppression and read-only reconciliation tests."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest
from offline_synthetic_guard import forbid_network

from secmate_worker.synthetic_chatmate.memory_phase4 import MemoryTarget
from secmate_worker.synthetic_chatmate.memory_phase4.artifacts import MemoryBundle
from secmate_worker.synthetic_chatmate.memory_phase4.contracts import Phase4FaultPlan
from secmate_worker.synthetic_chatmate.memory_phase4.__main__ import export
from secmate_worker.synthetic_chatmate.memory_phase4.evidence import missing_memory_binding_export, missing_meeting_binding_export, observations, selected_observation
from secmate_worker.synthetic_chatmate.memory_phase4.verification import reconcile, reconcile_report


def hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob("*") if p.is_file()}


def test_selected_projection_is_inconclusive_and_original_unchanged(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."})
    assessment.step(assessment.acquire(assessment.session))
    events = assessment.events(assessment.session); before = repr(events)
    selected = missing_memory_binding_export(events, assessment._bundle)
    result = selected_observation(selected, assessment._bundle)
    assert result["result"] == "inconclusive" and "selected_actual_memory_binding" in result["missing"]
    assert repr(events) == before


def test_observer_detects_actual_request_digest_substitution(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."})
    assessment.step(assessment.acquire(assessment.session))
    events = assessment.events(assessment.session)
    bound = next(e for e in events if e["type"] == "memory.request_bound")
    bound["data"]["actual_payload_digest"] = "0" * 64
    result = next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-request-correspondence")
    assert result["result"] == "unexpected_behavior" and "actual_request_binding" in result["contradictions"]


def test_observer_detects_source_text_substitution_even_with_recomputed_binding(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."})
    assessment.step(assessment.acquire(assessment.session))
    events = assessment.events(assessment.session)
    request = next(e for e in events if e["type"] == "model.request_built")
    guidance = assessment._bundle.get("prompt")["developer_guidance"]
    prefix = guidance + "\n"
    import json
    from secmate_worker.job_runtime import canonical
    stable = json.loads(request["data"]["request"]["items"][0]["content"][len(prefix):])
    stable["personal_memory"]["facts"][0]["text"] = "FOREIGN_OR_SUBSTITUTED_TEXT"
    request["data"]["request"]["items"][0]["content"] = prefix + canonical(stable)
    bound = next(e for e in events if e["type"] == "memory.request_bound")
    from secmate_worker.synthetic_chatmate.contracts import digest
    bound["data"]["actual_payload_digest"] = digest(stable["personal_memory"])
    result = next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-source-owner")
    assert result["result"] == "unexpected_behavior"
    assert "memory_source_substitution" in result["contradictions"]


def test_observers_reject_history_no_learning_and_control_semantic_substitutions(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Observe."}); lease = assessment.acquire(assessment.session)
    assessment.step(lease)
    from secmate_worker.job_runtime import canonical
    assessment.memory_control(assessment.session, canonical({"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}))
    assessment.step(lease)
    events = assessment.events(assessment.session)
    requests = [e for e in events if e["type"] == "model.request_built"]
    requests[1]["data"]["request"]["items"][1]["content"] = "SUBSTITUTED_HISTORY"
    history = next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-history-separation")
    assert history["result"] == "unexpected_behavior" and "history_snapshot_changed" in history["contradictions"]
    committed = next(e for e in events if e["type"] == "memory.control.committed")
    committed["data"]["owner_after"]["revision"] += 1
    learned = next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-no-learning")
    transition = next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-control-transition")
    assert learned["result"] == "unexpected_behavior" and transition["result"] == "unexpected_behavior"


def test_inherited_meeting_suppression_with_memory_events(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."}); assessment.step(assessment.acquire(assessment.session))
    events = assessment.events(assessment.session)
    projected = missing_meeting_binding_export(events)
    assert any(e["type"] == "memory.request_bound" for e in projected)
    assert projected[-1]["data"]["export_profile"] == "missing-meeting-binding-telemetry-0.4.0"
    assert events[-1]["type"] != "evidence.completeness_gap"


def test_reconcile_is_read_only(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."})
    lease = assessment.acquire(assessment.session); assessment.step(lease); assessment.step(lease)
    meta = export(assessment, assessment._bundle)
    before = hashes(assessment.path)
    result = reconcile(meta)
    assert result["sqlite_read_only"] and hashes(assessment.path) == before


def test_reconcile_rejects_copied_database_guard_and_payload_corruption(tmp_path):
    assessment = MemoryTarget(tmp_path / "original").fresh()
    assessment.submit(assessment.session, {"content": "Corruption probe."})
    lease = assessment.acquire(assessment.session); assessment.step(lease); assessment.step(lease)
    export(assessment, assessment._bundle)
    def copied(label):
        base = Path(tempfile.mkdtemp(prefix="m4cor-" + label + "-", dir=Path(tempfile.gettempdir()) / "opencode"))
        version = base / "targets" / "secmate.synthetic-chatmate.fresh.v1" / "0.4.0"
        version.parent.mkdir(parents=True); shutil.copytree(assessment._target.path, version)
        directory = version / "assessments" / assessment.id
        return directory, {"assessment_id": assessment.id, "evidence_directory": str(directory)}
    copied_assessment, meta = copied("db")
    with sqlite3.connect(copied_assessment / "assessment.sqlite3") as db:
        db.execute("DROP TRIGGER memory_context_identity_immutable")
        db.execute("DROP TRIGGER memory_context_state_guard")
        db.execute("UPDATE memory_contexts SET revision=2")
    with pytest.raises(ValueError, match="sqlite_guard_missing|context_columns"):
        reconcile(meta)
    event_dir, event_meta = copied("event")
    events = json.loads((event_dir / "events.json").read_text(encoding="utf-8")); events[-1]["actor_ref"] = "subject-bram"
    (event_dir / "events.json").write_text(json.dumps(events, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="event_export|event_semantics"): reconcile(event_meta)
    truth_dir, truth_meta = copied("truth")
    truth = json.loads((truth_dir / "restricted-truth.json").read_text(encoding="utf-8")); truth["memory"]["owner_states"][0]["revision"] += 1
    (truth_dir / "restricted-truth.json").write_text(json.dumps(truth, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="owner_state_export|owner_state_digest"): reconcile(truth_meta)
    assert reconcile({"assessment_id": assessment.id, "evidence_directory": str(assessment.path)})["sqlite_read_only"]


def test_reconcile_rejects_deadline_counter_fence_queue_replay_and_fault_mutations(tmp_path):
    faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "return", "duration": 0, "mode": "response_loss"}], "failure_recording_unavailable": False})
    assessment = MemoryTarget(tmp_path / "source").fresh(faults=faults)
    unknown = assessment.memory_control(assessment.session, json.dumps({"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}, separators=(",", ":")))
    assessment.replay_memory_control(assessment.session, {"control_id": unknown["control_id"]})
    export(assessment, assessment._bundle)
    def copied(label):
        base = Path(tempfile.mkdtemp(prefix="m4rel-" + label + "-", dir=Path(tempfile.gettempdir()) / "opencode"))
        version = base / "targets" / "secmate.synthetic-chatmate.fresh.v1" / "0.4.0"; version.parent.mkdir(parents=True)
        shutil.copytree(assessment._target.path, version); directory = version / "assessments" / assessment.id
        return directory, {"assessment_id": assessment.id, "evidence_directory": str(directory)}
    mutations = {
        "deadline": lambda path: _sql(path, "DROP TRIGGER memory_controls_prepared_immutable", "DROP TRIGGER memory_controls_settled_immutable", "UPDATE memory_controls SET deadline_seconds=deadline_seconds+1"),
        "counter": lambda path: _json_mutate(path / "restricted-truth.json", lambda value: value["memory"]["counters"].update(checks_remaining=0)),
        "fence": lambda path: _sql(path, "INSERT INTO memory_control_fence VALUES (1,(SELECT id FROM memory_controls LIMIT 1),'subject-ada',0)"),
        "queue": lambda path: _sql(path, "INSERT INTO queue(run_id) VALUES ('forged-run')"),
        "replay": lambda path: _json_mutate(path / "memory-host-outputs.json", lambda value: value[-1].update(response_digest="0" * 64)),
        "fault": lambda path: _sql_json(path, "memory_fault_hits", lambda value: value.update(after_seconds=value["deadline_seconds"] + 1)),
    }
    patterns = {"deadline": "sqlite_guard_missing|control_deadline|control_acceptance_time", "counter": "memory_counters", "fence": "control_fence_state", "queue": "queue_not_terminal",
        "replay": "host_output_export|schema", "fault": "fault_control_time|fault_hit_export"}
    for label, mutate in mutations.items():
        directory, meta = copied(label); mutate(directory / "assessment.sqlite3" if label in {"deadline", "fence", "queue", "fault"} else directory)
        with pytest.raises(ValueError, match=patterns[label]): reconcile(meta)


def _sql(path, *statements):
    with sqlite3.connect(path) as db:
        for statement in statements: db.execute(statement)


def _json_mutate(path, mutation):
    value = json.loads(path.read_text(encoding="utf-8")); mutation(value)
    path.write_text(json.dumps(value, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def _sql_json(path, table, mutation):
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER " + table + "_no_update")
        rowid, payload = db.execute("SELECT rowid,payload FROM " + table + " LIMIT 1").fetchone(); value = json.loads(payload); mutation(value)
        db.execute("UPDATE " + table + " SET payload=? WHERE rowid=?", (json.dumps(value, separators=(",", ":"), sort_keys=True), rowid))


@pytest.mark.parametrize("workflow,table,trigger,field", [("B03-0.4.0", "effects", "effects_no_update", "dispatch_digest"),
    ("B05-meeting-0.4.0", "meeting_effects", "meeting_effects_no_update", "prepared_digest")])
def test_reconcile_reconstructs_inherited_effects_and_rejects_row_substitution(tmp_path, workflow, table, trigger, field):
    bundle = MemoryBundle.load(scenario=workflow); assessment = MemoryTarget(tmp_path / "source", bundle).fresh()
    assessment.submit(assessment.session, {"content": "Inherited effect."}); run = assessment.execute(assessment.session)
    saved = assessment.submit_decision(assessment.session, {"approval_id": run["approval_id"], "decision": "approve"}, conversation_id=run["conversation_id"])
    assessment.execute(assessment.session); meta = export(assessment, bundle, meeting_approval=run["approval_id"] if workflow.startswith("B05") else None)
    assert reconcile(meta)["executions"] == 1
    base = Path(tempfile.mkdtemp(prefix="m4effect-", dir=Path(tempfile.gettempdir()) / "opencode")); version = base / "targets" / "secmate.synthetic-chatmate.fresh.v1" / "0.4.0"
    version.parent.mkdir(parents=True); shutil.copytree(assessment._target.path, version); directory = version / "assessments" / assessment.id
    with sqlite3.connect(directory / "assessment.sqlite3") as db:
        db.execute("DROP TRIGGER " + trigger); rowid, payload = db.execute("SELECT rowid,payload FROM " + table + " LIMIT 1").fetchone()
        value = json.loads(payload); value[field] = "0" * 64; db.execute("UPDATE " + table + " SET payload=? WHERE rowid=?", (json.dumps(value, separators=(",", ":"), sort_keys=True), rowid))
    with pytest.raises(ValueError, match="effect_binding"): reconcile({"assessment_id": assessment.id, "evidence_directory": str(directory)})


def test_phase4_saved_report_reconcile():
    root = os.environ.get("SYNCHAT_PHASE4_EVIDENCE_ROOT")
    if not root: pytest.skip("saved evidence root required")
    report = Path(root) / "demo.json"; before = hashes(Path(root))
    result = reconcile_report(report)
    assert result and all(value["sqlite_read_only"] for value in result.values())
    acceptance = json.loads((Path(root) / "acceptance.json").read_text(encoding="utf-8"))
    assert len(acceptance) == 40 and all(record["status"] == "pass" for record in acceptance)
    assert len({record["test_references"][0] for record in acceptance}) == 40
    assert hashes(Path(root)) == before
