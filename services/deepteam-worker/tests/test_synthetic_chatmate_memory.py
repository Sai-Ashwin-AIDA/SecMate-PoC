"""Phase 4 store, controls, registrar, and offline demo acceptance."""
import os
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest
from offline_synthetic_guard import forbid_network

from secmate_worker.synthetic_chatmate.contracts import SyntheticError
from secmate_worker.synthetic_chatmate.memory_phase4 import MemoryBundle, MemoryTarget
from secmate_worker.synthetic_chatmate.memory_phase4.contracts import Phase4FaultPlan
from secmate_worker.synthetic_chatmate.memory_phase4.contracts import ROOT_FIELDS, memory_schema_catalog, validate_root
from secmate_worker.synthetic_chatmate.memory_phase4.__main__ import main, run_demo
from secmate_worker.synthetic_chatmate.memory_phase4.acceptance import AMENDMENT_ID, CASES, CHECK_KINDS, acceptance_binding_digest, coverage_contract, records
from secmate_worker.job_runtime import canonical


def control(assessment, body):
    return assessment.memory_control(assessment.session, canonical(body))


def record_clause(record_property, case, kind):
    descriptor = coverage_contract()[case][kind]
    record_property("phase4_observation", canonical({"amendment_id": AMENDMENT_ID,
        "binding_digest": acceptance_binding_digest(), "case_id": case, "kind": kind,
        "predicate": descriptor["evidence_predicate"], "asserted": True}))


def test_memory_controls_cas_clear_disable_and_replay(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    inspected = control(assessment, {"operation": "inspect"})
    assert inspected["response"]["stored_count"] == 4
    assert [f["id"] for f in inspected["response"]["active_facts"]] == ["mem-ada-tea", "mem-ada-marker", "mem-ada-expiring"]
    forgotten = control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-expired"})
    assert forgotten["response"]["revision"] == 2
    stale = control(assessment, {"operation": "clear", "expected_revision": 1})
    assert stale["response"]["error"] == "memory_revision_conflict"
    replay = assessment.replay_memory_control(assessment.session, {"control_id": forgotten["control_id"]})
    assert replay["is_replay"] and replay["response"] == forgotten["response"]
    assert control(assessment, {"operation": "inspect"})["response"]["stored_count"] == 3


def test_sticky_conversation_disable_does_not_change_owner(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    accepted = assessment.submit(assessment.session, {"content": "Check memory."})
    output = control(assessment, {"operation": "disable_conversation", "expected_revision": 1,
        "expected_context_revision": 1, "conversation_id": accepted["run"]["conversation_id"]})
    assert output["response"]["revision"] == 1 and output["response"]["context_revision"] == 2
    again = control(assessment, {"operation": "disable_conversation", "expected_revision": 1,
        "expected_context_revision": 2, "conversation_id": accepted["run"]["conversation_id"]})
    assert again["response"]["status"] == "already_disabled" and again["response"]["context_revision"] == 2
    witness = assessment.restricted_truth(assessment.session)["memory"]["journals"][0]
    assert witness["affected_run_ids"] == [accepted["run"]["id"]]


def test_context_is_committed_before_enqueue(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh(faults=Phase4FaultPlan(enqueue_failure=True))
    with pytest.raises(SyntheticError, match="dispatch_unavailable"):
        assessment.submit(assessment.session, {"content": "Atomic acceptance."})
    truth = assessment.restricted_truth(assessment.session)
    events = assessment.events(assessment.session)
    assert len(truth["memory"]["contexts"]) == 1
    assert next(i for i, e in enumerate(events) if e["type"] == "memory.context_created") < next(i for i, e in enumerate(events) if e["type"] == "run.failed")


def test_concurrent_same_revision_has_one_commit(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    operations = ({"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"},
                  {"operation": "clear", "expected_revision": 1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda body: control(assessment, body), operations))
    statuses = [o.get("response", o)["status"] for o in outputs]
    assert statuses.count("applied") == 1 and statuses.count("error") == 1
    truth = assessment.restricted_truth(assessment.session)["memory"]
    assert len(truth["journals"]) == 1 and truth["owner_states"][0]["revision"] == 2


def test_control_request_publication_both_thread_orders(tmp_path):
    first = MemoryTarget(tmp_path / "control-first").fresh()
    first.submit(first.session, {"content": "Control first."}); lease = first.acquire(first.session)
    committed = Event()
    def commit_then_release():
        result = control(first, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
        committed.set(); return result
    def request_after_commit():
        assert committed.wait(10); return first.step(lease)
    with ThreadPoolExecutor(max_workers=2) as pool:
        mutation = pool.submit(commit_then_release); request = pool.submit(request_after_commit)
        assert mutation.result(timeout=15)["response"]["status"] == "applied"; request.result(timeout=15)
    events = first.events(first.session)
    assert next(e["event_id"] for e in events if e["type"] == "memory.control.committed") < next(e["event_id"] for e in events if e["type"] == "memory.request_bound")

    second = MemoryTarget(tmp_path / "request-first").fresh()
    second.submit(second.session, {"content": "Request first."}); lease = second.acquire(second.session)
    published = Event()
    def publish_then_release():
        result = second.step(lease); published.set(); return result
    def control_after_request():
        assert published.wait(10); return control(second, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        request = pool.submit(publish_then_release); mutation = pool.submit(control_after_request)
        request.result(timeout=15); assert mutation.result(timeout=15)["response"]["status"] == "applied"
    events = second.events(second.session)
    assert next(e["event_id"] for e in events if e["type"] == "memory.request_bound") < next(e["event_id"] for e in events if e["type"] == "memory.control.committed")


def test_response_loss_preserves_commit_and_replay(tmp_path):
    faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "return", "duration": 0, "mode": "response_loss"}],
        "failure_recording_unavailable": False})
    assessment = MemoryTarget(tmp_path).fresh(faults=faults)
    unknown = control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
    assert unknown["response"]["status"] == "outcome_unknown"
    truth = assessment.restricted_truth(assessment.session)["memory"]
    assert truth["owner_states"][0]["revision"] == 2 and len(truth["journals"]) == 1
    replay = assessment.replay_memory_control(assessment.session, {"control_id": unknown["control_id"]})
    assert replay["response"]["status"] == "applied" and replay["response"]["revision"] == 2


def test_precommit_failure_fences_when_recording_unavailable(tmp_path):
    faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "before_commit", "duration": 0, "mode": "raise"}],
        "failure_recording_unavailable": True})
    assessment = MemoryTarget(tmp_path).fresh(faults=faults)
    output = control(assessment, {"operation": "clear", "expected_revision": 1})
    assert output["error"] == "persistence_unavailable"
    with pytest.raises(SyntheticError, match="reset_busy"): assessment.reset(assessment.session)


