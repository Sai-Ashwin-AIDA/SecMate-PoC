"""Explicit offline cleanup of local assessment history, not configuration."""
import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from .config import API_ROOT
from .jobs import ControllerGuard, original_worker_exited


def clear_history(data: Path) -> dict:
    roots = [data / "deepteam-runs", data / "chatmate-runs"]
    if any(root.is_symlink() for root in roots):
        raise RuntimeError("Run roots must not be symbolic links.")
    with ControllerGuard(roots[0]):
        database = roots[0] / "jobs.sqlite3"
        if database.exists():
            with closing(sqlite3.connect(database)) as connection:
                for (payload,) in connection.execute("SELECT payload FROM jobs"):
                    job = json.loads(payload)
                    never_started = job.get("pid") is None and not job.get("launch_intent", False)
                    if not never_started and not original_worker_exited(job):
                        raise RuntimeError("A worker may still be alive. Stop it before clearing history.")
        deleted = 0
        for root in roots:
            if not root.exists():
                continue
            for entry in root.iterdir():
                if entry.name == "control-api.lock":
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    deleted += int(entry.name.startswith(("api-run-", "chatmate-run-")))
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
        epoch = uuid4().hex
        (data / "history-epoch").write_text(epoch, encoding="ascii")
        return {"deleted_runs": deleted, "history_epoch": epoch}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear-run-history", action="store_true", required=True)
    parser.add_argument("--confirm", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(clear_history(API_ROOT / "data")))


if __name__ == "__main__":
    main()
