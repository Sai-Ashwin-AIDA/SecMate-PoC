"""Exercise real schemas/adapters/HTTP accounting under the durable launch path.

No target or provider is contacted: only the HTTP transport is replaced.
"""
import hashlib
import json
import os
import runpy
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from secmate_worker import job_runtime as runtime
from secmate_worker import model_clients


def offline_clients():
    calls = []
    enhancements = []
    marker = "Return one JSON object matching this schema exactly. Do not add Markdown or prose outside the JSON object: "

    def respond(request):
        payload = json.loads(request.content)
        schema = json.loads(payload["messages"][0]["content"].split(marker)[-1])
        fields = set(schema["properties"])
        calls.append(schema["title"])
        if fields == {"candidates"}:
            output = {"candidates": [{"candidate_id": "candidate-1", "prompt": "Synthetic first boundary probe"},
                                     {"candidate_id": "candidate-2", "prompt": "Synthetic second boundary probe"}]}
        elif fields == {"decisions"}:
            output = {"decisions": [{"candidate_id": "candidate-1", "verdict": "ALIGNED"},
                                    {"candidate_id": "candidate-2", "verdict": "ALIGNED"}]}
        else:
            raise AssertionError(f"Unexpected non-baseline schema: {schema['title']}")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})

    real_clients = model_clients.StructuredModelClients

    class clients(real_clients):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, transport=httpx.MockTransport(respond), **kwargs)

    return calls, enhancements, clients


@pytest.fixture
def offline_cli(monkeypatch, tmp_path):
    calls, enhancements, clients = offline_clients()
    monkeypatch.setattr(model_clients, "StructuredModelClients", clients)
    from secmate_worker import chatmate_candidates
    monkeypatch.setattr(chatmate_candidates, "StructuredModelClients", clients)
    monkeypatch.setenv("GROQ_API_KEY", "fake-offline-key")
    monkeypatch.setenv("SECMATE_PROVIDER_MIN_SPACING_SECONDS", "0")
    monkeypatch.setenv("SECMATE_PROVIDER_MAX_SPACING_SECONDS", "0")
    return calls, enhancements, tmp_path / "candidate-batch.json"


def test_unsupported_unregistered_launcher_fails_before_any_provider_call(offline_cli, monkeypatch):
    calls, _, output = offline_cli
    monkeypatch.setattr(sys, "argv", ["chatmate_candidates", "--attack-profile", "prompt-probing-v1", "--output", str(output)])
    with pytest.warns(RuntimeWarning, match="found in sys.modules"), pytest.raises(SystemExit, match="GENERATION_SCHEMA_UNRESOLVED"):
        runpy.run_module("secmate_worker.chatmate_candidates", run_name="__main__", alter_sys=False)
    payload = json.loads(output.read_text())
    assert len(calls) == 0
    assert "ChatMateCandidateCompleteness" not in calls
    assert payload["budget"]["provider_calls_succeeded"] == 0
    assert payload["candidate_checks"] == []
    assert payload["error"]["stage"] == "PROMPT_GENERATION"


@pytest.mark.parametrize("operation_fails", [False, True])
def test_cli_cleanup_cannot_erase_safe_failure_or_publish_batch(offline_cli, monkeypatch, capsys, operation_fails):
    from secmate_worker import chatmate_candidates
    calls, _, output = offline_cli
    clients = model_clients.StructuredModelClients
    original_close = clients.close

    async def close(self):
        await original_close(self)
        raise RuntimeError("synthetic-private-close-detail")

    async def fail_baseline(self, *args, **kwargs):
        raise TypeError("synthetic-private-operation-detail")

    monkeypatch.setattr(clients, "close", close)
    if operation_fails:
        monkeypatch.setattr(chatmate_candidates.ChatMateCandidateGenerator, "_generate", fail_baseline)
    monkeypatch.setattr(sys, "argv", ["chatmate_candidates", "--attack-profile", "prompt-probing-v1", "--output", str(output)])
    code = "GENERATION_CHECK_ERROR" if operation_fails else "GENERATION_CLEANUP_ERROR"
    with pytest.raises(SystemExit, match=code) as exited:
        chatmate_candidates.main()
    failure = json.loads(output.read_text())
    assert failure["error"]["code"] == code
    assert failure["error"]["cleanup_failed"] is True
    assert failure["error"]["stage"] == ("BASELINES" if operation_fails else "CLEANUP")
    assert failure["budget"]["provider_calls_attempted"] == len(calls)
    assert failure["budget"]["provider_calls_succeeded"] == len(calls)
    assert failure["budget"]["provider_calls_failed"] == 0
    assert len(calls) == (0 if operation_fails else 2)
    assert "batch" not in failure
    captured = capsys.readouterr()
    observable = output.read_text() + str(exited.value) + captured.out + captured.err
    assert "synthetic-private" not in observable
    assert "Traceback" not in observable


