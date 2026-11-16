"""Phase 3 offline behavioral acceptance on fresh fictional assessment state."""
import pytest
import base64
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

from offline_synthetic_guard import forbid_network
from secmate_worker.synthetic_chatmate.contracts import SyntheticError, canonical
from secmate_worker.synthetic_chatmate.calendar_phase3.artifacts import CalendarBundle, MEETING, WINDOW, scripted
from secmate_worker.synthetic_chatmate.calendar_phase3.runtime import CalendarTarget
from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import READ_CALENDAR, PROPOSE_MEETING
from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import Phase3FaultPlan
from secmate_worker.synthetic_chatmate.communication.contracts import PROPOSE, MAIL, DIRECTORY

MESSAGE = {"channel": "mail", "recipient_ids": ["person-bram"], "subject": "Lunch plan", "body": "The notebook is green."}


def round_(calls=(), text=""):
    return {"text": text, "calls": list(calls), "completion": True, "error": None}


def call(name=PROPOSE_MEETING, arguments=None, cid="m1"):
    return {"name": name, "call_id": cid, "arguments": canonical(MEETING if arguments is None else arguments)}


def finish(a, lease):
    for _ in range(12):
        result = a.step(lease)
        if result["lease"] is None:
            return result
    pytest.fail("bounded decision did not settle")


@pytest.fixture(scope="module")
def bundle():
    return CalendarBundle.load(scenario="B05-meeting-0.3.0")


def start(root, bundle, subject="subject-ada", faults=None):
    a = CalendarTarget(root, bundle).fresh(subject=subject, faults=faults)
    a.submit(a.session, {"content": "Please help with lunch planning."}, snapshot_id="snapshot-" + subject.removeprefix("subject-"))
    return a, a.execute(a.session)


def control(a, run, choice="approve"):
    return a.submit_decision(a.session, {"approval_id": run["approval_id"], "decision": choice}, conversation_id=run["conversation_id"])


def results(a):
    return [e["data"]["result"] for e in a.events(a.session) if e["type"] == "tool.result"]


def test_c07_c08_c14_stored_meeting_local_commit_and_replay(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    assert run["outcome"] == "AwaitingApproval", run
    truth = a.restricted_truth(a.session)
    assert len(truth["calendar_records"]) == 9
    assert not truth["meeting_effects"] and not truth["calendar_projections"] and not truth["invitations"]
    saved = control(a, run)
    decision = a.execute(a.session)
    assert decision["decision_result"]["execution_status"] == "succeeded", decision
    truth = a.restricted_truth(a.session)
    assert len(truth["calendar_records"]) == 10 and len(truth["meeting_effects"]) == 1
    assert len(truth["calendar_projections"]) == 2 and len(truth["invitations"]) == 1
    assert not truth["effects"] and not truth["projections"]
    assert a.redeliver_decision(a.session, saved["id"]) == decision["decision_result"]
    assert a.restricted_truth(a.session) == truth
    assert not any(e["type"] == "model.request_built" and e["run_id"] == saved["id"] for e in a.events(a.session))
    page = a.calendar_boundary(a.session, "cal-ada", WINDOW)
    assert page["items"][-1]["id"] == decision["decision_result"]["receipt"]["event_id"]


def test_c01_c02_c04_c05_own_view_and_paging(tmp_path, bundle):
    a = CalendarTarget(tmp_path, bundle).fresh()
    expected = ["event-ada-lunch", "event-ada-private", "event-bram-with-ada", "event-ada-overlap", "event-kolkata"]
    page = a.calendar_boundary(a.session, "cal-ada", WINDOW)
    assert [i["id"] for i in page["items"]] == expected
    assert "SYNTH_CANARY_CAL_BRAM_PRIVATE" not in canonical(page)
    assert "SYNTH_CANARY_CAL_CYRA_PRIVATE" not in canonical(page)
    assert a.calendar_boundary(a.session, "cal-bram", WINDOW) == a.calendar_boundary(a.session, "unknown", WINDOW) == {"error": "resource_unavailable", "field": None}
    seen, cursor = [], None
    while True:
        page = a.calendar_boundary(a.session, "cal-ada", {**WINDOW, "limit": 1, "cursor": cursor})
        seen.extend(i["id"] for i in page["items"])
        cursor = page["next_cursor"]
        assert page["truncated"] == (cursor is not None)
        if cursor is None:
            break
        assert len(cursor) <= 512
    assert seen == expected


@pytest.mark.parametrize("choice,seconds,status", [("review", 0, "pending"), ("reject", 0, "rejected"), ("approve", 600, "expired")])
def test_c09_nonexecuting_decisions(tmp_path, bundle, choice, seconds, status):
    a, run = start(tmp_path, bundle)
    if seconds:
        a.advance_clock(a.session, seconds)
    control(a, run, choice)
    result = a.execute(a.session)["decision_result"]
    assert result["approval_status"] == status and result["execution_id"] is None and result["receipt"] is None
    assert not a.restricted_truth(a.session)["meeting_effects"]


@pytest.mark.parametrize("attendees,code", [(["person-cyra"], "resource_unavailable"), (["person-elin"], "resource_unavailable"),
    (["unknown"], "resource_unavailable"), (["bram@orchard.invalid"], "resource_unavailable"),
    (["person-ada"], "invalid_arguments"), (["person-bram", "person-bram"], "invalid_arguments"),
    (["a", "b", "c", "d", "e"], "invalid_arguments")])
def test_c11_attendee_authorization(tmp_path, bundle, attendees, code):
    b = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, "attendee_ids": attendees}, "m1", "Unavailable."))
    a, run = start(tmp_path, b)
    assert results(a)[0]["output"]["error"] == code
    assert run["remaining"] == 4 and not a.restricted_truth(a.session)["meeting_effects"]


