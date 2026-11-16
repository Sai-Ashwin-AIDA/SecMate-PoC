"""Export a synthetic offline API/worker contract fixture in an isolated temporary root."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


@patch("dotenv.load_dotenv", new=lambda *args, **kwargs: False)
def export_fixture(output: Path):
    output = output.resolve()
    if not output.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("Offline fixture output must be inside the temporary directory")
    output.mkdir(parents=True, exist_ok=False)
    sandbox_api = output / "sandbox" / "apps" / "api"
    sandbox_api.mkdir(parents=True)
    # Set the root BEFORE importing lifecycle modules: their import-time recovery
    # sees only the fresh sandbox, never the user's persisted runs or worker locks.
    os.environ["SECMATE_API_DATA_ROOT"] = str(sandbox_api / "data")
    os.environ["GROQ_API_KEY"] = "synthetic-offline-groq"
    os.environ["OPENROUTER_API_KEY"] = "synthetic-offline-openrouter"
    os.environ["DEEPTEAM_TELEMETRY_OPT_OUT"] = "YES"
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
    os.environ["TELEMETRY_OPT_OUT"] = "YES"
    from secmate_api import config
    config.API_ROOT = sandbox_api
    from secmate_api import chatmate_runs as runs, chatmate_critic as critic, main
    from secmate_api.contracts import ChatMateResponseSubmission
    from secmate_api.config import Settings
    from fastapi.testclient import TestClient
    from test_chatmate_runs import _record

    assert runs.CHATMATE_RUN_ROOT == sandbox_api / "data" / "chatmate-runs"
    assert not runs._runs and not runs._processes
    runs.RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(__file__).resolve().parents[3]
    worker_root = workspace / "services" / "deepteam-worker"
    worker_python = worker_root / ".venv" / "Scripts" / "python.exe"
    wrapper = worker_root / "tests" / "offline_chatmate_contract_worker.py"
    settings = Settings("synthetic-offline-groq", "synthetic-offline-openrouter", 45, groq_critic_api_key="synthetic-offline-critic")
    original_popen = subprocess.Popen
    launches = []
    observed_streams = []

    def offline_popen(command, **kwargs):
        modes = {"secmate_worker.manual_chatmate": "evaluation", "secmate_worker.manual_chatmate_critic": "critic"}
        assert command[:3] == [str(worker_python), "-m", "secmate_worker.job_runtime"] and command[4] in modes
        mode = modes[command[4]]
        launches.append(mode)
        # Drop the real env-file flag completely; this fixture never reads production .env.
        arguments = command[5:]
        if "--env-file" in arguments:
            env_index = arguments.index("--env-file")
            arguments = [*arguments[:env_index], *arguments[env_index + 2:]]
        kwargs["env"]["PYTHONIOENCODING"] = "utf-8"
        if mode == "evaluation":
            kwargs["env"]["OPENROUTER_API_KEY"] = "synthetic-offline-openrouter"
        else:
            assert kwargs["env"]["GROQ_CRITIC_API_KEY"] == "synthetic-offline-critic"
            assert "GROQ_API_KEY" not in kwargs["env"]
        inner = [str(wrapper), mode, *arguments]
        from secmate_api import jobs
        from secmate_api.run_store import digest
        session = jobs._current.get()
        session.ledger.update(session.job_id, session.token, command_hash=digest(inner))
        kwargs["env"]["SECMATE_JOB_COMMAND_HASH"] = digest(inner)
        process = original_popen([str(worker_python), "-m", "secmate_worker.job_runtime", *inner], **kwargs)
        original_communicate = process.communicate
        def communicate(*args, **options):
            streams = original_communicate(*args, **options)
            observed_streams.append(streams)
            return streams
        process.communicate = communicate
        return process

    class IdleThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass

    with patch.object(runs, "WORKER_ROOT", worker_root), patch.object(runs, "WORKER_PYTHON", worker_python), \
         patch.object(runs, "threading", SimpleNamespace(Thread=IdleThread)), \
         patch.object(critic, "threading", SimpleNamespace(Thread=IdleThread)), \
         patch.object(runs.subprocess, "Popen", offline_popen):
        record = _record("AWAITING_RESPONSE")
        selected = next(candidate for candidate in record.candidate_batch.candidates if candidate.candidate_id == record.selected_candidate_id)
        exact_prompt = "\t" + selected.prompt + "\r\n"
        exact_hash = hashlib.sha256(exact_prompt.encode("utf-8")).hexdigest()
        exact_candidate = selected.model_copy(update={"prompt": exact_prompt, "prompt_sha256": exact_hash})
        exact_batch = record.candidate_batch.model_copy(update={"candidates": [
            exact_candidate if candidate.candidate_id == selected.candidate_id else candidate for candidate in record.candidate_batch.candidates]})
        record = record.model_copy(update={"candidate_batch": exact_batch, "selected_candidate_sha256": exact_hash})
        now = runs._now()
        record = record.model_copy(update={"created_at": now, "generated_at": now, "selected_at": runs._now_datetime()})
        runs._runs[record.run_id] = record
        runs._persist(record)
        observed = runs.submit_chatmate_response(record.run_id, ChatMateResponseSubmission(
            candidate_id=record.selected_candidate_id, candidate_sha256=record.selected_candidate_sha256,
            outcome="RESPONSE", response_text="\t安全な拒否 — réponse sûre. operator@example.test gsk_syntheticresponsesecret123456789\r\n",
            prompt_submitted_unchanged=True, observation_captured_verbatim=True,
            judge_data_collection_attested=True, conversation_id="会話-offline-fixture"))
        assert "<redacted>" in observed.manual_evidence.redacted_response_text
        assert observed.manual_evidence.redacted_response_text.startswith("\t")
        assert observed.manual_evidence.redacted_response_text.endswith("\r\n")
        evaluating = runs.start_chatmate_evaluation(settings, record.run_id)
        runs._execute_evaluation(evaluating.run_id, runs.CHATMATE_RUN_ROOT / record.run_id / "evaluation-input.json")
        completed = runs.get_chatmate_run(record.run_id)
        assert completed.status == "COMPLETED" and completed.final_status == "RESISTED", (completed.error_message, observed_streams)
        original_audit = runs.get_chatmate_audit(record.run_id)
        assert original_audit is not None
        original_bytes = {path.name: path.read_bytes() for path in (runs.CHATMATE_RUN_ROOT / record.run_id / "evaluations" / completed.evaluation_id).glob("*.json")}
        turn = original_audit.evidence["paths"][0]["turns"][0]
        assert turn["target_response"] == observed.manual_evidence.redacted_response_text
        assert turn["probe"] == exact_prompt
        assert turn["manual_collection"] == [observed.manual_evidence.model_dump(mode="json")]
        # Verify the real managed worker's output seal and frozen input, not just
        # hand-authored dictionaries that already agree with the API contract.
        seals = list((runs.RUN_LOCK.parent / "job-attempts").glob("*/completion.json"))
        evaluation_seals = [path for path in seals if any(Path(name).name == "evidence.json" for name in json.loads(path.read_text())["files"])]
        assert len(evaluation_seals) == 1
        seal_path = evaluation_seals[0]
        seal = json.loads(seal_path.read_text())
        assert seal["returncode"] == 0
        for name, content in original_bytes.items():
            assert seal["files"][f"{completed.evaluation_id}/{name}"] == hashlib.sha256(content).hexdigest()
        frozen = json.loads((seal_path.parent / "input.json").read_text())
        assert frozen["manual_evidence"] == observed.manual_evidence.model_dump(mode="json")
        # Reject tampering on copies only; the published sealed bundle is retained.
        for case in ("trim", "probe", "missing", "duplicate", "hash", "correlation", "consent", "candidate"):
            directory = output / "negative-cases" / case
            directory.mkdir(parents=True)
            for name, content in original_bytes.items():
                (directory / name).write_bytes(content)
            evidence = json.loads(original_bytes["evidence.json"])
            altered = evidence["paths"][0]["turns"][0]
            if case == "trim": altered["target_response"] = altered["target_response"].strip()
            elif case == "probe": altered["probe"] += "x"
            elif case == "missing": altered["manual_collection"] = []
            elif case == "duplicate": altered["manual_collection"] *= 2
            elif case == "hash": altered["manual_collection"][0]["persisted_response_sha256"] = "a" * 64
            elif case == "correlation": altered["manual_collection"][0]["correlation_sha256"] = "b" * 64
            elif case == "consent": altered["manual_collection"][0]["judge_data_collection_attested"] = False
            else: altered["manual_collection"][0]["candidate_id"] = "wrong-candidate"
            (directory / "evidence.json").write_text(json.dumps(evidence), encoding="ascii")
            try:
                runs._validate_evaluation_bundle(directory, completed)
            except runs.ChatMateRunError:
                pass
            else:
                raise AssertionError(f"Tampered manual evidence accepted: {case}")
        active = critic.start_chatmate_critic(settings, record.run_id, True)
        critic_input = critic._source(active)
        assert "判断" in critic_input.canonical_judge.reasoning and "<redacted>" in critic_input.canonical_judge.reasoning
        assert "credential:" not in critic_input.canonical_judge.reasoning
        assert critic_input.canonical_judge.reasoning != original_audit.evidence["review_results"][0]["target_evaluation"]["reasoning"]
        critic._execute_critic(record.run_id, settings)
        finished = runs.get_chatmate_run(record.run_id)
        assert finished.critic_status == "COMPLETED", finished.critic_error_message
        directory = critic._attempt_directory(finished)
        assert (directory / "critic-review.json").read_bytes().isascii()
        review = critic.get_chatmate_critic(record.run_id)
        assert "任意" in review.management_summary and "<redacted>" in review.management_summary
        assert review.model_attempts[0]["role"] == "ATTACK_CRITIC"
        assert review.model_attempts[0]["usage"]["total_tokens"] == 1000
        assert original_audit == runs.get_chatmate_audit(record.run_id)
        assert original_bytes == {path.name: path.read_bytes() for path in (runs.CHATMATE_RUN_ROOT / record.run_id / "evaluations" / completed.evaluation_id).glob("*.json")}
        client = TestClient(main.app)
        base = f"/api/v1/chatmate-runs/{record.run_id}"
        exported = {}
        for name, route in (("record", base), ("audit", base + "/audit"), ("review", base + "/critic")):
            response = client.get(route)
            assert response.status_code == 200
            exported[name] = response.json()
        draft = client.post(base + "/follow-up", headers={"X-SecMate-Local-Run": "confirmed", "Origin": "http://localhost:5173"})
        assert draft.status_code == 201 and draft.json()["authorization_attested"] is False
        exported["follow_up_draft"] = draft.json()
        exported["critic_input"] = runs._read_json(directory / "input.json")
        exported["provider_calls"] = {"judge": 1, "critic": 1}
        exported["offline"] = True
        assert launches == ["evaluation", "critic"]
        assert not runs.RUN_LOCK.exists() and not runs._processes
    filenames = {"record": "record.json", "audit": "audit.json", "review": "critic-review.json",
        "critic_input": "critic-input.json", "follow_up_draft": "follow-up-draft.json"}
    for name, filename in filenames.items():
        (output / filename).write_text(json.dumps(exported[name], ensure_ascii=True, indent=2), encoding="ascii")
    fixture = output / "contract-fixture.json"
    serialized = json.dumps(exported, ensure_ascii=True, indent=2)
    assert "gsk_" not in serialized and "operator@example.test" not in serialized
    assert settings.groq_api_key not in serialized and settings.openrouter_api_key not in serialized
    fixture.write_text(serialized, encoding="ascii")
    return fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(str(export_fixture(args.output)))


if __name__ == "__main__":
    main()
