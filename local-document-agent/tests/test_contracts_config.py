import json
import os
import socket
import subprocess
import sys
import pytest
from pydantic import ValidationError

from local_document_agent.config import ConfigurationError, load_configuration
from local_document_agent.contracts import ReadData, ToolResult


def test_explicit_local_env_no_parent_search_or_interpolation(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=parent-secret\nMAX_HISTORY_TURNS=99\n")
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.chdir(tmp_path)
    config = load_configuration(app, environment={})
    assert config.api_key.get_secret_value() == ""
    assert config.max_history_turns == 4
    assert config.input_dir == app / "data" / "input"
    with pytest.raises(ConfigurationError, match="API_KEY"):
        config.require_inference_ready()
    (app / ".env").write_text("OPENROUTER_API_KEY=${PARENT_SECRET}\nMAX_HISTORY_TURNS=2\n")
    config = load_configuration(app, environment={"MAX_HISTORY_TURNS": "3"})
    assert config.max_history_turns == 3
    assert config.api_key.get_secret_value() == "${PARENT_SECRET}"
    assert "${PARENT_SECRET}" not in repr(config)
    assert "api_key" not in config.model_dump()
    with pytest.raises(ConfigurationError, match="consent"):
        config.require_inference_ready()


@pytest.mark.parametrize("environment", [
    {"MAX_OUTPUT_TOKENS": "255"}, {"MAX_HISTORY_TURNS": "9"},
    {"MAX_HISTORY_TURNS": "2.0"}, {"MAX_HISTORY_TURNS": "true"},
    {"MAX_HISTORY_TURNS": " 2"}, {"ALLOW_OPENROUTER_DOCUMENT_TRANSMISSION": "yes"},
    {"OPENROUTER_MODEL": "another/model"}, {"OPENROUTER_BASE_URL": "https://example.org"},
    {"LANGSMITH_TRACING": "true"}, {"REQUEST_TIMEOUT_SECONDS": "60", "TURN_TIMEOUT_SECONDS": "15"},
])
def test_configuration_rejects_invalid_values(tmp_path, environment):
    with pytest.raises(ConfigurationError):
        load_configuration(tmp_path, environment=environment)


def test_result_contract_rejects_false_success():
    with pytest.raises(ValidationError):
        ToolResult[ReadData](ok=True, tool="read_document", data=None, warnings=[], error=None)


def test_installed_cli_points_to_real_callable():
    from importlib.metadata import distribution

    package = distribution("local-document-agent")
    entries = [entry for entry in package.entry_points if entry.group == "console_scripts"]
    assert len(entries) == 1 and entries[0].name == "local-document-agent"
    assert callable(entries[0].load())


def test_tools_import_without_env_key_consent_or_provider(tmp_path):
    # Fresh process proves import isolation; no model module is imported.
    script = """
import os, socket, sys
def denied(*a, **kw): raise AssertionError("network")
socket.socket.connect = denied
socket.create_connection = denied
socket.getaddrinfo = denied
from local_document_agent.tools import build_tools
assert "langchain_openrouter" not in sys.modules
assert not os.environ.get("OPENROUTER_API_KEY")
assert os.environ.get("ALLOW_OPENROUTER_DOCUMENT_TRANSMISSION") is None
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=dict(os.environ),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_network_guard_is_active():
    with pytest.raises(AssertionError, match="Network"):
        socket.create_connection(("example.org", 443))


def test_exactly_three_provider_compatible_strict_schemas(kit):
    tools, _ = kit
    assert list(tools) == ["search_documents", "read_document", "create_document"]
    expected = {
        "search_documents": {"query", "scope", "offset", "limit"},
        "read_document": {"path", "start_line", "max_lines"},
        "create_document": {"filename", "kind", "content", "source_ids"},
    }
    from langchain_core.utils.function_calling import convert_to_openai_tool

    for name, tool in tools.items():
        schema = convert_to_openai_tool(tool)["function"]["parameters"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == expected[name]
        assert set(schema["properties"]) == expected[name]
        assert "$defs" not in schema
        assert all("description" in prop for prop in schema["properties"].values())


@pytest.mark.parametrize("name,arguments", [
    ("search_documents", {"query": "a", "scope": "text", "offset": "0", "limit": 2}),
    ("search_documents", {"query": " ", "scope": "text", "offset": 0, "limit": 2}),
    ("search_documents", {"query": "a", "scope": "text", "offset": 0, "limit": True}),
    ("read_document", {"path": "a.txt", "start_line": 1, "max_lines": 2, "extra": 1}),
    ("read_document", {"path": "a.txt", "start_line": False, "max_lines": 2}),
    ("create_document", {"filename": "x.md", "kind": "report", "content": "private", "source_ids": ()}),
    ("create_document", {"filename": "x.md", "kind": "report", "content": "private", "source_ids": ["R1", "R1"]}),
    ("create_document", {"filename": "x.md", "kind": "report", "content": "private", "source_ids": [], "overwrite": True}),
])
def test_strict_arguments_are_sanitized_and_have_no_side_effects(kit, roots, name, arguments, caplog):
    tools, context = kit
    result = json.loads(tools[name].invoke(arguments))
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert "private" not in json.dumps(result)
    assert "private" not in caplog.text
    assert not context.ledger.snapshot()
    assert not context.created
    assert not list(roots.output.iterdir())


def test_rejects_prose_arguments(kit):
    tools, _ = kit
    assert json.loads(tools["read_document"].invoke("I read a.txt"))["ok"] is False
