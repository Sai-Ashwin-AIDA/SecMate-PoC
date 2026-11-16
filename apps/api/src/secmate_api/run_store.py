"""Transactional run snapshots and a local, hash-chained lifecycle ledger.

JSON records remain compatibility projections. SQLite is authoritative once a
record is imported. Hashes detect changes against this local baseline; they are
not signatures or protection against replacement of the entire database.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class RunStoreError(RuntimeError):
    pass


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


class RunStore:
    def __init__(self, root: Path):
        self.path = root / "control.sqlite3"

    @contextmanager
    def connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise RunStoreError("Unsupported run database schema version.")
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, payload TEXT,
                    evidence TEXT NOT NULL DEFAULT '{}', deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    body TEXT NOT NULL, event_hash TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS job_receipts (
                    receipt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                    phase TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS report_evidence (
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END;
                PRAGMA user_version=3;
                COMMIT;
            """)
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as error:
            if connection is not None:
                connection.rollback()
            raise RunStoreError("Run persistence or audit verification failed.") from error
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def _verify(self, connection, run_id):
        row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        events = connection.execute("SELECT * FROM events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        previous = "0" * 64
        last = None
        for sequence, event in enumerate(events, 1):
            body = json.loads(event["body"])
            if (event["sequence"] != sequence or body["sequence"] != sequence
                    or body["run_id"] != run_id or body["previous_hash"] != previous
                    or digest(body) != event["event_hash"]):
                raise RunStoreError("Run audit chain verification failed.")
            previous, last = event["event_hash"], body
        if row is None:
            if events:
                raise RunStoreError("Run snapshot is missing from the audit ledger.")
            return None, previous, 0
        if (last is None or last["record_hash"] != digest(json.loads(row["payload"]) if row["payload"] else None)
                or last["evidence_hash"] != digest(json.loads(row["evidence"]))
                or last["deleted"] != bool(row["deleted"])):
            raise RunStoreError("Run snapshot does not match its audit ledger.")
        return row, previous, len(events)

    def _append(self, connection, run_id, payload, evidence, deleted, event_type, previous, sequence, job_intent=None, original_evidence=None):
        body = {"run_id": run_id, "sequence": sequence + 1, "previous_hash": previous,
                "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": event_type,
                "record_hash": digest(payload), "evidence_hash": digest(evidence), "deleted": deleted,
                "status": payload.get("status") if payload else None}
        if job_intent:
            body["job_id"] = job_intent["job_id"]
            body["job_token"] = job_intent["token"]
            body["job_phase"] = job_intent["phase"]
            body["job_intent_hash"] = digest(job_intent)
        if original_evidence is not None:
            body["original_evidence_hash"] = digest(original_evidence)
        connection.execute("INSERT INTO events VALUES (?, ?, ?, ?)", (run_id, sequence + 1, canonical(body), digest(body)))
        connection.execute("INSERT INTO runs VALUES (?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload, evidence=excluded.evidence, deleted=excluded.deleted",
                           (run_id, canonical(payload) if payload is not None else None, canonical(evidence), int(deleted)))

    def save(self, payload: dict, *, imported=False, evidence_bundle: tuple[str, dict] | None = None, job_intent=None, original_evidence=None):
        run_id = payload["run_id"]
        with self.connection() as connection:
            row, previous, sequence = self._verify(connection, run_id)
            if row and row["deleted"]:
                raise RunStoreError("Deleted run history cannot be persisted again.")
            new_original = False
            if original_evidence is not None:
                if original_evidence.get("run_id") != run_id:
                    raise RunStoreError("Original evidence does not match the run.")
                retained = self._original(connection, run_id, row)
                if retained is not None and retained != original_evidence:
                    raise RunStoreError("Original report evidence cannot be replaced.")
                if retained is None:
                    connection.execute("INSERT INTO report_evidence VALUES (?,?)", (run_id, canonical(original_evidence)))
                    new_original = True
            new_receipt = False
            if job_intent:
                if job_intent["payload_hash"] != digest(payload) or job_intent["run_id"] != run_id:
                    raise RunStoreError("Job intent does not match the run snapshot.")
                cursor = connection.execute("INSERT OR IGNORE INTO job_receipts VALUES (?,?,?,?)",
                    (job_intent["receipt_id"], job_intent["job_id"], job_intent["phase"], canonical(job_intent)))
                new_receipt = cursor.rowcount > 0
            evidence = json.loads(row["evidence"]) if row else {}
            if evidence_bundle is not None:
                reference, report = evidence_bundle
                actual = digest(report)
                if reference in evidence and evidence[reference] != actual:
                    raise RunStoreError("Evidence bundle changed after its audit baseline.")
                evidence[reference] = actual
            if row and canonical(payload) == row["payload"] and canonical(evidence) == row["evidence"] and not new_receipt and not new_original:
                return
            old = json.loads(row["payload"]) if row else None
            kind = "LEGACY_IMPORTED" if imported and row is None else "RUN_CREATED" if row is None else "RUN_UPDATED"
            if old and old.get("status") != payload.get("status"):
                kind = "RUN_STATUS_CHANGED"
            if old:
                for field, event_type in (("candidate_batch", "CANDIDATES_GENERATED"),
                                          ("selected_candidate_id", "CANDIDATE_SELECTED"),
                                          ("manual_evidence", "EVIDENCE_SUBMITTED"),
                                          ("evaluation_id", "JUDGE_EVALUATION_CHANGED"),
                                          ("critic_status", "CRITIC_STATUS_CHANGED")):
                    if old.get(field) != payload.get(field):
                        kind = event_type
            self._append(connection, run_id, payload, evidence, False, kind, previous, sequence, job_intent, original_evidence)

    def _original(self, connection, run_id, row):
        if row and row["deleted"]:
            return None
        bodies = [json.loads(event[0]) for event in connection.execute("SELECT body FROM events WHERE run_id=? ORDER BY sequence", (run_id,))]
        hashes = [body["original_evidence_hash"] for body in bodies if "original_evidence_hash" in body]
        retained = connection.execute("SELECT payload FROM report_evidence WHERE run_id=?", (run_id,)).fetchone()
        if retained is None:
            if hashes:
                raise RunStoreError("Original report evidence is missing.")
            return None
        value = json.loads(retained[0])
        if not hashes or digest(value) != hashes[-1] or value.get("run_id") != run_id:
            raise RunStoreError("Original report evidence failed audit verification.")
        return value

    def original_evidence(self, run_id):
        with self.connection() as connection:
            row, _, _ = self._verify(connection, run_id)
            return self._original(connection, run_id, row)

    def job_receipt(self, job_id, phase):
        with self.connection() as connection:
            row = connection.execute("SELECT payload FROM job_receipts WHERE job_id=? AND phase=? ORDER BY rowid DESC LIMIT 1", (job_id, phase)).fetchone()
            if row is None:
                return None
            receipt = json.loads(row[0])
            self._verify(connection, receipt["run_id"])
            bodies = [json.loads(event[0]) for event in connection.execute("SELECT body FROM events WHERE run_id=?", (receipt["run_id"],))]
            if receipt["job_id"] != job_id or receipt["phase"] != phase or not any(
                body.get("job_id") == job_id and body.get("job_token") == receipt["token"]
                and body.get("job_phase") == phase and body["record_hash"] == receipt["payload_hash"]
                and body.get("job_intent_hash") == digest(receipt) for body in bodies):
                raise RunStoreError("Job receipt failed audit verification.")
            return receipt

    def records(self) -> dict[str, dict]:
        with self.connection() as connection:
            ids = [row[0] for row in connection.execute("SELECT run_id FROM runs UNION SELECT run_id FROM events")]
            result = {}
            for run_id in ids:
                row, _, _ = self._verify(connection, run_id)
                if not row["deleted"]:
                    result[run_id] = json.loads(row["payload"])
            return result

    def contains(self, run_id: str) -> bool:
        with self.connection() as connection:
            row, _, _ = self._verify(connection, run_id)
            return row is not None

    def delete(self, run_id: str):
        with self.connection() as connection:
            row, previous, sequence = self._verify(connection, run_id)
            if row and row["deleted"]:
                return
            self._append(connection, run_id, None, {}, True, "RUN_DELETED", previous, sequence)
            connection.execute("DELETE FROM report_evidence WHERE run_id=?", (run_id,))

    def verify_evidence(self, run_id: str, reference: str, report: dict, *, baseline_only=False, allow_baseline=True):
        """Pin a first-observed bundle; subsequent reads must match exactly."""
        with self.connection() as connection:
            row, previous, sequence = self._verify(connection, run_id)
            if row is None or row["deleted"]:
                raise RunStoreError("Evidence has no retained run record.")
            evidence = json.loads(row["evidence"])
            expected = evidence.get(reference)
            if expected is not None and baseline_only:
                return
            actual = digest(report)
            if expected is not None and expected != actual:
                raise RunStoreError("Evidence bundle changed after its audit baseline.")
            if expected is None:
                if not allow_baseline:
                    raise RunStoreError("Evidence has no accepted completion baseline.")
                evidence[reference] = actual
                self._append(connection, run_id, json.loads(row["payload"]), evidence, False, "EVIDENCE_BASELINED", previous, sequence)

    def has_evidence(self, run_id: str, reference: str) -> bool:
        with self.connection() as connection:
            row, _, _ = self._verify(connection, run_id)
            return row is not None and reference in json.loads(row["evidence"])

    def legacy_import(self, run_id: str) -> bool:
        with self.connection() as connection:
            self._verify(connection, run_id)
            event = connection.execute("SELECT body FROM events WHERE run_id=? AND sequence=1", (run_id,)).fetchone()
            return event is not None and json.loads(event[0])["event_type"] == "LEGACY_IMPORTED"

    def write_projection(self, payload: dict, path: Path) -> bool:
        """Best-effort derived JSON: never turn a committed mutation into failure."""
        import os
        temporary = path.with_suffix(".json.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="ascii")
            os.replace(temporary, path)
            return True
        except OSError:
            import logging
            logging.getLogger(__name__).warning("JSON run projection unavailable; SQLite remains authoritative.")
            return False

    def verification(self, run_id: str) -> dict:
        with self.connection() as connection:
            row, head, sequence = self._verify(connection, run_id)
            if row is None:
                raise RunStoreError("Run not found in the audit ledger.")
            return {"run_id": run_id, "verified": True, "events": sequence, "head_sha256": head,
                    "deleted": bool(row["deleted"]), "evidence_baselines": json.loads(row["evidence"])}

    def events(self, run_id: str, after_sequence: int = 0, limit: int = 100) -> list[dict]:
        if after_sequence < 0 or not 1 <= limit <= 200:
            raise RunStoreError("Invalid audit event pagination.")
        with self.connection() as connection:
            row, _, _ = self._verify(connection, run_id)
            if row is None:
                raise RunStoreError("Run not found in the audit ledger.")
            return [{**json.loads(event["body"]), "event_hash": event["event_hash"]} for event in connection.execute(
                "SELECT body, event_hash FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run_id, after_sequence, limit))]
