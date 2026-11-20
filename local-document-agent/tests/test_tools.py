import hashlib
import json
import time

import pytest
from langchain_core.messages import ToolMessage

from local_document_agent.contracts import CreateData, ReadData, SearchData, ToolResult


def call(kit, name, **arguments):
    return json.loads(kit[0][name].invoke(arguments))


def test_deterministic_search_pagination_and_no_read_sources(roots, kit):
    (roots.input / "Beta.txt").write_text("Review beta\n", encoding="utf-8")
    (roots.input / "alpha.md").write_text("Review alpha\n", encoding="utf-8")
    (roots.input / "review-bad.txt").write_bytes(b"\xff")
    (roots.input / "ignored.pdf").write_text("Review")
    arguments = {"query": "REVIEW", "scope": "both", "offset": 0, "limit": 1}
    first = call(kit, "search_documents", **arguments)
    assert first == call(kit, "search_documents", **arguments)
    assert first["data"]["results"][0]["path"] == "alpha.md"
    assert first["data"]["has_more"]
    assert first["data"]["partial"]
    assert first["data"]["issues"][0]["code"] == "DECODE_ERROR"
    assert first["data"]["results"][0]["snippet"] == "Review alpha"
    second = call(kit, "search_documents", **(arguments | {"offset": 1, "limit": 20}))
    assert [row["path"] for row in second["data"]["results"]] == ["Beta.txt", "review-bad.txt"]
    assert second["data"]["results"][1]["snippet"] is None
    assert not kit[1].ledger.snapshot()
    ToolResult[SearchData].model_validate_json(json.dumps(first))
    literal = call(kit, "search_documents", query=".*", scope="text", offset=0, limit=20)
    assert literal["data"]["results"] == []


def test_filename_search_does_not_read_payloads(roots, kit, monkeypatch):
    (roots.input / "notes.txt").write_bytes(b"\xff")

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Filename search must not open file bodies")

    monkeypatch.setattr(type(roots), "read_bytes", forbidden_read)
    result = call(kit, "search_documents", query="notes", scope="filename", offset=0, limit=20)
    assert result["data"]["results"][0]["snippet"] is None
    assert result["data"]["inspected_file_count"] == 0


def test_search_partial_budget_snippet_and_timeout(roots, kit, monkeypatch):
    import local_document_agent.tools as module

    (roots.input / "a.txt").write_text("x" * 180, encoding="utf-8")
    (roots.input / "b.txt").write_text("x" * 180, encoding="utf-8")
    monkeypatch.setattr(module, "SEARCH_BYTE_LIMIT", 200)
    result = call(kit, "search_documents", query="x", scope="text", offset=0, limit=20)
    assert result["data"]["partial"]
    assert result["data"]["skipped_count"] == 1
    assert len(result["data"]["results"][0]["snippet"]) == 160
    assert result["data"]["results"][0]["snippet_truncated"]
    kit[1].deadline = time.monotonic() - 1
    result = call(kit, "search_documents", query="x", scope="text", offset=0, limit=20)
    assert result["error"]["code"] == "LIMIT_EXCEEDED"


def test_actual_bounded_read_hash_ranges_sources_and_version_warning(roots, kit):
    raw = b"\xef\xbb\xbfalpha\r\nbeta\r\ngamma\r\n"
    path = roots.input / "notes.md"
    path.write_bytes(raw)
    first = call(kit, "read_document", path="notes.md", start_line=1, max_lines=2)
    data = first["data"]
    assert data["text"] == "alpha\nbeta"
    assert data["sha256"] == hashlib.sha256(raw).hexdigest()
    assert data["source_id"] == "R1"
    assert data["has_more"] and data["next_start_line"] == 3
    assert not data["complete_document"]
    assert kit[1].ledger.snapshot()[0].reference() == '[R1] input/"notes.md", lines 1–2'
    ToolResult[ReadData].model_validate_json(json.dumps(first))
    second = call(kit, "read_document", path="notes.md", start_line=3, max_lines=2)
    assert second["data"]["text"] == "gamma"
    assert not second["data"]["has_more"]
    path.write_text("updated", encoding="utf-8")
    changed = call(kit, "read_document", path="notes.md", start_line=1, max_lines=2)
    assert changed["warnings"]
    assert changed["data"]["source_id"] == "R3"
    assert changed["data"]["complete_document"]


