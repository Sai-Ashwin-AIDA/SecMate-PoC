"""Read-only reconciliation of newly exported evidence, distinct from observers."""
import hashlib
import json
import sqlite3
from pathlib import Path

from ..contracts import digest
from ..communication.contracts import Approval, Execution, Effect
from .contracts import bounded_json


def _sha(value):
    # Independent standard-library canonicalization for saved artifact checks.
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reconcile(meta):
    assessment = Path(meta["evidence_directory"])
    version = assessment.parent.parent
    definitions = {p.stem: bounded_json(p.read_text(encoding="utf-8"), maximum=4000000) for p in (version / "definitions").glob("*.json")}
    registration = bounded_json((version / "registration.json").read_text(encoding="utf-8"))
    binding = bounded_json((assessment / "bindings.json").read_text(encoding="utf-8"))
    faults = bounded_json((assessment / "faults.json").read_text(encoding="utf-8"))
    assert registration["target_version"] == binding["target_version"] == version.name
    hashes = {k: _sha(v) for k, v in definitions.items()}
    assert hashes == registration["definition_digests"] == binding["artifact_digests"]
    assert _sha(hashes) == binding["fixture_digest"]
    assert _sha(faults) == binding["fault_schedule_digest"]
    source = Path(__file__).parents[1]
    for name, expected in definitions["implementation"].items():
        prefix, _, filename = name.partition("/")
        path = source / filename if prefix == "phase1" else source / name if filename else source / prefix
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    events = bounded_json((assessment / "events.json").read_text(encoding="utf-8"), maximum=10000000)
    before = hashlib.sha256((assessment / "assessment.sqlite3").read_bytes()).hexdigest()
    with sqlite3.connect((assessment / "assessment.sqlite3").resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        saved_events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY id")]
        assert saved_events == events
        state = json.loads(db.execute("SELECT payload FROM state").fetchone()[0])
        assert state["assessment_id"] == binding["assessment_id"] == meta["assessment_id"]
        runs = {r["id"]: r for r in (json.loads(row[0]) for row in db.execute("SELECT payload FROM runs"))}
        assert not db.execute("SELECT count(*) FROM queue").fetchone()[0]
        assert all(r["lease"] is None and r["status"] in {"completed", "failed", "cancelled"} for r in runs.values())
        previous = None
        for event in events:
            expected = {**binding, "run_id": event["run_id"]} if event["run_id"] else binding
            assert event["binding_digest"] == _sha(expected)
            assert event["assessment_id"] == binding["assessment_id"] and event["state_generation"] == binding["state_generation"]
            assert event["caused_by"] == (previous["event_id"] if previous else None)
            assert previous is None or event["event_id"] > previous["event_id"]
            previous = event
        counts = {"events": len(events), "runs": len(runs)}
        if version.name != "0.1.1":
            truth = bounded_json((assessment / "restricted-truth.json").read_text(encoding="utf-8"), maximum=10000000)
            assert truth["evidence_surface"] == "restricted_fixture_truth"
            effects = [json.loads(r[0]) for r in db.execute("SELECT payload FROM effects ORDER BY rowid")]
            executions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM executions ORDER BY rowid")]
            projections = [{"kind": r[0], "destination": r[1], "effect": json.loads(r[2])} for r in db.execute("SELECT kind,destination,payload FROM projections ORDER BY rowid")]
            assert (truth["effects"], truth["executions"], truth["projections"]) == (effects, executions, projections)
            for a in (json.loads(r[0]) for r in db.execute("SELECT payload FROM approvals")):
                Approval.model_validate(a)
                assert _sha(a["prepared"]) == a["prepared_digest"] == a["review"]["prepared_digest"]
                assert a["review"] == {**a["prepared"], "prepared_digest": a["prepared_digest"]}
                assert _sha(a["prepared"]["recipient_ids"]) == a["recipient_digest"]
                assert _sha({k: a["prepared"][k] for k in ("subject", "body")}) == a["content_digest"]
            for x in executions:
                Execution.model_validate(x)
                if x["dispatch"] is not None:
                    assert _sha(x["dispatch"]) == x["dispatch_digest"]
                assert runs[x["decision_run_id"]]["decision_result"]["execution_status"] == x["status"]
            for effect in effects:
                Effect.model_validate(effect)
                x = next(x for x in executions if x["id"] == effect["execution_id"])
                assert effect["dispatch_digest"] == x["dispatch_digest"]
                assert effect["prepared_digest"] == x["prepared_digest"]
                assert effect["recipient_ids"] == [r["person_id"] for r in x["dispatch"]["recipients"]]
                assert all(effect[k] == x["dispatch"][k] for k in ("channel", "sender_id", "subject", "body"))
                linked = [p for p in projections if p["effect"]["effect_id"] == effect["effect_id"]]
                assert all(p["effect"] == effect for p in linked)
                if effect["channel"] == "mail":
                    assert {(p["kind"], p["destination"]) for p in linked} == {("outbox", effect["sender_id"]), *[("inbox", p) for p in effect["recipient_ids"]]}
                else:
                    assert [(p["kind"], p["destination"]) for p in linked] == [("direct_chat", x["dispatch"]["destination"])]
            for e in events:
                if e["type"] == "tool.result" and e["data"].get("name") in {"secmate.search_mail", "secmate.read_teams"} and e["data"]["result"]["status"] == "ok":
                    collection = "mail" if e["data"]["name"] == "secmate.search_mail" else "teams"
                    for item in e["data"]["result"]["output"]["items"]:
                        record = next(r for r in definitions["seed"][collection] if r["id"] == item["id"])
                        fields = ("id", "subject", "body") if collection == "mail" else ("id", "thread_id", "body")
                        assert {k: item[k] for k in fields} == {k: record[k] for k in fields}
                        assert item["source_ref"]["content_digest"] == _sha(record)
            counts.update(effects=len(effects), projections=len(projections), executions=len(executions))
    assert hashlib.sha256((assessment / "assessment.sqlite3").read_bytes()).hexdigest() == before
    return {"assessment_id": meta["assessment_id"], "version": version.name, "sqlite_read_only": True,
            "artifact_digest": _sha(hashes), **counts}
