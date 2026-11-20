"""ASGI-only HTTP checks, real core/tools, explicit offline provider boundaries."""

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from langchain.messages import AIMessage
from pydantic import SecretStr

from local_document_agent.agent import DocumentAssistant
from local_document_agent.config import Configuration, ConfigurationError
from local_document_agent.http_adapter import create_app
from local_document_agent.http_config import AdapterSettings, load_adapter_settings
from local_document_agent.http_contracts import CONTRACT_VERSION
from local_document_agent.provider import create_provider

TOKEN = "offline-adapter-token-marker"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def isolated_adapter_environment(monkeypatch):
    monkeypatch.delenv("LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN", raising=False)


def settings(roots, **changes):
    return AdapterSettings(Configuration(
        input_dir=roots.input, output_dir=roots.output,
        api_key=SecretStr("offline-provider-key-marker"), allow_transmission=True,
        **changes,
    ), SecretStr(TOKEN))


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def bind_tools(self, tools, **kwargs):
        assert {tool.name for tool in tools} == {"search_documents", "read_document", "create_document"}
        return self

    async def ainvoke(self, messages, **kwargs):
        self.messages.append(messages)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return await response()
        return response


class Resource:
    def __init__(self, model):
        self.model = model
        self.closed = False

    async def aclose(self):
        self.closed = True


def fixture_app(roots, responses, **config):
    resources = []

    def factory(configuration):
        resource = Resource(Model(responses() if callable(responses) else responses))
        resources.append(resource)
        return resource

    return create_app(settings(roots, **config), provider_factory=factory), resources


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline", headers=AUTH)


def payload(app, message="A harmless question.", **changes):
    return {
        "contract_version": CONTRACT_VERSION,
        "adapter_instance_id": app.state.runs.instance_id,
        "submission_id": str(uuid4()), "message": message, **changes,
    }


async def settle(app, acknowledgement):
    run = app.state.runs.runs[acknowledgement["run_id"]]
    await asyncio.wait_for(asyncio.shield(run.owner), 5)
    return run


def call(name, args, identifier="one"):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": identifier}])


def create_call(filename="report.md", kind="report", identifier="create"):
    return call("create_document", {
        "filename": filename, "kind": kind, "content": "Fictional Tuesday review.",
        "source_ids": [],
    }, identifier)


def test_import_help_and_fixed_configuration_without_effects(tmp_path):
    # Fresh processes: never point this at the real application root.
    app_root = Path(__file__).resolve().parents[1]
    code = """
import os, socket
for name in list(os.environ):
    if name.startswith(('OPENROUTER_', 'LANGSMITH_', 'LANGCHAIN_', 'LOCAL_DOCUMENT_AGENT_ADAPTER_')):
        os.environ.pop(name)
def denied(*a, **k): raise AssertionError('network/config/provider access')
socket.socket.connect = socket.getaddrinfo = denied
from dotenv import main
main.dotenv_values = denied
from local_document_agent import provider
provider.create_provider = denied
import local_document_agent.http_adapter
import local_document_agent.http_config
from local_document_agent.http_cli import main
main(['--help'])
"""
    completed = subprocess.run(
        [str(app_root / ".venv/Scripts/python.exe"), "-c", code],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--port" in completed.stdout
    assert list(tmp_path.iterdir()) == []
    (tmp_path / ".env").write_text(
        "LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN=offline-local-token\n"
        "DOCUMENT_INPUT_DIR=unrelated\nDOCUMENT_OUTPUT_DIR=unrelated\n",
    )
    configured = load_adapter_settings(tmp_path, environment={})
    assert configured.configuration.input_dir == tmp_path / "data/input/mock-workspace"
    assert configured.configuration.output_dir == tmp_path / "data/output"
    assert not configured.readiness().ready
    assert "ROOTS_NOT_READY" in [reason.code for reason in configured.readiness().reasons]
    assert not (tmp_path / "data").exists()
    with pytest.raises(ConfigurationError):
        load_adapter_settings(tmp_path, environment={"LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN": ""})


def test_metadata_is_bounded_authenticated_configured_not_observed(roots, monkeypatch, caplog):
    def prohibited(*args, **kwargs):
        raise AssertionError("No body read or provider construction")
    app = create_app(settings(roots), provider_factory=prohibited)
    monkeypatch.setattr(type(roots), "read_bytes", prohibited)

    async def scenario():
        async with client(app) as http:
            response = await http.get("/v1/metadata")
            assert response.status_code == 200
            assert len(response.content) < 8192
            meta = response.json()
            assert meta["identity"]["observed_model"] is None
            assert meta["identity"]["configured_provider"] == "OpenRouter"
            assert meta["readiness"]["ready"]
            assert meta["limits"]["execution_slots"] == 1
            assert len(meta["capabilities"]) == 3
            assert str(roots.input) not in response.text
            assert TOKEN not in response.text and "offline-provider-key-marker" not in response.text
            assert not app.state.runs.runs
    asyncio.run(scenario())
    assert TOKEN not in caplog.text


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/metadata"), ("POST", "/v1/runs"),
    ("GET", f"/v1/runs/{uuid4()}"), ("POST", f"/v1/runs/{uuid4()}/cancel"),
])
@pytest.mark.parametrize("authorization", [None, "Bearer wrong-marker"])
def test_all_endpoints_reject_bad_auth_without_effects(roots, method, path, authorization, caplog):
    app, resources = fixture_app(roots, [])
    async def scenario():
        async with client(app) as http:
            headers = {} if authorization is None else {"Authorization": authorization}
            # Use a new client to avoid inheriting the fixture's correct token.
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline") as unauthenticated:
                response = await unauthenticated.request(method, path, headers=headers)
            assert response.status_code == 401
            assert "wrong-marker" not in response.text
            assert not resources and not app.state.runs.runs
    asyncio.run(scenario())
    assert list(roots.output.iterdir()) == []
    assert "wrong-marker" not in caplog.text