def test_read_failures_empty_file_and_ledger_are_truthful(roots, kit):
    (roots.input / "long.txt").write_text("x" * 12001)
    for path, start, code in [
        ("missing.txt", 1, "NOT_FOUND"), ("long.txt", 1, "RANGE_TOO_LARGE"),
        ("long.txt", 2, "INVALID_RANGE"),
    ]:
        result = call(kit, "read_document", path=path, start_line=start, max_lines=2)
        assert not result["ok"] and result["data"] is None
        assert result["error"]["code"] == code
    assert not kit[1].ledger.snapshot()
    (roots.input / "empty.txt").touch()
    result = call(kit, "read_document", path="empty.txt", start_line=1, max_lines=2)
    assert result["data"]["end_line"] == 0
    assert result["data"]["text"] == ""
    assert result["data"]["complete_document"]


def test_reports_drafts_real_bytes_sources_and_preserved_original(roots, kit):
    original = b"Tuesday review.\r\n"
    (roots.input / "notes.txt").write_bytes(original)
    read = call(kit, "read_document", path="notes.txt", start_line=1, max_lines=10)
    source = read["data"]["source_id"]
    report = call(
        kit, "create_document", filename="report.md", kind="report",
        content="# Review\r\nTuesday.", source_ids=[source],
    )
    ToolResult[CreateData].model_validate_json(json.dumps(report))
    report_bytes = (roots.output / "report.md").read_bytes()
    assert b"\r" not in report_bytes and not report_bytes.startswith(b"\xef\xbb\xbf")
    assert b"Source files read" in report_bytes
    assert '[R1] input/"notes.txt", lines 1–1' in report_bytes.decode()
    assert report["data"]["sha256"] == hashlib.sha256(report_bytes).hexdigest()
    assert report["data"]["bytes_written"] == len(report_bytes)
    draft = call(
        kit, "create_document", filename="reply.md", kind="email_draft",
        content="To: sender@example.invalid\nSubject: Re: Review\n\nTuesday works.", source_ids=[source],
    )
    assert draft["data"]["not_sent"] is True
    assert (roots.output / "reply.md").read_text(encoding="utf-8").startswith("EMAIL DRAFT — NOT SENT\n")
    collision = call(
        kit, "create_document", filename="report.md", kind="report",
        content="overwrite", source_ids=[],
    )
    assert collision["error"]["code"] == "FILE_EXISTS"
    assert (roots.output / "report.md").read_bytes() == report_bytes
    assert (roots.input / "notes.txt").read_bytes() == original
    assert len(kit[1].created) == 2
    assert len(kit[1].reads) == 1


@pytest.mark.parametrize("filename", ["../x.md", "x.MD", "x/y.md", "CON.txt", " x.md", "x.md "])
def test_output_names_not_silently_rewritten(roots, kit, filename):
    result = call(
        kit, "create_document", filename=filename, kind="report",
        content="ordinary", source_ids=[],
    )
    assert result["error"]["code"] == "INVALID_PATH"
    assert not list(roots.output.iterdir())
    assert not kit[1].created


def test_unknown_evicted_sources_and_oversized_output_prevent_writes(roots, kit):
    result = call(
        kit, "create_document", filename="x.md", kind="report", content="text", source_ids=["R1"]
    )
    assert result["error"]["code"] == "UNKNOWN_SOURCE"
    result = call(
        kit, "create_document", filename="x.md", kind="report", content="😀" * 20000, source_ids=[]
    )
    assert result["error"]["code"] == "FILE_TOO_LARGE"
    assert not list(roots.output.iterdir())
    (roots.input / "x.txt").write_text("ordinary")
    call(kit, "read_document", path="x.txt", start_line=1, max_lines=1)
    kit[1].ledger.discard(["R1"])
    result = call(
        kit, "create_document", filename="x.md", kind="report", content="text", source_ids=["R1"]
    )
    assert result["error"]["code"] == "UNKNOWN_SOURCE"