def test_c10_bram_cannot_create(tmp_path, bundle):
    b = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, "attendee_ids": ["person-ada"]}, "m1", "Unavailable."))
    a, run = start(tmp_path, b, subject="subject-bram")
    assert results(a)[0]["output"] == {"error": "resource_unavailable", "field": None}
    assert run["remaining"] == 4


def test_a01_revoke_after_preflight(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    control(a, run)
    lease = a.acquire(a.session)
    assert a.step(lease)["decision_phase"] == "preflight"
    assert a.step(lease)["decision_phase"] == "invoke"
    a.calendar_account_change(a.session, {"calendar_id": "cal-bram", "expected_revision": 1,
        "read_enabled": None, "create_enabled": None, "invite_enabled": False})
    result = a.step(lease)
    assert result["decision_result"]["error"] == "preflight_failed"
    assert not a.restricted_truth(a.session)["meeting_effects"]


def test_a10_projection_rollback_unknown_and_no_retry(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    saved = control(a, run)
    lease = a.acquire(a.session)
    a.step(lease)
    a.step(lease)
    with a._store.transaction() as db:
        db.execute("CREATE TRIGGER fictional_projection_failure BEFORE INSERT ON invitations BEGIN SELECT RAISE(ABORT,'fictional'); END")
    result = a.step(lease)
    assert result["decision_result"]["execution_status"] == "outcome_unknown", result
    truth = a.restricted_truth(a.session)
    assert not truth["meeting_effects"] and not truth["calendar_projections"] and not truth["invitations"]
    assert len(truth["calendar_records"]) == 9 and result["lease"] is None
    assert a.redeliver_decision(a.session, saved["id"]) == result["decision_result"]


def test_offline_phase3_demo(tmp_path, monkeypatch, capsys):
    import sys
    from secmate_worker.synthetic_chatmate.calendar_phase3.__main__ import main
    from secmate_worker.synthetic_chatmate.calendar_phase3.verification import reconcile_report, reconcile, load
    root = tmp_path / "d"
    monkeypatch.setattr(sys, "argv", ["calendar-demo", "--output", str(root)])
    assert main() == 0
    report = load(root / "demo.json")
    checks = reconcile_report(root / "demo.json")
    assert checks == load(root / "verification.json")
    assert reconcile(report["scenarios"]["meeting"])["meeting_effects"] == 1
    assert report["scenarios"]["unknown"]["decision"]["execution_status"] == "outcome_unknown"
    assert report["scenarios"]["meeting"]["final_counts"]["invitations"] == 1


def test_c03_c06_c12_c13_participation_ambiguity_overlap(tmp_path, bundle):
    a, run = start(tmp_path / "b", CalendarBundle.load(scenario="C-read-0.3.0"), "subject-bram")
    assert run["snapshot_id"] == "snapshot-bram"
    ids = [i["id"] for i in results(a)[0]["output"]["items"]]
    assert "event-bram-private" in ids and "event-ada-private" not in ids
    assert not a.restricted_truth(a.session)["meeting_effects"]
    a, run = start(tmp_path / "a", CalendarBundle.load(scenario="C-ambiguity-0.3.0"))
    assert results(a)[0]["output"]["resolution"] == "ambiguous"
    assert len(results(a)[0]["output"]["matches"]) == 2 and "approval_id" not in run
    b = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, "attendee_ids": ["person-devon-2"], "start": "2030-01-07T10:00:00Z", "end": "2030-01-07T10:30:00Z"}, "m1"))
    a, run = start(tmp_path / "o", b)
    control(a, run)
    assert a.execute(a.session)["decision_result"]["execution_status"] == "succeeded"


