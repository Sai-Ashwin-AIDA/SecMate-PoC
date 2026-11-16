"""Single-machine durable execution ownership; lease expiry never means retry.

Run-store receipts are the cross-database outbox/inbox. Worker processes cannot
pass their attempt gate until the accepted receipt and PID identity are durable.
"""
from __future__ import annotations

import contextvars
import functools
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .run_store import RunStore, RunStoreError, canonical, digest

ACTIVE = {"PREPARED", "QUEUED", "STARTING", "RUNNING", "RESULT_READY", "PUBLISHING", "RECONCILING", "UNCERTAIN"}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "ABORTED"}
KINDS = {"SYNTHETIC", "GENERATION", "JUDGE", "CRITIC", "TARGET_SMOKE"}
TRANSITIONS = {
    "PREPARED": {"QUEUED", "ABORTED", "FAILED", "RECONCILING", "UNCERTAIN"},
    "QUEUED": {"STARTING", "PUBLISHING", "ABORTED", "FAILED", "CANCELLED", "RECONCILING", "UNCERTAIN"},
    "STARTING": {"RUNNING", "PUBLISHING", "ABORTED", "FAILED", "RECONCILING", "UNCERTAIN"},
    "RUNNING": {"RESULT_READY", "PUBLISHING", "RECONCILING", "UNCERTAIN"},
    "RESULT_READY": {"PUBLISHING", "FAILED", "CANCELLED", "UNCERTAIN", "RECONCILING"},
    "PUBLISHING": {"SUCCEEDED", "FAILED", "CANCELLED", "RESULT_READY", "RECONCILING", "UNCERTAIN"},
    "RECONCILING": {"PUBLISHING", "RESULT_READY", "FAILED", "CANCELLED", "UNCERTAIN"},
    "UNCERTAIN": {"RESULT_READY", "FAILED", "CANCELLED", "ABORTED"},
}
_epoch = uuid4().hex
_current = contextvars.ContextVar("secmate_job", default=None)
_request = contextvars.ContextVar("secmate_idempotency_request", default=None)
_sessions: dict[tuple[str, str], "JobSession"] = {}
_registry_lock = threading.RLock()
_HeartbeatThread = threading.Thread
_controllers = {}
_diagnostics = set()


class JobConflict(RunStoreError):
    """Valid storage, but the requested ownership transition is not permitted."""


def machine_identity():
    import uuid
    return digest({"host": platform.node(), "node": uuid.getnode(), "os": os.name})