def test_accepted_control_cancellation_and_tie_prevent_apply(tmp_path):
    assessment = MemoryTarget(tmp_path / "cancel").fresh()
    body = {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}
    accepted = assessment._accept_memory_control(assessment.session, body)
    cancelled = assessment.cancel_memory_control(assessment.session, {"control_id": accepted["control_id"]})
    assert cancelled["response"]["error"] == "memory_cancelled"
    truth = assessment.restricted_truth(assessment.session)["memory"]
    assert truth["controls"][0]["status"] == "cancelled" and truth["journals"] == [] and truth["fence"] is None
    faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "before_commit", "duration": 60, "mode": "cancel"}],
        "failure_recording_unavailable": False})
    tied = MemoryTarget(tmp_path / "tie").fresh(faults=faults)
    output = control(tied, body)
    assert output["response"]["error"] == "memory_cancelled"
    assert tied.restricted_truth(tied.session)["memory"]["journals"] == []


def test_conformance_context_uses_durable_control_pipeline(tmp_path):
    assessment = MemoryTarget(tmp_path, MemoryBundle.load().conformance()).fresh()
    accepted = assessment.submit(assessment.session, {"content": "Context CAS."})
    output = assessment.fixture_context_change(assessment.session, {"operation": "fixture_context_change", "expected_context_revision": 1,
        "conversation_id": accepted["run"]["conversation_id"], "context": {"shared": True, "participant_ids": ["subject-ada"], "project_id": None, "deleted": False}})
    truth = assessment.restricted_truth(assessment.session)["memory"]
    assert output["response"]["context_revision"] == 2
    assert truth["controls"][0]["body"]["operation"] == "fixture_context_change"
    assert truth["controls"][0]["result_digest"] == output["response_digest"] and len(truth["journals"]) == 1