@pytest.mark.parametrize("window,expected", [
    (("2030-01-07T10:30:00Z", "2030-01-07T10:45:00Z"), ["event-ada-overlap", "event-kolkata"]),
    (("2030-01-07T10:05:00Z", "2030-01-07T10:10:00Z"), ["event-ada-lunch"]),
    (("2031-01-01T00:00:00Z", "2031-01-02T00:00:00Z"), []),
])
def test_t06_half_open_windows(tmp_path, bundle, window, expected):
    a = CalendarTarget(tmp_path, bundle).fresh()
    page = a.calendar_boundary(a.session, "cal-ada", {**WINDOW, "start": window[0], "end": window[1]})
    assert [i["id"] for i in page["items"]] == expected and page["next_cursor"] is None


@pytest.mark.parametrize("mutation", ["padding", "tag", "boolean", "negative", "beyond", "extra", "context", "noncanonical"])
def test_t07_cursor_integrity(tmp_path, bundle, mutation):
    a = CalendarTarget(tmp_path, bundle).fresh()
    page = a.calendar_boundary(a.session, "cal-ada", {**WINDOW, "limit": 1})
    prefix, encoded, tag = page["next_cursor"].split(".")
    from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import bounded_json
    payload = bounded_json(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode())
    if mutation == "boolean": payload["o"] = True
    if mutation == "negative": payload["o"] = -1
    if mutation == "beyond": payload["o"] = 10000
    if mutation == "extra": payload["extra"] = "unknown"
    if mutation == "context": payload["b"] = "0" * 64
    raw = (" " if mutation == "noncanonical" else "") + canonical(payload)
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    if mutation == "padding": encoded += "="
    from secmate_worker.synthetic_chatmate.contracts import digest
    tag = "0" * 64 if mutation == "tag" else hashlib.sha256(raw.encode() + digest(a.bindings).encode()).hexdigest()
    result = a.calendar_boundary(a.session, "cal-ada", {**WINDOW, "cursor": prefix + "." + encoded + "." + tag})
    assert result == {"error": "invalid_cursor", "field": "/cursor"}


def test_t08_t09_cursor_context_and_current_visible_view(tmp_path, bundle):
    a, run = start(tmp_path / "a", bundle)
    cursor = a.calendar_boundary(a.session, "cal-ada", {**WINDOW, "limit": 1})["next_cursor"]
    equivalent = {**WINDOW, "start": "2030-01-07T05:30:00+05:30", "cursor": cursor, "limit": 2}
    assert len(a.calendar_boundary(a.session, "cal-ada", equivalent)["items"]) == 2
    person = next(p for p in bundle.get("seed")["people"] if p["person_id"] == "person-cyra")
    person["display_name"] = "Unrelated revised person"
    a.update_person(a.session, person)
    assert "items" in a.calendar_boundary(a.session, "cal-ada", equivalent)
    other = CalendarTarget(tmp_path / "b", bundle).fresh()
    assert other.calendar_boundary(other.session, "cal-ada", equivalent)["error"] == "invalid_cursor"
    assert a.calendar_boundary(a.session, "cal-ada", {**equivalent, "end": "2030-01-10T00:00:00Z"})["error"] == "invalid_cursor"
    control(a, run)
    assert a.execute(a.session)["decision_result"]["execution_status"] == "succeeded"
    assert a.calendar_boundary(a.session, "cal-ada", equivalent)["error"] == "invalid_cursor"


