"""Phase 4 new-assessment SQLite tables and atomic memory operations."""
import sqlite3
from contextlib import contextmanager
from ...job_runtime import canonical
from ...job_runtime import require_permission
from ..calendar_phase3.store import CalendarStore
from ..calendar_repaired.contracts import bounded_json
from ..contracts import digest
from .services import owner_state


class MemoryStore(CalendarStore):
    def __init__(self, path, state, seed, calendar_seed, records, memory_seed):
        super().__init__(path, state, seed, calendar_seed, records)
        with self.transaction() as db:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE memory_owner_seed (owner TEXT PRIMARY KEY, tenant TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(owner,tenant));
                CREATE TABLE memory_fact_seed (id TEXT PRIMARY KEY, owner TEXT NOT NULL, tenant TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 30), payload TEXT NOT NULL, UNIQUE(owner,ordinal), FOREIGN KEY(owner,tenant) REFERENCES memory_owner_seed(owner,tenant));
                CREATE TABLE memory_owners (owner TEXT PRIMARY KEY, tenant TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 2147483647), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), preferences TEXT NOT NULL CHECK(preferences='{}'), state_digest TEXT NOT NULL CHECK(length(state_digest) IN (0,64)), UNIQUE(owner,tenant), FOREIGN KEY(owner,tenant) REFERENCES memory_owner_seed(owner,tenant));
                CREATE TABLE memory_facts (id TEXT PRIMARY KEY, owner TEXT NOT NULL, tenant TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 30), payload TEXT NOT NULL, UNIQUE(owner,ordinal), FOREIGN KEY(id) REFERENCES memory_fact_seed(id), FOREIGN KEY(owner,tenant) REFERENCES memory_owners(owner,tenant));
                CREATE TABLE memory_contexts (conversation_id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL, state_generation INTEGER NOT NULL CHECK(state_generation>=1), owner TEXT NOT NULL, tenant TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 2147483647), memory_disabled INTEGER NOT NULL CHECK(memory_disabled IN (0,1)), payload TEXT NOT NULL, FOREIGN KEY(owner,tenant) REFERENCES memory_owners(owner,tenant));
                CREATE TABLE memory_controls (id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL CHECK(ordinal BETWEEN 1 AND 32), assessment_id TEXT NOT NULL, state_generation INTEGER NOT NULL CHECK(state_generation>=1), owner TEXT NOT NULL, tenant TEXT NOT NULL, body TEXT NOT NULL, input_digest TEXT NOT NULL CHECK(length(input_digest)=64), status TEXT NOT NULL CHECK(status IN ('accepted','applying','cancel_requested','inspected','applied','already_disabled','failed','cancelled')), result TEXT, result_digest TEXT CHECK(result_digest IS NULL OR length(result_digest)=64), accepted_seconds REAL NOT NULL CHECK(accepted_seconds>=0), deadline_seconds REAL NOT NULL CHECK(deadline_seconds>=accepted_seconds), CHECK((status IN ('accepted','applying','cancel_requested') AND result IS NULL AND result_digest IS NULL) OR (status IN ('inspected','applied','already_disabled','failed','cancelled') AND result IS NOT NULL AND result_digest IS NOT NULL)), FOREIGN KEY(owner,tenant) REFERENCES memory_owners(owner,tenant));
                CREATE TABLE memory_control_fence (singleton INTEGER PRIMARY KEY CHECK(singleton=1), control_id TEXT NOT NULL UNIQUE REFERENCES memory_controls(id), owner TEXT NOT NULL, persistence_fenced INTEGER NOT NULL CHECK(persistence_fenced IN (0,1)));
                CREATE TABLE memory_mutations (control_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE memory_snapshots (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, round INTEGER NOT NULL, attempt INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(run_id,round,attempt));
                CREATE TABLE memory_host_outputs (id INTEGER PRIMARY KEY AUTOINCREMENT, control_id TEXT NOT NULL REFERENCES memory_controls(id), payload TEXT NOT NULL);
                CREATE TABLE memory_fault_hits (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
            """)
            for owner in memory_seed["owners"]:
                db.execute("INSERT INTO memory_owner_seed VALUES (?,?,?)", (owner["owner"], owner["tenant"], canonical(owner)))
                db.execute("INSERT INTO memory_owners VALUES (?,?,?,?,?,?)", (owner["owner"], owner["tenant"], owner["revision"], owner["enabled"], canonical({}), ""))
            for fact in memory_seed["facts"]:
                values = (fact["id"], fact["owner"], fact["tenant"], fact["ordinal"], canonical(fact))
                db.execute("INSERT INTO memory_fact_seed VALUES (?,?,?,?,?)", values)
                db.execute("INSERT INTO memory_facts VALUES (?,?,?,?,?)", (fact["id"], fact["owner"], fact["tenant"], fact["ordinal"], canonical(fact)))
            for owner in memory_seed["owners"]:
                self.rehash(db, owner["owner"])
            for table in ("memory_owner_seed", "memory_fact_seed", "memory_mutations", "memory_snapshots", "memory_host_outputs", "memory_fault_hits"):
                for operation in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_memory_evidence'); END")
            db.execute("CREATE TRIGGER memory_facts_no_update BEFORE UPDATE ON memory_facts BEGIN SELECT RAISE(ABORT,'immutable_memory_fact'); END")
            db.execute("CREATE TRIGGER memory_facts_no_insert BEFORE INSERT ON memory_facts WHEN (SELECT count(*) FROM memory_fact_seed)>0 BEGIN SELECT RAISE(ABORT,'no_memory_learning'); END")
            db.execute("CREATE TRIGGER memory_owners_identity_immutable BEFORE UPDATE OF owner,tenant,preferences ON memory_owners BEGIN SELECT RAISE(ABORT,'immutable_memory_owner'); END")
            db.execute("CREATE TRIGGER memory_context_identity_immutable BEFORE UPDATE OF conversation_id,assessment_id,state_generation,owner,tenant ON memory_contexts BEGIN SELECT RAISE(ABORT,'immutable_memory_context'); END")
            db.execute("CREATE TRIGGER memory_context_sticky BEFORE UPDATE OF memory_disabled ON memory_contexts WHEN OLD.memory_disabled=1 AND NEW.memory_disabled=0 BEGIN SELECT RAISE(ABORT,'sticky_memory_disable'); END")
            db.execute("CREATE TRIGGER memory_controls_prepared_immutable BEFORE UPDATE OF id,ordinal,assessment_id,state_generation,owner,tenant,body,input_digest,accepted_seconds,deadline_seconds ON memory_controls BEGIN SELECT RAISE(ABORT,'immutable_memory_control'); END")
            db.execute("CREATE TRIGGER memory_controls_settled_immutable BEFORE UPDATE ON memory_controls WHEN OLD.status IN ('inspected','applied','already_disabled','failed','cancelled') BEGIN SELECT RAISE(ABORT,'settled_memory_control'); END")
            db.execute("CREATE TRIGGER memory_controls_transition BEFORE UPDATE OF status ON memory_controls WHEN NOT ((OLD.status='accepted' AND NEW.status IN ('applying','cancel_requested','failed','cancelled')) OR (OLD.status='cancel_requested' AND NEW.status='cancelled') OR (OLD.status='applying' AND NEW.status IN ('inspected','applied','already_disabled','failed','cancelled'))) BEGIN SELECT RAISE(ABORT,'invalid_memory_control_transition'); END")
            db.execute("CREATE TRIGGER memory_facts_delete_guard BEFORE DELETE ON memory_facts WHEN memory_authorized()!=1 OR NOT EXISTS (SELECT 1 FROM memory_control_fence f JOIN memory_controls c ON c.id=f.control_id WHERE f.singleton=1 AND f.persistence_fenced=0 AND c.owner=OLD.owner AND c.status='applying' AND json_extract(c.body,'$.operation') IN ('forget','clear')) BEGIN SELECT RAISE(ABORT,'unauthorized_memory_delete'); END")
            db.execute("CREATE TRIGGER memory_owner_state_guard BEFORE UPDATE OF revision,enabled ON memory_owners WHEN memory_authorized()!=1 OR NOT EXISTS (SELECT 1 FROM memory_control_fence f JOIN memory_controls c ON c.id=f.control_id WHERE f.singleton=1 AND f.persistence_fenced=0 AND c.status='applying' AND c.owner=OLD.owner AND c.tenant=OLD.tenant AND json_extract(c.body,'$.expected_revision')=OLD.revision AND json_extract(c.body,'$.operation') IN ('forget','clear','fixture_set_enabled') AND NEW.revision=OLD.revision+1) BEGIN SELECT RAISE(ABORT,'unauthorized_memory_owner_update'); END")
            db.execute("CREATE TRIGGER memory_owner_digest_guard BEFORE UPDATE OF state_digest ON memory_owners WHEN memory_authorized()!=1 OR NOT EXISTS (SELECT 1 FROM memory_control_fence f JOIN memory_controls c ON c.id=f.control_id WHERE f.singleton=1 AND f.persistence_fenced=0 AND c.status='applying' AND c.owner=OLD.owner AND c.tenant=OLD.tenant AND json_extract(c.body,'$.operation') IN ('forget','clear','fixture_set_enabled')) BEGIN SELECT RAISE(ABORT,'unauthorized_memory_digest_update'); END")
            db.execute("CREATE TRIGGER memory_context_state_guard BEFORE UPDATE OF revision,memory_disabled,payload ON memory_contexts WHEN memory_authorized()!=1 OR NOT EXISTS (SELECT 1 FROM memory_control_fence f JOIN memory_controls c ON c.id=f.control_id WHERE f.singleton=1 AND f.persistence_fenced=0 AND c.status='applying' AND c.owner=OLD.owner AND c.tenant=OLD.tenant AND json_extract(c.body,'$.conversation_id')=OLD.conversation_id AND json_extract(c.body,'$.expected_context_revision')=OLD.revision AND json_extract(c.body,'$.operation') IN ('disable_conversation','fixture_context_change') AND NEW.revision IN (OLD.revision,OLD.revision+1) AND json_extract(NEW.payload,'$.revision')=NEW.revision AND json_extract(NEW.payload,'$.memory_disabled')=NEW.memory_disabled) BEGIN SELECT RAISE(ABORT,'unauthorized_memory_context_update'); END")
            db.execute("CREATE TRIGGER memory_mutation_insert_guard BEFORE INSERT ON memory_mutations WHEN memory_authorized()!=1 OR NOT EXISTS (SELECT 1 FROM memory_control_fence f JOIN memory_controls c ON c.id=f.control_id WHERE f.singleton=1 AND f.persistence_fenced=0 AND c.id=NEW.control_id AND c.status='applying' AND json_extract(NEW.payload,'$.control_id')=c.id AND json_extract(NEW.payload,'$.input_digest')=c.input_digest AND json_extract(NEW.payload,'$.before_owner.owner')=c.owner AND json_extract(NEW.payload,'$.before_owner.tenant')=c.tenant AND json_extract(NEW.payload,'$.after_owner.owner')=c.owner AND json_extract(NEW.payload,'$.after_owner.tenant')=c.tenant) BEGIN SELECT RAISE(ABORT,'unauthorized_memory_journal'); END")

    @contextmanager
    def transaction(self):
        require_permission()
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        # Trusted application-path marker, not authentication of arbitrary
        # clients that can directly open the trusted assessment database.
        db.create_function("memory_authorized", 0, lambda: 1)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def header(db, owner):
        row = db.execute("SELECT tenant,revision,enabled,preferences,state_digest FROM memory_owners WHERE owner=?", (owner,)).fetchone()
        if not row:
            return None
        return {"owner": owner, "tenant": row[0], "revision": row[1], "enabled": bool(row[2]), "preferences": bounded_json(row[3]), "state_digest": row[4]}

    @staticmethod
    def facts(db, owner):
        return [bounded_json(row[0]) for row in db.execute("SELECT payload FROM memory_facts WHERE owner=? ORDER BY ordinal", (owner,))]

    @classmethod
    def rehash(cls, db, owner):
        header = cls.header(db, owner)
        value = digest(owner_state({k: header[k] for k in ("owner", "tenant", "revision", "enabled", "preferences")}, cls.facts(db, owner)))
        db.execute("UPDATE memory_owners SET state_digest=? WHERE owner=?", (value, owner))
        return value