def process_identity(pid: int) -> str | None:
    """Creation identity, not merely PID existence. Unknown is never dead."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                values = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                    return None
                return f"windows:{values[0].dwHighDateTime << 32 | values[0].dwLowDateTime}"
            finally:
                kernel.CloseHandle(handle)
        stat = Path(f"/proc/{pid}/stat").read_text()
        started = stat[stat.rindex(")") + 2:].split()[19]
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return f"linux:{boot}:{started}"
    except (OSError, ValueError, IndexError):
        return None


def process_absent(pid: int) -> bool:
    if os.name == "nt":
        return not _windows_pid_present(pid)
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        if os.name != "nt":
            try:
                os.killpg(pid, 0)
                return False
            except ProcessLookupError:
                return True
            except OSError:
                return False
        return True
    except OSError:
        return False


def _windows_pid_present(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = kernel.OpenProcess(0x00101000, False, pid)
    if handle:
        try:
            # OpenProcess can succeed for an exited process while another owner
            # retains a handle. Never use Windows os.kill(pid, 0) as a probe.
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    return ctypes.get_last_error() != 87


def original_worker_exited(job):
    if job.get("machine") != machine_identity():
        return False
    identities = [(job.get("pid"), job.get("identity"))]
    if job.get("worker_pid") is not None:
        identities.append((job["worker_pid"], job.get("worker_identity")))
    for pid, identity in identities:
        if not isinstance(pid, int):
            return False
        current = process_identity(pid)
        if not process_absent(pid) and not (current is not None and identity is not None and current != identity):
            return False
    if os.name != "nt":
        # A replaced/absent leader does not prove its original group is empty.
        try:
            os.killpg(job["pid"], 0)
            return False
        except ProcessLookupError:
            pass
        except OSError:
            return False
    return True


class ProcessContainment:
    """Windows kill-on-controller-close Job Object; POSIX uses a new session."""
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                ("active_limit", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            process.kill()
            process.wait(timeout=5)
            raise RunStoreError("Worker containment could not be established.")

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def terminate_and_wait(self, timeout=10):
        """Keep the handle until the Job Object reports no active processes."""
        if self.handle is None:
            return True
        import ctypes
        from ctypes import wintypes

        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
                (name, wintypes.DWORD) for name in ("faults", "total", "active", "terminated")]

        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        if not self.kernel.TerminateJobObject(self.handle, 75):
            return False
        deadline = time.monotonic() + timeout
        while True:
            value = Accounting()
            if not self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(value), ctypes.sizeof(value), None):
                return False
            if value.active == 0:
                self.close()
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(.02)

    def accept_worker(self, worker_pid, launcher_pid):
        """Windows venv launchers can own a separate interpreter child. Verify
        its parent using a process handle before accepting/containing that child.
        """
        if os.name != "nt" or self.handle is None:
            return worker_pid == launcher_pid
        import ctypes
        from ctypes import wintypes

        class BasicProcess(ctypes.Structure):
            _fields_ = [("reserved", ctypes.c_void_p), ("peb", ctypes.c_void_p),
                        ("reserved2", ctypes.c_void_p * 2), ("pid", ctypes.c_size_t), ("parent", ctypes.c_size_t)]

        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        handle = self.kernel.OpenProcess(0x1501, False, worker_pid)
        if not handle:
            return False
        try:
            ntdll = ctypes.WinDLL("ntdll")
            ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p]
            basic = BasicProcess()
            if ntdll.NtQueryInformationProcess(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic), None) != 0 or basic.parent != launcher_pid:
                return False
            self.kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
            contained = wintypes.BOOL()
            if not self.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(contained)):
                return False
            return bool(contained.value) or bool(self.kernel.AssignProcessToJobObject(self.handle, handle))
        finally:
            self.kernel.CloseHandle(handle)


class ControllerGuard:
    """Lifetime OS lock, acquired before any startup reconciliation/migration."""
    def __init__(self, root):
        self.root, self.file = Path(root), None

    def __enter__(self):
        global _epoch
        self.root.mkdir(parents=True, exist_ok=True)
        self.file = (self.root / "control-api.lock").open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            self.file = None
            raise RunStoreError("Another API controller owns this data directory.") from error
        _epoch = uuid4().hex
        return self

    def __exit__(self, *args):
        if self.file is not None:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()


class JobLedger:
    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.path = self.lock_path.parent / "jobs.sqlite3"
        self.root = self.lock_path.parent / "job-attempts"

    @contextmanager
    def connection(self):
        connection = None
        _registry_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30)
            connection.row_factory = sqlite3.Row
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            if connection.execute("PRAGMA user_version").fetchone()[0] not in (0, 1, 2):
                raise RunStoreError("Unsupported job schema version.")
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    token INTEGER NOT NULL UNIQUE, state TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_worker ON jobs((1)) WHERE state IN
                    ('PREPARED','QUEUED','STARTING','RUNNING','RESULT_READY','PUBLISHING','RECONCILING','UNCERTAIN');
                CREATE TABLE IF NOT EXISTS requests (
                    request_key TEXT PRIMARY KEY, body_hash TEXT NOT NULL, run_id TEXT,
                    namespace TEXT, state TEXT NOT NULL, status_code INTEGER, job_id TEXT
                );
            """)
            if "action" not in {row[1] for row in connection.execute("PRAGMA table_info(requests)")}:
                connection.execute("ALTER TABLE requests ADD COLUMN action TEXT")
            connection.execute("PRAGMA user_version=2")
            connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except FileExistsError:
            if connection is not None:
                connection.rollback()
            raise
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as error:
            if connection is not None:
                connection.rollback()
            raise RunStoreError("Durable job storage is unavailable.") from error
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()
            _registry_lock.release()

    def prepare(self, run_id, kind, source_root):
        if kind not in KINDS:
            raise RunStoreError("Invalid durable job kind.")
        with self.connection() as connection:
            if str(self.lock_path.resolve()) in _diagnostics:
                raise FileExistsError("Diagnostic inference owns the local inference slot.")
            if connection.execute("SELECT 1 FROM jobs WHERE state NOT IN ('SUCCEEDED','FAILED','CANCELLED','ABORTED')").fetchone():
                raise FileExistsError("Another durable worker job is active or unresolved.")
            token = connection.execute("SELECT COALESCE(MAX(token),0)+1 FROM jobs").fetchone()[0]
            job_id = f"job-{uuid4().hex}"
            payload = {"job_id": job_id, "run_id": run_id, "kind": kind, "token": token,
                       "owner": _epoch, "controller_pid": os.getpid(), "controller_identity": process_identity(os.getpid()),
                       "machine": machine_identity(),
                       "source_root": str(Path(source_root).resolve()), "state": "PREPARED", "created_at": time.time(),
                       "lease_until": time.time() + 30, "pid": None, "identity": None,
                       # perf_counter uses QPC on both Python 3.11 and 3.14 on
                       # Windows; monotonic uses different epochs between them.
                       "lease_monotonic_until": time.perf_counter() + 30,
                       "lease_clock": "perf_counter",
                       "authorized": False, "cancel_requested": False, "source_receipt": None,
                       "publication_receipt": None, "execution_started": False, "reason": None}
            payload["launch_intent"] = False
            payload["directory_name"] = f"j{token:x}"
            request = _request.get()
            if request:
                payload["request_key"] = request["key"]
                connection.execute("UPDATE requests SET run_id=?,job_id=? WHERE request_key=?",
                                   (run_id, job_id, request["key"]))
            connection.execute("INSERT INTO jobs VALUES (?,?,?,?,?)", (job_id, run_id, token, "PREPARED", canonical(payload)))
        return payload

    def get(self, job_id, *, missing_ok=False):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                if missing_ok:
                    return None
                raise RunStoreError("Durable job not found.")
            value = json.loads(row["payload"])
            if value["job_id"] != row["job_id"] or value["state"] != row["state"] or value["token"] != row["token"] or value["run_id"] != row["run_id"]:
                raise RunStoreError("Durable job metadata is inconsistent.")
            return value

    def update(self, job_id, token, *, owner=None, **changes):
        with self.connection() as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE job_id=? AND token=?", (job_id, token)).fetchone()
            if row is None:
                raise RunStoreError("Stale durable job fencing token.")
            value = json.loads(row[0])
            if value["owner"] != (owner or _epoch) or value["state"] in TERMINAL:
                raise RunStoreError("Stale durable job owner or terminal attempt.")
            next_state = changes.get("state", value["state"])
            if next_state != value["state"] and next_state not in TRANSITIONS[value["state"]]:
                raise RunStoreError("Invalid durable job state transition.")
            value.update(changes)
            connection.execute("UPDATE jobs SET state=?,payload=? WHERE job_id=? AND token=?", (value["state"], canonical(value), job_id, token))
            return value

    def active(self):
        with self.connection() as connection:
            rows = connection.execute("SELECT payload FROM jobs WHERE state NOT IN ('SUCCEEDED','FAILED','CANCELLED','ABORTED')").fetchall()
            return [json.loads(row[0]) for row in rows]

    def reconcile(self, source_roots=None):
        """Conservative classification: never invoke a provider during recovery."""
        with _registry_lock:
            for job in self.active():
                if job["state"] == "UNCERTAIN" and job.get("requires_explicit_resolution"):
                    continue
                if job["owner"] == _epoch and job["state"] not in {"RECONCILING", "UNCERTAIN", "RESULT_READY"}:
                    continue
                if job["owner"] == _epoch and job["state"] == "RESULT_READY":
                    continue
                configured_roots = source_roots.get(job["kind"]) if source_roots else None
                if job["kind"] == "CRITIC" and isinstance(configured_roots, (tuple, list)):
                    namespace = "SYNTHETIC" if job["run_id"].startswith("api-run-") else "GENERATION"
                    configured_roots = source_roots.get(namespace, configured_roots)
                allowed_roots = configured_roots if isinstance(configured_roots, (tuple, list)) else (configured_roots,)
                if source_roots and Path(job["source_root"]).resolve() not in {Path(root).resolve() for root in allowed_roots if root is not None}:
                    self._adopt(job, "UNCERTAIN", "RESTORE_REQUIRES_OFFLINE_RECONCILIATION")
                    continue
                if job["machine"] != machine_identity():
                    self._adopt(job, "UNCERTAIN", "HOST_IDENTITY_CHANGED")
                    continue
                if job["pid"] is None and job["state"] not in {"PREPARED", "QUEUED"}:
                    ready = self.root / job.get("directory_name", job["job_id"]) / "ready.json"
                    if ready.is_file():
                        acknowledgment = json.loads(ready.read_text())
                        if acknowledgment.get("job_id") == job["job_id"] and acknowledgment.get("token") == job.get("execution_token", job["token"]):
                            job["pid"], job["identity"] = acknowledgment["pid"], acknowledgment["identity"]
                known_exit = (job["pid"] is None and not job.get("launch_intent", False)) or original_worker_exited(job)
                if not known_exit:
                    self._adopt(job, "UNCERTAIN", "WORKER_EXIT_UNRESOLVED")
                    continue
                source = RunStore(Path(job["source_root"]))
                receipt = source.job_receipt(job["job_id"], "PUBLICATION")
                if receipt and not job.get("needs_publication") and (job.get("completion_hash") or not job["execution_started"] or job["cancel_requested"]):
                    outcome = receipt.get("outcome")
                    self._adopt(job, "CANCELLED" if job["cancel_requested"] else "FAILED" if outcome == "FAILED" else "SUCCEEDED", "RECONCILED_PUBLICATION")
                    continue
                if job["pid"] is None and not job["execution_started"]:
                    self._adopt(job, "ABORTED", "INTERRUPTED_BEFORE_DISPATCH")
                    continue
                session = JobSession(self, job)
                try:
                    session.completion(job)
                    if source.job_receipt(job["job_id"], "ACCEPTANCE") is None:
                        raise RunStoreError("Recovery has no accepted operation.")
                except (RunStoreError, OSError, ValueError, KeyError):
                    self._adopt(job, "UNCERTAIN", "PROVIDER_COMPLETION_UNCERTAIN")
                    continue
                self._adopt(job, "RESULT_READY", "VERIFIED_COMPLETION_RECOVERY")

    def _adopt(self, job, state, reason):
        with self.connection() as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE job_id=? AND token=?", (job["job_id"], job["token"])).fetchone()
            if row is None:
                raise RunStoreError("Recovery fencing token changed.")
            stored = json.loads(row[0])
            if stored["owner"] == _epoch and stored["state"] == state and stored.get("reason") == reason and stored.get("pid") == job.get("pid"):
                return stored
            token = connection.execute("SELECT MAX(token)+1 FROM jobs").fetchone()[0]
            value = {**stored, **{key: job[key] for key in ("pid", "identity", "recovery_attempts") if key in job},
                     "execution_token": stored.get("execution_token", job["token"]), "owner": _epoch,
                     "token": token, "state": state, "authorized": False, "reason": reason}
            connection.execute("UPDATE jobs SET token=?,state=?,payload=? WHERE job_id=? AND token=?",
                               (token, state, canonical(value), job["job_id"], job["token"]))
        if state in TERMINAL:
            self.clear_projection(value)
        return value

    def clear_projection(self, value):
        with _registry_lock:
            try:
                projection = json.loads(self.lock_path.read_text())
                if projection.get("job_id") == value["job_id"]:
                    self.lock_path.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass

    def resolve_uncertain(self, job_id, acknowledgment):
        with _registry_lock:
            job = self.get(job_id)
            if job["state"] != "UNCERTAIN" or acknowledgment is not True:
                raise JobConflict("Explicit acknowledgment of uncertain provider completion is required.")
            if not original_worker_exited(job):
                raise JobConflict("Worker exit cannot be proved on this host. Do not clear ownership.")
            return self._adopt(job, "FAILED", "OPERATOR_ACKNOWLEDGED_UNCERTAIN_COMPLETION")