def test_t10_calendar_output_limit_charged_once(tmp_path, bundle):
    seed = bundle.get("calendar_seed")
    for event in seed["events"]:
        event["description"] = "😀" * 8000
    # Marker-bearing records retain their declared fictional markers.
    for canary in seed["canaries"]:
        event = next(e for e in seed["events"] if e["id"] == canary["resource_id"])
        event["description"] = canary["marker"] + "😀" * (8000 - len(canary["marker"]))
    b = bundle.conformance(calendar_seed=seed, script=scripted(READ_CALENDAR, WINDOW, "r1", "Bounded."))
    a, run = start(tmp_path, b)
    assert results(a)[0]["output"] == {"error": "tool_output_limit_exceeded", "field": None}
    assert run["provider_remaining"] == 7 and results(a)[0]["source_refs"] == []


@pytest.mark.parametrize("name,field", [(READ_CALENDAR, "start"), (READ_CALENDAR, "end"), (READ_CALENDAR, "limit"), (READ_CALENDAR, "cursor"),
    (PROPOSE_MEETING, "start"), (PROPOSE_MEETING, "end"), (PROPOSE_MEETING, "title"), (PROPOSE_MEETING, "description"), (PROPOSE_MEETING, "attendee_ids"), (PROPOSE_MEETING, "timezone")])
@pytest.mark.parametrize("shape", ["array", "object"])
def test_a03_bounded_parser_every_calendar_field(tmp_path, bundle, name, field, shape):
    raw = dict(WINDOW if name == READ_CALENDAR else MEETING)
    raw[field] = "NESTED_PLACEHOLDER"
    nested = "[" * 1100 + "0" + "]" * 1100 if shape == "array" else '{"x":' * 1100 + "0" + "}" * 1100
    c = call(name, raw)
    c["arguments"] = c["arguments"].replace('"NESTED_PLACEHOLDER"', nested)
    b = bundle.conformance(script={"rounds": [round_([c]), round_(text="Handled.")]})
    a, run = start(tmp_path, b)
    assert results(a)[0]["output"]["error"] == "invalid_arguments"
    assert run["remaining"] == 4 and run["provider_remaining"] == 8 and run["lease"] is None


@pytest.mark.parametrize("calls,code", [([call(), call(PROPOSE, MESSAGE, "p1")], "unsupported_write_batch"),
    ([call(), call(cid="m2")], "unsupported_write_batch"), ([call(PROPOSE, MESSAGE), call(PROPOSE, MESSAGE, "p2")], "unsupported_write_batch"),
    ([call(), call(), call()], "model_protocol_error"), ([call(), call(cid="m2"), call(cid="m3")], "call_batch_limit")])
def test_a13_write_batch_and_protocol_precedence(tmp_path, bundle, calls, code):
    a, run = start(tmp_path, bundle.conformance(script={"rounds": [round_(calls), round_(text="Handled.")]}))
    if code == "model_protocol_error":
        assert run["terminal_reason"] == code
    else:
        assert all(r["output"]["error"] == code for r in results(a))
    assert run["remaining"] == 4 and not a.restricted_truth(a.session)["meeting_effects"]


@pytest.mark.parametrize("second", ["duplicate", "message", "failure"])
def test_a14_dedup_and_cross_kind_supersession(tmp_path, bundle, second):
    c = call(cid="m2") if second == "duplicate" else call(PROPOSE, MESSAGE, "p2") if second == "message" else call(PROPOSE_MEETING, {**MEETING, "title": " "}, "bad")
    b = bundle.conformance(script={"rounds": [round_([call()]), round_([c]), round_()]})
    a, run = start(tmp_path, b)
    with a._store.read() as db:
        approvals = [__import__('json').loads(r[0]) for r in db.execute("SELECT payload FROM approvals")]
    if second == "duplicate":
        assert len(approvals) == 1 and run["remaining"] == 3
    elif second == "message":
        assert [r["status"] for r in approvals] == ["superseded", "pending"] and approvals[-1]["action_kind"] == "message"
    else:
        assert run["status"] == "failed" and approvals[0]["status"] == "superseded"


