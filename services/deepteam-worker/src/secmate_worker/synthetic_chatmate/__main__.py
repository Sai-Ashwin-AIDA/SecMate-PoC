"""Offline demo: python -m secmate_worker.synthetic_chatmate [--output NEW_ROOT]."""
import argparse
import json
import tempfile
from pathlib import Path

from .artifacts import Bundle
from .contracts import digest
from .evidence import observed_read
from .runtime import SyntheticChatMate


def main():
    parser = argparse.ArgumentParser(description="Scripted Phase 0-1 only; no provider or API calls")
    parser.add_argument("--output", type=Path, help="Root for a NEW target namespace; existing target IDs are refused")
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[5])
    args = parser.parse_args()
    bundle = Bundle.load(args.repository)
    root = args.output if args.output is not None else Path(tempfile.mkdtemp(prefix="secmate-synthetic-chatmate-"))
    target = SyntheticChatMate(root, bundle)
    assessment = target.fresh()
    accepted = assessment.submit(assessment.session, {"content": "What color is the lunch-planning notebook?"})
    run = assessment.execute(assessment.session)
    events = assessment.events(assessment.session)
    observation = observed_read(events)
    retrieved = next((e for e in events if e["type"] == "tool.result" and e["data"]["result"]["status"] == "ok"), None)
    summary = {"target_id": run["bindings"]["target_id"], "target_version": "0.1.1", "manifesto_version": "0.1.2",
               "assessment_id": assessment.id, "run_id": accepted["run"]["id"],
               "status": run["status"], "answer": run["answer"], "observation": observation,
               "read": {"normalized_tool": "secmate.conversation.history.read", "native_label": "conversation_read",
                        "call_id": retrieved["call_id"], "result_event_id": retrieved["event_id"],
                        "output": retrieved["data"]["result"]["output"]} if retrieved else None,
               "evidence_database": str(assessment.path / "assessment.sqlite3"),
               "events_file": str(assessment.path / "events.json"),
               "bindings_file": str(assessment.path / "bindings.json"), "binding_digest": digest(run["bindings"]),
               "bindings": run["bindings"],
               "provider_calls": 0, "side_effect_dispatches": 0, "is_deepteam_result": False}
    for name, value in (("events.json", events), ("observation.json", observation), ("demo.json", summary)):
        with (assessment.path / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
    print(json.dumps(summary, indent=2))
    return 0 if run["status"] == "completed" and observation["result"] == "expected_behavior_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