def session_for(lock_path, run_id):
    current = _current.get()
    if current is not None:
        if current.run_id != run_id or current.ledger.lock_path.resolve() != Path(lock_path).resolve():
            raise RunStoreError("Job does not own this run mutation.")
        return current
    with _registry_lock:
        key = (str(Path(lock_path).resolve()), run_id)
        session = _sessions.get(key)
        if session:
            value = session.ledger.get(session.job_id)
            if value["token"] != session.token or value["owner"] != _epoch or value["state"] in TERMINAL:
                _sessions.pop(key, None)
                return None
            if value["state"] in {"UNCERTAIN", "RECONCILING"}:
                return None
        return session


def prepare(lock_path, run_id, kind, source_root):
    ledger = JobLedger(lock_path)
    value = ledger.prepare(run_id, kind, source_root)
    session = JobSession(ledger, value)
    with _registry_lock:
        _sessions[(str(Path(lock_path).resolve()), run_id)] = session
    return session


def retained_session(lock_path, run_id):
    with _registry_lock:
        return _sessions.get((str(Path(lock_path).resolve()), run_id))


class JobSession:
    def __init__(self, ledger, value):
        self.ledger, self.value = ledger, value
        self.run_id, self.job_id, self.token = value["run_id"], value["job_id"], value["token"]
        self.directory = ledger.root / value.get("directory_name", self.job_id)
        self.process = None
        self.stop = threading.Event()
        self.heartbeat = None
        self.verified_files = {}
        self.input_buffers = {}
        self.containment = None
        self.last_worker_seen = time.monotonic()

    def state(self):
        value = self.ledger.get(self.job_id)
        if value["owner"] != _epoch or value["token"] != self.token or value["state"] in TERMINAL:
            raise RunStoreError("Stale job cannot mutate a run.")
        return value

    def intent(self, payload):
        value = self.state()
        kind = value["kind"]
        terminal = payload.get("critic_status") in {"COMPLETED", "FAILED"} if kind == "CRITIC" else (
            payload.get("status") in {"COMPLETED", "FAILED", "CANCELLED", "AWAITING_SELECTION"})
        outcome = payload.get("critic_status") if kind == "CRITIC" else payload.get("status")
        if value["cancel_requested"] and outcome in {"COMPLETED", "AWAITING_SELECTION"}:
            raise RunStoreError("Cancelled job cannot publish successful completion.")
        phase = "ACCEPTANCE" if value["source_receipt"] is None else "PUBLICATION" if terminal else "UPDATE"
        if phase == "PUBLICATION" and outcome in {"COMPLETED", "AWAITING_SELECTION"} and not value.get("worker_completion"):
            raise RunStoreError("Successful publication requires a sealed worker completion.")
        return {"job_id": self.job_id, "run_id": self.run_id, "token": self.token, "kind": kind, "phase": phase,
                "receipt_id": f"{self.job_id}:{phase}:{digest(payload)}", "payload_hash": digest(payload),
                "outcome": outcome, "request_key": value.get("request_key"),
                "attempt_id": payload.get("critic_review_id") if kind == "CRITIC" else None,
                "critic_review_sha256": payload.get("critic_review_sha256") if kind == "CRITIC" else None}

    def acknowledge(self, intent):
        value = self.state()
        if intent["phase"] == "ACCEPTANCE":
            self.ledger.update(self.job_id, self.token, state="QUEUED", source_receipt=intent["receipt_id"], attempt_id=intent.get("attempt_id"))
        elif intent["phase"] == "PUBLICATION":
            self.ledger.update(self.job_id, self.token, state="PUBLISHING", publication_receipt=intent["receipt_id"])
        if value.get("cancel_requested") or intent.get("outcome") == "CANCEL_REQUESTED":
            self.ledger.update(self.job_id, self.token, cancel_requested=True)

    def pulse(self):
        while not self.stop.wait(5):
            try:
                value = self.state()
                self.ledger.update(self.job_id, self.token, lease_until=time.time() + 30,
                                   lease_monotonic_until=time.perf_counter() + 30, lease_clock="perf_counter")
                heartbeat = self.directory / "heartbeat.json"
                if value["authorized"]:
                    try:
                        body = json.loads(heartbeat.read_text())
                        if body.get("job_id") != self.job_id or body.get("token") != self.token:
                            raise RunStoreError("Worker heartbeat identity mismatch.")
                        if body.get("clock") == "perf_counter" and 0 <= time.perf_counter() - body["monotonic"] <= 30:
                            self.last_worker_seen = time.monotonic()
                    except (OSError, ValueError, KeyError):
                        pass  # Bounded grace for missing/atomic-replacement reads.
                    if time.monotonic() - self.last_worker_seen > 30:
                        self.ledger.update(self.job_id, self.token, state="RECONCILING", authorized=False, reason="WORKER_HEARTBEAT_LOST")
                        return
            except (RunStoreError, OSError, ValueError, KeyError):
                # No renewal on failure: worker's independent lease guard stops
                # subsequent work; it never turns failure into retry permission.
                return

    def launch(self, command, **options):
        value = self.state()
        if value["state"] == "RESULT_READY":
            marker = self.completion()
            self.process = RecoveredProcess(value.get("pid"), marker["returncode"])
            return ManagedProcess(self, self.process)
        if value["state"] != "QUEUED":
            raise RunStoreError("Only a queued accepted attempt can launch a worker.")
        controller = _controllers.get(str(self.ledger.lock_path.resolve()))
        if value["cancel_requested"] or controller is not None and controller.stop.is_set():
            raise RunStoreError("Job dispatch was cancelled or the controller is stopping.")
        receipt = RunStore(Path(value["source_root"])).job_receipt(self.job_id, "ACCEPTANCE")
        if receipt is None or receipt["receipt_id"] != value["source_receipt"]:
            raise RunStoreError("Worker dispatch has no committed acceptance intent.")
        self.directory.mkdir(parents=True, exist_ok=False)
        command = list(command)
        mappings, frozen_inputs, input_mappings = [], {}, {}
        for flag in ("--input", "--generation-context"):
            if flag in command:
                index = command.index(flag) + 1
                original = Path(command[index])
                frozen = self.directory / (flag[2:] + ".json")
                data = original.read_bytes()
                document = json.loads(data)
                hash_flag = "--input-sha256" if flag == "--input" else "--generation-context-sha256"
                if hash_flag in command and digest(document) != command[command.index(hash_flag) + 1]:
                    raise RunStoreError("Frozen job input failed canonical digest verification.")
                if flag == "--input" and value["kind"] == "JUDGE":
                    snapshot = RunStore(Path(value["source_root"])).records()[self.run_id]
                    expected = {"schema_version": "1.0", "run_id": self.run_id, **{key: snapshot[key] for key in (
                        "max_total_tokens", "candidate_batch", "selected_candidate_id", "selected_candidate_sha256", "manual_evidence")}}
                    if document != expected:
                        raise RunStoreError("Judge input differs from the accepted evidence snapshot.")
                frozen.write_bytes(data)
                frozen_inputs[frozen.name] = hashlib.sha256(data).hexdigest()
                input_mappings[str(original.resolve())] = frozen.name
                self.input_buffers[str(original.resolve())] = data
                command[index] = str(frozen)
        if "--output" in command:
            index = command.index("--output") + 1
            original = Path(command[index])
            result = self.directory / "results"
            if original.suffix == ".json":
                result.mkdir()
                command[index] = str(result / original.name)
                mappings.append((result, original.parent))
            else:
                command[index] = str(result)
                mappings.append((result, original))
        command_hash = digest(command[1:])
        self.ledger.update(self.job_id, self.token, state="STARTING", command_hash=command_hash,
                           output_mappings=[(str(a), str(b)) for a, b in mappings], frozen_inputs=frozen_inputs,
                           input_mappings=input_mappings, launch_intent=True)
        environment = dict(options.get("env", os.environ))
        environment.update({"SECMATE_JOB_ID": self.job_id, "SECMATE_JOB_FENCE": str(self.token),
                            "SECMATE_JOB_DB": str(self.ledger.path), "SECMATE_JOB_DIR": str(self.directory),
                            "SECMATE_JOB_COMMAND_HASH": command_hash})
        options["env"] = environment
        if os.name != "nt":
            options.setdefault("start_new_session", True)
        if command[1:2] == ["-m"]:
            wrapped = [command[0], "-m", "secmate_worker.job_runtime", *command[1:]]
        else:
            # Trusted internal probe/script commands still use the same stdlib
            # gate; they may run under the API interpreter without worker imports.
            runtime = Path(__file__).resolve().parents[4] / "services/deepteam-worker/src/secmate_worker/job_runtime.py"
            wrapped = [command[0], str(runtime), *command[1:]]
        guard = controller.launch_mutex if controller is not None else threading.RLock()
        try:
            with guard:
                if controller is not None and controller.stop.is_set():
                    raise RunStoreError("Controller is stopping before process creation.")
                self.process = subprocess.Popen(wrapped, **options)
                self.containment = ProcessContainment(self.process)
                identity = process_identity(self.process.pid)
                if identity is None and self.process.poll() is None:
                    raise RunStoreError("Worker process creation identity cannot be verified.")
                self.ledger.update(self.job_id, self.token, pid=self.process.pid, identity=identity)
            self.heartbeat = _HeartbeatThread(target=self.pulse, daemon=True, name=f"job-heartbeat-{self.job_id}")
            self.heartbeat.start()
            self.authorize()
        except Exception:
            self.terminate()
            raise
        return ManagedProcess(self, self.process)

    def authorize(self):
        deadline = time.monotonic() + 30
        ready = self.directory / "ready.json"
        while True:
            try:
                value = json.loads(ready.read_text())
                break
            except (OSError, ValueError):
                if self.process.poll() is not None:
                    raise RunStoreError("Worker exited before readiness authorization.")
                if time.monotonic() >= deadline:
                    raise RunStoreError("Worker readiness handshake timed out.")
                time.sleep(.05)
        state = self.state()
        if value.get("job_id") != self.job_id or value.get("token") != self.token or process_identity(value.get("pid")) != value.get("identity"):
            raise RunStoreError("Worker readiness identity mismatch.")
        if value["pid"] != state["pid"] and not self.containment.accept_worker(value["pid"], state["pid"]):
            raise RunStoreError("Worker interpreter is not the contained launcher child.")
        controller = _controllers.get(str(self.ledger.lock_path.resolve()))
        with controller.launch_mutex if controller is not None else _registry_lock:
            state = self.state()
            if state["cancel_requested"] or controller is not None and controller.stop.is_set():
                raise RunStoreError("Worker was cancelled before gate authorization.")
            self.ledger.update(self.job_id, self.token, state="RUNNING", authorized=True, execution_started=True,
                               worker_pid=value["pid"], worker_identity=value["identity"],
                               lease_until=time.time() + 30, lease_monotonic_until=time.perf_counter() + 30,
                               lease_clock="perf_counter")
        self.last_worker_seen = time.monotonic()

    def completion(self, value=None):
        value = self.state() if value is None else value
        path = self.directory / "completion.json"
        if path.exists() and path.stat().st_size > 1_000_000:
            raise RunStoreError("Worker completion manifest is oversized.")
        marker = value.get("completion_manifest")
        if not value.get("worker_completion") or not isinstance(marker, dict) or digest(marker) != value.get("completion_hash"):
            raise RunStoreError("Completion has no trusted worker journal seal.")
        if path.exists() and digest(json.loads(path.read_text())) != value["completion_hash"]:
            raise RunStoreError("Worker completion manifest changed after sealing.")
        if any(marker.get(key) != expected for key, expected in {"job_id": self.job_id, "token": value.get("execution_token", self.token),
              "command_hash": value["command_hash"]}.items()):
            raise RunStoreError("Worker completion identity mismatch.")
        results = self.directory / "results"
        actual, buffers = {}, {}
        total = 0
        for file in results.rglob("*") if results.exists() else []:
            if file.is_symlink() or not file.resolve().is_relative_to(results.resolve()):
                raise RunStoreError("Unsafe worker completion artifact.")
            if file.is_file():
                total += file.stat().st_size
                if total > 64_000_000 or len(buffers) >= 256:
                    raise RunStoreError("Worker completion output limit exceeded.")
                name = file.relative_to(results).as_posix()
                buffers[name] = file.read_bytes()
                actual[name] = hashlib.sha256(buffers[name]).hexdigest()
        if actual != marker.get("files"):
            raise RunStoreError("Worker completion artifacts changed.")
        self.verified_files = buffers
        return marker

    def projected_bytes(self, path):
        value = self.state()
        path = Path(path).resolve()
        if str(path) in value.get("input_mappings", {}):
            if str(path) not in self.input_buffers:
                name = value["input_mappings"][str(path)]
                frozen = self.directory / name
                if frozen.resolve().parent != self.directory.resolve() or frozen.is_symlink():
                    raise RunStoreError("Unsafe frozen job input.")
                data = frozen.read_bytes()
                if hashlib.sha256(data).hexdigest() != value["frozen_inputs"].get(name):
                    raise RunStoreError("Frozen job input changed after acceptance.")
                self.input_buffers[str(path)] = data
            return self.input_buffers[str(path)]
        for origin, destination in value.get("output_mappings", []):
            destination = Path(destination).resolve()
            if path.is_relative_to(destination):
                name = path.relative_to(destination).as_posix()
                if name not in self.verified_files:
                    raise RunStoreError("Required mapped output is absent from the verified completion seal.")
                return self.verified_files[name]
        return None

    def terminate(self):
        """Revoke permission and prove local containment exit without PID kills."""
        try:
            value = self.state()
            self.ledger.update(self.job_id, self.token, authorized=False)
        except RunStoreError:
            pass
        if self.containment is not None and os.name == "nt":
            exited = self.containment.terminate_and_wait()
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    return False
            return exited
        if self.process is None:
            return True
        if os.name != "nt":
            import signal
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                return False
        elif self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            return False
        return original_worker_exited(self.ledger.get(self.job_id))

    def finish(self):
        self.stop.set()
        if self.heartbeat:
            self.heartbeat.join(timeout=2)
        value = self.ledger.get(self.job_id)
        if value["token"] != self.token or value["owner"] != _epoch:
            raise RunStoreError("Stale attempt cannot release worker ownership.")
        if value["state"] in TERMINAL:
            return True
        if self.process is not None and self.process.poll() is None:
            self.ledger.update(self.job_id, self.token, state="RECONCILING", authorized=False,
                               pid=self.process.pid, identity=value.get("identity") or process_identity(self.process.pid),
                               reason="WORKER_EXIT_UNRESOLVED")
            return False
        if self.containment is not None and not self.terminate():
            self.ledger.update(self.job_id, self.token, state="RECONCILING", authorized=False, reason="CONTAINED_WORKER_EXIT_UNRESOLVED")
            return False
        if self.process is not None and self.containment is None and not original_worker_exited(value):
            self.ledger.update(self.job_id, self.token, state="RECONCILING", authorized=False, reason="WORKER_EXIT_UNRESOLVED")
            return False
        if value["state"] == "UNCERTAIN" and value.get("requires_explicit_resolution"):
            return False
        if value.get("needs_publication"):
            self.ledger.update(self.job_id, self.token, state="RESULT_READY", authorized=False)
            return False
        receipt = RunStore(Path(value["source_root"])).job_receipt(self.job_id, "PUBLICATION")
        if value["execution_started"] and not value.get("completion_hash") and not value["cancel_requested"]:
            self.ledger.update(self.job_id, self.token, state="UNCERTAIN", authorized=False, reason="PROVIDER_COMPLETION_UNCERTAIN")
            return False
        status = ("CANCELLED" if value["cancel_requested"] else
                  "FAILED" if receipt and receipt.get("outcome") == "FAILED" else
                  "SUCCEEDED" if receipt else "UNCERTAIN" if value["authorized"] else "ABORTED")
        self.ledger.update(self.job_id, self.token, state=status, authorized=False, reason=None if receipt else "NO_COMMITTED_PUBLICATION")
        if status == "UNCERTAIN":
            return False
        self.ledger.clear_projection(self.ledger.get(self.job_id))
        key = (str(self.ledger.lock_path.resolve()), self.run_id)
        with _registry_lock:
            if _sessions.get(key) is self:
                _sessions.pop(key, None)
        return True


