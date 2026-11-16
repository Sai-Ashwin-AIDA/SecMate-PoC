import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_synthetic_guard import forbid_network  # autouse even without -p

from secmate_worker.synthetic_chatmate import Budget, Bundle, FaultPlan, Session, SyntheticChatMate, SyntheticError
from secmate_worker.synthetic_chatmate.artifacts import verify_source_inputs
from secmate_worker.synthetic_chatmate.contracts import MAPPER_BLOB, READ_TOOL, TARGET_ID, canonical, digest
from secmate_worker.synthetic_chatmate.evidence import observed_read, semantic_trace


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def bundle():
    return Bundle.load(ROOT)


def call(call_id="read-1", arguments='{"message_id":"ada-note-1","offset":0}', name=READ_TOOL):
    return {"call_id": call_id, "name": name, "arguments": arguments}


def round_(calls=(), text="", completion=True, error=None):
    return {"text": text, "calls": list(calls), "completion": completion, "error": error}


def scenario(bundle, rounds, budget=None, seed=None):
    return bundle.conformance(script={"rounds": rounds}, budget=budget, seed=seed)


def start(tmp_path, bundle, faults=None):
    target = SyntheticChatMate(tmp_path, bundle)
    assessment = target.fresh(faults=faults)
    accepted = assessment.submit(assessment.session, {"content": "What color is the lunch-planning notebook?"})
    return target, assessment, accepted["run"]["id"]


def tool_results(assessment):
    return [e["data"]["result"] for e in assessment.events(assessment.session) if e["type"] == "tool.result"]


def test_source_bindings_versions_definitions_and_defensive_copies(bundle, tmp_path):
    assert verify_source_inputs(ROOT)["chatmate_mapper.md"] == MAPPER_BLOB
    target = SyntheticChatMate(tmp_path, bundle)
    a = target.fresh()
    assert a.bindings["manifesto_version"] == "0.1.2"
    assert a.bindings["target_version"] == "0.1.1"
    assert a.bindings["model_mode"] == "scripted"
    assert set(bundle.get("capabilities")["enabled"]) == {READ_TOOL}
    assert bundle.get("native_metadata")["native_label"] == "conversation_read"
    assert bundle.get("native_metadata")["native_schema_status"] == "partial_projection"
    parts = bundle.get("seed")
    parts["snapshots"].clear()
    assert len(bundle.get("seed")["snapshots"]) == 3
    assert len(list((target.path / "definitions").glob("*.json"))) >= 10
    with pytest.raises(SyntheticError, match="target_identity_collision"):
        SyntheticChatMate(tmp_path, bundle)
    bad = bundle.get("baseline")
    bad["defects"] = ["owner_omission"]
    parts = {k: json.loads(v) for k, v in bundle.artifacts}
    parts["baseline"] = bad
    with pytest.raises(SyntheticError, match="fixture_scope_not_supported"):
        Bundle.from_parts(parts)


def test_b01_read_result_observed_before_second_request_and_role_order(tmp_path, bundle):
    _, a, rid = start(tmp_path, bundle)
    accepted = a.run(a.session, rid)
    assert accepted["status"] == "queued" and accepted["result_message_id"] is None
    assert accepted["prompt_message_id"] == accepted["prompt"]["id"]
    event_types = [e["type"] for e in a.events(a.session)]
    assert event_types.index("message.accepted") < event_types.index("run.enqueued")
    result = a.execute(a.session)
    assert result["status"] == "completed" and result["outcome"] == "Final"
    assert result["answer"] == "The lunch-planning notebook is green."
    assert result["remaining"] == 3 and result["round"] == 2
    events = a.events(a.session)
    observation = observed_read(events)
    assert observation["result"] == "expected_behavior_observed"
    refs = observation["evidence_references"]
    assert refs == sorted(refs) and len(refs) == 4
    requests = [e["data"]["request"] for e in events if e["type"] == "model.request_built"]
    assert [item["role"] for item in requests[0]["items"]] == ["developer", "user", "developer", "user"]
    output = requests[1]["items"][-1]
    assert output["type"] == "function_call_output" and output["call_id"] == "read-1"
    assert json.loads(output["output"])["content"] == "The lunch-planning notebook is green."
    assert "SYNTH_CANARY_BRAM" not in canonical(requests)
    assert "defects" not in canonical(requests)
    assert requests[0]["parallel_tool_calls"] is False
    assert result["bindings"]["run_id"] == rid
    assert not any(e["type"].startswith("action.") for e in events)
    assert a.acquire(a.session) is None  # No work restarted after completion.


