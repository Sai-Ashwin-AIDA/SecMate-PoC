import asyncio
import json

import pytest
from langchain.messages import AIMessage, ToolMessage

from local_document_agent.agent import DocumentAssistant
from local_document_agent.config import Configuration


class ScriptedModel:
    """Explicit offline fake; never installed as a production CLI provider."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.options = []

    def bind_tools(self, tools, **options):
        assert [tool.name for tool in tools] == ["search_documents", "read_document", "create_document"]
        assert options == {"tool_choice": "auto"}
        return self

    async def ainvoke(self, messages, **kwargs):
        self.requests.append(list(messages))
        self.options.append(kwargs)
        assert self.responses, "Unexpected model call"
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return await response()
        return response


def tool_call(name, arguments, identifier="call_1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": identifier}])


def reader(identifier="call_1", path="notes.txt"):
    return tool_call("read_document", {"path": path, "start_line": 1, "max_lines": 20}, identifier)


def writer(identifier="call_2", source_ids=None, filename="report.md", kind="report"):
    return tool_call("create_document", {
        "filename": filename, "kind": kind, "content": "# Report\nTuesday review.",
        "source_ids": ["R1"] if source_ids is None else source_ids,
    }, identifier)


def assistant(roots, model, **options):
    return DocumentAssistant(
        Configuration(input_dir=roots.input, output_dir=roots.output, **options),
        model, roots=roots,
    )


@pytest.mark.parametrize("kind,filename", [("report", "report.md"), ("email_draft", "reply.md")])
def test_real_search_read_create_with_scripted_model(roots, kind, filename):
    (roots.input / "notes.txt").write_text("Tuesday review.", encoding="utf-8")
    model = ScriptedModel(
        tool_call("search_documents", {"query": "Tuesday", "scope": "text", "offset": 0, "limit": 5}, "search"),
        reader(), writer(kind=kind, filename=filename), AIMessage(content="Saved the requested file [R1]."),
    )
    core = assistant(roots, model)
    result = asyncio.run(core.chat("Find the review note and save a report or draft."))
    assert result.status == "completed"
    assert result.sources[0].source_id == "R1"
    assert result.created_files[0].path == filename
    body = (roots.output / filename).read_text(encoding="utf-8")
    assert "Source files read" in body
    assert body.startswith("EMAIL DRAFT — NOT SENT") == (kind == "email_draft")
    assert len(result.tool_events) == 3
    assert all(options["retries"] is None and 0 < options["timeout_ms"] <= 30000 for options in model.options)
    messages = model.requests[-1]
    tool_results = [item for item in messages if isinstance(item, ToolMessage)]
    assert [item.tool_call_id for item in tool_results] == ["search", "call_1", "call_2"]


def test_prose_is_not_provenance_and_invented_reference_flagged(roots):
    model = ScriptedModel(AIMessage(content="I read secret.txt and saved it [R99]."))
    result = asyncio.run(assistant(roots, model).chat("Summarize a file."))
    assert result.status == "completed"
    assert not result.sources and not result.created_files
    assert result.unverified_source_ids == ("R99",)
    assert not list(roots.output.iterdir())


def test_error_feedback_allows_explicit_correction_without_coercion(roots):
    (roots.input / "notes.txt").write_text("ordinary")
    model = ScriptedModel(
        tool_call("read_document", {"path": "notes.txt", "start_line": "1", "max_lines": 20}),
        reader("call_2"), AIMessage(content="Read [R1]."),
    )
    result = asyncio.run(assistant(roots, model).chat("Read the note."))
    first_feedback = model.requests[1][-1]
    assert first_feedback.status == "error"
    assert json.loads(first_feedback.content)["error"]["code"] == "INVALID_ARGUMENTS"
    assert len(result.sources) == 1 and result.status == "completed"


def test_unknown_tool_gets_ordinary_correlated_error(roots):
    model = ScriptedModel(
        tool_call("shell", {"command": "do not run"}),
        AIMessage(content="That tool is unavailable."),
    )
    result = asyncio.run(assistant(roots, model).chat("Help me."))
    message = model.requests[-1][-1]
    assert message.tool_call_id == "call_1" and message.status == "error"
    assert json.loads(message.content)["error"]["code"] == "UNKNOWN_TOOL"
    assert result.status == "completed"


@pytest.mark.parametrize("response", [
    AIMessage(content="", invalid_tool_calls=[{"name": "read_document", "args": "{", "id": "bad", "error": "invalid"}]),
    AIMessage(content="", tool_calls=[
        {"name": "read_document", "args": {}, "id": "same"},
        {"name": "create_document", "args": {}, "id": "same"},
    ]),
    AIMessage(content="", tool_calls=[{"name": "read_document", "args": {}, "id": None}]),
    AIMessage(content="", tool_calls=[{"name": "create_document", "args": {}, "id": "x"}],
              response_metadata={"finish_reason": "length"}),
])
def test_malformed_or_truncated_batch_has_no_filesystem_effect(roots, response):
    result = asyncio.run(assistant(roots, ScriptedModel(response)).chat("Do a task."))
    assert result.status in ("failed", "limited")
    assert not result.created_files and not result.sources and not result.tool_events


def test_repeated_failed_call_stops_without_semantic_retry_loop(roots):
    model = ScriptedModel(reader("first"), reader("second"))
    result = asyncio.run(assistant(roots, model).chat("Read missing note."))
    assert result.error.code == "REPEATED_FAILURE"
    assert len(model.requests) == 2 and len(result.tool_events) == 1


def test_provider_failure_preserves_write_observation_but_discards_failed_history(roots):
    (roots.input / "notes.txt").write_text("Tuesday review.")
    model = ScriptedModel(reader(), writer(), RuntimeError("private provider diagnostic"), AIMessage(content="Hello."))
    core = assistant(roots, model)

    async def scenario():
        failed = await core.chat("Save a report.")
        assert failed.status == "failed"
        assert failed.created_files[0].path == "report.md" and (roots.output / "report.md").exists()
        assert failed.sources[0].source_id == "R1"
        assert not core.ledger.snapshot() and not core._history
        assert "private" not in failed.error.message
        await core.chat("Hello.")
        assert len(model.requests[-1]) == 2
    asyncio.run(scenario())


def test_uncertain_write_reported_without_fake_success(roots, monkeypatch):
    import os
    def fail(fd):
        raise PermissionError("private")
    monkeypatch.setattr(os, "fsync", fail)
    model = ScriptedModel(writer(source_ids=[]), AIMessage(content="The file could not be saved reliably."))
    result = asyncio.run(assistant(roots, model).chat("Save a report."))
    assert result.uncertain_outputs == ("report.md",)
    assert not result.created_files
    assert model.requests[-1][-1].status == "error"


def test_retained_sources_evict_by_whole_turn_and_ids_remain_monotonic(roots):
    (roots.input / "notes.txt").write_text("Tuesday review.")
    model = ScriptedModel(
        reader(), AIMessage(content="Read [R1]."),
        writer(), AIMessage(content="Report saved [R1]."),
        reader("again"), AIMessage(content="Read [R2]."),
    )
    core = assistant(roots, model, max_history_turns=1)

    async def scenario():
        await core.chat("Read the note.")
        assert core.ledger.snapshot()[0].source_id == "R1"
        report = await core.chat("Save it as report.md.")
        assert not report.unverified_source_ids
        assert report.retained_sources[0].source_id == "R1"
        assert not core.ledger.snapshot()  # The owning read turn was evicted.
        third = await core.chat("Read it again.")
        assert third.sources[0].source_id == "R2"
        assert len(core._history) == 1 and len(core.ledger.snapshot()) == 1
        session = core.session_id
        core.new_session()
        assert core.session_id != session and not core._history and not core.ledger.snapshot()
        assert (roots.output / "report.md").exists()
    asyncio.run(scenario())


def test_many_turns_do_not_accumulate_pages_or_ledger_entries(roots):
    (roots.input / "notes.txt").write_text("ordinary")
    responses = []
    for index in range(40):
        responses.extend([reader(), AIMessage(content=f"Read [R{index + 1}].")])
    core = assistant(roots, ScriptedModel(*responses), max_history_turns=1)

    async def scenario():
        for index in range(40):
            result = await core.chat("Read note.")
            assert result.status == "completed"
            assert len(core._history) == 1
            assert len(core.ledger.snapshot()) == 1
            assert core.ledger.snapshot()[0].source_id == f"R{index + 1}"
    asyncio.run(scenario())


@pytest.mark.parametrize("limit,expected", [
    ({"max_model_calls_per_turn": 1}, "MODEL_LIMIT"),
    ({"max_turn_token_budget": 8192}, "TOKEN_LIMIT"),
])
def test_model_and_cumulative_token_limits_make_no_extra_calls(roots, limit, expected):
    (roots.input / "notes.txt").write_text("ordinary")
    model = ScriptedModel(reader())
    result = asyncio.run(assistant(roots, model, **limit).chat("Read note."))
    assert result.error.code == expected
    assert len(model.requests) == 1


def test_tool_batch_limit_rejects_before_side_effect(roots):
    response = AIMessage(content="", tool_calls=writer(source_ids=[]).tool_calls + reader("other").tool_calls)
    result = asyncio.run(assistant(roots, ScriptedModel(response), max_tool_calls_per_turn=1).chat("Do task."))
    assert result.error.code == "TOOL_LIMIT" and not result.tool_events
    assert not list(roots.output.iterdir())


def test_active_context_limit_preserves_observed_read_but_drops_failed_turn(roots):
    (roots.input / "notes.txt").write_text("x" * 12000)
    core = assistant(roots, ScriptedModel(reader()), context_budget_units=8192, max_output_tokens=256)
    result = asyncio.run(core.chat("Read note."))
    assert result.error.code == "CONTEXT_LIMIT" and len(result.sources) == 1
    assert not core._history and not core.ledger.snapshot()


def test_old_history_is_pruned_to_fit_context(roots):
    model = ScriptedModel(AIMessage(content="a" * 13000), AIMessage(content="Okay."))
    core = assistant(roots, model, context_budget_units=20000, max_output_tokens=256)

    async def scenario():
        first = await core.chat("Hello.")
        assert first.status == "completed"
        second = await core.chat("b" * 4000)
        assert second.status == "completed"
        assert len(model.requests[-1]) == 2
    asyncio.run(scenario())


def test_request_deadline_and_cancellation(roots):
    async def slow():
        await asyncio.sleep(60)
        return AIMessage(content="Too late")

    core = assistant(roots, ScriptedModel(slow), request_timeout_seconds=5, turn_timeout_seconds=15)
    timed = asyncio.run(core.chat("Hello."))
    assert timed.error.code == "REQUEST_TIMEOUT" and not core._history

    async def scenario():
        started = asyncio.Event()
        async def waiting():
            started.set()
            await asyncio.Event().wait()
        model = ScriptedModel(waiting)
        core = assistant(roots, model)
        task = asyncio.create_task(core.chat("Hello."))
        await started.wait()
        busy = await core.chat("Concurrent turn.")
        assert busy.error.code == "BUSY"
        with pytest.raises(RuntimeError):
            core.new_session()
        task.cancel()
        cancelled = await task
        assert cancelled.status == "cancelled" and not core._history
        core.new_session()
    asyncio.run(scenario())


def test_outer_turn_deadline_and_cancel_after_successful_write(roots, monkeypatch):
    original_timeout = asyncio.timeout
    # Accelerate only the test's outer timer, without weakening Configuration.
    monkeypatch.setattr(
        asyncio, "timeout",
        lambda seconds: original_timeout(0.02 if seconds == 15 else seconds),
    )
    async def waiting():
        await asyncio.sleep(60)
    core = assistant(roots, ScriptedModel(waiting), request_timeout_seconds=5, turn_timeout_seconds=15)
    result = asyncio.run(core.chat("Hello."))
    assert result.error.code == "TURN_TIMEOUT" and not core._history
    monkeypatch.setattr(asyncio, "timeout", original_timeout)

    async def scenario():
        ready = asyncio.Event()
        async def pause_after_write():
            ready.set()
            await asyncio.Event().wait()
        core = assistant(roots, ScriptedModel(writer(source_ids=[]), pause_after_write))
        task = asyncio.create_task(core.chat("Save a report."))
        await ready.wait()
        task.cancel()
        cancelled = await task
        assert cancelled.status == "cancelled"
        assert cancelled.created_files[0].path == "report.md"
        assert (roots.output / "report.md").exists() and not core._history
    asyncio.run(scenario())