def filesystem_path(path):
    """Use Win32 extended paths for evidence I/O, without relocating evidence."""
    path = Path(path).absolute()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        value = str(path)
        return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)
    return path


class ManagedProcess:
    def __init__(self, session, process):
        self.session, self.process = session, process

    def __getattr__(self, name):
        return getattr(self.process, name)

    def __setattr__(self, name, value):
        if name == "returncode" and "process" in self.__dict__:
            self.process.returncode = value
        else:
            object.__setattr__(self, name, value)

    def communicate(self, *args, **kwargs):
        streams = self.process.communicate(*args, **kwargs)
        self.session.state()  # fence before accepting any output
        if self.process.returncode == 0:
            marker = self.session.completion()
            if marker["returncode"] != self.process.returncode:
                raise RunStoreError("Worker exit disagrees with its completion seal.")
        else:
            # A failed pre-gate process need not have a completion marker.
            if (self.session.directory / "completion.json").exists():
                marker = self.session.completion()
                if marker["returncode"] != self.process.returncode:
                    raise RunStoreError("Worker exit disagrees with its completion seal.")
        value = self.session.state()
        try:
            for origin, destination in value.get("output_mappings", []):
                origin, destination = Path(origin), Path(destination)
                for name, data in self.session.verified_files.items():
                    target = filesystem_path(destination / name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix(target.suffix + ".job.tmp")
                    temporary.write_bytes(data)
                    os.replace(temporary, target)
        except OSError as error:
            if self.session.verified_files:
                self.session.ledger.update(self.session.job_id, self.session.token, needs_publication=True, reason="ARTIFACT_PROJECTION_FAILED")
            raise RunStoreError("Verified completion is awaiting artifact publication.") from error
        if value.get("needs_publication"):
            self.session.ledger.update(self.session.job_id, self.session.token, needs_publication=False)
        return streams


class RecoveredProcess:
    def __init__(self, pid, returncode):
        self.pid, self.returncode = pid, returncode

    def poll(self):
        return self.returncode

    def wait(self, *args, **kwargs):
        return self.returncode

    def communicate(self, *args, **kwargs):
        return "", ""


def launch(command, **options):
    session = _current.get()
    if session is None:
        raise RunStoreError("Worker launch requires durable job ownership.")
    return session.launch(command, **options)


def execution(kind, lock_path, source_root, records):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(run_id, *args, **kwargs):
            lock = lock_path()
            session = session_for(lock, run_id)
            if session is None:
                session = prepare(lock, run_id, kind, source_root())
            token = _current.set(session)
            try:
                # Direct internal execution/tests also require a durable intent.
                value = session.state()
                if value["source_receipt"] is None:
                    store = RunStore(source_root())
                    intent = store.job_receipt(session.job_id, "ACCEPTANCE")
                    if intent is None:
                        payload = records()[run_id].model_dump(mode="json")
                        intent = session.intent(payload)
                        store.save(payload, job_intent=intent)
                    session.acknowledge(intent)
                return function(run_id, *args, **kwargs)
            finally:
                try:
                    try:
                        released = session.finish()
                        if released and lock.exists():
                            value = json.loads(lock.read_text())
                            if value.get("job_id") == session.job_id and value.get("token") == session.token:
                                lock.unlink(missing_ok=True)
                    except (RunStoreError, OSError, ValueError):
                        pass  # Retain unresolved ownership; never pretend cleanup succeeded.
                finally:
                    _current.reset(token)
        return wrapped
    return decorate


def assert_deletable(lock_path, run_id):
    for job in JobLedger(lock_path).active():
        if job["run_id"] == run_id:
            raise RunStoreError("Run owns an active or unresolved durable job.")


def purge_attempt_files(lock_path, run_id):
    ledger = JobLedger(lock_path)
    assert_deletable(lock_path, run_id)
    with ledger.connection() as connection:
        rows = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM jobs WHERE run_id=?", (run_id,))]
    for row in rows:
        directory = ledger.root / row.get("directory_name", row["job_id"])
        if directory.resolve().parent != ledger.root.resolve() or directory.is_symlink() or getattr(directory, "is_junction", lambda: False)():
            raise RunStoreError("Unsafe job cleanup path.")
        if directory.exists():
            shutil.rmtree(directory)


def persist(store, lock_path, payload, evidence_bundle=None, original_evidence=None):
    """Serialize run commit with recovery fencing within this controller."""
    with _registry_lock:
        session = session_for(lock_path, payload["run_id"])
        intent = session.intent(payload) if session else None
        request = _request.get()
        request_intent = None
        if request:
            ledger = JobLedger(lock_path)
            with ledger.connection() as connection:
                connection.execute("UPDATE requests SET run_id=?,namespace=? WHERE request_key=?",
                    (payload["run_id"], "target_smoke" if payload["run_id"].startswith("target-smoke-") else
                     "synthetic" if payload["run_id"].startswith("api-run-") else "chatmate", request["key"]))
            if intent is None:
                intent = {"job_id": "request-" + request["key"], "run_id": payload["run_id"], "token": 0,
                          "kind": "CONTROL", "phase": "REQUEST", "request_key": request["key"],
                           "receipt_id": "request-" + request["key"] + ":" + digest(payload), "payload_hash": digest(payload)}
            with ledger.connection() as connection:
                entry = dict(connection.execute("SELECT * FROM requests WHERE request_key=?", (request["key"],)).fetchone())
            intent.update({"request_body_hash": entry["body_hash"], "request_action": entry["action"],
                            "request_status_code": entry["status_code"], "request_namespace": entry["namespace"]})
            if session is not None and entry["job_id"] is None:
                request_intent = {"job_id": "request-" + request["key"], "run_id": payload["run_id"], "token": 0,
                    "kind": "CONTROL", "phase": "REQUEST", "request_key": request["key"],
                    "receipt_id": "request-" + request["key"] + ":" + digest(payload), "payload_hash": digest(payload),
                    "request_body_hash": entry["body_hash"], "request_action": entry["action"],
                    "request_status_code": entry["status_code"], "request_namespace": entry["namespace"]}
        store.save(payload, evidence_bundle=evidence_bundle, job_intent=intent, original_evidence=original_evidence)
        if request_intent is not None:
            store.save(payload, job_intent=request_intent)
        if session:
            try:
                session.acknowledge(intent)
            except RunStoreError:
                import logging
                logging.getLogger(__name__).warning("Durable job acknowledgment pending reconciliation.")


def dispatch(function, args, lock_path, name, thread_factory=threading.Thread):
    controller = _controllers.get(str(Path(lock_path).resolve()))
    if controller is not None:
        controller.submit(function, args)
    else:
        # Embedded/internal callers must supply their own lifetime guard. The
        # supported ASGI deployment always installs the central dispatcher.
        thread_factory(target=function, args=args, daemon=True, name=name).start()


def pending_recovery(lock_path, run_id):
    return any(job["run_id"] == run_id and job["state"] == "RESULT_READY" for job in JobLedger(lock_path).active())


class Coordinator:
    """One dispatcher thread; durable receipts, not this notification list,
    define accepted work. Restart recovery publishes verified results only.
    """
    def __init__(self, lock_path):
        self.ledger = JobLedger(lock_path)
        self.stop, self.wake = threading.Event(), threading.Event()
        self.mutex = threading.Lock()
        self.launch_mutex = threading.RLock()
        self.notifications = []
        self.thread = _HeartbeatThread(target=self.loop, daemon=True, name="secmate-job-dispatcher")

    def start(self):
        _controllers[str(self.ledger.lock_path.resolve())] = self
        self.thread.start()

    def submit(self, function, args):
        with self.mutex:
            if self.stop.is_set():
                raise RunStoreError("Controller is stopping; dispatch remains pending reconciliation.")
            self.notifications.append((function, args))
        self.wake.set()

    def loop(self):
        import logging
        while not self.stop.is_set():
            self.wake.wait(2)
            self.wake.clear()
            try:
                from . import deepteam_runs as deep, chatmate_runs as chat, chatmate_critic as critic, standard_reviews
                from . import synthetic_chatmate_smoke as smoke
                from .config import get_settings
                self.ledger.reconcile({"SYNTHETIC": deep.RUN_ROOT, "GENERATION": chat.CHATMATE_RUN_ROOT,
                                       "JUDGE": chat.CHATMATE_RUN_ROOT, "CRITIC": (chat.CHATMATE_RUN_ROOT, deep.RUN_ROOT),
                                       "TARGET_SMOKE": smoke.RUN_ROOT})
                with self.mutex:
                    task = self.notifications.pop(0) if self.notifications else None
                if task:
                    task[0](*task[1])
                    continue
                for job in self.ledger.active():
                    if job["state"] != "RESULT_READY":
                        continue
                    attempts = job.get("recovery_attempts", 0)
                    if attempts >= 3:
                        self.ledger._adopt(job, "UNCERTAIN", "PUBLICATION_RETRY_LIMIT")
                        continue
                    value = self.ledger._adopt({**job, "recovery_attempts": attempts + 1}, "RESULT_READY", f"PUBLICATION_RECOVERY_{attempts + 1}")
                    session = JobSession(self.ledger, value)
                    with _registry_lock:
                        _sessions[(str(self.ledger.lock_path.resolve()), job["run_id"])] = session
                    socmate_review = job["kind"] == "CRITIC" and job["run_id"].startswith("api-run-")
                    records = smoke._runs if job["kind"] == "TARGET_SMOKE" else deep._runs if job["kind"] == "SYNTHETIC" or socmate_review else chat._runs
                    record = records.get(job["run_id"])
                    if record is None:
                        self.ledger._adopt(value, "UNCERTAIN", "RECOVERY_RUN_MISSING")
                        continue
                    if job["kind"] == "TARGET_SMOKE":
                        smoke._execute_run(record.run_id)
                    elif job["kind"] == "SYNTHETIC":
                        deep._execute_run(record.run_id, record.attack_profile_id, record.vulnerability_profile_id,
                                          record.max_total_tokens, record.execution_mode, record.max_paths, record.target_profile_id)
                    elif job["kind"] == "GENERATION":
                        chat._execute_generation(record.run_id, record.attack_profile_id, record.max_total_tokens, get_settings())
                    elif job["kind"] == "JUDGE":
                        chat._execute_evaluation(record.run_id, chat.CHATMATE_RUN_ROOT / record.run_id / "evaluation-input.json")
                    elif socmate_review:
                        standard_reviews.execute_review(record.run_id, get_settings())
                    else:
                        critic._execute_critic(record.run_id, get_settings())
            except Exception:
                logging.getLogger(__name__).error("Durable job reconciliation remains pending; no automatic inference retry.")

    def close(self):
        with self.launch_mutex:
            self.stop.set()
        self.wake.set()
        with _registry_lock:
            sessions = [session for session in _sessions.values() if session.ledger.path.resolve() == self.ledger.path.resolve()]
        for session in sessions:
            while True:
                try:
                    if session.terminate():
                        break
                except Exception:
                    import logging
                    logging.getLogger(__name__).error("Shutdown retains ownership while contained exit remains unresolved.")
                # Keep the lifetime guard: lack of exit proof is not quiescence.
                time.sleep(.1)
        # Never release the OS guard/registration while dispatch is still alive.
        self.thread.join()
        _controllers.pop(str(self.ledger.lock_path.resolve()), None)


@contextmanager
def diagnostic_slot(lock_path):
    key = str(Path(lock_path).resolve())
    with _registry_lock:
        if key in _diagnostics or JobLedger(lock_path).active():
            raise FileExistsError("Another local inference operation is active or unresolved.")
        _diagnostics.add(key)
    try:
        yield
    finally:
        with _registry_lock:
            _diagnostics.discard(key)


def critic_job(lock_path, run_id, attempt_id):
    ledger = JobLedger(lock_path)
    with ledger.connection() as connection:
        values = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM jobs WHERE run_id=? ORDER BY token DESC", (run_id,))]
    return next((value for value in values if value["kind"] == "CRITIC" and value.get("attempt_id") in (None, attempt_id)), None)


def claim_projection(session):
    """An exclusive projection is disposable until acceptance is committed."""
    path = session.ledger.lock_path
    descriptor, created = None, False
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        created = True
        data = json.dumps({"run_id": session.run_id, "pid": None, "job_id": session.job_id, "token": session.token}).encode("ascii")
        while data:
            count = os.write(descriptor, data)
            if count <= 0:
                raise OSError("Incomplete job lock projection write.")
            data = data[count:]
        os.close(descriptor)
        descriptor = None
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            path.unlink(missing_ok=True)
        session.finish()
        raise


class RequestCache:
    def __init__(self, lock_path):
        self.ledger = JobLedger(lock_path)

    def reserve(self, key, body_hash, status_code=202, action=None):
        with self.ledger.connection() as connection:
            row = connection.execute("SELECT * FROM requests WHERE request_key=?", (key,)).fetchone()
            if row is not None:
                if row["body_hash"] != body_hash or row["action"] != action:
                    raise RunStoreError("Idempotency key was reused with different input.")
                return dict(row)
            connection.execute("INSERT INTO requests(request_key,body_hash,run_id,namespace,state,status_code,job_id,action) VALUES (?,?,NULL,NULL,'PROCESSING',?,NULL,?)", (key, body_hash, status_code, action))
            return None

    def complete(self, key, status_code):
        with self.ledger.connection() as connection:
            connection.execute("UPDATE requests SET state=?,status_code=? WHERE request_key=?",
                               ("COMMITTED" if 200 <= status_code < 300 else "REJECTED", status_code, key))

    def replay(self, entry, roots):
        if entry["state"] == "REJECTED":
            return None, entry["status_code"] or 409
        if not entry["run_id"] or entry["namespace"] not in roots:
            return None, 409
        store = RunStore(roots[entry["namespace"]])
        receipt = store.job_receipt(entry["job_id"], "ACCEPTANCE") if entry["job_id"] else store.job_receipt("request-" + entry["request_key"], "REQUEST")
        expected = {"request_key": entry["request_key"], "request_body_hash": entry["body_hash"],
                    "request_action": entry["action"], "request_status_code": entry["status_code"],
                    "request_namespace": entry["namespace"], "run_id": entry["run_id"]}
        if receipt is None or any(receipt.get(key) != value for key, value in expected.items()):
            return None, 409
        payload = store.records().get(entry["run_id"])
        return payload, (entry["status_code"] or 202) if payload else 410