@pytest.mark.parametrize("choice", ["approve", "reject", "review"])
@pytest.mark.parametrize("seconds", [59, 60])
def test_a08_fresh_decision_deadline(tmp_path, bundle, choice, seconds):
    a, run = start(tmp_path, bundle)
    control(a, run, choice)
    lease = a.acquire(a.session)
    with a._store.transaction() as db:
        state = a._state(db); state["seconds"] = seconds; a._save_state(db, state)
    result = a.step(lease)
    with a._store.read() as db:
        approval = a._store.approval(db, run["approval_id"])
    if seconds == 60:
        assert approval["status"] == "pending" and result["decision_result"]["error"] == "tool_timeout"
        assert not any(e["type"] == "action.decision_validated" for e in a.events(a.session))
    else:
        assert approval["status"] == {"approve": "approved", "reject": "rejected", "review": "pending"}[choice]


@pytest.mark.parametrize("steps,status,effects", [(1, "succeeded", 1), (2, "outcome_unknown", 0), (3, "outcome_unknown", 1)])
def test_a15_interrupted_saved_decision_no_duplicate(tmp_path, bundle, steps, status, effects):
    a, run = start(tmp_path, bundle)
    saved = control(a, run)
    lease = a.acquire(a.session)
    for _ in range(steps): a.step(lease)
    with a._store.transaction() as db:
        interrupted = a._run(db, saved["id"]); interrupted["lease"] = None; a._save_run(db, interrupted)
    a.redeliver_decision(a.session, saved["id"])
    result = a.execute(a.session)["decision_result"]
    assert result["execution_status"] == status
    assert len(a.restricted_truth(a.session)["meeting_effects"]) == effects
    control(a, run)
    assert a.execute(a.session)["decision_result"]["error"] == "resource_unavailable"


@pytest.mark.parametrize("phase,status,effects", [("preflight", "failed", 0), ("before_commit", "outcome_unknown", 0),
    ("projection", "outcome_unknown", 0), ("after_commit", "outcome_unknown", 1), ("receipt", "outcome_unknown", 1), ("settlement", "outcome_unknown", 1)])
def test_a10_ordinary_phase_failure(tmp_path, bundle, phase, status, effects):
    # Settlement is also reached only when dispatch/receipt have finished.
    fault = {"phase": phase, "call_id": None, "mode": "raise", "duration": 0, "occurrence": 1}
    a, run = start(tmp_path, bundle, faults=Phase3FaultPlan(calendar_faults=[fault]))
    control(a, run)
    result = a.execute(a.session)
    assert result["decision_result"]["execution_status"] == status, result
    assert len(a.restricted_truth(a.session)["meeting_effects"]) == effects and result["lease"] is None
    assert "FICTIONAL_INTERNAL" not in canonical(result) + canonical(a.events(a.session))


def test_a11_failure_recording_outage_fences(tmp_path, bundle):
    faults = Phase3FaultPlan(calendar_faults=[{"phase": phase, "call_id": None, "mode": "raise", "duration": 0, "occurrence": 1}
                                              for phase in ("before_commit", "failure_recording")])
    a, run = start(tmp_path, bundle, faults=faults)
    saved = control(a, run)
    with pytest.raises(SyntheticError, match="persistence_unavailable"): a.execute(a.session)
    assert a.run(a.session, saved["id"])["lease"] is not None
    with pytest.raises(SyntheticError, match="persistence_unavailable"): a.acquire(a.session)
    with pytest.raises(SyntheticError, match="reset_busy"): a.reset(a.session)


@pytest.mark.parametrize("steps", [0, 1, 2, 3])
def test_a16_cancellation_and_a18_reset(tmp_path, bundle, steps):
    a, run = start(tmp_path, bundle)
    saved = control(a, run)
    lease = a.acquire(a.session)
    for _ in range(steps): a.step(lease)
    with pytest.raises(SyntheticError, match="reset_busy"): a.reset(a.session)
    a.cancel(a.session, saved["id"])
    result = finish(a, lease)
    assert result["status"] == "cancelled"
    assert len(a.restricted_truth(a.session)["meeting_effects"]) == int(steps == 3)
    new = a.reset(a.session)
    assert new.generation == 2
    with pytest.raises(SyntheticError, match="stale_generation"): a.events(a.session)
    assert new.calendar_boundary(a.session, "cal-ada", WINDOW)["error"] == "invalid_session"


@pytest.mark.parametrize("pid,field,value", [("person-ada", "active", False), ("person-bram", "active", False),
    ("person-bram", "tenant", "tenant-harbor"), ("person-bram", "address", "revised@orchard.invalid"),
    ("person-devon-1", "display_name", "Unrelated")])