@pytest.mark.skipif(os.name != "nt", reason="Real Windows containment identity; POSIX requires a dedicated process group")
@pytest.mark.parametrize("profile", ["prompt-injection-v1", "system-override-v1", "prompt-probing-v1", "goal-redirection-v1", "context-poisoning-v1"])
def test_durable_launcher_completes_real_schemas_and_seals_batch(offline_cli, monkeypatch, profile):
    calls, enhancements, output = offline_cli
    directory = output.parent
    output = directory / "results" / output.name
    command = ["-m", "secmate_worker.chatmate_candidates", "--attack-profile", profile, "--output", str(output),
               "--start-gate", str(directory / "old-directory" / "start.gate")]
    command_hash = hashlib.sha256(runtime.canonical(command).encode("ascii")).hexdigest()
    database = directory / "jobs.sqlite3"
    state = {"run_id": "chatmate-run-managed-progress", "token": 1, "state": "RUNNING", "authorized": True, "cancel_requested": False,
        "lease_monotonic_until": time.perf_counter() + 55, "lease_clock": "perf_counter", "worker_pid": os.getpid(),
        "worker_identity": runtime.identity(), "frozen_inputs": {}}
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE jobs (job_id TEXT, token INTEGER, state TEXT, payload TEXT)")
        connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", ("offline-job", 1, "RUNNING", json.dumps(state)))
    for key, value in {"SECMATE_JOB_DIR": str(directory), "SECMATE_JOB_DB": str(database),
                       "SECMATE_JOB_ID": "offline-job", "SECMATE_JOB_FENCE": "1", "SECMATE_JOB_COMMAND_HASH": command_hash}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["job_runtime", *command])
    with pytest.raises(SystemExit) as exited:
        runtime.main()
    assert exited.value.code == 0
    progress = json.loads((directory / "generation-progress.json").read_text())
    assert {key: progress[key] for key in ("run_id", "job_id", "token")} == {
        "run_id": state["run_id"], "job_id": "offline-job", "token": 1}
    assert progress["succeeded"] == 2 and progress["failed"] == 0
    payload = json.loads(output.read_text())
    candidates = payload["batch"]["candidates"]
    assert len(candidates) == 2
    for candidate in candidates:
        assert candidate["prompt_sha256"] == hashlib.sha256(candidate["prompt"].encode("utf-8")).hexdigest()
        assert candidate["generation_mode"] == "BASELINE_METHOD_REVIEWED"
        assert candidate["method_review"]["verdict"] == "ALIGNED"
        assert candidate["prompt"] == candidate["source_prompt"]
    assert not enhancements
    assert len(calls) == 2
    assert not any("Enhanced" in name or "Completeness" in name or "Explanation" in name for name in calls)
    assert payload["budget"]["provider_calls_attempted"] == len(calls)
    assert payload["budget"]["provider_calls_succeeded"] == len(calls)
    assert payload["budget"]["provider_calls_failed"] == 0
    assert payload["budget"]["tokens_consumed"] == 20 * len(calls)
    assert all(check["outcome"] == "ALIGNED" for check in payload["candidate_checks"])
    seal = json.loads((directory / "completion.json").read_text())
    assert seal["returncode"] == 0
    assert seal["files"]["candidate-batch.json"] == hashlib.sha256(output.read_bytes()).hexdigest()
    with sqlite3.connect(database) as connection:
        saved = json.loads(connection.execute("SELECT payload FROM jobs").fetchone()[0])
    assert saved["worker_completion"] is True
    assert saved["completion_hash"] == hashlib.sha256(runtime.canonical(seal).encode("ascii")).hexdigest()


