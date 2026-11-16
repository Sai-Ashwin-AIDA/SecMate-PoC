"""Offline scripted Phase 4 demo and evidence export."""
import argparse
import tempfile
from pathlib import Path

from ...job_runtime import canonical
from ..contracts import SyntheticError
from .acceptance import records
from .artifacts import MemoryBundle
from .contracts import Phase4FaultPlan
from .evidence import missing_memory_binding_export, missing_meeting_binding_export, observations, selected_observation
from ..calendar_repaired.evidence import observed_meeting
from .runtime import MemoryTarget
from .verification import reconcile_report


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(canonical(value))


def export(assessment, bundle, *, selected=False, meeting_approval=None):
    events = assessment.events(assessment.session)
    truth = assessment.restricted_truth(assessment.session)
    host = truth["memory"]["host_outputs"]
    values = observations(events, bundle, host)
    write(assessment.path / "events.json", events)
    write(assessment.path / "memory-host-outputs.json", host)
    write(assessment.path / "restricted-truth.json", truth)
    write(assessment.path / "observations.json", values)
    if selected:
        projected = missing_memory_binding_export(events, bundle)
        write(assessment.path / "missing-memory-request-binding-events.json", projected)
        write(assessment.path / "missing-memory-request-binding-observation.json", selected_observation(projected, bundle))
    if meeting_approval:
        projected = missing_meeting_binding_export(events)
        write(assessment.path / "missing-meeting-binding-events.json", projected)
        write(assessment.path / "missing-meeting-binding-observation.json", observed_meeting(projected, meeting_approval, bundle))
    return {"assessment_id": assessment.id, "evidence_directory": str(assessment.path)}