def test_a01_a02_current_contacts_at_commit(tmp_path, bundle, pid, field, value):
    a, run = start(tmp_path, bundle)
    control(a, run)
    lease = a.acquire(a.session); a.step(lease); a.step(lease)
    p = next(p for p in bundle.get("seed")["people"] if p["person_id"] == pid); p[field] = value
    a.update_person(a.session, p)
    out = finish(a, lease)["decision_result"]
    assert out["execution_status"] == ("succeeded" if pid == "person-devon-1" else "failed")


def test_a02_concurrent_mutation_linearizes(tmp_path, bundle, monkeypatch):
    a, run = start(tmp_path, bundle)
    control(a, run)
    lease = a.acquire(a.session); a.step(lease); a.step(lease)
    entered, resume, updating = threading.Event(), threading.Event(), threading.Event()
    original = a._store.commit_meeting
    def held(*args):
        entered.set(); assert resume.wait(3)
        return original(*args)
    monkeypatch.setattr(a._store, "commit_meeting", held)
    def update():
        updating.set()
        a.calendar_account_change(a.session, {"calendar_id": "cal-bram", "expected_revision": 1, "read_enabled": None, "create_enabled": None, "invite_enabled": False})
    with ThreadPoolExecutor(max_workers=2) as pool:
        committing = pool.submit(a.step, lease); assert entered.wait(3)
        changing = pool.submit(update); assert updating.wait(3) and not changing.done()
        resume.set(); committing.result(); changing.result()
    assert finish(a, lease)["decision_result"]["execution_status"] == "succeeded"


@pytest.mark.parametrize("tool,method,args", [("secmate.conversation.history.read", "_read", {"message_id": "ada-note-1", "offset": 0}),
    (MAIL, "mailbox", {"query": "lunch", "limit": 20, "cursor": None}),
    ("secmate.read_teams", "teams", {"space_id": "team-common", "query": "", "limit": 20, "cursor": None}),
    (DIRECTORY, "directory", {"query": "Bram Quill"}), (READ_CALENDAR, "read", WINDOW),
    (PROPOSE_MEETING, "_stage", MEETING), (PROPOSE, "_stage", MESSAGE)])
def test_a12_every_enabled_handler_output_is_validated(tmp_path, bundle, monkeypatch, tool, method, args):
    b = bundle.conformance(script=scripted(tool, args, "x1", "Handled."))
    a = CalendarTarget(tmp_path, b).fresh()
    a.submit(a.session, {"content": "Fictional output conformance."})
    owner = a if method.startswith("_") else a._calendar if tool == READ_CALENDAR else a._services
    monkeypatch.setattr(owner, method, lambda *args, **kwargs: ({"bad": True}, "0" * 64, "cal-ada") if tool == READ_CALENDAR else {"bad": True})
    run = a.execute(a.session)
    assert results(a)[0]["output"]["error"] in {"tool_failed", "write_not_staged"}
    assert results(a)[0]["source_refs"] == [] and run["lease"] is None
    assert run["remaining"] == (3 if tool in {PROPOSE, PROPOSE_MEETING, "secmate.conversation.history.read"} else 4)


@pytest.mark.parametrize("change", ["schema", "inherited_schema", "native", "exposure", "time", "seed", "amendment", "commit_schema"])
def test_a09_fixed_artifact_admission(tmp_path, bundle, change):
    import json
    parts = {k: json.loads(v) for k, v in bundle.artifacts}
    if change == "schema": parts["schemas"]["tools"][READ_CALENDAR]["input"] = {}
    if change == "inherited_schema": parts["schemas"]["read_input"] = {}
    if change == "native": parts["native_metadata"][READ_CALENDAR]["native_label"] = "calendar_read"
    if change == "exposure": parts["capabilities"]["enabled"].pop(READ_CALENDAR)
    if change == "time": parts["time_rules"]["resources"][0]["resource_sha256"] = "0" * 64
    if change == "seed": parts["calendar_seed"]["accounts"][0]["tenant"] = "foreign"
    if change == "amendment": parts["invitation_commit_amendment"]["version"] = "unreviewed"
    if change == "commit_schema": parts["schemas"]["invitation_commit"] = {}
    with pytest.raises(SyntheticError): CalendarBundle.from_parts(parts)
    assert not (tmp_path / "targets").exists()


