"""Independent read-only artifact/SQLite checks, separate from public observers."""
import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from ..communication_repaired.verification import reconcile as reconcile_earlier
from ..communication.contracts import Approval, Execution, Effect
from .artifacts import CalendarBundle
from .contracts import validate, validate_event, INVITATION_EVENT
from .evidence import observations, observed_meeting


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def inventory(root):
    root = Path(root)
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reconcile(meta):
    directory = Path(meta["evidence_directory"])
    if directory.parent.parent.name != "0.3.0":
        return reconcile_earlier(meta)
    before = inventory(directory)
    version = directory.parent.parent
    definitions = {p.stem: load(p) for p in (version / "definitions").glob("*.json")}
    bundle = CalendarBundle.from_parts(definitions)
    required = set(dict(bundle.artifacts))
    binding, faults = [load(directory / (name + ".json")) for name in ("bindings", "faults")]
    registration = load(version / "registration.json")
    assert set(definitions) == required == set(registration["definition_digests"])
    hashes = {k: sha(v) for k, v in definitions.items()}
    assert registration["definition_digests"] == binding["artifact_digests"] == hashes
    assert sha(hashes) == binding["fixture_digest"] and sha(faults) == binding["fault_schedule_digest"]
    assert registration["target_version"] == binding["target_version"] == "0.3.0"
    assert registration["phase_scope"] == [0, 1, 2, 3] and registration["target_id"] == binding["target_id"] == "secmate.synthetic-chatmate.fresh.v1"
    source = Path(__file__).parents[1]
    for name, expected in definitions["implementation"].items():
        prefix, _, filename = name.partition("/")
        path = source / filename if prefix == "phase1" else source / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    validate("Phase3FaultPlan", faults)
    events, truth = load(directory / "events.json"), load(directory / "restricted-truth.json")
    with sqlite3.connect((directory / "assessment.sqlite3").resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = lambda table: [json.loads(r[0]) for r in db.execute(f"SELECT payload FROM {table} ORDER BY rowid")]
        assert events == rows("events")
        state = rows("state")[0]
        assert state["assessment_id"] == binding["assessment_id"] == meta["assessment_id"]
        assert state["generation"] == binding["state_generation"]
        runs = {r["id"]: r for r in rows("runs")}
        assert not db.execute("SELECT count(*) FROM queue").fetchone()[0]
        assert all(r["lease"] is None and r["status"] in {"completed", "failed", "cancelled"} for r in runs.values())
        previous = None
        for event in events:
            validate_event(event, bundle)
            assert event["binding_digest"] == sha({**binding, "run_id": event["run_id"]} if event["run_id"] else binding)
            assert event["caused_by"] == (previous["event_id"] if previous else None)
            assert not previous or (event["event_id"] > previous["event_id"] and datetime.fromisoformat(event["logical_time"].replace("Z", "+00:00")) >= datetime.fromisoformat(previous["logical_time"].replace("Z", "+00:00")))
            previous = event
        approvals = {a["id"]: a for a in rows("approvals")}
        executions = {x["id"]: x for x in rows("executions")}
        records = {r["id"]: r for r in rows("calendar_records")}
        for a in approvals.values():
            if a["action_kind"] == "meeting":
                validate("MeetingApproval", a)
                assert sha(a["prepared"]) == a["prepared_digest"] == a["review"]["prepared_digest"]
                assert sha(a["organizer_snapshot"]) == a["review"]["organizer_snapshot_digest"]
                assert sha(a["attendee_snapshot"]) == a["review"]["attendee_snapshot_digest"]
                assert sha(a["prepared"]["attendee_ids"]) == a["review"]["attendee_ids_digest"]
                assert sha({"tool": "secmate.propose_meeting", "arguments": a["prepared"]}) == a["argument_digest"]
                assert sha({k: a["prepared"][k] for k in ("title", "description")}) == a["review"]["content_digest"]
                timing = {k: a["prepared"][k] for k in ("start", "end", "timezone")}
                timing.update(start_utc=a["review"]["start_utc"], end_utc=a["review"]["end_utc"], time_rules_digest=binding["time_rules_digest"])
                assert sha(timing) == a["review"]["timing_digest"]
                assert a["transformation_digest"] == sha(definitions["transformation"])
            else:
                Approval.model_validate({k: v for k, v in a.items() if k != "action_kind"})
        for x in executions.values():
            if x["action_kind"] == "meeting":
                validate("MeetingExecution", x)
            else:
                Execution.model_validate({k: v for k, v in x.items() if k != "action_kind"})
            assert x["action_kind"] == approvals[x["approval_id"]]["action_kind"]
            assert approvals[x["approval_id"]]["decision_run_id"] == x["decision_run_id"]
            assert runs[x["decision_run_id"]]["decision_result"]["execution_status"] == x["status"]
            if x["dispatch"] is not None:
                assert sha(x["dispatch"]) == x["dispatch_digest"]
        for table in ("calendar_records", "meeting_effects", "calendar_projections", "invitations", "executions", "effects", "normalizations"):
            assert truth[table] == rows(table)
        from .services import normalize_meeting
        from .time_rules import TimeRules
        for normalization in rows("normalizations"):
            requested = next(e for e in events if e["type"] == "tool.requested" and e["run_id"] == normalization["run_id"] and e["call_id"] == normalization["call_id"])
            prepared, times = normalize_meeting(json.loads(requested["data"]["arguments"]), TimeRules(definitions["time_rules"]))
            assert normalization["times"] == times and normalization["prepared_digest"] == sha(prepared)
        for effect in rows("meeting_effects"):
            validate("MeetingEffect", effect)
            x = executions[effect["execution_id"]]
            a = approvals[effect["approval_id"]]
            record = records[effect["event_id"]]
            assert record == effect["calendar_record"]
            assert effect["dispatch_digest"] == x["dispatch_digest"] and effect["prepared_digest"] == a["prepared_digest"]
            assert all(record[k] == x["dispatch"][k] for k in ("title", "description", "start", "end", "start_utc", "end_utc", "timezone"))
            projections = [p for p in rows("calendar_projections") if p["effect_id"] == effect["effect_id"]]
            invitations = [p for p in rows("invitations") if p["effect_id"] == effect["effect_id"]]
            assert len(projections) == len(record["attendee_ids"]) + 1 and len(invitations) == len(record["attendee_ids"])
            assert {p["owner_person_id"] for p in projections} == {record["organizer_id"], *record["attendee_ids"]}
            assert [p["attendee_id"] for p in invitations] == record["attendee_ids"]
            assert all(p["record_digest"] == sha(record) and p["event_id"] == record["id"] for p in projections + invitations)
            committed = [e for e in events if e["type"] == INVITATION_EVENT and e["data"]["execution_id"] == x["id"]]
            assert len(committed) == 1
            data = committed[0]["data"]
            assert data["approval_id"] == a["id"] and data["decision_run_id"] == x["decision_run_id"]
            assert data["effect_id"] == effect["effect_id"] and data["event_id"] == record["id"] and data["record_digest"] == sha(record)
            assert data["invitations"] == [{**{k: p[k] for k in ("id", "effect_id", "event_id", "attendee_id", "calendar_id", "record_digest")},
                                            "approval_id": a["id"], "execution_id": x["id"]} for p in invitations]
            if x["receipt"] is not None:
                assert x["receipt"]["invitation_ids"] == [p["id"] for p in invitations]
                assert x["receipt"]["effect_id"] == effect["effect_id"] and x["receipt"]["event_id"] == effect["event_id"]
                assert x["receipt"]["completed_at"] == effect["committed_at"] and all(p["created_at"] == effect["committed_at"] for p in invitations)
        for effect in rows("effects"):
            Effect.model_validate(effect)
            x = executions[effect["execution_id"]]
            assert x["action_kind"] == "message" and effect["dispatch_digest"] == x["dispatch_digest"]
            assert all(effect[k] == x["dispatch"][k] for k in ("channel", "sender_id", "subject", "body"))
            assert effect["recipient_ids"] == [p["person_id"] for p in x["dispatch"]["recipients"]]
            linked = [(r[0], r[1], json.loads(r[2])) for r in db.execute("SELECT kind,destination,payload FROM projections WHERE effect_id=?", (effect["effect_id"],))]
            expected = {("outbox", effect["sender_id"]), *[("inbox", p) for p in effect["recipient_ids"]]} if effect["channel"] == "mail" else {("direct_chat", x["dispatch"]["destination"])}
            assert {(r[0], r[1]) for r in linked} == expected and all(r[2] == effect for r in linked)
        for event in events:
            if event["type"] == "tool.result" and event["data"]["name"] == "secmate.read_calendar" and event["data"]["result"]["status"] == "ok":
                for item in event["data"]["result"]["output"]["items"]:
                    record = records[item["id"]]
                    assert all(item[k] == record[k] for k in ("title", "description", "organizer_id", "attendee_ids", "start", "end", "timezone"))
                    assert item["source_ref"]["content_digest"] == sha(record)
        counts = {table: len(rows(table)) for table in ("calendar_records", "meeting_effects", "calendar_projections", "invitations", "effects")}
    assert load(directory / "observations.json") == observations(events, bundle)
    if (directory / "missing-meeting-binding-events.json").exists():
        selected = load(directory / "missing-meeting-binding-events.json")
        approval = next(e["action_id"] for e in selected if e["type"] == "action.staged")
        assert load(directory / "missing-meeting-binding-observation.json") == observed_meeting(selected, approval, bundle)
    assert before == inventory(directory)
    return {"assessment_id": meta["assessment_id"], "version": "0.3.0", "sqlite_read_only": True, "events": len(events), **counts}


def reconcile_report(report_path):
    report = load(report_path)
    return {name: reconcile(meta) for name, meta in report["scenarios"].items()}
