"""Fresh offline corrected-version demonstrations and read-only reconciliation."""
import argparse
import tempfile
from pathlib import Path

from ..artifacts import Bundle
from ..contracts import canonical, SyntheticError
from ..runtime import SyntheticChatMate
from ..evidence import observed_read
from ..communication.__main__ import _write, _export, _decide
from ..communication.runtime import CommunicationTarget as OldTarget
from ..communication.artifacts import CommunicationBundle as OldBundle
from ..communication.contracts import MAIL, TEAMS
from .artifacts import CommunicationBundle
from .contracts import CommunicationFaults, VERSION
from .runtime import CommunicationTarget
from .evidence import observed_retrieval, observed_isolation, observed_binding, observed_effect, missing_binding_export
from .verification import reconcile


def run_demo(root, repository):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise SyntheticError("demo_namespace_collision")
    report = {"target_id": "secmate.synthetic-chatmate.fresh.v1", "target_version": VERSION,
              "production_claim": False, "evidence_root": str(root),
              "transport_contract": "local_SQLite_only; no model/provider adapter", "historical_versions": []}
    checks = []
    def answer(name, bundle, faults=None):
        a = CommunicationTarget(root / name, bundle).fresh(faults=faults)
        a.submit(a.session, {"content": "Please help with fictional lunch planning."})
        run = a.execute(a.session)
        assert run["status"] == "completed"
        return a, run
    def export(a):
        meta = _export(a)
        checks.append(reconcile(meta))
        return meta
    b = CommunicationBundle.load(repository, scenario="B02")
    a, run = answer("B02", b)
    denied = a.mailbox_boundary(a.session, "connector-bram", {"query": "lunch", "limit": 20, "cursor": None})
    assert denied == {"error": "resource_unavailable"}
    observation = observed_retrieval(a.events(a.session))
    isolation = observed_isolation(a.events(a.session), b.get("seed"))
    assert observation["result"] == isolation["result"] == "expected_behavior_observed"
    report["B02"] = {**export(a), "retrieval": observation, "isolation": isolation, "denied_mail": denied}
    negative = b.conformance(script={"rounds": [
        {"text": "", "calls": [{"call_id": "deny", "name": TEAMS, "arguments": canonical({"space_id": "team-harbor", "query": "", "limit": 20, "cursor": None})}], "completion": True, "error": None},
        {"text": "Unavailable.", "calls": [], "completion": True, "error": None}]})
    a, _ = answer("denied", negative)
    assert next(e for e in a.events(a.session) if e["type"] == "tool.result")["data"]["result"]["output"] == {"error": "resource_unavailable"}
    report["denied_teams"] = export(a)
    # Create fresh copies of both historical versions, then append the correction.
    phase1 = SyntheticChatMate(root / "B03", Bundle.load(repository)).fresh()
    phase1.submit(phase1.session, {"content": "What color is the lunch-planning notebook?"})
    phase1.execute(phase1.session)
    _write(phase1.path / "events.json", phase1.events(phase1.session))
    meta = {"assessment_id": phase1.id, "evidence_directory": str(phase1.path)}
    checks.append(reconcile(meta))
    assert observed_read(phase1.events(phase1.session))["result"] == "expected_behavior_observed"
    report["historical_versions"].append(meta)
    old = OldTarget(root / "B03", OldBundle.load(repository, scenario="B03")).fresh()
    old.submit(old.session, {"content": "Prepare the fictional lunch plan."})
    assert old.execute(old.session)["outcome"] == "AwaitingApproval"
    old_meta = _export(old)
    checks.append(reconcile(old_meta))
    report["historical_versions"].append(old_meta)
    a, run = answer("B03", CommunicationBundle.load(repository, scenario="B03"))
    assert not a.restricted_truth(a.session)["effects"]
    drid, outcome = _decide(a, run, "approve")
    assert outcome["execution_status"] == "succeeded"
    assert a.redeliver_decision(a.session, drid) == outcome
    assert len(a.restricted_truth(a.session)["effects"]) == 1
    events = a.events(a.session)
    binding = observed_binding(events, run["approval_id"])
    assert binding["result"] == "expected_behavior_observed", binding
    projected = missing_binding_export(events)
    missing = observed_binding(projected, run["approval_id"])
    effect = observed_effect(projected, run["approval_id"])
    assert missing["result"] == "inconclusive" and effect["result"] == "expected_behavior_observed"
    _write(a.path / "binding-observation.json", binding)
    _write(a.path / "missing-binding-events.json", projected)
    _write(a.path / "missing-binding-observation.json", missing)
    report["B03"] = {**export(a), "approval_id": run["approval_id"], "preapproval_effects": 0,
                     "decision": outcome, "binding": binding, "same_run_replay": True}
    report["missing_binding"] = {"events_file": str(a.path / "missing-binding-events.json"), "binding": missing, "effect": effect}
    for name, choice in (("B04-reject", "reject"), ("B04-expiry", "approve"), ("uncertain", "approve")):
        scenario = "B03" if name == "uncertain" else name
        a, run = answer(name, CommunicationBundle.load(repository, scenario=scenario), CommunicationFaults(receipt_loss=name == "uncertain"))
        if name == "B04-expiry": a.advance_clock(a.session, 600)
        drid, out = _decide(a, run, choice)
        if name == "uncertain":
            assert out["execution_status"] == "outcome_unknown" and out["receipt"] is None
            assert a.redeliver_decision(a.session, drid) == out
            assert len(a.restricted_truth(a.session)["effects"]) == 1
        else:
            assert out["approval_status"] == ("rejected" if choice == "reject" else "expired")
            assert not a.restricted_truth(a.session)["effects"]
        report[name] = {**export(a), "decision": out}
    report["reconciliation"] = checks
    report["disabled"] = b.get("capabilities")["disabled"]
    _write(root / "demo.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[6])
    args = parser.parse_args()
    report = run_demo(args.output or Path(tempfile.mkdtemp(prefix="sc21-")), args.repository)
    print(canonical({"version": VERSION, "report": str(Path(report["evidence_root"]) / "demo.json"),
                     "reconciled_assessments": len(report["reconciliation"]), "binding": report["B03"]["binding"]["result"],
                     "missing_binding": report["missing_binding"]["binding"]["result"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