def test_langchain_tool_message_id_status_and_async_no_model(kit, roots):
    (roots.input / "x.txt").write_text("ordinary")
    tool = kit[0]["read_document"]
    result = tool.invoke({
        "name": "read_document", "args": {"path": "x.txt", "start_line": 1, "max_lines": 1},
        "id": "call_1", "type": "tool_call",
    })
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "call_1" and result.status == "success"
    pending = tool.ainvoke({
        "name": "read_document", "args": {"path": "x.txt", "start_line": "1", "max_lines": 1},
        "id": "call_2", "type": "tool_call",
    })
    # The bounded async wrapper deliberately executes synchronously without
    # suspension. Drive that one coroutine directly, avoiding Windows'
    # network-backed asyncio self-pipe and keeping every socket blocked.
    with pytest.raises(StopIteration) as stopped:
        pending.send(None)
    bad = stopped.value.value
    assert bad.tool_call_id == "call_2" and bad.status == "error"
    assert len(kit[1].reads) == 1


def test_email_read_reference_is_extracted_not_raw_mime(roots, kit):
    (roots.input / "mail.eml").write_bytes(
        b"From: sender@example.invalid\r\nSubject: Review\r\nContent-Type: text/plain\r\n\r\nTuesday.\r\n"
    )
    result = call(kit, "read_document", path="mail.eml", start_line=1, max_lines=20)
    assert result["data"]["representation"] == "extracted_email"
    assert result["data"]["text"].endswith("Tuesday.")
    assert "extracted email lines" in kit[1].ledger.snapshot()[0].reference()


@pytest.mark.parametrize("filename,raw", [
    ("notes.txt", b"Tuesday review.\r\n"),
    ("notes.md", b"# Tuesday review\r\n"),
    ("notes.eml", b"Subject: Review\r\nContent-Type: text/plain\r\n\r\nTuesday review.\r\n"),
])
def test_direct_real_search_read_create_sequence(roots, kit, filename, raw):
    (roots.input / filename).write_bytes(raw)
    found = call(kit, "search_documents", query="Tuesday", scope="text", offset=0, limit=5)
    assert found["data"]["results"][0]["path"] == filename
    assert not kit[1].ledger.snapshot()
    read = call(kit, "read_document", path=filename, start_line=1, max_lines=20)
    assert read["ok"] and "Tuesday" in read["data"]["text"]
    created = call(
        kit, "create_document", filename="review.md", kind="report",
        content="# Review\nTuesday review.", source_ids=[read["data"]["source_id"]],
    )
    assert created["ok"]
    assert filename in (roots.output / "review.md").read_text(encoding="utf-8")
    assert (roots.input / filename).read_bytes() == raw


def test_search_deadline_and_permission_errors_are_tool_feedback(roots, kit, monkeypatch):
    import local_document_agent.filesystem as filesystem

    with monkeypatch.context() as patch:
        ticks = iter((0.0, 6.0))
        patch.setattr(filesystem.time, "monotonic", lambda: next(ticks))
        result = call(kit, "search_documents", query="text", scope="text", offset=0, limit=2)
        assert result["error"]["code"] == "SEARCH_TIMEOUT"
    (roots.input / "a.txt").write_text("ordinary")
    original_open = filesystem.Path.open

    def denied(path, mode="r", *args, **kwargs):
        if path == roots.input / "a.txt" and mode == "rb":
            raise PermissionError("do not expose this diagnostic")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(filesystem.Path, "open", denied)
    result = call(kit, "read_document", path="a.txt", start_line=1, max_lines=1)
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert "diagnostic" not in json.dumps(result)
    assert not kit[1].ledger.snapshot()


def test_failed_write_never_registers_created_file(roots, kit, monkeypatch):
    import os

    def fail(fd):
        raise OSError("simulated flush failure")

    monkeypatch.setattr(os, "fsync", fail)
    result = call(
        kit, "create_document", filename="partial.md", kind="report", content="ordinary", source_ids=[]
    )
    assert not result["ok"] and result["data"] is None
    assert result["error"]["code"] == "WRITE_FAILED"
    assert "partial" in result["error"]["message"]
    assert not kit[1].created


def test_ledger_capacity_and_discard_do_not_reuse_ids(roots, kit):
    kit[1].ledger.capacity = 1
    (roots.input / "a.txt").write_text("ordinary")
    first = call(kit, "read_document", path="a.txt", start_line=1, max_lines=1)
    full = call(kit, "read_document", path="a.txt", start_line=1, max_lines=1)
    assert full["error"]["code"] == "LIMIT_EXCEEDED"
    kit[1].ledger.discard([first["data"]["source_id"]])
    next_read = call(kit, "read_document", path="a.txt", start_line=1, max_lines=1)
    assert next_read["data"]["source_id"] == "R2"
