"""Focused regressions for the independent Slice 1 audit, A1–A4."""

import json
import os
from pathlib import Path

import pytest

from local_document_agent.config import ConfigurationError
from local_document_agent.contracts import DocumentError
from local_document_agent.text import extract


@pytest.mark.parametrize("headers", [
    b"Content-Type: text/plain\r\nContent-Type: text/html\r\n",
    b"Content-Type: text/plain\r\nContent-Transfer-Encoding: 7bit\r\nContent-Transfer-Encoding: base64\r\n",
    b"Content-Type: text/plain\r\nContent-Disposition: inline\r\nContent-Disposition: attachment\r\n",
])
@pytest.mark.parametrize("nested", [False, True])
def test_ambiguous_mime_rejected_by_extractor_and_tools(roots, kit, headers, nested):
    raw = headers + b"\r\n<p>hidden-html-marker</p>"
    if nested:
        raw = (
            b"Content-Type: multipart/mixed; boundary=part\r\n\r\n--part\r\n"
            + raw + b"\r\n--part--\r\n"
        )
    with pytest.raises(DocumentError) as caught:
        extract(raw, ".eml")
    assert caught.value.error.code == "MALFORMED_EMAIL"
    (roots.input / "ambiguous.eml").write_bytes(raw)
    read = json.loads(kit[0]["read_document"].invoke({
        "path": "ambiguous.eml", "start_line": 1, "max_lines": 20,
    }))
    assert read["error"]["code"] == "MALFORMED_EMAIL"
    assert not kit[1].reads and not kit[1].ledger.snapshot()
    search = json.loads(kit[0]["search_documents"].invoke({
        "query": "hidden-html-marker", "scope": "text", "offset": 0, "limit": 10,
    }))
    assert search["data"]["results"] == []
    assert search["data"]["issues"][0]["code"] == "MALFORMED_EMAIL"


def test_unknown_encoded_header_charset_rejected():
    with pytest.raises(DocumentError) as caught:
        extract(b"Subject: =?not-a-codec?b?YWJj?=\r\n\r\nordinary body", ".eml")
    assert caught.value.error.code == "MALFORMED_EMAIL"
    assert "abc" not in str(caught.value)


@pytest.mark.parametrize("stage", ["deadline", "permission", "close", "verify"])
def test_post_creation_failures_report_uncertainty(roots, kit, monkeypatch, stage):
    filename = "uncertain.md"
    target = roots.output / filename
    if stage == "deadline":
        def check():
            if target.exists():
                raise DocumentError("LIMIT_EXCEEDED", "The operation deadline has expired.")
        monkeypatch.setattr(kit[1], "check_deadline", check)
    elif stage == "permission":
        def fail(fd):
            raise PermissionError("private diagnostic")
        monkeypatch.setattr(os, "fsync", fail)
    elif stage == "verify":
        import local_document_agent.filesystem as filesystem
        def fail(*args):
            raise DocumentError("OUTSIDE_ROOT", "Opened location verification failed.")
        monkeypatch.setattr(filesystem, "verify_handle", fail)
    else:
        original = Path.open
        class CloseFailure:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self.stream
            def __exit__(self, *args):
                self.stream.close()
                raise OSError("private close diagnostic")
        def opened(path, mode="r", *args, **kwargs):
            stream = original(path, mode, *args, **kwargs)
            return CloseFailure(stream) if path == target and mode == "xb" else stream
        monkeypatch.setattr(Path, "open", opened)
    result = json.loads(kit[0]["create_document"].invoke({
        "filename": filename, "kind": "report", "content": "ordinary", "source_ids": [],
    }))
    assert not result["ok"] and result["data"] is None
    assert filename in result["warnings"][0]
    assert filename in result["error"]["message"]
    assert str(roots.output) not in json.dumps(result)
    assert "private" not in json.dumps(result)
    assert target.exists()
    assert kit[1].uncertain_outputs == [filename]
    assert not kit[1].created


@pytest.mark.parametrize("stage", ["permission", "deadline"])
def test_pre_creation_failure_has_no_possible_file_notice(roots, kit, monkeypatch, stage):
    if stage == "permission":
        def denied(*args, **kwargs):
            raise PermissionError("private pre-open diagnostic")
        monkeypatch.setattr(Path, "open", denied)
    else:
        def denied():
            raise DocumentError("LIMIT_EXCEEDED", "The operation deadline has expired.")
        monkeypatch.setattr(kit[1], "check_deadline", denied)
    result = json.loads(kit[0]["create_document"].invoke({
        "filename": "absent.md", "kind": "report", "content": "ordinary", "source_ids": [],
    }))
    assert not result["ok"] and result["warnings"] == []
    assert not kit[1].uncertain_outputs and not kit[1].created
    assert not list(roots.output.iterdir())


def test_windows_case_alias_version_detection(roots, kit):
    if os.name != "nt":
        pytest.skip("Case-insensitive Windows alias regression.")
    path = roots.input / "notes.txt"
    path.write_text("old")
    read = kit[0]["read_document"]
    first = json.loads(read.invoke({"path": "notes.txt", "start_line": 1, "max_lines": 1}))
    same = json.loads(read.invoke({"path": "NOTES.TXT", "start_line": 1, "max_lines": 1}))
    assert not same["warnings"]
    path.write_text("new")
    changed = json.loads(read.invoke({"path": "NOTES.TXT", "start_line": 1, "max_lines": 1}))
    assert changed["warnings"]
    assert first["data"]["sha256"] != changed["data"]["sha256"]
    assert changed["data"]["path"] == "NOTES.TXT"


@pytest.mark.parametrize("method", ["invoke", "ainvoke", "run", "arun"])
def test_every_public_tool_execution_path_rejects_enabled_tracing(roots, kit, monkeypatch, method):
    (roots.input / "notes.txt").write_text("must remain unread")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    arguments = {"path": "notes.txt", "start_line": 1, "max_lines": 1}
    with pytest.raises(ConfigurationError, match="Tracing"):
        result = getattr(kit[0]["read_document"], method)(arguments)
        if method.startswith("a"):
            try:
                result.send(None)
            finally:
                result.close()
    assert not kit[1].reads and not kit[1].ledger.snapshot()
