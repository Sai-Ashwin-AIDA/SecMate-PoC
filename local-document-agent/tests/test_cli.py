import asyncio
import json
import subprocess
from pathlib import Path

from langchain.messages import AIMessage

from local_document_agent.agent import DocumentAssistant
from local_document_agent.cli import main, run_cli, safe_terminal
from local_document_agent.config import Configuration


class CLIMockModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, messages, **kwargs):
        self.messages.append(list(messages))
        return next(self.responses)


def call(name, args, identifier):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": identifier}])


def test_cli_mocked_task_shapes_activity_sources_paths_reset_and_exit(roots):
    (roots.input / "notes.txt").write_text("Tuesday review.")
    (roots.input / "mail.eml").write_bytes(b"Subject: Review\r\n\r\nTuesday review.")
    model = CLIMockModel([
        call("read_document", {"path": "notes.txt", "start_line": 1, "max_lines": 20}, "read_summary"),
        AIMessage(content="The review is on Tuesday [R1]."),
        call("read_document", {"path": "mail.eml", "start_line": 1, "max_lines": 20}, "read_email"),
        call("create_document", {
            "filename": "reply.md", "kind": "email_draft",
            "content": "Subject: Re: Review\n\nTuesday works.", "source_ids": ["R2"],
        }, "draft"),
        AIMessage(content="Saved an unsent draft [R2]."),
        call("create_document", {
            "filename": "report.md", "kind": "report", "content": "# Review\nTuesday.", "source_ids": ["R1", "R2"],
        }, "report"),
        AIMessage(content="Saved a report [R1] [R2]."),
        AIMessage(content="Fresh conversation."),
    ])
    core = DocumentAssistant(Configuration(input_dir=roots.input, output_dir=roots.output), model, roots=roots)
    commands = iter(["Summarize notes.", "Draft a reply.", "Save a report.", "/help", "/new", "Hello.", "/exit"])
    output = []
    result = asyncio.run(run_cli(core, read=lambda _: next(commands), write=output.append))
    text = "\n".join(output)
    assert result == 0
    assert "OpenRouter" in output[0]
    assert "[tool] read_document" in text and "[tool] create_document" in text
    assert "extracted email lines" in text
    assert str(roots.output / "reply.md") in text
    assert "Email draft — not sent" in text
    assert "New conversation" in text
    assert len(model.messages[-1]) == 2
    assert (roots.output / "reply.md").read_text(encoding="utf-8").startswith("EMAIL DRAFT — NOT SENT")
    assert (roots.output / "report.md").exists()


def test_cli_truthful_about_prose_only_saves_and_eof(roots):
    core = DocumentAssistant(
        Configuration(input_dir=roots.input, output_dir=roots.output),
        CLIMockModel([AIMessage(content="I saved a file [R77].")]), roots=roots,
    )
    messages = iter(["Save a file."])
    def read(_):
        try:
            return next(messages)
        except StopIteration:
            raise EOFError
    output = []
    assert asyncio.run(run_cli(core, read=read, write=output.append)) == 0
    assert "No file creation was observed." in output
    assert "[R77] is an unverified source reference." in output
    assert not list(roots.output.iterdir())


def test_startup_missing_key_and_consent_have_no_provider_construction(roots, tmp_path, monkeypatch, capsys):
    def forbidden(config):
        raise AssertionError("Provider must not be constructed")
    monkeypatch.setattr("local_document_agent.cli.create_provider", forbidden)
    assert main(["--app-root", str(tmp_path)]) == 2
    assert "API_KEY" in capsys.readouterr().err
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=offline-placeholder\n")
    assert main(["--app-root", str(tmp_path)]) == 2
    assert "consent" in capsys.readouterr().err


def test_startup_and_shutdown_use_explicit_mock_only(roots, tmp_path, monkeypatch):
    import local_document_agent.cli as cli
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=offline-placeholder\nALLOW_OPENROUTER_DOCUMENT_TRANSMISSION=true\n"
        "DOCUMENT_INPUT_DIR=./input\nDOCUMENT_OUTPUT_DIR=./output\n"
    )
    class Bundle:
        model = CLIMockModel([AIMessage(content="Mocked response.")])
        closed = False
        async def aclose(self):
            self.closed = True
    bundle = Bundle()
    monkeypatch.setattr(cli, "create_provider", lambda config: bundle)
    real_run_cli = cli.run_cli
    commands = iter(["Hello.", "/exit"])
    output = []
    async def scripted(core):
        return await real_run_cli(core, read=lambda _: next(commands), write=output.append)
    monkeypatch.setattr(cli, "run_cli", scripted)
    assert cli.main(["--app-root", str(tmp_path)]) == 0
    assert bundle.closed and "Mocked response." in output


def test_terminal_control_characters_are_escaped():
    assert safe_terminal("notes\x1b[31m.txt") == r"notes\x1b[31m.txt"
    assert safe_terminal("a\u202eb") == r"a\u202eb"


def test_installed_console_and_module_help_are_real_without_credentials():
    import sys
    import os
    paths = [
        [str(Path(sys.executable).parent / "local-document-agent.exe"), "--help"],
        [sys.executable, "-m", "local_document_agent", "--help"],
    ]
    for command in paths:
        result = subprocess.run(command, capture_output=True, text=True, env=dict(os.environ), timeout=60)
        assert result.returncode == 0
        assert "--app-root" in result.stdout