def run_demo(root, *, acceptance_junit=None):
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()): raise SyntheticError("demo_namespace_collision")
    short_parent = Path(tempfile.gettempdir()) / "opencode"
    short_parent.mkdir(exist_ok=True)
    def scenario_root(label):
        # Assessment SQLite paths stay independent of arbitrarily deep pytest
        # output roots. mkdtemp provides exclusive fresh allocation; demo.json
        # retains the resolved evidence path for reconciliation.
        return Path(tempfile.mkdtemp(prefix="m4" + label[:3] + "-", dir=short_parent))
    report = {"target_id": "secmate.synthetic-chatmate.fresh.v1", "target_version": "0.4.0", "production_claim": False,
              "transport_contract": "scripted; local SQLite only; no provider adapter", "evidence_root": str(root), "scenarios": {}}
    def scenario(name, *, profile="private", before=None, between=None, faults=None, subject="subject-ada"):
        scenario_id = "M-" + subject.removeprefix("subject-") + "-0.4.0" if subject != "subject-ada" else "M-baseline-0.4.0"
        bundle = MemoryBundle.load(scenario=scenario_id)
        assessment = MemoryTarget(scenario_root(name), bundle).fresh(subject=subject, context_profile=profile, faults=faults)
        if before: before(assessment, None, None)
        snapshot = "snapshot-" + subject.removeprefix("subject-")
        accepted = assessment.submit(assessment.session, {"content": "Please check the fictional memory context."}, snapshot_id=snapshot)
        lease = assessment.acquire(assessment.session); first = assessment.step(lease)
        if first["status"] != "running": raise AssertionError(first)
        if between: between(assessment, accepted, lease)
        final = assessment.step(lease)
        if final["outcome"] != "Final": raise AssertionError(final)
        report["scenarios"][name] = export(assessment, bundle, selected=name == "forget")

    scenario("inspect", before=lambda a, _x, _l: a.memory_control(a.session, canonical({"operation": "inspect"})))
    scenario("forget", between=lambda a, _x, _l: a.memory_control(a.session, canonical({"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"})))
    scenario("clear", between=lambda a, _x, _l: a.memory_control(a.session, canonical({"operation": "clear", "expected_revision": 1})))
    scenario("disable", between=lambda a, x, _l: a.memory_control(a.session, canonical({"operation": "disable_conversation", "expected_revision": 1,
        "expected_context_revision": 1, "conversation_id": x["run"]["conversation_id"]})))
    scenario("expiry", between=lambda a, _x, lease: a.advance_at_memory_checkpoint(a.session, lease, {"seconds": 10}))
    scenario("unavailable", faults=Phase4FaultPlan(memory={"loads": [{"round": 2, "attempt": 1, "duration": 0, "mode": "unavailable"}],
        "controls": [], "failure_recording_unavailable": False}))
    for profile in ("shared", "multiparticipant", "project", "deleted", "conversation_disabled"):
        scenario("ineligible-" + profile, profile=profile)
    scenario("bram", subject="subject-bram")
    scenario("cyra", subject="subject-cyra")
    response_faults = Phase4FaultPlan(memory={"loads": [], "controls": [{"ordinal": 1, "phase": "return", "duration": 0, "mode": "response_loss"}],
        "failure_recording_unavailable": False})
    def lose_response(a, _x, _l):
        output = a.memory_control(a.session, canonical({"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}))
        if output["response"]["status"] != "outcome_unknown": raise AssertionError(output)
        replay = a.replay_memory_control(a.session, {"control_id": output["control_id"]})
        if replay["response"]["status"] != "applied": raise AssertionError(replay)
    scenario("response-loss", faults=response_faults, between=lose_response)

    # Conformance context mutations use the same durable controller pipeline.
    conformance = MemoryBundle.load().conformance()
    changed = MemoryTarget(scenario_root("conformance"), conformance).fresh()
    accepted = changed.submit(changed.session, {"content": "Conformance context."})
    lease = changed.acquire(changed.session); changed.step(lease)
    output = changed.fixture_context_change(changed.session, {"operation": "fixture_context_change", "expected_context_revision": 1,
        "conversation_id": accepted["run"]["conversation_id"], "context": {"shared": True, "participant_ids": ["subject-ada"], "project_id": None, "deleted": False}})
    if output["response"]["status"] != "applied": raise AssertionError(output)
    changed.step(lease)
    report["scenarios"]["conformance-context"] = export(changed, conformance)

    # Re-run inherited B01-B05 behavior under actual 0.4.0 artifacts/runtime.
    workflows = (("B01", "B01-0.4.0", None), ("B02", "B02-0.4.0", None), ("B03", "B03-0.4.0", "approve"),
        ("B04", "B04-reject-0.4.0", "reject"), ("B05", "B05-meeting-0.4.0", "approve"))
    for name, script_id, decision in workflows:
        bundle = MemoryBundle.load(scenario=script_id)
        assessment = MemoryTarget(scenario_root(name), bundle).fresh()
        assessment.submit(assessment.session, {"content": "Run the bound inherited fictional workflow."})
        run = assessment.execute(assessment.session)
        decision_result = None
        if decision:
            saved = assessment.submit_decision(assessment.session, {"approval_id": run["approval_id"], "decision": decision}, conversation_id=run["conversation_id"])
            decided = assessment.execute(assessment.session); decision_result = decided["decision_result"]
            if name == "B03" and decision_result["execution_status"] != "succeeded": raise AssertionError(decision_result)
            if name == "B04" and decision_result["approval_status"] != "rejected": raise AssertionError(decision_result)
            if name == "B05" and len(assessment.restricted_truth(assessment.session)["meeting_effects"]) != 1: raise AssertionError("missing meeting effect")
        report["scenarios"][name] = {**export(assessment, bundle, meeting_approval=run.get("approval_id") if name == "B05" else None),
            "decision": decision_result}
    write(root / "demo.json", report)
    write(root / "verification.json", reconcile_report(root / "demo.json"))
    write(root / "acceptance.json", records(report, acceptance_junit))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--acceptance-junit", type=Path)
    args = parser.parse_args()
    root = args.output or Path(tempfile.mkdtemp(prefix="m4-"))
    report = run_demo(root, acceptance_junit=args.acceptance_junit)
    print(canonical({"version": "0.4.0", "report": str(root / "demo.json"), "assessments": len(report["scenarios"]), "production_claim": False}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