def test_entrypoint_startup_configuration_and_safe_errors(tmp_path, monkeypatch, capsys):
    from local_document_agent import http_cli
    import uvicorn
    from importlib.metadata import distribution
    assert any(entry.name == "local-document-agent-http" for entry in distribution("local-document-agent").entry_points)
    assert http_cli.main(["--app-root", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []
    (tmp_path / ".env").write_text(
        "LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN=offline-token\n"
        "OPENROUTER_API_KEY=private-startup-marker\n",
    )
    seen = []
    def run(app, **kwargs):
        seen.append(kwargs)
        assert app.state.runs.runs == {}
        assert not app.state.runs.settings.readiness().ready
    monkeypatch.setattr(uvicorn, "run", run)
    assert http_cli.main(["--app-root", str(tmp_path)]) == 0
    assert seen[0]["host"] == "127.0.0.1" and seen[0]["port"] == 7310
    assert seen[0]["workers"] == 1 and not seen[0]["reload"] and not seen[0]["access_log"]
    assert seen[0]["log_config"] is None and seen[0]["log_level"] == "critical"
    assert "private-startup-marker" not in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def test_duplicate_authorization_and_no_authenticated_redirects(roots):
    app, resources = fixture_app(roots, [])
    async def scenario():
        async with client(app) as http:
            response = await http.get("/v1/metadata", headers=[
                ("Authorization", f"Bearer {TOKEN}"), ("Authorization", "Bearer wrong"),
            ])
            assert response.status_code == 401
            response = await http.get("/v1/metadata/")
            assert response.status_code == 404 and "location" not in response.headers
            assert not resources
    asyncio.run(scenario())


def test_fresh_runs_do_not_share_source_ids(roots):
    (roots.input / "notes.txt").write_text("Fictional source.")
    sequences = iter([
        [call("read_document", {"path": "notes.txt", "start_line": 1, "max_lines": 10}), AIMessage("Read [R1].")],
        [call("create_document", {
            "filename": "not-created.md", "kind": "report", "content": "No valid source.",
            "source_ids": ["R1"],
        }), AIMessage("Source unavailable.")],
    ])
    app, resources = fixture_app(roots, lambda: next(sequences))
    async def scenario():
        async with client(app) as http:
            first = (await http.post("/v1/runs", json=payload(app))).json()
            await settle(app, first)
            first_result = (await http.get(first["status_path"])).json()["result"]
            assert first_result["sources"][0]["source_id"] == "R1"
            second = (await http.post("/v1/runs", json=payload(app))).json()
            await settle(app, second)
            result = (await http.get(second["status_path"])).json()["result"]
            assert result["session_id"] != first_result["session_id"]
            assert result["sources"] == result["retained_sources"] == result["created_files"] == []
            assert result["tool_events"][0]["summary"] == "UNKNOWN_SOURCE"
            assert not (roots.output / "not-created.md").exists()
            assert len(resources[1].model.messages[0]) == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("status,code", [
    (401, "AUTHENTICATION_ERROR"), (429, "RATE_LIMIT"), (503, "PROVIDER_UNAVAILABLE"),
])
def test_http_sdk_errors_are_terminal_truthful_single_attempts(roots, status, code, caplog):
    attempts = []
    def transport(request):
        attempts.append(request)
        return httpx.Response(status, json={"error": {"code": status, "message": "private-provider-body"}})
    app = create_app(settings(roots), provider_factory=lambda configuration: create_provider(
        configuration, transport=httpx.MockTransport(transport),
    ))
    async def scenario():
        async with client(app) as http:
            ack = (await http.post("/v1/runs", json=payload(app))).json()
            await settle(app, ack)
            response = await http.get(ack["status_path"])
            result = response.json()["result"]
            assert result["status"] == "failed" and result["error"]["code"] == code
            assert result["sources"] == result["created_files"] == []
            assert "private-provider-body" not in response.text
            assert len(attempts) == 1
    asyncio.run(scenario())
    assert "private-provider-body" not in caplog.text


def test_close_keeps_slot_owned_and_completed_core_result_on_close_error(roots):
    closing, release = None, None
    class Provider(Resource):
        async def aclose(self):
            closing.set()
            await release.wait()
            raise OSError("private-close-prose")
    provider = Provider(Model([AIMessage("Available answer.")]))
    app = create_app(settings(roots), provider_factory=lambda configuration: provider)
    async def scenario():
        nonlocal closing, release
        closing, release = asyncio.Event(), asyncio.Event()
        async with client(app) as http:
            body = payload(app)
            ack = (await http.post("/v1/runs", json=body)).json()
            await closing.wait()
            assert app.state.runs.active is not None
            snapshot = (await http.get(ack["status_path"])).json()
            assert snapshot["state"] == "running" and snapshot["result"]["status"] == "completed"
            assert (await http.post("/v1/runs", json=payload(app))).json()["error"]["code"] == "TARGET_BUSY"
            assert (await http.post("/v1/runs", json=body)).json()["run_id"] == ack["run_id"]
            await http.post(ack["cancel_path"])
            await http.post(ack["cancel_path"])
            assert app.state.runs.active is not None
            release.set()
            await settle(app, ack)
            response = await http.get(ack["status_path"])
            final = response.json()
            assert final["state"] == "failed" and final["cleanup_status"] == "failed"
            assert final["result"]["status"] == "completed"
            assert final["result"]["answer"] == "Available answer."
            assert final["adapter_error"]["code"] == "PROVIDER_CLOSE_ERROR"
            assert app.state.runs.active is not None
            assert (await http.post("/v1/runs", json=payload(app))).json()["error"]["code"] == "TARGET_BUSY"
            assert (await http.get(ack["status_path"])).content == response.content
    asyncio.run(scenario())


@pytest.mark.parametrize("change", [
    {"extra": "private-value"}, {"message": 1}, {"message": True}, {"message": None},
    {"message": ""}, {"message": " \t\n"}, {"message": "x" * 4001},
    {"message": "\ud800"}, {"submission_id": 1}, {"submission_id": "not-a-uuid"},
    {"submission_id": uuid4().hex}, {"submission_id": str(uuid4()).upper()},
    {"contract_version": "unknown"}, {"adapter_instance_id": "not-a-uuid"},
])
def test_strict_rejection_before_acceptance(roots, change):
    app, resources = fixture_app(roots, [])
    async def scenario():
        async with client(app) as http:
            response = await http.post("/v1/runs", content=json.dumps(payload(app, **change)))
            assert response.status_code == 422
            assert "private-value" not in response.text
            assert not resources and not app.state.runs.runs
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["sized", "chunked", "bad-json", "nonobject", "deep"])
def test_body_bounds_and_malformed_json(roots, mode):
    app, resources = fixture_app(roots, [])
    async def chunks():
        for _ in range(40):
            yield b"x" * 1024
    async def scenario():
        async with client(app) as http:
            body = {
                "sized": b"x" * 32769, "chunked": chunks(), "bad-json": b'{"message":',
                "nonobject": b"[]", "deep": b"[" * 1500 + b"]" * 1500,
            }[mode]
            response = await http.post("/v1/runs", content=body)
            assert response.status_code == (413 if mode in ("sized", "chunked") else 422)
            assert not resources and not app.state.runs.runs
    asyncio.run(scenario())


def test_exact_bytes_dedup_conflict_busy_poll_cancel_and_fresh_sessions(roots):
    entered, release = None, None
    async def blocked():
        entered.set()
        await release.wait()
        return AIMessage("Exact answer é\n")
    app, resources = fixture_app(roots, lambda: [blocked])
    exact = " \nRead the fictional note é.\t "
    async def scenario():
        nonlocal entered, release
        entered, release = asyncio.Event(), asyncio.Event()
        async with client(app) as http:
            body = payload(app, exact)
            ack = (await http.post("/v1/runs", json=body)).json()
            await entered.wait()
            duplicate = await http.post("/v1/runs", json=body)
            assert duplicate.status_code == 202 and duplicate.json()["run_id"] == ack["run_id"]
            assert (await http.post("/v1/runs", json={**body, "message": exact + "!"})).status_code == 409
            assert (await http.post("/v1/runs", json=payload(app))).json()["error"]["code"] == "TARGET_BUSY"
            assert (await http.get("/v1/metadata")).status_code == 200
            assert (await http.get(ack["status_path"])).json()["state"] == "running"
            assert len(resources) == 1
            assert resources[0].model.messages[0][-1].content == exact
            assert ack["request_sha256"] == hashlib.sha256(exact.encode()).hexdigest()
            release.set()
            await settle(app, ack)
            first = await http.get(ack["status_path"])
            assert first.json()["result"]["answer"] == "Exact answer é\n"
            assert first.json()["result"]["answer_sha256"] == hashlib.sha256("Exact answer é\n".encode()).hexdigest()
            assert resources[0].closed
            for _ in range(3):
                assert (await http.get(ack["status_path"])).content == first.content
            assert (await http.post(ack["cancel_path"])).json()["state"] == "completed"
            assert (await http.get(ack["status_path"])).content == first.content
            second = (await http.post("/v1/runs", json=payload(app))).json()
            await settle(app, second)
            second_result = (await http.get(second["status_path"])).json()["result"]
            assert second_result["session_id"] != first.json()["result"]["session_id"]
            assert len(resources[1].model.messages[0]) == 2  # system + new human only
            assert second_result["sources"] == second_result["retained_sources"] == []
            assert len(resources) == 2
            for bad in ("bad", str(uuid4()), ack["run_id"].replace("-", "")):
                assert (await http.get(f"/v1/runs/{bad}")).status_code == 404
                assert (await http.post(f"/v1/runs/{bad}/cancel")).status_code == 404
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["report", "email_draft"])
def test_http_real_sdk_all_tools_provenance_and_single_create(roots, kind, caplog):
    source = roots.input / "notes.txt"
    source.write_bytes(b"Fictional Tuesday review.\n")
    requests, providers = [], []

    def completion(content=None, name=None, args=None):
        message = {"role": "assistant", "content": content}
        if name:
            message["tool_calls"] = [{
                "id": f"call_{len(requests)}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }]
        return {
            "id": "offline", "object": "chat.completion", "created": 1, "model": "offline-observed-model",
            "system_fingerprint": None,
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if name else "stop"}],
        }

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            response = completion(name="search_documents", args={"query": "notes", "scope": "filename", "offset": 0, "limit": 5})
        elif len(requests) == 2:
            assert json.loads(body["messages"][-1]["content"])["ok"]
            response = completion(name="read_document", args={"path": "notes.txt", "start_line": 1, "max_lines": 20})
        elif len(requests) == 3:
            assert json.loads(body["messages"][-1]["content"])["data"]["source_id"] == "R1"
            response = completion(name="create_document", args={
                "filename": "http-output.md", "kind": kind,
                "content": "Fictional Tuesday review.", "source_ids": ["R1"],
            })
        else:
            assert json.loads(body["messages"][-1]["content"])["ok"]
            response = completion(content="Fictional Tuesday review [R1]. Saved.")
        return httpx.Response(200, json=response)

    def factory(configuration):
        provider = create_provider(configuration, transport=httpx.MockTransport(transport))
        providers.append(provider)
        return provider
    app = create_app(settings(roots), provider_factory=factory)

    async def scenario():
        async with client(app) as http:
            body = payload(app, "Summarize notes.txt and save a new local document.")
            ack = (await http.post("/v1/runs", json=body)).json()
            await settle(app, ack)
            response = await http.get(ack["status_path"])
            result = response.json()["result"]
            assert result["status"] == "completed"
            assert result["sources"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert result["sources"][0]["path"] == "notes.txt"
            assert len(result["sources"]) == 1  # search did not register a source
            raw = (roots.output / "http-output.md").read_bytes()
            created = result["created_files"][0]
            assert created["sha256"] == hashlib.sha256(raw).hexdigest()
            assert created["bytes_written"] == len(raw) and created["source_ids"] == ["R1"]
            assert created["not_sent"] == (True if kind == "email_draft" else None)
            assert (b"NOT SENT" in raw) == (kind == "email_draft")
            assert result["observed_model"] is None and result["model_call_usage"] is None
            assert len(result["tool_events"]) == 3
            assert (await http.post("/v1/runs", json=body)).json()["run_id"] == ack["run_id"]
            assert (await http.get(ack["status_path"])).content == response.content
            assert len(requests) == 4 and len(providers) == 1
            assert providers[0].sync_client.is_closed and providers[0].async_client.is_closed
            assert source.read_bytes() == b"Fictional Tuesday review.\n"
            assert list(roots.output.iterdir()) == [roots.output / "http-output.md"]
    asyncio.run(scenario())
    assert TOKEN not in caplog.text and "Fictional Tuesday review" not in caplog.text


@pytest.mark.parametrize("ending", ["failure", "limit", "cancel", "uncertain"])
def test_after_write_failures_limits_cancellation_and_uncertain_outputs(roots, ending, monkeypatch):
    entered = None
    async def blocked():
        entered.set()
        await asyncio.Event().wait()
    if ending == "uncertain":
        def fail_fsync(descriptor):
            raise PermissionError("private-exception-marker")
        monkeypatch.setattr("os.fsync", fail_fsync)
    responses = [create_call()]
    responses += [blocked] if ending == "cancel" else [RuntimeError("private-exception-marker")] if ending == "failure" else [AIMessage("File effect reported.")]
    app, resources = fixture_app(roots, responses, **({"max_model_calls_per_turn": 1} if ending == "limit" else {}))
    async def scenario():
        nonlocal entered
        entered = asyncio.Event()
        async with client(app) as http:
            ack = (await http.post("/v1/runs", json=payload(app))).json()
            if ending == "cancel":
                await entered.wait()
                for _ in range(2):
                    cancel = (await http.post(ack["cancel_path"])).json()
                    assert cancel["cancel_requested"]
            await settle(app, ack)
            response = await http.get(ack["status_path"])
            result = response.json()["result"]
            assert result["status"] == {"failure": "failed", "limit": "limited", "cancel": "cancelled", "uncertain": "completed"}[ending]
            assert (roots.output / "report.md").exists()
            assert len(result["created_files"]) == (0 if ending == "uncertain" else 1)
            assert result["uncertain_outputs"] == (["report.md"] if ending == "uncertain" else [])
            assert "private-exception-marker" not in response.text
            assert resources[0].closed
            original = (roots.output / "report.md").read_bytes()
            await http.post(ack["cancel_path"])
            assert (await http.get(ack["status_path"])).content == response.content
            assert (roots.output / "report.md").read_bytes() == original
    asyncio.run(scenario())


def test_discovery_and_model_claims_are_not_provenance_and_collision_preserves_bytes(roots):
    (roots.input / "notes.md").write_text("Fictional note.")
    (roots.output / "report.md").write_bytes(b"preserved-existing-bytes")
    app, _ = fixture_app(roots, [
        call("search_documents", {"query": "notes", "scope": "filename", "offset": 0, "limit": 5}),
        create_call(), AIMessage("I read the note [R99] and saved a report."),
    ])
    async def scenario():
        async with client(app) as http:
            ack = (await http.post("/v1/runs", json=payload(app))).json()
            await settle(app, ack)
            result = (await http.get(ack["status_path"])).json()["result"]
            assert result["sources"] == result["created_files"] == []
            assert result["unverified_source_ids"] == ["R99"]
            assert result["tool_events"][1]["summary"] == "FILE_EXISTS"
            assert (roots.output / "report.md").read_bytes() == b"preserved-existing-bytes"
    asyncio.run(scenario())


def test_readiness_restart_capacity_and_no_receipt_eviction(roots):
    app, resources = fixture_app(roots, lambda: [AIMessage("No operation claimed.")])
    not_ready = create_app(AdapterSettings(Configuration(
        input_dir=roots.input, output_dir=roots.output,
    ), SecretStr(TOKEN)), provider_factory=lambda _: pytest.fail("not ready"))
    async def scenario():
        async with client(not_ready) as http:
            assert (await http.post("/v1/runs", json=payload(not_ready))).status_code == 503
            assert not not_ready.state.runs.runs
        async with client(app) as http:
            old = payload(app, adapter_instance_id=str(uuid4()))
            assert (await http.post("/v1/runs", json=old)).json()["error"]["code"] == "ADAPTER_INSTANCE_CHANGED"
            first_body = payload(app)
            first = None
            for index in range(32):
                ack = (await http.post("/v1/runs", json=first_body if index == 0 else payload(app))).json()
                first = first or ack
                await settle(app, ack)
            assert len(resources) == 32
            assert (await http.post("/v1/runs", json=payload(app))).json()["error"]["code"] == "RUN_CAPACITY_REACHED"
            assert (await http.post("/v1/runs", json=first_body)).json()["run_id"] == first["run_id"]
            assert len(app.state.runs.submissions) == 32 and len(resources) == 32
        restarted, new_resources = fixture_app(roots, [])
        async with client(restarted) as http:
            response = await http.post("/v1/runs", json=first_body)
            assert response.status_code == 409 and not new_resources
            assert (await http.get(first["status_path"])).status_code == 404
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["normal", "timeout", "close-failure"])
def test_shutdown_single_deadline_slot_ownership_and_close_failure(roots, monkeypatch, mode):
    entered, release, closing = None, None, None
    records = []
    class Diagnostics:
        def record(self, phase, code, **kwargs):
            records.append((phase, code))
    class Provider(Resource):
        async def aclose(self):
            closing.set()
            if mode == "timeout":
                await release.wait()
            if mode == "close-failure":
                raise OSError("private-close-marker")
            self.closed = True
    async def blocked():
        entered.set()
        await asyncio.Event().wait()
    resources = []
    def factory(configuration):
        provider = Provider(Model([create_call(), blocked]))
        resources.append(provider)
        return provider
    app = create_app(settings(roots), provider_factory=factory, diagnostics=Diagnostics())
    if mode == "timeout":
        monkeypatch.setattr("local_document_agent.http_adapter.SHUTDOWN_SECONDS", 0.01)
    async def scenario():
        nonlocal entered, release, closing
        entered, release, closing = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async with client(app) as http:
            ack = (await http.post("/v1/runs", json=payload(app))).json()
            await entered.wait()
            manager = app.state.runs
            await manager.shutdown()
            response = await http.get(ack["status_path"])
            state = response.json()
            assert (await http.post("/v1/runs", json=payload(app))).json()["error"]["code"] == "SERVICE_STOPPING"
            assert (roots.output / "report.md").exists()
            if mode == "timeout":
                assert manager.active is not None and not manager.active.owner.done()
                assert state["state"] == "running" and state["disposition"] == "unknown"
                assert state["cleanup_status"] == "unknown"
                assert ("shutdown", "SHUTDOWN_TIMEOUT") in records
                assert state["result"]["created_files"][0]["path"] == "report.md"
                assert not resources[0].closed
                await http.post(ack["cancel_path"])  # must not cancel close
                release.set()
                await settle(app, ack)
                assert resources[0].closed
            elif mode == "close-failure":
                assert state["state"] == "failed" and state["cleanup_status"] == "failed"
                assert state["adapter_error"]["code"] == "PROVIDER_CLOSE_ERROR"
                assert state["result"]["status"] == "cancelled"
            else:
                assert state["state"] == "cancelled" and state["cleanup_status"] == "closed"
                assert state["result"]["created_files"][0]["path"] == "report.md"
                assert resources[0].closed and manager.active is None
            assert "private-close-marker" not in response.text
    asyncio.run(scenario())