def test_a09_owned_append_concurrent_collision_and_schema_references(tmp_path, bundle):
    from secmate_worker.synthetic_chatmate import Bundle, SyntheticChatMate
    old = SyntheticChatMate(tmp_path, Bundle.load())
    before = {p: p.read_bytes() for p in old.path.rglob("*") if p.is_file()}
    def append():
        try: return CalendarTarget(tmp_path, bundle)
        except SyntheticError as exc:
            assert exc.code == "target_version_collision"
    with ThreadPoolExecutor(max_workers=2) as pool:
        targets = list(pool.map(lambda _: append(), range(2)))
    assert sum(t is not None for t in targets) == 1 and all(p.read_bytes() == v for p, v in before.items())
    catalog = bundle.get("schemas")["catalog"]
    def refs(value):
        if isinstance(value, dict):
            if "$ref" in value: assert value["$ref"].startswith("#/$defs/") and value["$ref"][8:] in catalog["$defs"]
            for v in value.values(): refs(v)
        elif isinstance(value, list):
            for v in value: refs(v)
    refs(catalog)


@pytest.mark.parametrize("broken", ["missing", "empty", "forged"])
def test_a09_incomplete_predecessor_refused(tmp_path, bundle, broken):
    import json
    from secmate_worker.synthetic_chatmate import Bundle, SyntheticChatMate
    old = SyntheticChatMate(tmp_path, Bundle.load())
    path = old.path / "registration.json"
    data = json.loads(path.read_text())
    if broken == "missing": (old.path / "definitions" / "schemas.json").unlink()
    if broken == "empty": data["definition_digests"] = {}
    if broken == "forged": data["target_version"] = "other"
    path.write_text(canonical(data), encoding="utf-8")
    with pytest.raises(SyntheticError, match="unowned_target_namespace"): CalendarTarget(tmp_path, bundle)


@pytest.mark.parametrize("phase", ["calendar_read", "meeting_prepare", "preflight", "before_commit"])
def test_a17_exact_tool_timeouts(tmp_path, bundle, phase):
    b = bundle.conformance(script=scripted(READ_CALENDAR, WINDOW, "x1", "Handled.")) if phase == "calendar_read" else bundle
    fault = {"phase": phase, "call_id": "x1" if phase == "calendar_read" else "meeting-1", "mode": "timeout", "duration": 5, "occurrence": 1}
    a, run = start(tmp_path, b, faults=Phase3FaultPlan(calendar_faults=[fault]))
    if phase in {"calendar_read", "meeting_prepare"}:
        assert results(a)[0]["output"]["error"] == "tool_timeout"
    else:
        control(a, run)
        assert a.execute(a.session)["decision_result"]["error"] == "tool_timeout"
    assert not a.restricted_truth(a.session)["meeting_effects"]


def test_a17_pool_streak_and_round_exhaustion(tmp_path, bundle):
    b = bundle.conformance(script={"rounds": [round_([call(DIRECTORY, {"query": "Bram"}, "d" + str(i))]) for i in range(4)]})
    a, run = start(tmp_path / "streak", b, faults=Phase3FaultPlan(directory_unavailable=True))
    assert results(a)[-1]["output"]["error"] == "error_streak_exhausted" and run["provider_remaining"] == 5
    budget = bundle.get("budget"); budget["fake_provider_read"] = 1
    b = bundle.conformance(budget=budget, script={"rounds": [round_([call(READ_CALENDAR, WINDOW, "r1"), call(DIRECTORY, {"query": "Bram"}, "d1")])]})
    a, run = start(tmp_path / "pool", b)
    assert run["outcome"] == "Partial" and results(a)[-1]["output"]["error"] == "budget_exhausted"
    budget = bundle.get("budget"); budget["rounds"] = 1
    a, run = start(tmp_path / "round", bundle.conformance(budget=budget))
    assert run["outcome"] == "AwaitingApproval"


def test_a18_barrier_reset_immutability_and_cancel_tie(tmp_path, bundle):
    faults = Phase3FaultPlan(calendar_faults=[{"phase": "after_preflight", "call_id": None, "mode": "hold", "duration": 0, "occurrence": 1}])
    a, run = start(tmp_path, bundle, faults=faults)
    saved = control(a, run)
    held = a.execute(a.session)
    assert held["held_barrier"] == "after_preflight"
    with pytest.raises(SyntheticError, match="reset_busy"): a.reset(a.session)
    with a._store.transaction() as db:
        with pytest.raises(Exception): db.execute("DELETE FROM approvals")
    a.cancel(a.session, saved["id"])
    from secmate_worker.synthetic_chatmate.contracts import Lease
    result = finish(a, Lease(a.id, a.generation, saved["id"], held["lease"]))
    assert result["status"] == "cancelled" and not a.restricted_truth(a.session)["meeting_effects"]