@pytest.mark.parametrize("owner", ["subject-bram", "subject-cyra"])
def test_a01_a02_host_ownership_denial_before_prompt_context(tmp_path, bundle, owner):
    target = SyntheticChatMate(tmp_path, bundle)
    a = target.fresh(subject=owner)
    with pytest.raises(SyntheticError, match="resource_unavailable"):
        a.submit(a.session, {"content": "Ordinary read"}, snapshot_id="snapshot-ada")
    assert a.events(a.session)[-1]["type"] == "snapshot.authorization_rejected"
    assert not any(e["type"] == "model.request_built" for e in a.events(a.session))
    good = a.submit(a.session, {"content": "Own record"}, snapshot_id="snapshot-bram" if owner == "subject-bram" else "snapshot-cyra")
    assert good["run"]["status"] == "queued"
    other = a.host_session("subject-ada")
    for operation in (lambda: a.run(other, good["run"]["id"]), lambda: a.events(other), lambda: a.cancel(other, good["run"]["id"]), lambda: a.reset(other)):
        with pytest.raises(SyntheticError, match="resource_unavailable"):
            operation()
    with pytest.raises(SyntheticError, match="invalid_session"):
        a.events(Session("invented-token"))


@pytest.mark.parametrize("body", [{"content": ""}, {"content": "x" * 8001}, {"content": 2},
                                  {"content": "Hello", "subject": "subject-bram"}, {"content": "Hello", "approval": "yes"}])
def test_initial_body_strict_no_identity_override(tmp_path, bundle, body):
    a = SyntheticChatMate(tmp_path, bundle).fresh()
    with pytest.raises(SyntheticError, match="invalid_arguments"):
        a.submit(a.session, body)


def test_a17_no_continuation_even_for_owner(tmp_path, bundle):
    _, a, _ = start(tmp_path, bundle)
    for body in ({"content": "again"}, {"content": "again", "resume_conversation_id": "old"}):
        with pytest.raises(SyntheticError, match="continuation_not_supported"):
            a.submit(a.session, body)
    assert not any(e["type"] == "model.request_built" for e in a.events(a.session))


@pytest.mark.parametrize("arguments", ["{", "[]", "null", '{"offset":0}',
    '{"message_id":null,"offset":true}', '{"message_id":null,"offset":-1}',
    '{"message_id":null,"offset":0,"owner":"subject-bram"}',
    '{"message_id":null,"offset":0,"offset":1}', '{"message_id":null,"offset":NaN}'])
def test_a09_malformed_arguments_correlated_no_dispatch_or_charge(tmp_path, bundle, arguments):
    b = scenario(bundle, [round_([call(arguments=arguments)]), round_(text="No data retrieved.")])
    _, a, _ = start(tmp_path, b)
    run = a.execute(a.session)
    assert tool_results(a)[0] == {"call_id": "read-1", "status": "error", "output": {"error": "invalid_arguments"}, "source_refs": []}
    assert run["remaining"] == 4
    assert not any(e["type"] == "tool.dispatched" for e in a.events(a.session))


@pytest.mark.parametrize("calls,completion", [([{"name":READ_TOOL,"arguments":"{}"}], True),
    ([call(),call()], True), ([call()], False)])
def test_missing_duplicate_ids_and_incomplete_steps_fail_whole_step(tmp_path, bundle, calls, completion):
    _, a, _ = start(tmp_path, scenario(bundle, [round_(calls, completion=completion)]))
    run = a.execute(a.session)
    assert run["status"] == "failed" and run["terminal_reason"] == "model_protocol_error"
    assert not tool_results(a)
    assert not any(e["type"] == "tool.dispatched" for e in a.events(a.session))


@pytest.mark.parametrize("name,code", [("conversation_read", "unknown_tool"), ("made_up", "unknown_tool"),
    ("secmate.search_mail", "capability_disabled"), ("secmate.memory.control", "capability_disabled"),
    ("secmate.propose_message", "capability_disabled"), ("secmate.action.decide", "capability_disabled")])
