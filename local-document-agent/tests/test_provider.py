import asyncio
import json

import httpx
import pytest
from langchain.messages import HumanMessage, ToolMessage
from pydantic import SecretStr

from local_document_agent.config import BASE_URL, MODEL, Configuration, ConfigurationError
from local_document_agent.context import ToolContext
from local_document_agent.provider import create_provider, provider_failure
from local_document_agent.tools import build_tools


def completion(content=None, calls=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {
        "id": "offline-completion", "object": "chat.completion", "created": 1,
        "model": MODEL, "system_fingerprint": None,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50},
    }


def configured(roots):
    return Configuration(
        input_dir=roots.input, output_dir=roots.output,
        api_key=SecretStr("offline-test-key"), allow_transmission=True,
    )


def test_real_sdk_transport_tools_results_timeout_route_and_privacy(roots, monkeypatch, caplog):
    seen = []
    monkeypatch.setenv("OPENROUTER_DEBUG", "1")
    monkeypatch.setenv("OPENROUTER_SESSION_ID", "must-not-leak")
    (roots.input / "notes.txt").write_text("fictional document marker", encoding="utf-8")

    def handle(request):
        payload = json.loads(request.content)
        seen.append((request, payload))
        assert str(request.url) == BASE_URL + "/chat/completions"
        assert request.headers["authorization"] == "Bearer offline-test-key"
        assert request.extensions["timeout"]["read"] == 2.5
        assert payload["model"] == MODEL
        assert payload["provider"] == {"allow_fallbacks": False, "require_parameters": True}
        assert payload["max_tokens"] == 2048 and payload["temperature"] == 0
        assert payload.get("session_id") is None and payload.get("trace") is None
        assert "parallel_tool_calls" not in payload
        assert {item["function"]["name"] for item in payload["tools"]} == {
            "search_documents", "read_document", "create_document",
        }
        assert all(item["function"]["parameters"]["additionalProperties"] is False for item in payload["tools"])
        if len(seen) == 1:
            return httpx.Response(200, json=completion(calls=[{
                "id": "call_read", "type": "function", "function": {
                    "name": "read_document",
                    "arguments": '{"path":"notes.txt","start_line":1,"max_lines":10}',
                },
            }]))
        result = payload["messages"][-1]
        assert result["role"] == "tool" and result["tool_call_id"] == "call_read"
        assert json.loads(result["content"])["data"]["text"] == "fictional document marker"
        return httpx.Response(200, json=completion("Read the note [R1]."))

    async def scenario():
        provider = create_provider(configured(roots), transport=httpx.MockTransport(handle))
        context = ToolContext()
        tools = build_tools(roots, context)
        try:
            bound = provider.model.bind_tools(tools, tool_choice="auto")
            first = await bound.ainvoke([HumanMessage("Read notes.txt")], retries=None, timeout_ms=2500)
            result = tools[1].invoke(first.tool_calls[0])
            assert isinstance(result, ToolMessage) and result.status == "success"
            final = await bound.ainvoke(
                [HumanMessage("Read notes.txt"), first, result], retries=None, timeout_ms=2500,
            )
            assert final.content == "Read the note [R1]."
        finally:
            await provider.aclose()
        assert provider.sync_client.is_closed and provider.async_client.is_closed

    asyncio.run(scenario())
    assert len(seen) == 2
    assert "fictional document marker" not in caplog.text
    assert "offline-test-key" not in caplog.text


@pytest.mark.parametrize("status,code", [
    (401, "AUTHENTICATION_ERROR"), (402, "QUOTA_ERROR"), (429, "RATE_LIMIT"),
    (500, "PROVIDER_UNAVAILABLE"), (400, "PROVIDER_REJECTED"),
])
def test_sdk_http_errors_are_single_attempt_and_sanitized(roots, status, code, caplog):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "private diagnostic body", "code": status}})

    async def scenario():
        provider = create_provider(configured(roots), transport=httpx.MockTransport(handle))
        try:
            with pytest.raises(Exception) as caught:
                await provider.model.bind_tools(build_tools(roots)).ainvoke(
                    [HumanMessage("hello")], retries=None, timeout_ms=2500,
                )
            failure = provider_failure(caught.value)
            assert failure.code == code
            assert "private" not in failure.message
        finally:
            await provider.aclose()

    asyncio.run(scenario())
    assert len(requests) == 1
    assert "private diagnostic body" not in caplog.text


def test_provider_readiness_before_construction(roots):
    with pytest.raises(ConfigurationError, match="API_KEY"):
        create_provider(Configuration(input_dir=roots.input, output_dir=roots.output))


def test_full_agent_wiring_through_real_sdk_mock_transport(roots):
    from local_document_agent.agent import DocumentAssistant
    (roots.input / "notes.txt").write_text("Tuesday review.")
    requests = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            name = "read_document"
            args = {"path": "notes.txt", "start_line": 1, "max_lines": 20}
        elif len(requests) == 2:
            read = json.loads(payload["messages"][-1]["content"])
            assert read["data"]["source_id"] == "R1"
            name = "create_document"
            args = {"filename": "sdk-report.md", "kind": "report", "content": "Tuesday review.", "source_ids": ["R1"]}
        else:
            created = json.loads(payload["messages"][-1]["content"])
            assert created["ok"] and created["data"]["path"] == "sdk-report.md"
            return httpx.Response(200, json=completion("Saved the report [R1]."))
        return httpx.Response(200, json=completion(calls=[{
            "id": f"call_{len(requests)}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }]))

    async def scenario():
        configuration = configured(roots)
        provider = create_provider(configuration, transport=httpx.MockTransport(handle))
        try:
            result = await DocumentAssistant(configuration, provider.model, roots=roots).chat("Save a report from the note.")
            assert result.status == "completed"
            assert result.created_files[0].path == "sdk-report.md"
            assert result.sources[0].source_id == "R1"
        finally:
            await provider.aclose()
    asyncio.run(scenario())
    assert len(requests) == 3
    assert (roots.output / "sdk-report.md").exists()


def test_sdk_timeout_and_malformed_success_are_safe_single_attempts(roots):
    for mode in ("timeout", "malformed"):
        count = []
        def handle(request):
            count.append(request)
            if mode == "timeout":
                raise httpx.ReadTimeout("private timeout diagnostic", request=request)
            body = completion("fictional private response")
            del body["system_fingerprint"]  # Required by the pinned SDK's response model.
            return httpx.Response(200, json=body)

        async def scenario():
            provider = create_provider(configured(roots), transport=httpx.MockTransport(handle))
            try:
                with pytest.raises(Exception) as caught:
                    await provider.model.ainvoke([HumanMessage("hello")], retries=None, timeout_ms=1000)
                failure = provider_failure(caught.value)
                assert failure.code == ("REQUEST_TIMEOUT" if mode == "timeout" else "PROVIDER_PROTOCOL_ERROR")
                assert "private" not in failure.message
            finally:
                await provider.aclose()
        asyncio.run(scenario())
        assert len(count) == 1