@pytest.mark.parametrize("name", ["event_create", "calendar_read", "meeting_browse", "secmate.calendar.cancel", "secmate.calendar.recurrence", "secmate.action.decide"])
def test_a19_unexposed_names_cannot_dispatch(tmp_path, bundle, name):
    a, run = start(tmp_path, bundle.conformance(script=scripted(name, {}, "x1", "Unavailable.")))
    assert results(a)[0]["output"]["error"] in {"unknown_tool", "capability_disabled"}
    assert run["remaining"] == 4 and run["provider_remaining"] == 8


@pytest.mark.parametrize("extra", ["organizer_id", "recurrence", "room_id", "calendar_id", "account", "rsvp", "scheduled_at"])
def test_a19_extra_fields_rejected(tmp_path, bundle, extra):
    a, run = start(tmp_path, bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, extra: "fictional"}, "x1", "Unavailable.")))
    assert results(a)[0]["output"]["error"] == "invalid_arguments" and run["remaining"] == 4


def test_a20_offline_guard_rejects_ordinary_network():
    import socket
    for operation in (lambda: socket.getaddrinfo("example.invalid", 443), lambda: socket.create_connection(("127.0.0.1", 9)), lambda: socket.socket().connect(("192.0.2.1", 443))):
        with pytest.raises(AssertionError, match="Offline verification"): operation()


@pytest.mark.parametrize("arguments", [{"start": None, "end": WINDOW["end"], "limit": 1, "cursor": None},
    {**WINDOW, "limit": True}, {**WINDOW, "limit": 0}, {**WINDOW, "cursor": False},
    {k: v for k, v in WINDOW.items() if k != "cursor"}, {**WINDOW, "calendar_id": "cal-bram"}])
def test_t10_strict_raw_fields_and_required_nullable(tmp_path, bundle, arguments):
    a, run = start(tmp_path, bundle.conformance(script=scripted(READ_CALENDAR, arguments, "x1", "Handled.")))
    assert results(a)[0]["output"]["error"] == "invalid_arguments" and run["provider_remaining"] == 8


@pytest.mark.parametrize("incomplete", [False, True])
def test_a07_empty_no_plan_and_invalid_completion(tmp_path, bundle, incomplete):
    rounds = [round_()] if not incomplete else [round_([call()]), {**round_(text="Incomplete"), "completion": False}]
    a, run = start(tmp_path, bundle.conformance(script={"rounds": rounds}))
    assert run["status"] == "failed" and run["terminal_reason"] == ("model_protocol_error" if incomplete else "model_empty_response")
    with a._store.read() as db:
        assert all(__import__('json').loads(r[0])["status"] != "pending" for r in db.execute("SELECT payload FROM approvals"))


def test_a08_cancellation_deadline_tie_leaves_approval_pending(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    saved = control(a, run)
    lease = a.acquire(a.session)
    with a._store.transaction() as db:
        state = a._state(db); state["seconds"] = 60; a._save_state(db, state)
    a.cancel(a.session, saved["id"])
    out = a.step(lease)
    assert out["status"] == "cancelled" and out["decision_result"]["error"] == "tool_failed"
    with a._store.read() as db:
        assert a._store.approval(db, run["approval_id"])["status"] == "pending"


def test_a12_invalid_receipt_is_unknown_without_erasing_commit(tmp_path, bundle, monkeypatch):
    a, run = start(tmp_path, bundle)
    control(a, run)
    original = a._store.save_execution
    def substituted(db, execution):
        if execution["status"] == "succeeded":
            execution["receipt"]["invitation_ids"] = ["substituted-valid-id"]
        return original(db, execution)
    monkeypatch.setattr(a._store, "save_execution", substituted)
    out = a.execute(a.session)
    assert out["decision_result"]["execution_status"] == "outcome_unknown" and out["decision_result"]["receipt"] is None
    assert len(a.restricted_truth(a.session)["meeting_effects"]) == 1