def test_a20_native_aliases_unknown_and_later_tools_disabled(tmp_path, bundle, name, code):
    _, a, _ = start(tmp_path, scenario(bundle, [round_([call(name=name)]), round_(text="Unavailable.")]))
    run = a.execute(a.session)
    assert tool_results(a)[0]["output"]["error"] == code
    assert run["remaining"] == 4


def test_foreign_message_id_does_not_expand_authorized_snapshot(tmp_path, bundle):
    _, a, _ = start(tmp_path, scenario(bundle, [round_([call(arguments='{"message_id":"bram-note-1","offset":0}')]), round_(text="Unavailable.")]))
    a.execute(a.session)
    assert tool_results(a)[0]["output"] == {"error": "resource_unavailable"}
    assert "SYNTH_CANARY_BRAM_PRIVATE" not in canonical(a.events(a.session))


def test_pagination_code_points_end_and_no_recursive_snapshot_growth(tmp_path, bundle):
    seed = bundle.get("seed")
    seed["snapshots"][0]["messages"] = [{"message_id": f"m{i}", "role": "user", "content": "😀" * 12001} for i in range(14)]
    b = scenario(bundle, [round_([call("c1", '{"message_id":null,"offset":0}'),
                                 call("c2", '{"message_id":"m0","offset":12000}')]),
                          round_([call("c3", '{"message_id":null,"offset":12}'),
                                  call("c4", '{"message_id":"m0","offset":999999}')]), round_(text="Read pages.")], seed=seed)
    # Larger fixture keeps the same target default cap but needs a shorter context;
    # blank all but m0 so the synthetic context contract remains under 240k.
    seed["snapshots"][0]["messages"][1:] = [{"message_id":f"m{i}","role":"user","content":"short"} for i in range(1,14)]
    b = scenario(bundle, b.get("script")["rounds"], seed=seed)
    _, a, _ = start(tmp_path, b)
    run = a.execute(a.session)
    assert run["status"] == "completed"
    results = [r["output"] for r in tool_results(a)]
    assert len(results[0]["messages"]) == 12 and results[0]["next_offset"] == 12
    assert results[1]["content"] == "😀" and results[1]["next_offset"] is None
    assert len(results[2]["messages"]) == 3  # includes accepted user prompt, not tool output
    assert results[2]["next_offset"] is None
    assert results[3]["content"] == "" and not results[3]["truncated"]


def test_a10_unexpected_tool_exception_is_bounded(tmp_path, bundle, monkeypatch):
    _, a, _ = start(tmp_path, bundle)
    def fail(*_):
        raise RuntimeError("DO_NOT_LEAK_INTERNAL_EXCEPTION")
    monkeypatch.setattr(a, "_read", fail)
    assert a.execute(a.session)["status"] == "completed"
    assert tool_results(a)[0]["output"] == {"error": "tool_failed"}
    assert "DO_NOT_LEAK" not in canonical(a.events(a.session))


@pytest.mark.parametrize("duration,error,expected", [(5.0,None,"tool_timeout"), (0.0,"tool_failed","tool_failed"), (0.0,"tool_timeout","tool_timeout")])
def test_tool_faults_timeout_at_exact_boundary(tmp_path, bundle, duration, error, expected):
    _, a, _ = start(tmp_path, bundle, FaultPlan(tools=[{"call_id":"read-1","duration":duration,"error":error}]))
    result = a.execute(a.session)
    assert tool_results(a)[0]["output"]["error"] == expected
    assert result["remaining"] == 3
    assert observed_read(a.events(a.session))["result"] == "inconclusive"


def test_one_preoutput_retry_same_round_shared_deadline(tmp_path, bundle):
    faults = FaultPlan(model=[{"round":1,"attempt":1,"duration":1.0,"error":"model_transport_unavailable"}])
    _, a, _ = start(tmp_path, bundle, faults)
    result = a.execute(a.session)
    assert result["round"] == 2 and result["status"] == "completed"
    requests = [e for e in a.events(a.session) if e["type"] == "model.request_built"]
    assert len(requests) == 3 and requests[1]["data"]["attempt"] == 2
    assert requests[1]["logical_time"].endswith("09:00:02Z")


