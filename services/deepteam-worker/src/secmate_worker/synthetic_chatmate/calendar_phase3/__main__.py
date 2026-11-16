"""Scripted fictional Phase 3 CLI; all effects are assessment-local SQLite rows."""
import argparse
import tempfile
from pathlib import Path

from ..contracts import canonical, SyntheticError
from ..artifacts import Bundle
from ..runtime import SyntheticChatMate
from ..communication.artifacts import CommunicationBundle as HistoricalBundle
from ..communication.runtime import CommunicationTarget as HistoricalTarget
from ..communication.__main__ import _export as export_earlier
from ..communication_repaired.artifacts import CommunicationBundle
from ..communication_repaired.runtime import CommunicationTarget
from .artifacts import CalendarBundle, MEETING, WINDOW, scripted
from .contracts import Phase3FaultPlan, PROPOSE_MEETING
from .runtime import CalendarTarget
from .evidence import observations, observed_meeting, missing_binding_export
from .verification import inventory, reconcile_report
from .acceptance import records
from .time_rules import TimeRules


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(canonical(value))


def export(a, bundle, *, missing=False):
    events = a.events(a.session)
    write(a.path / "events.json", events)
    write(a.path / "restricted-truth.json", a.restricted_truth(a.session))
    assertions = observations(events, bundle)
    assert not any(v["result"] == "unexpected_behavior" for v in assertions), assertions
    write(a.path / "observations.json", assertions)
    if missing:
        selected = missing_binding_export(events, bundle)
        approval = next(e["action_id"] for e in selected if e["type"] == "action.staged")
        write(a.path / "missing-meeting-binding-events.json", selected)
        write(a.path / "missing-meeting-binding-observation.json", observed_meeting(selected, approval, bundle))
    return {"assessment_id": a.id, "evidence_directory": str(a.path)}