@pytest.mark.skipif(os.name != "nt", reason="Windows managed-worker launch regression")
def test_fresh_managed_process_completes_with_real_gate_and_schema_pipeline(tmp_path):
    """Do not rely on pytest's already-imported candidate classes for the fix."""
    output = tmp_path / "results" / "candidate-batch.json"
    command = ["-m", "secmate_worker.chatmate_candidates", "--attack-profile", "prompt-probing-v1", "--output", str(output)]
    command_hash = hashlib.sha256(runtime.canonical(command).encode("ascii")).hexdigest()
    database = tmp_path / "jobs.sqlite3"
    state = {"run_id": "chatmate-run-follow-up-progress", "token": 1, "state": "RUNNING", "authorized": False, "cancel_requested": False,
             "lease_monotonic_until": time.perf_counter() + 55, "lease_clock": "perf_counter", "frozen_inputs": {}}
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE jobs (job_id TEXT, token INTEGER, state TEXT, payload TEXT)")
        connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", ("fresh-job", 1, "RUNNING", json.dumps(state)))
    environment = {key: value for key, value in os.environ.items() if not key.startswith("SECMATE_JOB_")}
    environment.update({"SECMATE_JOB_DIR": str(tmp_path), "SECMATE_JOB_DB": str(database),
        "SECMATE_JOB_ID": "fresh-job", "SECMATE_JOB_FENCE": "1", "SECMATE_JOB_COMMAND_HASH": command_hash,
        "GROQ_API_KEY": "fake-offline-key", "OPENROUTER_API_KEY": "",
        "SECMATE_PROVIDER_MIN_SPACING_SECONDS": "0", "SECMATE_PROVIDER_MAX_SPACING_SECONDS": "0"})
    # Only the HTTP transport is injected. The outer runtime, authorization,
    # registered main module and fresh canonical candidate import are real.
    script = (
        "import sys, json, runpy; "
        f"sys.path.insert(0, {str(Path(__file__).parent)!r}); "
        "from test_managed_candidate_execution import offline_clients; "
        "from secmate_worker import model_clients; "
        "calls, enhancements, clients = offline_clients(); "
        "model_clients.StructuredModelClients = clients; "
        "sys.argv = ['job_runtime', *json.loads(sys.argv[1])]; "
        "runpy.run_module('secmate_worker.job_runtime', run_name='__main__', alter_sys=True)"
    )
    with subprocess.Popen([sys.executable, "-c", script, json.dumps(command)], env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        try:
            deadline = time.monotonic() + 20
            ready = tmp_path / "ready.json"
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            assert ready.exists(), "Fresh runtime never reached the authorization gate"
            identity = json.loads(ready.read_text())
            # Windows venv python.exe may be a launcher: authorize the actual
            # interpreter that wrote ready.json, not Popen's launcher PID.
            assert isinstance(identity["pid"], int) and identity["pid"] > 0
            state.update(authorized=True, worker_pid=identity["pid"], worker_identity=identity["identity"])
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE jobs SET payload=?", (json.dumps(state),))
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr
        finally:
            if process.poll() is None:
                with sqlite3.connect(database) as connection:
                    state["cancel_requested"] = True
                    connection.execute("UPDATE jobs SET payload=?", (json.dumps(state),))
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    payload = json.loads(output.read_text())
    assert len(payload["batch"]["candidates"]) == 2
    assert json.loads((tmp_path / "generation-progress.json").read_text())["run_id"] == state["run_id"]
    assert payload["budget"]["provider_calls_succeeded"] == 2
    assert payload["budget"]["provider_calls_failed"] == 0
    assert [event["stage"] for event in payload["model_attempts"]] == ["PROMPT_GENERATION", "METHOD_ALIGNMENT"]
    seal = json.loads((tmp_path / "completion.json").read_text())
    assert seal["returncode"] == 0
    assert seal["files"][output.name] == hashlib.sha256(output.read_bytes()).hexdigest()
    with sqlite3.connect(database) as connection:
        saved = json.loads(connection.execute("SELECT payload FROM jobs").fetchone()[0])
    assert saved["worker_completion"] is True
    assert saved["completion_hash"] == hashlib.sha256(runtime.canonical(seal).encode("ascii")).hexdigest()