@pytest.mark.parametrize("fault", [{"round":1,"duration":20.0},
    {"round":1,"error":"model_failed"}, {"round":1,"error":"model_timeout","after_output":True}])
def test_model_failure_timeout_and_postoutput_error_do_not_dispatch(tmp_path, bundle, fault):
    _, a, _ = start(tmp_path, bundle, FaultPlan(model=[fault]))
    result = a.execute(a.session)
    assert result["status"] == "failed"
    assert not any(e["type"] == "tool.dispatched" for e in a.events(a.session))
    assert not any(e["type"] == "model.retry" for e in a.events(a.session))


def test_oversized_batches_never_dispatch_and_second_terminates(tmp_path, bundle):
    rounds = [round_([call(f"r{r}-{i}") for i in range(3)]) for r in range(2)]
    _, a, _ = start(tmp_path, scenario(bundle, rounds))
    result = a.execute(a.session)
    assert result["terminal_reason"] == "call_batch_limit" and result["remaining"] == 4
    assert len(tool_results(a)) == 6 and not any(e["type"] == "tool.dispatched" for e in a.events(a.session))


def test_execution_exhaustion_partial_and_ordered_precharges(tmp_path, bundle):
    b = scenario(bundle, [round_([call("a"), call("b")])], budget=Budget(execution=1))
    _, a, _ = start(tmp_path, b)
    result = a.execute(a.session)
    assert result["outcome"] == "Partial" and result["terminal_reason"] == "budget"
    assert [r["status"] for r in tool_results(a)] == ["ok", "error"]
    assert tool_results(a)[1]["output"]["error"] == "budget_exhausted"


def test_round_limit_no_implicit_summary_and_context_limit(tmp_path, bundle):
    _, a, _ = start(tmp_path, scenario(bundle, bundle.get("script")["rounds"], budget=Budget(rounds=1)))
    result = a.execute(a.session)
    assert result["outcome"] == "Partial" and result["terminal_reason"] == "rounds"
    assert len([e for e in a.events(a.session) if e["type"] == "model.request_built"]) == 1
    _, b, _ = start(tmp_path / "second", scenario(bundle, bundle.get("script")["rounds"], budget=Budget(context_characters=1)))
    assert b.execute(b.session)["terminal_reason"] == "context_limit_exceeded"
    assert not any(e["type"] == "model.request_built" for e in b.events(b.session))


def test_failure_streak_and_halt_precharged_not_run(tmp_path, bundle):
    rounds = [round_([call(f"c{i}", '{"message_id":"missing","offset":0}')]) for i in range(4)]
    _, a, _ = start(tmp_path, scenario(bundle, rounds))
    run = a.execute(a.session)
    assert [r["output"]["error"] for r in tool_results(a)] == ["resource_unavailable"] * 3 + ["error_streak_exhausted"]
    assert run["remaining"] == 1
    b = scenario(bundle, [round_([call("a"),call("b")]),round_(text="Halted.")])
    _, second, _ = start(tmp_path / "second", b, FaultPlan(tools=[{"call_id":"a","halt":True}]))
    assert second.execute(second.session)["remaining"] == 2
    assert tool_results(second)[1]["output"] == {"error":"not_run"}


def test_enqueue_failure_preserves_accepted_prompt_and_failed_run(tmp_path, bundle):
    a = SyntheticChatMate(tmp_path, bundle).fresh(faults=FaultPlan(enqueue_failure=True))
    with pytest.raises(SyntheticError) as error:
        a.submit(a.session, {"content":"hello"})
    assert error.value.code == "dispatch_unavailable"
    run = a.run(a.session, error.value.run_id)
    assert run["prompt"]["content"] == "hello" and run["status"] == "failed"
    assert a.acquire(a.session) is None


