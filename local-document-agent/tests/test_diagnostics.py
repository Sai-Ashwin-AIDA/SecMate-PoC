import asyncio
import json
from pathlib import Path

from langchain.messages import AIMessage

from local_document_agent.agent import DocumentAssistant
from local_document_agent.cli import main
from local_document_agent.config import Configuration
from local_document_agent.diagnostics import DiagnosticLog


def test_tool_and_provider_errors_are_logged_without_payloads(roots, tmp_path):
    class Model:
        calls = 0
        def bind_tools(self, tools, **kwargs):
            return self
        async def ainvoke(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content="", tool_calls=[{
                    "name": "read_document",
                    "args": {"path": "private-file-name.txt", "start_line": 1, "max_lines": 2},
                    "id": "call_1",
                }])
            raise RuntimeError("credential-marker private-document-marker provider-body-marker")

    log = DiagnosticLog(tmp_path)
    try:
        core = DocumentAssistant(
            Configuration(input_dir=roots.input, output_dir=roots.output), Model(),
            roots=roots, diagnostics=log,
        )
        result = asyncio.run(core.chat("private-user-prompt-marker"))
        assert result.status == "failed"
        records = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
        assert [record["code"] for record in records] == ["NOT_FOUND", "PROVIDER_ERROR"]
        assert records[0]["tool"] == "read_document"
        assert records[1]["exception_type"] == "RuntimeError"
        assert records[1]["frames"] and records[1]["session_id"] == core.session_id
        text = json.dumps(records)
        for value in (
            "credential-marker", "private-document-marker", "provider-body-marker",
            "private-user-prompt-marker", "private-file-name.txt", str(tmp_path),
        ):
            assert value not in text
    finally:
        log.close()


def test_startup_error_logged_without_loading_parent_env(tmp_path, capsys):
    parent_secret = "parent-key-never-loaded"
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=" + parent_secret)
    app = tmp_path / "app"
    app.mkdir()
    assert main(["--app-root", str(app)]) == 2
    records = [json.loads(line) for line in (app / ".logs" / "errors.log").read_text().splitlines()]
    assert records[-1]["phase"] == "startup"
    assert records[-1]["code"] == "CONFIGURATION_ERROR"
    assert parent_secret not in json.dumps(records) + capsys.readouterr().err


def test_logs_rotate_with_bounded_retention_and_safe_metadata(tmp_path):
    log = DiagnosticLog(tmp_path, max_bytes=500)
    for _ in range(50):
        log.record("turn", "REQUEST_TIMEOUT", session_id="a" * 32)
    log.close()
    files = list((tmp_path / ".logs").glob("errors.log*"))
    assert 1 < len(files) <= 4
    assert all(path.stat().st_size <= 500 for path in files)
    assert all(json.loads(line)["code"] == "REQUEST_TIMEOUT"
               for path in files for line in path.read_text().splitlines())


def test_log_io_failure_marks_degraded_state_without_exposing_exception(tmp_path, monkeypatch):
    log = DiagnosticLog(tmp_path)
    def fail(record):
        raise OSError("private storage diagnostic")
    monkeypatch.setattr(log._handler, "emit", fail)
    log.record("turn", "PROVIDER_ERROR")
    assert log.failed
    log.close()


def test_log_rejects_non_allowlisted_freeform_fields(tmp_path):
    log = DiagnosticLog(tmp_path)
    log.record("private-phase", "contains private text", tool="private-tool", session_id="private-id")
    record = json.loads(log.path.read_text().strip())
    assert record["phase"] == "unknown"
    assert record["code"] == "UNCLASSIFIED_ERROR" and record["tool"] == "unknown"
    assert "session_id" not in record
    log.close()