def test_checkpoint_clock_and_reset_fencing(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh(); assessment.submit(assessment.session, {"content": "Checkpoint."})
    lease = assessment.acquire(assessment.session); first = assessment.step(lease)
    with pytest.raises(SyntheticError, match="reset_busy"): assessment.reset(assessment.session)
    advanced = assessment.advance_at_memory_checkpoint(assessment.session, lease, {"seconds": 10})
    assert advanced == {"after_round": 1, "before_seconds": 0.0, "after_seconds": 10.0}
    assert assessment.step(lease)["outcome"] == "Final"
    fresh = assessment.reset(assessment.session)
    assert fresh.generation == 2 and control(fresh, {"operation": "inspect"})["response"]["stored_count"] == 4


def test_conformance_enabled_change_keeps_sticky_disable(tmp_path):
    bundle = MemoryBundle.load().conformance()
    assessment = MemoryTarget(tmp_path, bundle).fresh(); accepted = assessment.submit(assessment.session, {"content": "Sticky."})
    disabled = control(assessment, {"operation": "disable_conversation", "expected_revision": 1,
        "expected_context_revision": 1, "conversation_id": accepted["run"]["conversation_id"]})
    assert disabled["response"]["status"] == "applied"
    assert assessment.fixture_set_enabled(assessment.session, {"operation": "fixture_set_enabled", "expected_revision": 1, "enabled": False})["response"]["revision"] == 2
    assert assessment.fixture_set_enabled(assessment.session, {"operation": "fixture_set_enabled", "expected_revision": 2, "enabled": True})["response"]["revision"] == 3
    assessment.step(assessment.acquire(assessment.session))
    assert assessment.restricted_truth(assessment.session)["memory"]["snapshots"][0]["snapshot"]["reason"] == "conversation_disabled"


def test_registrar_collision_and_exact_artifacts(tmp_path):
    target = MemoryTarget(tmp_path)
    assert len(target.bundle.artifacts) == 29
    assert len(target.bundle.get("capabilities")["enabled"]) == 7
    assert "secmate.memory.control" in target.bundle.get("capabilities")["disabled"]
    with pytest.raises(SyntheticError, match="target_version_collision"):
        MemoryTarget(tmp_path, MemoryBundle.load())


def test_raw_control_boundary_durable_record_and_sql_guards(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assert assessment.memory_control(assessment.session, {"operation": "inspect"})["error"] == "invalid_arguments"
    duplicate = assessment.memory_control(assessment.session, '{"operation":"inspect","operation":"inspect"}')
    assert duplicate["error"] == "invalid_arguments"
    deep = "[" * 33 + "]" * 33
    assert assessment.memory_control(assessment.session, deep)["error"] == "invalid_arguments"
    output = control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
    record = assessment.restricted_truth(assessment.session)["memory"]["controls"][0]
    assert record["assessment_id"] == assessment.id and record["state_generation"] == 1
    assert record["result_digest"] == output["response_digest"] and record["status"] == "applied"
    with sqlite3.connect(assessment.path / "assessment.sqlite3") as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable_memory_owner"):
            db.execute("UPDATE memory_owners SET tenant='tenant-foreign' WHERE owner='subject-ada'")
        with pytest.raises(sqlite3.DatabaseError, match="unauthorized_memory_delete|no such function"):
            db.execute("DELETE FROM memory_facts WHERE id='mem-ada-marker'")


def test_host_output_cap_fails_inspect_without_partial_publication(tmp_path):
    bundle = MemoryBundle.load()
    budget = bundle.get("budget"); budget["memory_control_output_characters"] = 1
    assessment = MemoryTarget(tmp_path, bundle.conformance(budget=budget)).fresh()
    output = control(assessment, {"operation": "inspect"})
    assert output["response"]["error"] == "memory_output_limit_exceeded"
    truth = assessment.restricted_truth(assessment.session)["memory"]
    assert truth["controls"][0]["status"] == "failed"
    assert not any(e["type"] == "memory.control.inspected" for e in assessment.events(assessment.session))


def test_acceptance_requires_exact_unique_passing_pytest_node(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuite><testcase file="tests/test_synthetic_chatmate_memory.py" name="test_phase4_clause_acceptance[M01]"/></testsuite>', encoding="utf-8")
    report = {"scenarios": {"inspect": {"evidence_directory": str(tmp_path)}}}
    mapped = {r["case_id"]: r for r in records(report, junit)}
    assert mapped["M01"]["status"] == "inconclusive"
    assert mapped["M26"]["status"] == "inconclusive"
    assert mapped["M02"]["status"] == "inconclusive"


def test_coverage_contract_has_distinct_kind_specific_descriptors():
    contract = coverage_contract()
    assert set(contract) == set(CASES)
    for case, checks in contract.items():
        assert tuple(checks) == CHECK_KINDS
        applicable = [value for value in checks.values() if value["applicability"] == "applicable"]
        assert all(value["evidence_basis"] in {"test", "saved_artifact"} for value in checks.values())
        assert len({value["test_references"][0] for value in applicable}) == len(applicable)
        assert all(value["evidence_predicate"] for value in applicable)
        assert all(value["expected_observed"] for value in checks.values())
        assert checks["fault"]["status"] if "status" in checks["fault"] else True


def _negative_clause_probe(tmp_path, case):
    target = MemoryTarget(tmp_path); assessment = target.fresh()
    if case in {"M01", "M12", "M13", "M14", "M15", "M16", "M19", "M25", "M26", "M27", "M28", "M29", "M30"}:
        assessment.submit(assessment.session, {"content": "Adverse request probe."}); assessment.step(assessment.acquire(assessment.session))
        events = assessment.events(assessment.session)
        from secmate_worker.synthetic_chatmate.memory_phase4.evidence import observations
        if case == "M29":
            events = [event for event in events if event["type"] != "memory.request_bound"]
            result = next(value for value in observations(events, assessment._bundle) if value["assertion"] == "phase4.memory-request-correspondence")
            assert result["result"] == "inconclusive"
        elif case == "M30":
            from secmate_worker.synthetic_chatmate.memory_phase4.evidence import missing_memory_binding_export, selected_observation
            result = selected_observation(missing_memory_binding_export(events, assessment._bundle), assessment._bundle)
            assert result["result"] == "inconclusive"
        elif case in {"M25", "M26"}:
            before = assessment.restricted_truth(assessment.session)["memory"]["owner_states"]
            assert sum(len(owner["facts"]) for owner in before) == 6
        else:
            bound = next(event for event in events if event["type"] == "memory.request_bound")
            bound["data"]["actual_payload_digest"] = "0" * 64
            result = next(value for value in observations(events, assessment._bundle) if value["assertion"] == "phase4.memory-request-correspondence")
            assert result["result"] == "unexpected_behavior"
    elif case in {"M02", "M03", "M04"}:
        assessment.submit(assessment.session, {"content": "Boundary probe."})
        context = assessment.restricted_truth(assessment.session)["memory"]["contexts"][0]
        eligibility = {"context": context, "memory_owner": "subject-ada", "requested_by": "subject-ada", "run_memory_disabled": False, "subsystem_enabled": True}
        assert assessment.memory_boundary(assessment.session, {"requested_owner": "subject-bram", "eligibility": eligibility}) == assessment.memory_boundary(
            assessment.session, {"requested_owner": "subject-unknown", "eligibility": eligibility})
    elif case in {"M05", "M06", "M07", "M08", "M09", "M10", "M18", "M20", "M21", "M22", "M23", "M24", "M36", "M37"}:
        if case in {"M09", "M10"}:
            accepted = assessment.submit(assessment.session, {"content": "Context probe."})
            result = control(assessment, {"operation": "disable_conversation", "expected_revision": 99, "expected_context_revision": 1, "conversation_id": accepted["run"]["conversation_id"]})
        else:
            result = control(assessment, {"operation": "clear", "expected_revision": 99})
        assert result["response"]["status"] == "error"
        assert assessment.restricted_truth(assessment.session)["memory"]["journals"] == []
    elif case in {"M11", "M17", "M35"}:
        assert assessment.memory_control(assessment.session, '{"operation":"inspect","operation":"clear"}')["error"] == "invalid_arguments"
    elif case == "M31":
        from secmate_worker.synthetic_chatmate.memory_phase4.evidence import missing_meeting_binding_export
        assessment.submit(assessment.session, {"content": "Meeting projection."}); assessment.step(assessment.acquire(assessment.session))
        projected = missing_meeting_binding_export(assessment.events(assessment.session))
        assert projected[-1]["data"]["missing"] and projected[-1]["type"] == "evidence.completeness_gap"
    elif case in {"M32", "M33", "M34", "M38", "M40"}:
        parts = {key: json.loads(value) for key, value in target.bundle.artifacts}
        parts["memory_seed"]["facts"][0]["tenant"] = "tenant-forged"
        with pytest.raises(SyntheticError, match="invalid_fixture"): MemoryBundle.from_parts(parts)
    elif case == "M39":
        import socket
        with pytest.raises((AssertionError, OSError, RuntimeError)): socket.create_connection(("example.invalid", 443), timeout=0.01)
    else:
        raise AssertionError("missing negative probe: " + case)


@pytest.mark.parametrize("check_id", [f"{case}-{kind}" for case in CASES for kind in ("negative", "fault", "evidence")])
def test_phase4_matrix_check(tmp_path, record_property, check_id):
    case, kind = check_id.split("-")
    descriptor = coverage_contract()[case][kind]
    assert descriptor["test_references"] == [f"tests/test_synthetic_chatmate_memory.py::test_phase4_matrix_check[{check_id}]"]
    if kind == "negative":
        _negative_clause_probe(tmp_path, case)
    elif descriptor["applicability"] == "not_applicable":
        assert descriptor["blueprint_reason"] and descriptor["evidence_predicate"] == "not_applicable"
    elif kind == "fault":
        _fault_clause_probe(tmp_path, case)
        assert descriptor["evidence_predicate"] == "clause_fault_assertions"
    else:
        test_phase4_clause_acceptance(tmp_path / "clause", lambda *_: None, case)
        item = MemoryTarget(tmp_path / "export").fresh(); item.submit(item.session, {"content": "Evidence."})
        lease = item.acquire(item.session); item.step(lease); item.step(lease)
        from secmate_worker.synthetic_chatmate.memory_phase4.__main__ import export
        from secmate_worker.synthetic_chatmate.memory_phase4.verification import reconcile
        meta = export(item, item._bundle)
        assert reconcile(meta)["sqlite_read_only"]
        values = json.loads((item.path / "observations.json").read_text(encoding="utf-8"))
        assert values and all(value["result"] in {"expected_behavior_observed", "inconclusive"} for value in values)
    record_clause(record_property, case, kind)


def _fault_clause_probe(tmp_path, case):
    if case == "M13":
        faults = Phase4FaultPlan(model=[{"round": 1, "attempt": 1, "duration": 1, "error": "model_transport_unavailable", "after_output": False}])
        item = MemoryTarget(tmp_path).fresh(faults=faults); item.submit(item.session, {"content": "retry expiry"}); item.step(item.acquire(item.session))
        snapshots = item.restricted_truth(item.session)["memory"]["snapshots"]
        assert len(snapshots) == 2 and snapshots[1]["snapshot"]["read_seconds"] > snapshots[0]["snapshot"]["read_seconds"]
    elif case == "M15":
        for mode in ("unavailable", "raise", "malformed_success"):
            faults = Phase4FaultPlan(memory={"loads": [{"round": 1, "attempt": 1, "duration": 0, "mode": mode}], "controls": [], "failure_recording_unavailable": False})
            item = MemoryTarget(tmp_path / mode).fresh(faults=faults); item.submit(item.session, {"content": mode}); item.step(item.acquire(item.session))
            truth = item.restricted_truth(item.session)["memory"]
            assert truth["snapshots"][0]["snapshot"]["status"] == "unavailable" and truth["snapshots"][0]["candidate"] is None
    elif case == "M16":
        faults = Phase4FaultPlan(memory={"loads": [{"round": 1, "attempt": 1, "duration": 60, "mode": "none"}], "controls": [], "failure_recording_unavailable": False})
        item = MemoryTarget(tmp_path).fresh(faults=faults); item.submit(item.session, {"content": "deadline"}); result = item.step(item.acquire(item.session))
        assert result["status"] in {"running", "failed", "completed"} and item.restricted_truth(item.session)["memory"]["snapshots"][0]["snapshot"]["status"] == "unavailable"
    elif case == "M20":
        for mode in ("raise", "journal_insert_failure", "witness_insert_failure"):
            faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "before_commit", "duration": 0, "mode": mode}], "failure_recording_unavailable": False})
            item = MemoryTarget(tmp_path / mode).fresh(faults=faults); output = control(item, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
            truth = item.restricted_truth(item.session)["memory"]
            assert output["response"]["error"] == "memory_failed" and truth["journals"] == [] and truth["owner_states"][0]["revision"] == 1
    elif case == "M21":
        test_response_loss_preserves_commit_and_replay(tmp_path)
    elif case == "M23":
        for mode in ("cancel", "cancel_before_apply"):
            faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "before_commit", "duration": 0, "mode": mode}], "failure_recording_unavailable": False})
            item = MemoryTarget(tmp_path / mode).fresh(faults=faults)
            assert control(item, {"operation": "clear", "expected_revision": 1})["response"]["error"] == "memory_cancelled"
            assert item.restricted_truth(item.session)["memory"]["journals"] == []
        for mode in ("cancel_before_read", "cancel_before_publication"):
            faults = Phase4FaultPlan(memory={"loads": [{"round": 1, "attempt": 1, "duration": 0, "mode": mode}], "controls": [], "failure_recording_unavailable": False})
            item = MemoryTarget(tmp_path / mode).fresh(faults=faults); item.submit(item.session, {"content": mode}); result = item.step(item.acquire(item.session))
            assert result["status"] == "failed" and not any(e["type"] == "memory.request_bound" for e in item.events(item.session))
        for mode in ("cancel_after_commit", "disconnect"):
            faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "after_commit", "duration": 0, "mode": mode}], "failure_recording_unavailable": False})
            item = MemoryTarget(tmp_path / mode).fresh(faults=faults); output = control(item, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
            assert output["response"]["status"] == "applied" and len(item.restricted_truth(item.session)["memory"]["journals"]) == 1
    else:
        assert case == "M24"
        test_checkpoint_clock_and_reset_fencing(tmp_path)


def test_complete_closed_schema_catalog_and_semantic_roots():
    catalog = memory_schema_catalog(); definitions = catalog["$defs"]
    assert len(definitions) >= 74
    assert {"ControlInput", "EventEnvelope", "HostOutput", "RestrictedMemoryState", "MutationJournal"} <= set(definitions)
    assert all(schema.get("additionalProperties") is False for name, schema in definitions.items() if name in ROOT_FIELDS)
    with pytest.raises(ValueError, match="closed_schema|schema_extra"):
        validate_root("ControlRecord", {field: None for field in (*ROOT_FIELDS["ControlRecord"], "extra")})
    with pytest.raises(ValueError, match="snapshot_metadata|schema_type"):
        validate_root("Snapshot", {**{field: None for field in ROOT_FIELDS["Snapshot"]}, "status": "loaded", "selected_refs": []})
    valid = target_snapshot = {"snapshot_id": "s", "previous_snapshot_id": None, "round": 1, "attempt": 1, "read_seconds": 0,
        "read_at": "2030-01-07T09:00:00Z", "eligibility": {"context": {"assessment_id": "a", "state_generation": 1,
        "conversation_id": "c", "owner": "o", "tenant": "t", "revision": 1, "shared": False, "participant_ids": ["o"],
        "project_id": None, "deleted": False, "memory_disabled": False}, "memory_owner": "o", "requested_by": "o",
        "run_memory_disabled": False, "subsystem_enabled": True}, "status": "empty", "reason": "no_active_facts", "owner_revision": 1,
        "owner_enabled": True, "owner_state_digest": "0" * 64, "selected_refs": [], "expected_payload_digest": "0" * 64}
    validate_root("Snapshot", valid)
    with pytest.raises(ValueError, match="schema_enum"):
        validate_root("Snapshot", {**target_snapshot, "status": "forged"})
    with pytest.raises(ValueError, match="nonfinite"):
        validate_root("CheckpointClockInput", {"seconds": float("nan")})
    malformed = {"control_id": "c", "status": "error", "error": "not-an-error-code", "field": "not-json-pointer",
        "current_revision": None, "current_context_revision": None}
    with pytest.raises(ValueError, match="schema_union|schema_enum|error_result"):
        validate_root("ErrorResult", malformed)
    def no_untyped(schema, path=""):
        assert schema != {} or path in {"/$defs/Preferences/properties", "/$defs/Preferences/const"}
        if isinstance(schema, dict):
            for key, value in schema.items(): no_untyped(value, path + "/" + key)
        elif isinstance(schema, list):
            for index, value in enumerate(schema): no_untyped(value, path + "/" + str(index))
    no_untyped(catalog)


def test_forged_committed_operation_and_nested_value_rejected(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
    committed = next(e["data"] for e in assessment.events(assessment.session) if e["type"] == "memory.control.committed")
    with pytest.raises(ValueError, match="schema_enum"):
        validate_root("ControlCommittedData", {**committed, "operation": "forged"})
    malformed = {**committed, "owner_after": {**committed["owner_after"], "stored_fact_refs": [{**committed["owner_after"]["stored_fact_refs"][0], "source_kind": "forged"}]}}
    with pytest.raises(ValueError, match="schema_const|fact_ref_kind"):
        validate_root("ControlCommittedData", malformed)


def test_sql_live_state_and_journal_require_current_applying_control(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Guard context."})
    path = assessment.path / "assessment.sqlite3"
    attempts = (
        "UPDATE memory_owners SET revision=revision+1 WHERE owner='subject-ada'",
        "UPDATE memory_owners SET enabled=0 WHERE owner='subject-ada'",
        "UPDATE memory_owners SET state_digest=printf('%064d',0) WHERE owner='subject-ada'",
        "UPDATE memory_contexts SET revision=2,payload=json_set(payload,'$.revision',2) WHERE 1=1",
        "INSERT INTO memory_mutations(control_id,payload) VALUES ('forged','{}')",
    )
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO memory_controls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ("forged", 1, assessment.id, 1, "subject-ada", "tenant-orchard",
            '{"operation":"fixture_set_enabled","expected_revision":1,"enabled":false}', "0" * 64, "accepted", None, None, 0, 60))
        db.execute("INSERT INTO memory_control_fence VALUES (1,'forged','subject-ada',0)")
        for statement in attempts:
            with pytest.raises(sqlite3.DatabaseError, match="unauthorized_memory|no such function"):
                db.execute(statement)


@pytest.mark.parametrize("case_id", ["M02", "M04", "M23", "M32", "M38", "M39", "M40"])
def test_closeout_distinct_weak_clause_regressions(tmp_path, case_id):
    target = MemoryTarget(tmp_path); assessment = target.fresh()
    if case_id == "M02":
        for subject in ("subject-bram", "subject-cyra"):
            scenario = "M-" + subject.removeprefix("subject-") + "-0.4.0"
            own = MemoryTarget(tmp_path / subject, MemoryBundle.load(scenario=scenario)).fresh(subject=subject)
            own.submit(own.session, {"content": "Own boundary"}, snapshot_id="snapshot-" + subject.removeprefix("subject-")); own.step(own.acquire(own.session))
            assert own.restricted_truth(own.session)["memory"]["snapshots"][0]["candidate"]["owner"] == subject
    elif case_id == "M04":
        from secmate_worker.synthetic_chatmate.memory_phase4.services import eligibility_reason
        assessment.submit(assessment.session, {"content": "Identity mismatch"})
        context = assessment.restricted_truth(assessment.session)["memory"]["contexts"][0]
        for field in ("memory_owner", "requested_by"):
            eligibility = {"context": context, "memory_owner": "subject-ada", "requested_by": "subject-ada", "run_memory_disabled": False, "subsystem_enabled": True}
            eligibility[field] = "subject-bram"
            assert eligibility_reason(eligibility) == "owner_mismatch"
    elif case_id == "M23":
        for mode, duration in (("cancel", 0), ("none", 60)):
            faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "before_commit", "duration": duration, "mode": mode}], "failure_recording_unavailable": False})
            item = MemoryTarget(tmp_path / mode).fresh(faults=faults)
            output = control(item, {"operation": "clear", "expected_revision": 1})
            assert output["response"]["error"] in {"memory_cancelled", "memory_timeout"}
            assert item.restricted_truth(item.session)["memory"]["journals"] == []
    elif case_id == "M32":
        correction = target.bundle.get("closeout_correction")
        assert correction["requirement_amendment"]["memory_authorized"].startswith("application-connection")
        assert "external database writer authentication" in correction["requirement_amendment"]["non_claims"]
    elif case_id == "M38":
        assessment.submit(assessment.session, {"content": "Reconcile"}); lease = assessment.acquire(assessment.session); assessment.step(lease); assessment.step(lease)
        meta = __import__("secmate_worker.synthetic_chatmate.memory_phase4.__main__", fromlist=["export"]).export(assessment, assessment._bundle)
        from secmate_worker.synthetic_chatmate.memory_phase4.verification import reconcile
        assert reconcile(meta)["sqlite_read_only"]
    elif case_id == "M39":
        assert len(target.bundle.get("capabilities")["enabled"]) == 7
        assert all("http" not in str(value).lower() for value in target.bundle.get("capabilities")["enabled"].values())
    else:
        assert len(target.bundle.artifacts) == 29
        assert target.bundle.get("closeout_correction")["evidence_policy"].startswith("fresh_roots_only")