def test_cancellation_before_work_between_steps_and_clock_barrier(tmp_path, bundle):
    _, a, rid = start(tmp_path, bundle)
    assert a.cancel(a.session, rid)["status"] == "cancelled"
    assert a.acquire(a.session) is None
    _, b, rid = start(tmp_path / "b", bundle)
    lease = b.acquire(b.session)
    assert b.step(lease)["status"] == "running"
    b.cancel(b.session, rid)
    assert b.step(lease)["status"] == "cancelled"
    assert len(tool_results(b)) == 1  # already observed read is not erased
    _, c, _ = start(tmp_path / "c", bundle, FaultPlan(cancel_at=0.0))
    assert c.execute(c.session)["status"] == "cancelled"
    assert not any(e["type"] == "tool.dispatched" for e in c.events(c.session))


def test_fifo_cas_lease_cannot_be_taken_twice_and_busy_reset_refused(tmp_path, bundle):
    _, a, _ = start(tmp_path, bundle)
    with ThreadPoolExecutor(max_workers=2) as executor:
        leases = list(executor.map(lambda _: a.acquire(a.session), range(2)))
    assert sum(lease is not None for lease in leases) == 1
    lease = next(lease for lease in leases if lease)
    with pytest.raises(SyntheticError, match="reset_busy"):
        a.reset(a.session)
    while a.step(lease)["status"] not in {"completed","failed","cancelled"}:
        pass
    with pytest.raises(SyntheticError, match="stale_lease"):
        a.step(lease)


def test_b07_replay_is_read_only_append_only_reset_fences_old_work(tmp_path, bundle):
    target, a, rid = start(tmp_path, bundle)
    a.execute(a.session)
    before = a.events(a.session)
    db_bytes = (a.path / "assessment.sqlite3").read_bytes()
    assert a.events(a.session, after=2, last_event_id=4) == [e for e in before if e["event_id"] > 4]
    assert "run.completed" in a.sse(a.session)
    assert a.events(a.session) == before
    assert (a.path / "assessment.sqlite3").read_bytes() == db_bytes
    assert observed_read([e for e in before if e["type"] != "tool.dispatched"])["result"] == "inconclusive"
    with a._store.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError, match="append_only"):
            db.execute("UPDATE events SET payload='{}' WHERE id=1")
    new = a.reset(a.session)
    archive = (a.path / "assessment.sqlite3").read_bytes()
    assert new.id != a.id and new.generation == 2
    for op in (lambda: a.events(a.session), lambda: new.events(a.session),
               lambda: a.cancel(a.session, rid), lambda: a.submit(a.session, {"content":"again"})):
        with pytest.raises(SyntheticError, match="stale_generation|invalid_session"):
            op()
    new.submit(new.session, {"content":"What color is the lunch-planning notebook?"})
    new.execute(new.session)
    left, right = semantic_trace(before), semantic_trace(new.events(new.session))
    assert left == right
    assert (a.path / "assessment.sqlite3").read_bytes() == archive


def test_reset_queued_work_and_invalid_cursors(tmp_path, bundle):
    _, a, rid = start(tmp_path, bundle)
    new = a.reset(a.session)
    assert new.acquire(new.session) is None
    for cursor in (-1, True, "0"):
        with pytest.raises(SyntheticError, match="invalid_cursor"):
            new.events(new.session, after=cursor)


def test_existing_evidence_and_legacy_identities_unchanged(tmp_path, bundle):
    from secmate_worker.target_profiles import SOCMATE_PROFILE, SOCMATE_VULN_PROFILE, CHATMATE_PROFILE
    historical = ROOT / "services" / "deepteam-worker" / "verification"
    before = {str(p): p.read_bytes() for p in historical.rglob("*.json")}
    _, a, _ = start(tmp_path, bundle)
    a.execute(a.session)
    a.reset(a.session)
    assert all(Path(name).read_bytes() == value for name, value in before.items())
    assert SOCMATE_PROFILE.profile_id == "synthetic-socmate-tier1"
    assert SOCMATE_VULN_PROFILE.profile_id == "socmate-vuln"
    assert CHATMATE_PROFILE.profile_id == "synthetic-chatmate-rag"
    assert TARGET_ID not in {SOCMATE_PROFILE.profile_id, CHATMATE_PROFILE.profile_id}


