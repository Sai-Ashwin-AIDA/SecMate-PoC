"""Assessment-local persistence, never SecMate's control/job or accepted run DB."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..job_runtime import canonical, require_permission


class Store:
    @staticmethod
    def enqueue(db, run_id):
        db.execute("INSERT INTO queue (run_id) VALUES (?)", (run_id,))

    @staticmethod
    def dequeue(db):
        row = db.execute("SELECT seq, run_id FROM queue ORDER BY seq LIMIT 1").fetchone()
        if row is None:
            return None
        db.execute("DELETE FROM queue WHERE seq=?", (row[0],))
        return row[1]

    def __init__(self, path: Path, state: dict):
        self.path = path
        # Refuse to attach to any old/live data. Recovery is intentionally not a
        # public Phase 1 feature; archived DBs are inspected read-only.
        with path.open("xb"):
            pass
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
                CREATE TABLE runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE queue (seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT UNIQUE NOT NULL);
                CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
                CREATE TRIGGER events_no_update BEFORE UPDATE ON events
                  BEGIN SELECT RAISE(ABORT, 'append_only'); END;
                CREATE TRIGGER events_no_delete BEFORE DELETE ON events
                  BEGIN SELECT RAISE(ABORT, 'append_only'); END;
            """)
            db.execute("INSERT INTO state VALUES (1, ?)", (canonical(state),))

    @contextmanager
    def transaction(self):
        require_permission()
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def read(self):
        require_permission()
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            yield db
        finally:
            db.close()