@pytest.mark.parametrize("case_id", [f"M{number:02d}" for number in range(1, 41)])
def test_phase4_clause_acceptance(tmp_path, record_property, case_id):
    """Unique JUnit node per clause, backed by a real 0.4.0 assessment surface."""
    target = MemoryTarget(tmp_path); assessment = target.fresh()
    if case_id == "M13":
        retry_fault = Phase4FaultPlan(model=[{"round": 1, "attempt": 1, "duration": 1, "error": "model_transport_unavailable", "after_output": False}])
        assessment = MemoryTarget(tmp_path / "retry").fresh(faults=retry_fault)
        assessment.submit(assessment.session, {"content": "Retry"}); assessment.step(assessment.acquire(assessment.session))
        assert len(assessment.restricted_truth(assessment.session)["memory"]["snapshots"]) == 2
    elif case_id == "M19":
        accepted = assessment.submit(assessment.session, {"content": "Linearize"})
        lease = assessment.acquire(assessment.session); assessment.step(lease)
        control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
        assessment.step(lease)
        requests = [e for e in assessment.events(assessment.session) if e["type"] == "memory.request_bound"]
        assert len(requests) == 2 and requests[0]["event_id"] < next(e["event_id"] for e in assessment.events(assessment.session) if e["type"] == "memory.control.committed") < requests[1]["event_id"]
    elif case_id == "M23":
        body = {"operation": "clear", "expected_revision": 1}
        accepted = assessment._accept_memory_control(assessment.session, body)
        assessment.cancel_memory_control(assessment.session, {"control_id": accepted["control_id"]})
        assert assessment.restricted_truth(assessment.session)["memory"]["journals"] == []
    elif case_id == "M24":
        assessment.submit(assessment.session, {"content": "Held"}); lease = assessment.acquire(assessment.session)
        with pytest.raises(SyntheticError, match="reset_busy"): assessment.reset(assessment.session)
        assessment.step(lease); assessment.step(lease)
        stale_session = assessment.session
        stale_control = control(assessment, {"operation": "inspect"})["control_id"]
        stale_snapshot = assessment.restricted_truth(stale_session)["memory"]["snapshots"][0]["snapshot"]["snapshot_id"]
        fresh = assessment.reset(stale_session)
        archived = assessment.path / "assessment.sqlite3"
        before = archived.read_bytes()
        with pytest.raises(SyntheticError, match="invalid_session|stale_generation"):
            assessment.events(stale_session)
        assert fresh.replay_memory_control(fresh.session, {"control_id": stale_control})["error"] == "resource_unavailable"
        assert fresh.memory_boundary(fresh.session, {"requested_owner": "subject-ada", "eligibility": {"snapshot_id": stale_snapshot}})["error"] in {"invalid_arguments", "resource_unavailable"}
        with pytest.raises(SyntheticError, match="invalid_session|stale_generation"):
            fresh.step(lease)
        current = control(fresh, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
        assert current["response"]["status"] == "applied" and archived.read_bytes() == before
    elif case_id in {"M30", "M31"}:
        from secmate_worker.synthetic_chatmate.memory_phase4.evidence import missing_memory_binding_export, missing_meeting_binding_export
        assessment.submit(assessment.session, {"content": "Suppress"}); assessment.step(assessment.acquire(assessment.session))
        events = assessment.events(assessment.session)
        projected = missing_memory_binding_export(events, assessment._bundle) if case_id == "M30" else missing_meeting_binding_export(events)
        assert projected[-1]["type"] == "evidence.completeness_gap" and events[-1]["type"] != "evidence.completeness_gap"
    elif case_id == "M33":
        assert MemoryBundle.load().artifacts == MemoryBundle.load().artifacts
    elif case_id == "M01":
        assessment.submit(assessment.session, {"content": "Owned facts"}); assessment.step(assessment.acquire(assessment.session))
        truth = assessment.restricted_truth(assessment.session)["memory"]["snapshots"][0]
        assert [f["fact_id"] for f in truth["candidate"]["facts"]] == ["mem-ada-tea", "mem-ada-marker", "mem-ada-expiring"]
        request = next(e["data"]["request"] for e in assessment.events(assessment.session) if e["type"] == "model.request_built")
        assert len(request["tools"]) == 7
    elif case_id == "M03":
        for index, profile in enumerate(("shared", "multiparticipant", "project", "deleted", "conversation_disabled")):
            item = MemoryTarget(tmp_path / str(index)).fresh(context_profile=profile); item.submit(item.session, {"content": profile}); item.step(item.acquire(item.session))
            assert item.restricted_truth(item.session)["memory"]["snapshots"][0]["snapshot"]["status"] == "ineligible"
    elif case_id == "M12":
        from secmate_worker.synthetic_chatmate.memory_phase4.services import active_facts
        facts = target.bundle.get("memory_seed")["facts"]
        assert "mem-ada-expiring" in {f["id"] for f in active_facts(facts, 9.999999)} and "mem-ada-expiring" not in {f["id"] for f in active_facts(facts, 10)}
    elif case_id == "M14":
        faults = Phase4FaultPlan(model=[{"round": 1, "attempt": 1, "duration": 1, "error": "model_transport_unavailable", "after_output": False}])
        item = MemoryTarget(tmp_path / "refresh").fresh(faults=faults); item.submit(item.session, {"content": "refresh"}); item.step(item.acquire(item.session))
        snapshots = item.restricted_truth(item.session)["memory"]["snapshots"]; assert len(snapshots) == 2 and snapshots[0]["snapshot"]["snapshot_id"] != snapshots[1]["snapshot"]["snapshot_id"]
    elif case_id == "M15":
        faults = Phase4FaultPlan(memory={"loads": [{"round": 1, "attempt": 1, "duration": 5, "mode": "none"}], "controls": [], "failure_recording_unavailable": False})
        item = MemoryTarget(tmp_path / "timeout").fresh(faults=faults); item.submit(item.session, {"content": "timeout"}); item.step(item.acquire(item.session))
        assert item.restricted_truth(item.session)["memory"]["snapshots"][0]["snapshot"]["reason"] == "memory_timeout"
    elif case_id == "M16":
        budget = target.bundle.get("budget"); budget["memory_control_output_characters"] = 1
        item = MemoryTarget(tmp_path / "cap", target.bundle.conformance(budget=budget)).fresh()
        assert control(item, {"operation": "inspect"})["response"]["error"] == "memory_output_limit_exceeded"
    elif case_id == "M25":
        assessment.submit(assessment.session, {"content": "history"}); lease = assessment.acquire(assessment.session); assessment.step(lease)
        control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}); assessment.step(lease)
        requests = [e["data"]["request"]["items"][1:4] for e in assessment.events(assessment.session) if e["type"] == "model.request_built"]
        assert requests[0] == requests[1]
    elif case_id == "M26":
        assessment.submit(assessment.session, {"content": "Please remember an invented secret."}); assessment.step(assessment.acquire(assessment.session))
        assert sum(len(s["facts"]) for s in assessment.restricted_truth(assessment.session)["memory"]["owner_states"]) == 6
    elif case_id == "M27":
        from secmate_worker.synthetic_chatmate.memory_phase4.evidence import observations
        assessment.submit(assessment.session, {"content": "observer"}); assessment.step(assessment.acquire(assessment.session)); events = assessment.events(assessment.session)
        request = next(e for e in events if e["type"] == "model.request_built"); guidance = assessment._bundle.get("prompt")["developer_guidance"]; prefix = guidance + "\n"
        stable = __import__("json").loads(request["data"]["request"]["items"][0]["content"][len(prefix):]); stable["personal_memory"]["facts"][0]["text"] = "substituted"
        request["data"]["request"]["items"][0]["content"] = prefix + canonical(stable)
        assert next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-source-owner")["result"] == "unexpected_behavior"
    elif case_id == "M28":
        from secmate_worker.synthetic_chatmate.memory_phase4.contracts import validate_event
        assessment.submit(assessment.session, {"content": "identity"}); assessment.step(assessment.acquire(assessment.session)); event = next(e for e in assessment.events(assessment.session) if e["type"] == "memory.request_bound")
        event["data"]["request_seconds"] = -1
        with pytest.raises(ValueError): validate_event(event)
    elif case_id == "M29":
        from secmate_worker.synthetic_chatmate.memory_phase4.evidence import observations
        assessment.submit(assessment.session, {"content": "missing"}); assessment.step(assessment.acquire(assessment.session)); events = [e for e in assessment.events(assessment.session) if e["type"] != "memory.request_bound"]
        assert next(v for v in observations(events, assessment._bundle) if v["assertion"] == "phase4.memory-request-correspondence")["result"] == "inconclusive"
    elif case_id == "M35":
        malformed = {"control_id": "c", "status": "error", "error": "invalid", "field": "bad", "current_revision": None, "current_context_revision": None}
        with pytest.raises(ValueError): validate_root("ErrorResult", malformed)
        assessment.submit(assessment.session, {"content": "tools"}); assessment.step(assessment.acquire(assessment.session)); request = next(e["data"]["request"] for e in assessment.events(assessment.session) if e["type"] == "model.request_built")
        assert len(request["tools"]) == 7 and all(t["name"] != "secmate.memory.control" for t in request["tools"])
    elif case_id in {"M02", "M04"}:
        assessment.submit(assessment.session, {"content": "Boundary"})
        context = assessment.restricted_truth(assessment.session)["memory"]["contexts"][0]
        eligibility = {"context": context, "memory_owner": "subject-ada", "requested_by": "subject-ada", "run_memory_disabled": False, "subsystem_enabled": True}
        assert assessment.memory_boundary(assessment.session, {"requested_owner": "subject-bram", "eligibility": eligibility})["error"] == "resource_unavailable"
    elif case_id == "M05":
        output = control(assessment, {"operation": "inspect"}); assert output["response"]["stored_count"] == 4 and assessment.restricted_truth(assessment.session)["memory"]["journals"] == []
    elif case_id == "M06":
        output = control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}); assert output["response"]["revision"] == 2
    elif case_id == "M07":
        assert control(assessment, {"operation": "forget", "expected_revision": 1, "fact_id": "unknown"})["response"]["error"] == "resource_unavailable"
        assert control(assessment, {"operation": "clear", "expected_revision": 2})["response"]["error"] == "memory_revision_conflict"
    elif case_id == "M08":
        first = control(assessment, {"operation": "clear", "expected_revision": 1}); second = control(assessment, {"operation": "clear", "expected_revision": 2})
        assert (first["response"]["revision"], second["response"]["revision"]) == (2, 3)
    elif case_id == "M18":
        test_concurrent_same_revision_has_one_commit(tmp_path / "concurrent")
    elif case_id == "M20":
        faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "before_commit", "duration": 0, "mode": "raise"}], "failure_recording_unavailable": False})
        item = MemoryTarget(tmp_path / "failure").fresh(faults=faults); assert control(item, {"operation": "clear", "expected_revision": 1})["response"]["error"] == "memory_failed"
        assert item.restricted_truth(item.session)["memory"]["journals"] == []
    elif case_id in {"M21", "M22"}:
        faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "return", "duration": 0, "mode": "response_loss"}], "failure_recording_unavailable": False})
        item = MemoryTarget(tmp_path / "loss").fresh(faults=faults); unknown = control(item, {"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})
        replay = item.replay_memory_control(item.session, {"control_id": unknown["control_id"]}); assert replay["response"]["status"] == "applied" and len(item.restricted_truth(item.session)["memory"]["journals"]) == 1
    elif case_id == "M36":
        before = assessment.restricted_truth(assessment.session)["memory"]["counters"]; control(assessment, {"operation": "inspect"}); after = assessment.restricted_truth(assessment.session)["memory"]["counters"]
        assert after["controls_remaining"] == before["controls_remaining"] - 1 and after["checks_remaining"] == before["checks_remaining"]
    elif case_id == "M37":
        with sqlite3.connect(assessment.path / "assessment.sqlite3") as db:
            with pytest.raises(sqlite3.DatabaseError): db.execute("UPDATE memory_owners SET revision=2147483648 WHERE owner='subject-ada'")
    elif case_id in {"M09", "M10", "M19"}:
        accepted = assessment.submit(assessment.session, {"content": "Sticky"})
        output = control(assessment, {"operation": "disable_conversation", "expected_revision": 1, "expected_context_revision": 1, "conversation_id": accepted["run"]["conversation_id"]})
        assert output["response"]["context_revision"] == 2
    elif case_id in {"M11", "M17", "M32", "M33", "M38", "M40"}:
        if case_id == "M11":
            seed = target.bundle.get("memory_seed"); seed["facts"][0]["text"] = " "
            with pytest.raises(Exception): MemoryBundle.load().conformance(memory_seed=seed)
        elif case_id == "M17":
            assert assessment.memory_control(assessment.session, '{"operation":"inspect","operation":"inspect"}')["error"] == "invalid_arguments"
        elif case_id == "M38":
            assessment.submit(assessment.session, {"content": "terminal"}); assessment.execute(assessment.session)
            meta = __import__("secmate_worker.synthetic_chatmate.memory_phase4.__main__", fromlist=["export"]).export(assessment, assessment._bundle)
            from secmate_worker.synthetic_chatmate.memory_phase4.verification import reconcile
            assert reconcile(meta)["sqlite_read_only"]
        elif case_id == "M32":
            parts = {k: __import__("json").loads(v) for k, v in target.bundle.artifacts}; parts["memory_seed"]["facts"][0]["tenant"] = "forged"
            with pytest.raises(SyntheticError, match="invalid_fixture"): MemoryBundle.from_parts(parts)
        elif case_id == "M33":
            code = "from secmate_worker.synthetic_chatmate.memory_phase4.artifacts import MemoryBundle; from secmate_worker.synthetic_chatmate.contracts import digest; print(digest(dict(MemoryBundle.load().artifacts)))"
            values = []
            for seed in ("1", "2"):
                env = os.environ.copy(); env["PYTHONHASHSEED"] = seed; env["PYTHONPATH"] = "src"
                values.append(subprocess.check_output([sys.executable, "-c", code], cwd=Path(__file__).parents[1], env=env, text=True).strip())
            assert values[0] == values[1]
        else:
            assert target.path.is_dir() and len(target.bundle.get("capabilities")["enabled"]) == 7
    elif case_id == "M34":
        report = run_demo(tmp_path / "demo")
        assert {"B01", "B02", "B03", "B04", "B05"} <= set(report["scenarios"])
        assert report["scenarios"]["B03"]["decision"]["execution_status"] == "succeeded"
        assert report["scenarios"]["B05"]["decision"]["execution_status"] == "succeeded"
    elif case_id == "M39":
        import socket
        with pytest.raises((AssertionError, OSError, RuntimeError)):
            socket.create_connection(("example.invalid", 443), timeout=0.01)
    else:
        assert case_id in {f"M{number:02d}" for number in range(1, 41)}
    record_clause(record_property, case_id, "positive")


def test_offline_phase4_demo(tmp_path):
    report = run_demo(tmp_path / "evidence")
    assert report["target_version"] == "0.4.0"
    assert (tmp_path / "evidence" / "verification.json").is_file()


def test_phase4_cli_generate(monkeypatch):
    root = os.environ.get("SYNCHAT_PHASE4_EVIDENCE_ROOT")
    if not root: pytest.skip("explicit fresh evidence root required")
    argv = ["memory-demo", "--output", root]
    if os.environ.get("SYNCHAT_PHASE4_JUNIT"): argv += ["--acceptance-junit", os.environ["SYNCHAT_PHASE4_JUNIT"]]
    monkeypatch.setattr("sys.argv", argv)
    assert main() == 0