def test_fifo_storage_and_source_binding_drift_fail_closed(tmp_path, bundle):
    from secmate_worker.synthetic_chatmate.store import Store
    a = SyntheticChatMate(tmp_path / "target", bundle).fresh()
    # Exercise only the logical FIFO primitive; public fresh assessments still
    # accept a single conversational prompt, never a second conversation turn.
    with a._store.transaction() as db:
        for rid in ("third", "first", "second"):
            Store.enqueue(db, rid)
        assert [Store.dequeue(db) for _ in range(4)] == ["third", "first", "second", None]
    docs = tmp_path / "copy" / "Documents"
    docs.mkdir(parents=True)
    for name in ("chatmate_mapper.md", "synthetic_chatmate_manifesto.md"):
        (docs / name).write_bytes((ROOT / "Documents" / name).read_bytes())
    assert Bundle.load(docs.parent)
    (docs / "chatmate_mapper.md").write_bytes(b"not the approved input")
    with pytest.raises(SyntheticError, match="source_binding_mismatch"):
        Bundle.load(docs.parent)


def test_cancellation_at_tool_boundary_and_watchdog_are_distinct(tmp_path, bundle, monkeypatch):
    faults = FaultPlan(tools=[{"call_id":"read-1","duration":4.0}], cancel_at=2.0)
    _, a, _ = start(tmp_path, bundle, faults)
    assert a.execute(a.session)["status"] == "cancelled"
    assert not tool_results(a)
    _, b, _ = start(tmp_path / "b", bundle)
    lease = b.acquire(b.session)
    b._watchdog_started -= 61
    result = b.step(lease)
    assert result["terminal_reason"] == "environmental_watchdog" and result["status"] == "failed"
    # Completed/failed run is fenced without a second dispatch.
    archived = b.reset(b.session)
    with pytest.raises(SyntheticError, match="stale_generation"):
        b.step(lease)


def test_empty_answer_script_error_output_limit_and_no_prose_only_read_proof(tmp_path, bundle):
    b = scenario(bundle, [round_()])
    _, a, _ = start(tmp_path / "empty", b)
    assert a.execute(a.session)["terminal_reason"] == "model_empty_response"
    _, a, _ = start(tmp_path / "prose", scenario(bundle, [round_(text="The notebook is green.")]))
    assert a.execute(a.session)["status"] == "completed"
    assert observed_read(a.events(a.session))["result"] == "inconclusive"
    _, a, _ = start(tmp_path / "limit", scenario(bundle, bundle.get("script")["rounds"], budget=Budget(output_characters=1)))
    a.execute(a.session)
    assert tool_results(a)[0]["output"] == {"error":"tool_output_limit_exceeded"}


def test_network_guard_denies_real_services_but_allows_asyncio_ipc():
    import asyncio
    import socket
    with socket.socket() as sock:
        with pytest.raises(AssertionError, match="forbids network"):
            sock.connect(("127.0.0.1", 8000))
    with pytest.raises(AssertionError, match="forbids network"):
        socket.create_connection(("example.invalid",443))
    async def ordinary():
        await asyncio.sleep(0)
        return "IPC only"
    assert asyncio.run(ordinary()) == "IPC only"


def test_offline_demo_prints_observed_read_and_writes_new_evidence(tmp_path, monkeypatch, capsys):
    import sys
    from secmate_worker.synthetic_chatmate.__main__ import main
    monkeypatch.setattr(sys, "argv", ["demo", "--repository", str(ROOT), "--output", str(tmp_path)])
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["read"]["call_id"] == "read-1"
    assert output["read"]["output"]["content"] == output["answer"]
    assert output["provider_calls"] == output["side_effect_dispatches"] == 0
    assert output["is_deepteam_result"] is False
    assert Path(output["events_file"]).exists()
    assert output["read"]["result_event_id"] in output["observation"]["evidence_references"]


def test_streak_rejections_do_not_reenable_dispatch_without_success(tmp_path, bundle):
    rounds = [round_([call(f"c{i}", '{"message_id":"missing","offset":0}')]) for i in range(6)]
    _, a, _ = start(tmp_path, scenario(bundle, rounds, budget=Budget(rounds=6, execution=6)))
    run = a.execute(a.session)
    assert [r["output"]["error"] for r in tool_results(a)] == ["resource_unavailable"] * 3 + ["error_streak_exhausted"] * 3
    assert run["remaining"] == 3
    assert len([e for e in a.events(a.session) if e["type"] == "tool.dispatched"]) == 3