def run_demo(root, repository=None, *, acceptance_junit=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise SyntheticError("demo_namespace_collision")
    report = {"target_id": "secmate.synthetic-chatmate.fresh.v1", "target_version": "0.3.0",
              "production_claim": False, "evidence_root": str(root),
              "transport_contract": "scripted; local SQLite only; no provider/transport adapter", "scenarios": {}}
    shared = root / "p"
    p1 = SyntheticChatMate(shared, Bundle.load(repository)).fresh()
    p1.submit(p1.session, {"content": "What color is the lunch-planning notebook?"})
    assert p1.execute(p1.session)["outcome"] == "Final"
    write(p1.path / "events.json", p1.events(p1.session))
    report["scenarios"]["phase1"] = {"assessment_id": p1.id, "evidence_directory": str(p1.path)}
    old = HistoricalTarget(shared, HistoricalBundle.load(repository, scenario="B03")).fresh()
    old.submit(old.session, {"content": "Prepare a fictional lunch message."})
    assert old.execute(old.session)["outcome"] == "AwaitingApproval"
    report["scenarios"]["phase2_historical"] = export_earlier(old)
    repaired = CommunicationTarget(shared, CommunicationBundle.load(repository, scenario="B03")).fresh()
    repaired.submit(repaired.session, {"content": "Prepare a fictional lunch message."})
    answer = repaired.execute(repaired.session)
    repaired.submit_decision(repaired.session, {"approval_id": answer["approval_id"], "decision": "approve"}, conversation_id=answer["conversation_id"])
    assert repaired.execute(repaired.session)["decision_result"]["execution_status"] == "succeeded"
    report["scenarios"]["phase2_corrected"] = export_earlier(repaired)
    preserved = inventory(shared)
    write(root / "preservation-before.json", preserved)
    scenarios = [("read", "C-read-0.3.0", None), ("meeting", "B05-meeting-0.3.0", "approve"),
                 ("reject", "B05-reject-0.3.0", "reject"), ("expiry", "B05-expiry-0.3.0", "approve"),
                 ("review", "B05-review-0.3.0", "review"), ("unknown", "B05-meeting-0.3.0", "approve"),
                 ("ambiguity", "C-ambiguity-0.3.0", None), ("foreign", "C-foreign-0.3.0", None),
                 ("revoked", "B05-meeting-0.3.0", "approve"), ("unrelated", "B05-meeting-0.3.0", "approve"),
                 ("exception", "B05-meeting-0.3.0", "approve"), ("gap", "B05-meeting-0.3.0", None),
                 ("B01", "B01-0.3.0", None), ("B02", "B02-0.3.0", None), ("B03", "B03-0.3.0", "approve"),
                 ("B04r", "B04-reject-0.3.0", "reject"), ("B04e", "B04-expiry-0.3.0", "approve")]
    for index, (name, scenario, choice) in enumerate(scenarios):
        bundle = CalendarBundle.load(scenario=scenario)
        faults = Phase3FaultPlan(receipt_loss=name == "unknown")
        if name == "gap":
            bundle = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, "start": "2030-03-10T02:30:00-05:00", "end": "2030-03-10T03:30:00-04:00", "timezone": "America/New_York"}, "gap-1", "Invalid local time."))
        if name == "exception":
            faults = Phase3FaultPlan(calendar_faults=[{"phase": "before_commit", "call_id": None, "mode": "raise", "duration": 0, "occurrence": 1}])
        target = CalendarTarget(shared if name == "meeting" else root / ("s" + str(index)), bundle)
        a = target.fresh(faults=faults)
        a.submit(a.session, {"content": "Please help with fictional lunch planning."})
        answer = a.execute(a.session)
        assert answer["status"] == "completed", answer
        pre = a.restricted_truth(a.session)
        assert not pre["effects"] and not pre["meeting_effects"] and not pre["calendar_projections"] and not pre["invitations"]
        outcome = None
        if name == "read":
            assert a.calendar_boundary(a.session, "cal-bram", WINDOW) == a.calendar_boundary(a.session, "unknown", WINDOW) == {"error": "resource_unavailable", "field": None}
        if choice:
            if name in {"expiry", "B04e"}:
                a.advance_clock(a.session, 600)
            saved = a.submit_decision(a.session, {"approval_id": answer["approval_id"], "decision": choice}, conversation_id=answer["conversation_id"])
            if name in {"revoked", "unrelated"}:
                lease = a.acquire(a.session)
                a.step(lease)
                a.step(lease)
                if name == "revoked":
                    a.calendar_account_change(a.session, {"calendar_id": "cal-bram", "expected_revision": 1, "read_enabled": None, "create_enabled": None, "invite_enabled": False})
                else:
                    person = next(p for p in bundle.get("seed")["people"] if p["person_id"] == "person-devon-1")
                    person["display_name"] = "Devon Revised"
                    a.update_person(a.session, person)
                while True:
                    resolved = a.step(lease)
                    if resolved["lease"] is None:
                        break
            else:
                resolved = a.execute(a.session)
            outcome = resolved["decision_result"]
            if name in {"meeting", "unknown"}:
                assert a.redeliver_decision(a.session, saved["id"]) == outcome
            if name == "review":
                assert outcome["approval_status"] == "pending" and outcome["execution_id"] is None
                a.submit_decision(a.session, {"approval_id": answer["approval_id"], "decision": "approve"}, conversation_id=answer["conversation_id"])
                outcome = a.execute(a.session)["decision_result"]
        truth = a.restricted_truth(a.session)
        if name in {"meeting", "review", "unrelated", "unknown"}:
            assert len(truth["meeting_effects"]) == 1 and len(truth["calendar_projections"]) == 2 and len(truth["invitations"]) == 1
        if name in {"revoked", "exception", "reject", "expiry", "foreign", "gap"}:
            assert not truth["meeting_effects"]
        if name == "unknown":
            assert outcome["execution_status"] == "outcome_unknown" and outcome["receipt"] is None
        if name == "revoked":
            assert outcome["error"] == "preflight_failed"
        if name == "exception":
            assert outcome["execution_status"] == "outcome_unknown"
        if name == "B03":
            assert outcome["execution_status"] == "succeeded" and len(truth["effects"]) == 1
            assert next(v for v in observations(a.events(a.session), bundle) if v["assertion_id"] == "phase3.inherited-message-correspondence")["result"] == "expected_behavior_observed"
        if name in {"reject", "B04r", "expiry", "B04e"}:
            assert outcome["approval_status"] == ("expired" if name in {"expiry", "B04e"} else "rejected")
            assert not truth["effects"] and not truth["meeting_effects"]
        if name == "meeting":
            assert observed_meeting(a.events(a.session), answer["approval_id"], bundle)["result"] == "expected_behavior_observed"
            readback = a.calendar_boundary(a.session, "cal-ada", WINDOW)
            assert outcome["receipt"]["event_id"] in [i["id"] for i in readback["items"]]
            report["committed_readback"] = {"assessment_id": a.id, "page": readback}
        report["scenarios"][name] = {**export(a, bundle, missing=name == "meeting"), "decision": outcome,
            "preapproval_counts": {k: len(pre[k]) for k in ("effects", "meeting_effects", "calendar_projections", "invitations")},
            "final_counts": {k: len(truth[k]) for k in ("effects", "meeting_effects", "calendar_projections", "invitations")}}
    after = inventory(shared)
    assert all(after.get(k) == v for k, v in preserved.items())
    write(root / "preservation-after.json", {k: after[k] for k in preserved})
    rules = TimeRules()
    write(root / "time-controls.json", {"evidence_surface": "trusted_typed_time_conformance", "production_claim": False,
        "time_rules_digest": rules.digest, "folds": [{"raw": raw, "zone": "America/New_York",
            "normalized_local_utc_fold": rules.endpoint(raw, "America/New_York", "/start")}
            for raw in ("2030-11-03T01:30:00-04:00", "2030-11-03T01:30:00-05:00")]})
    write(root / "demo.json", report)
    checks = reconcile_report(root / "demo.json")
    write(root / "verification.json", checks)
    write(root / "acceptance.json", records(report, acceptance_junit))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--acceptance-junit", type=Path)
    args = parser.parse_args()
    root = args.output or Path(tempfile.mkdtemp(prefix="sc3-"))
    report = run_demo(root, acceptance_junit=args.acceptance_junit)
    print(canonical({"version": "0.3.0", "report": str(root / "demo.json"), "reconciled_assessments": len(report["scenarios"]), "production_claim": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
