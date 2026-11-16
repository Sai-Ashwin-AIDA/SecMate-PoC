"""Assessment-local communication tables layered on the accepted transaction store."""
from __future__ import annotations

from ...job_runtime import canonical
from ..contracts import SyntheticError, strict_json
from ..store import Store
from .contracts import Approval, Effect, Execution, Person


class CommunicationStore(Store):
    def __init__(self, path, state, seed):
        super().__init__(path, state)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE resources (collection TEXT, id TEXT, position INTEGER, payload TEXT NOT NULL,
                                        PRIMARY KEY(collection,id));
                CREATE TABLE live_people (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE approvals (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE executions (id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE effects (execution_id TEXT PRIMARY KEY, effect_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE projections (effect_id TEXT, kind TEXT, destination TEXT, payload TEXT NOT NULL,
                                          PRIMARY KEY(effect_id,kind,destination));
                CREATE TRIGGER approvals_frozen BEFORE UPDATE ON approvals
                  WHEN json_remove(OLD.payload,'$.status','$.decision_run_id') !=
                       json_remove(NEW.payload,'$.status','$.decision_run_id')
                  BEGIN SELECT RAISE(ABORT,'immutable_prepared_action'); END;
                CREATE TRIGGER approvals_no_delete BEFORE DELETE ON approvals
                  BEGIN SELECT RAISE(ABORT,'immutable_prepared_action'); END;
            """)
            for collection in ("people", "mail", "spaces", "teams", "chats"):
                for index, record in enumerate(seed[collection]):
                    rid = record["person_id"] if collection == "people" else record["id"]
                    db.execute("INSERT INTO resources VALUES (?,?,?,?)", (collection, rid, index, canonical(record)))
                    if collection == "people":
                        db.execute("INSERT INTO live_people VALUES (?,?)", (rid, canonical(record)))
            for table in ("resources", "effects", "projections"):
                for op in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER {table}_no_{op.lower()} BEFORE {op} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'immutable_fixture_truth'); END")

    @staticmethod
    def records(db, collection):
        return [strict_json(row[0]) for row in db.execute(
            "SELECT payload FROM resources WHERE collection=? ORDER BY position", (collection,))]

    @staticmethod
    def people(db):
        return [strict_json(row[0]) for row in db.execute(
            "SELECT l.payload FROM resources r JOIN live_people l ON r.id=l.id "
            "WHERE r.collection='people' ORDER BY r.position")]

    @staticmethod
    def update_person(db, person):
        person = Person.model_validate(person).model_dump()
        cursor = db.execute("UPDATE live_people SET payload=? WHERE id=?", (canonical(person), person["person_id"]))
        if cursor.rowcount != 1:
            raise SyntheticError("resource_unavailable")

    @staticmethod
    def approval(db, approval_id):
        row = db.execute("SELECT payload FROM approvals WHERE id=?", (approval_id,)).fetchone()
        return strict_json(row[0]) if row else None

    @staticmethod
    def save_approval(db, approval):
        value = Approval.model_validate(approval).model_dump()
        db.execute("INSERT INTO approvals VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (value["id"], canonical(value)))

    @staticmethod
    def execution(db, approval_id):
        row = db.execute("SELECT payload FROM executions WHERE approval_id=?", (approval_id,)).fetchone()
        return strict_json(row[0]) if row else None

    @staticmethod
    def save_execution(db, execution):
        value = Execution.model_validate(execution).model_dump()
        db.execute("INSERT INTO executions VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (value["id"], value["approval_id"], canonical(value)))

    @staticmethod
    def commit_effect(db, effect, destination):
        """One effect and its projections atomically, idempotent by execution ID."""
        value = Effect.model_validate(effect).model_dump()
        existing = db.execute("SELECT payload FROM effects WHERE execution_id=?", (value["execution_id"],)).fetchone()
        if existing:
            return strict_json(existing[0])
        db.execute("INSERT INTO effects VALUES (?,?,?)", (value["execution_id"], value["effect_id"], canonical(value)))
        projections = ([("outbox", value["sender_id"])] + [("inbox", rid) for rid in value["recipient_ids"]]
                       if value["channel"] == "mail" else [("direct_chat", destination)])
        for kind, resource in projections:
            db.execute("INSERT INTO projections VALUES (?,?,?,?)", (value["effect_id"], kind, resource, canonical(value)))
        return value
