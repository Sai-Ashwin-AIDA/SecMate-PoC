"""New-assessment typed storage; meetings never enter message DTOs."""
from ...job_runtime import canonical
from ..contracts import SyntheticError, digest
from ..communication.contracts import Approval, Execution
from ..communication.store import CommunicationStore
from .contracts import bounded_json, validate


class CalendarStore(CommunicationStore):
    def __init__(self, path, state, seed, calendar_seed, records):
        super().__init__(path, state, seed)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE calendar_account_seed (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE calendar_accounts (id TEXT PRIMARY KEY, owner_person_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE calendar_records (id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE meeting_effects (execution_id TEXT PRIMARY KEY, effect_id TEXT UNIQUE NOT NULL,
                    event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE calendar_projections (effect_id TEXT, calendar_id TEXT, role TEXT, payload TEXT NOT NULL,
                    PRIMARY KEY(effect_id,calendar_id,role));
                CREATE TABLE invitations (id TEXT PRIMARY KEY, effect_id TEXT, attendee_id TEXT, payload TEXT NOT NULL,
                    UNIQUE(effect_id,attendee_id));
                CREATE TABLE normalizations (call_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            for value in calendar_seed["accounts"]:
                validate("CalendarAccount", value)
                db.execute("INSERT INTO calendar_account_seed VALUES (?,?)", (value["id"], canonical(value)))
                db.execute("INSERT INTO calendar_accounts VALUES (?,?,?)", (value["id"], value["owner_person_id"], canonical(value)))
            for value in records:
                validate("CalendarRecord", value)
                db.execute("INSERT INTO calendar_records VALUES (?,?,?)", (value["id"], value["ordinal"], canonical(value)))
            for table in ("calendar_account_seed", "calendar_records", "meeting_effects", "calendar_projections", "invitations", "normalizations"):
                for op in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER {table}_no_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_calendar_truth'); END")

    @staticmethod
    def save_approval(db, approval):
        kind = approval.get("action_kind")
        if kind == "meeting":
            value = validate("MeetingApproval", approval)
        elif kind == "message":
            value = {"action_kind": "message", **Approval.model_validate({k: v for k, v in approval.items() if k != "action_kind"}).model_dump()}
        else:
            raise ValueError("action_kind")
        old = CalendarStore.approval(db, value["id"])
        if old and old["status"] != "pending" and value["status"] != old["status"]:
            raise ValueError("approval_transition")
        if not db.execute("SELECT 1 FROM runs WHERE id=?", (value["originating_run_id"],)).fetchone():
            raise ValueError("approval_origin")
        db.execute("INSERT INTO approvals VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (value["id"], canonical(value)))

    @staticmethod
    def save_execution(db, execution):
        approval = CalendarStore.approval(db, execution["approval_id"])
        if approval is None or execution.get("action_kind") != approval["action_kind"] or execution["decision_run_id"] != approval["decision_run_id"] or execution["prepared_digest"] != approval["prepared_digest"]:
            raise ValueError("execution_binding")
        if execution["action_kind"] == "meeting":
            value = validate("MeetingExecution", execution)
        elif execution["action_kind"] == "message":
            value = {"action_kind": "message", **Execution.model_validate({k: v for k, v in execution.items() if k != "action_kind"}).model_dump()}
        else:
            raise ValueError("action_kind")
        old = CalendarStore.execution(db, value["approval_id"])
        if old:
            transitions = {"prepared": {"prepared", "invoking", "failed"}, "invoking": {"invoking", "succeeded", "failed", "outcome_unknown"},
                           "succeeded": {"succeeded"}, "failed": {"failed"}, "outcome_unknown": {"outcome_unknown"}}
            if old["id"] != value["id"] or value["status"] not in transitions[old["status"]] or old["dispatch"] is not None and (old["dispatch"], old["dispatch_digest"]) != (value["dispatch"], value["dispatch_digest"]):
                raise ValueError("execution_transition")
        db.execute("INSERT INTO executions VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (value["id"], value["approval_id"], canonical(value)))

    @staticmethod
    def commit_meeting(db, approval, execution, record, effect, projections, invitations):
        validate("CalendarRecord", record)
        validate("MeetingEffect", effect)
        existing = db.execute("SELECT payload FROM meeting_effects WHERE execution_id=?", (execution["id"],)).fetchone()
        if existing:
            saved = bounded_json(existing[0])
            if saved["prepared_digest"] != approval["prepared_digest"] or saved["dispatch_digest"] != execution["dispatch_digest"]:
                raise ValueError("idempotence_payload_mismatch")
            return saved
        if db.execute("SELECT count(*) FROM calendar_records").fetchone()[0] >= 10000:
            raise SyntheticError("preflight_failed")
        saved = CalendarStore.execution(db, approval["id"])
        if saved != execution or execution["status"] != "invoking" or effect["execution_id"] != execution["id"] or effect["approval_id"] != approval["id"] or effect["calendar_record"] != record:
            raise ValueError("effect_binding")
        dispatch = execution["dispatch"]
        if record["organizer_id"] != dispatch["organizer"]["person_id"] or record["organizer_calendar_id"] != dispatch["calendar_id"] or record["attendee_ids"] != [p["person_id"] for p in dispatch["attendees"]] or any(record[k] != dispatch[k] for k in ("title", "description", "start", "end", "start_utc", "end_utc", "timezone", "time_rules_digest")):
            raise ValueError("committed_dispatch_correspondence")
        if len(projections) != len(approval["prepared"]["attendee_ids"]) + 1 or len(invitations) != len(approval["prepared"]["attendee_ids"]):
            raise ValueError("effect_projection_count")
        accounts = {bounded_json(r[0])["owner_person_id"]: bounded_json(r[0])["id"] for r in db.execute("SELECT payload FROM calendar_accounts")}
        if [v["attendee_id"] for v in invitations] != approval["prepared"]["attendee_ids"] or len({v["id"] for v in invitations}) != len(invitations):
            raise ValueError("invitation_order_uniqueness")
        for value in projections + invitations:
            person = value.get("owner_person_id", value.get("attendee_id"))
            if value["event_id"] != record["id"] or value["effect_id"] != effect["effect_id"] or value["record_digest"] != digest(record) or value["calendar_id"] != accounts.get(person):
                raise ValueError("projection_reference")
        if [(v["owner_person_id"], v["role"]) for v in projections] != [(record["organizer_id"], "organizer")] + [(p, "attendee") for p in record["attendee_ids"]]:
            raise ValueError("calendar_projection_correspondence")
        db.execute("INSERT INTO calendar_records VALUES (?,?,?)", (record["id"], record["ordinal"], canonical(record)))
        db.execute("INSERT INTO meeting_effects VALUES (?,?,?,?)", (effect["execution_id"], effect["effect_id"], effect["event_id"], canonical(effect)))
        for value in projections:
            validate("CalendarProjection", value)
            db.execute("INSERT INTO calendar_projections VALUES (?,?,?,?)", (value["effect_id"], value["calendar_id"], value["role"], canonical(value)))
        for value in invitations:
            validate("InvitationProjection", value)
            db.execute("INSERT INTO invitations VALUES (?,?,?,?)", (value["id"], value["effect_id"], value["attendee_id"], canonical(value)))
        return effect

    @staticmethod
    def commit_effect(db, effect, destination):
        existing = db.execute("SELECT payload FROM effects WHERE execution_id=?", (effect["execution_id"],)).fetchone()
        if existing:
            saved = bounded_json(existing[0])
            if any(saved[k] != v for k, v in effect.items() if k not in {"effect_id", "committed_at"}):
                raise ValueError("idempotence_payload_mismatch")
            return saved
        return CommunicationStore.commit_effect(db, effect, destination)
