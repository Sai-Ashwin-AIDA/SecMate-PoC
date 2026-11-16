"""Attempt-specific provider start gate and independent worker lease watchdog.

Uses stdlib only. Invoked by the API as the outer runner for existing worker CLIs.
It never retries a provider call. Its only control-database mutation is sealing
its own authorized completion; it cannot publish runs or release ownership.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import runpy
import sqlite3
import sys
import threading
import time
from pathlib import Path

_inputs = {}


def read_frozen(path):
    path = Path(path)
    if "SECMATE_JOB_ID" not in os.environ:
        return path.read_bytes()
    value = _inputs.get(path.resolve())
    if value is None:
        raise RuntimeError("Input was not sealed by the durable worker gate")
    return value


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def identity():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        values = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(ctypes.byref(value) for value in values)):
            raise RuntimeError("Worker identity unavailable")
        return f"windows:{values[0].dwHighDateTime << 32 | values[0].dwLowDateTime}"
    stat = Path("/proc/self/stat").read_text()
    started = stat[stat.rindex(")") + 2:].split()[19]
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    return f"linux:{boot}:{started}"


def job():
    path = Path(os.environ["SECMATE_JOB_DB"])
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        row = connection.execute("SELECT payload FROM jobs WHERE job_id=?", (os.environ["SECMATE_JOB_ID"],)).fetchone()
        if row is None:
            raise RuntimeError("Job disappeared")
        value = json.loads(row[0])
        if value["token"] != int(os.environ["SECMATE_JOB_FENCE"]):
            raise RuntimeError("Stale worker token")
        return value
    finally:
        connection.close()


def require_permission():
    if "SECMATE_JOB_ID" not in os.environ:
        return
    value = job()
    # The API and worker can run different Python versions. On Windows their
    # monotonic() epochs differ; perf_counter() shares QueryPerformanceCounter.
    remaining = value.get("lease_monotonic_until", 0) - time.perf_counter()
    if value.get("lease_clock") != "perf_counter" or value["state"] != "RUNNING" or not value["authorized"] or value["cancel_requested"] or not 0 <= remaining <= 60 or value.get("worker_pid") != os.getpid() or value.get("worker_identity") != identity():
        raise RuntimeError("Durable worker authorization expired or was revoked")


def progress_identity():
    """Bind advisory progress to the authorized ledger attempt, not a path name."""
    require_permission()
    value = job()
    return {"run_id": value["run_id"], "job_id": os.environ["SECMATE_JOB_ID"], "token": value["token"]}


def atomic(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(canonical(value), encoding="ascii")
    deadline = time.monotonic() + 1
    while True:
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.02)


def seal_completion(marker):
    """Trusted worker may seal its own completion, never release the slot or
    update a run. The digest is durable before the optional marker projection.
    """
    connection = sqlite3.connect(os.environ["SECMATE_JOB_DB"], timeout=5)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT payload FROM jobs WHERE job_id=? AND token=? AND state='RUNNING'",
                                 (marker["job_id"], marker["token"])).fetchone()
        if row is None:
            raise RuntimeError("Stale completion cannot be sealed")
        value = json.loads(row[0])
        if value.get("lease_clock") != "perf_counter" or not value["authorized"] or value["cancel_requested"] or value.get("lease_monotonic_until", 0) < time.perf_counter():
            raise RuntimeError("Completion authorization was revoked")
        value["completion_hash"] = hashlib.sha256(canonical(marker).encode("ascii")).hexdigest()
        value["completion_manifest"] = marker
        value["worker_completion"] = True
        connection.execute("UPDATE jobs SET payload=? WHERE job_id=? AND token=? AND state='RUNNING'",
                           (canonical(value), marker["job_id"], marker["token"]))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    directory = Path(os.environ["SECMATE_JOB_DIR"])
    sys.modules["secmate_worker.job_runtime"] = sys.modules[__name__]
    job_id, token = os.environ["SECMATE_JOB_ID"], int(os.environ["SECMATE_JOB_FENCE"])
    command = sys.argv[1:]
    if hashlib.sha256(canonical(command).encode("ascii")).hexdigest() != os.environ["SECMATE_JOB_COMMAND_HASH"]:
        raise SystemExit("Job command integrity failed")
    if os.name != "nt":
        import ctypes
        import signal
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        if os.getpgrp() != os.getpid() or libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise SystemExit("Worker parent-death containment unavailable")
        def parent_died(*args):
            os.killpg(os.getpgrp(), signal.SIGKILL)
        signal.signal(signal.SIGTERM, parent_died)
        if os.getppid() != job()["controller_pid"]:
            raise SystemExit("Worker controller disappeared before launch")
    atomic(directory / "ready.json", {"job_id": job_id, "token": token, "pid": os.getpid(), "identity": identity()})
    deadline = time.monotonic() + 30
    while True:
        value = job()
        if value["cancel_requested"] or value["state"] in {"RECONCILING", "UNCERTAIN", "ABORTED", "CANCELLED"}:
            raise SystemExit("Worker authorization cancelled")
        if value["state"] == "RUNNING" and value["authorized"]:
            require_permission()
            break
        if time.monotonic() >= deadline:
            raise SystemExit("Worker gate timed out")
        time.sleep(.05)
    atomic(directory / "started.json", {"job_id": job_id, "token": token, "timestamp": time.time()})
    for name, expected in value.get("frozen_inputs", {}).items():
        path = directory / name
        if path.resolve().parent != directory.resolve() or path.is_symlink():
            raise SystemExit("Unsafe frozen input path")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit("Frozen input changed before execution")
        _inputs[path.resolve()] = data
    stopped = threading.Event()

    def watch():
        while not stopped.is_set():
            try:
                require_permission()
                atomic(directory / "heartbeat.json", {"job_id": job_id, "token": token, "timestamp": time.time(), "monotonic": time.perf_counter(), "clock": "perf_counter"})
            except Exception:
                os._exit(75)
            stopped.wait(2)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    # The unique outer gate replaces legacy per-run gates; keep CLI contracts.
    had_gate = "--start-gate" in command
    if had_gate:
        index = command.index("--start-gate")
        del command[index:index + 2]
    code = 0
    try:
        if had_gate:
            gate = directory / "authorized-inner.gate"
            gate.write_text("go", encoding="ascii")
            command.extend(["--start-gate", str(gate)])
        if command[:1] == ["-c"]:
            sys.argv = ["-c", *command[2:]]
            exec(compile(command[1], "<trusted-worker-probe>", "exec"), {"__name__": "__main__"})
        elif command and command[0].endswith(".py"):
            script = Path(command[0]).resolve()
            if not script.is_relative_to(Path(__file__).resolve().parents[2]):
                raise RuntimeError("Worker script outside trusted worker installation")
            sys.argv = [str(script), *command[1:]]
            runpy.run_path(str(script), run_name="__main__")
        elif len(command) >= 2 and command[0] == "-m" and command[1] in {
             "secmate_worker.single_attack", "secmate_worker.chatmate_candidates",
             "secmate_worker.manual_chatmate", "secmate_worker.manual_chatmate_critic", "secmate_worker.standard_review",
             "secmate_worker.synthetic_chatmate.model_phase5"}:
            sys.argv = [command[1], *command[2:]]
            # Keep the CLI in its registered module namespace. Running a fresh
            # __main__ dict without registering it breaks postponed annotations
            # (e.g. Pydantic Literal fields) and can duplicate contract identities.
            # Importing the allowlisted module also avoids swapping __main__ while
            # the lease watchdog runs. Gates, argv and completion sealing stay here.
            module_name = command[1] + ".__main__" if command[1] == "secmate_worker.synthetic_chatmate.model_phase5" else command[1]
            importlib.import_module(module_name).main()
        else:
            raise RuntimeError("Unsupported worker command")
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1 if error.code else 0
        if isinstance(error.code, str):
            print(error.code, file=sys.stderr)
    except Exception:
        code = 1
        print("Worker execution failed.", file=sys.stderr)
    finally:
        stopped.set()
        watcher.join(timeout=3)
    files = {}
    root = directory / "results"
    total = 0
    for path in root.rglob("*") if root.exists() else []:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise SystemExit("Unsafe completion output")
        if path.is_file():
            total += path.stat().st_size
            if total > 64_000_000 or len(files) >= 256:
                raise SystemExit("Worker completion output limit exceeded")
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    marker = {"job_id": job_id, "token": token,
        "command_hash": os.environ["SECMATE_JOB_COMMAND_HASH"], "returncode": code, "files": files}
    seal_completion(marker)
    atomic(directory / "completion.json", marker)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
