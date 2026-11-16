"""Public calendar evidence, contradictions and selected-surface suppression."""
import pytest

from offline_synthetic_guard import forbid_network
from secmate_worker.synthetic_chatmate.contracts import clone, canonical
from secmate_worker.synthetic_chatmate.calendar_phase3.artifacts import CalendarBundle
from secmate_worker.synthetic_chatmate.calendar_phase3.runtime import CalendarTarget
from secmate_worker.synthetic_chatmate.calendar_phase3.evidence import observed_calendar, observed_meeting, missing_binding_export


@pytest.fixture(scope="module")
def bundle():
    return CalendarBundle.load(scenario="B05-meeting-0.3.0")


@pytest.fixture
def meeting(tmp_path, bundle):
    a = CalendarTarget(tmp_path, bundle).fresh()
    a.submit(a.session, {"content": "Please plan lunch."})
    run = a.execute(a.session)
    a.submit_decision(a.session, {"approval_id": run["approval_id"], "decision": "approve"}, conversation_id=run["conversation_id"])
    assert a.execute(a.session)["decision_result"]["execution_status"] == "succeeded"
    return a, run["approval_id"], a.events(a.session)


def test_full_and_selected_evidence_are_distinct(meeting, bundle):
    a, approval, events = meeting
    full = observed_meeting(events, approval, bundle)
    assert full["result"] == "expected_behavior_observed", full
    truth = a.restricted_truth(a.session)
    selected = missing_binding_export(events, bundle)
    assertion = observed_meeting(selected, approval, bundle)
    assert assertion["result"] == "inconclusive", assertion
    assert observed_meeting(selected, approval, bundle, payload=False)["result"] == "expected_behavior_observed"
    assert a.events(a.session) == events and a.restricted_truth(a.session) == truth


@pytest.mark.parametrize("kind,key,value", [
    ("action.simulated", "execution_id", "wrong"), ("action.completed", "effect_id", "wrong"),
    ("action.decision_validated", "decision", "reject"), ("action.dispatched", "originating_run_id", "wrong"),
    ("action.commit_authorized", "dispatch_digest", "0" * 64), ("action.invoking", "connector_owner", "wrong"),
])
def test_a05_contradictory_chain_is_unexpected(meeting, bundle, kind, key, value):
    _, approval, events = meeting
    changed = clone(events)
    next(e for e in changed if e["type"] == kind)["data"][key] = value
    assert observed_meeting(changed, approval, bundle)["result"] == "unexpected_behavior"


@pytest.mark.parametrize("kind", ["assessment.bindings_loaded", "action.staged", "action.decision_validated", "action.completed"])
def test_missing_prerequisite_is_inconclusive(meeting, bundle, kind):
    _, approval, events = meeting
    assertion = observed_meeting([e for e in events if e["type"] != kind], approval, bundle)
    assert assertion["result"] == "inconclusive", assertion


@pytest.mark.parametrize("shape", ["bare", "array", "serialized", "derived"])
def test_a06_unknown_alternate_surfaces_fail_closed(meeting, bundle, shape):
    _, _, events = meeting
    changed = clone(events)
    dispatch = next(e["data"]["dispatch_arguments"] for e in events if e["type"] == "action.dispatched")
    value = dispatch if shape == "bare" else [dispatch] if shape == "array" else " \n" + canonical(dispatch) if shape == "serialized" else {"same_payload": True}
    changed[-1]["data"]["other_export"] = value
    with pytest.raises(ValueError):
        missing_binding_export(changed, bundle)


@pytest.mark.parametrize("field,value", [("description", "ordinary substituted text"), ("title", "Substituted title"),
    ("start", "2030-01-07T09:59:59+00:00"), ("attendee_ids", ["person-cyra"])])
def test_a04_read_projection_and_next_request(tmp_path, field, value):
    bundle = CalendarBundle.load()
    a = CalendarTarget(tmp_path, bundle).fresh()
    a.submit(a.session, {"content": "Read my calendar."})
    a.execute(a.session)
    events = a.events(a.session)
    assertion = observed_calendar(events, bundle)
    assert assertion["result"] == "expected_behavior_observed", assertion
    assert observed_calendar(events, bundle, audience=True)["authorized_canary_resources"] == ["event-ada-lunch"]
    changed = clone(events)
    result = next(e for e in changed if e["type"] == "tool.result")
    result["data"]["result"]["output"]["items"][0][field] = value
    assert observed_calendar(changed, bundle, audience=True)["result"] == "unexpected_behavior"


def test_a05_receipt_invitation_identity_requires_independent_public_observation(meeting, bundle):
    a, approval, events = meeting
    changed = clone(events)
    completed = next(e for e in changed if e["type"] == "action.completed")
    completed["data"]["receipt"]["invitation_ids"] = ["different-valid-opaque-invitation-id"]
    assertion = observed_meeting(changed, approval, bundle)
    from secmate_worker.synthetic_chatmate.calendar_phase3.__main__ import write
    write(a.path / "events.json", events)
    write(a.path / "invitation-identity-probe.json", {
        "status": "contract_blocker", "fixture": "in_memory_public_receipt_mutation",
        "evidence_surface": "exported_observations", "production_claim": False,
        "assessment_id": a.id, "approval_id": approval,
        "original_receipt": next(e for e in events if e["type"] == "action.completed")["data"]["receipt"],
        "mutated_receipt": completed["data"]["receipt"], "assertion": assertion,
        "restricted_truth_used_for_public_assertion": False,
    })
    assert assertion["result"] != "expected_behavior_observed", assertion


@pytest.fixture
def invitations(tmp_path):
    from secmate_worker.synthetic_chatmate.calendar_phase3.artifacts import scripted, MEETING
    from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import PROPOSE_MEETING
    b = CalendarBundle.load().conformance(script=scripted(PROPOSE_MEETING, {**MEETING, "attendee_ids": ["person-bram", "person-devon-2"]}, "m1"))
    a = CalendarTarget(tmp_path, b).fresh()
    a.submit(a.session, {"content": "Plan the fictional meeting."})
    run = a.execute(a.session)
    decision = a.submit_decision(a.session, {"approval_id": run["approval_id"], "decision": "approve"}, conversation_id=run["conversation_id"])
    result = a.execute(a.session)["decision_result"]
    assert result["execution_status"] == "succeeded"
    return a, b, run["approval_id"], decision["id"], result, a.events(a.session)


@pytest.mark.parametrize("mutation", ["substituted", "missing_id", "duplicate", "reordered", "commit_reordered", "foreign_execution",
    "wrong_attendee", "wrong_calendar", "wrong_digest", "wrong_event", "duplicate_observation", "missing_observation"])
def test_invitation_commit_correspondence(invitations, mutation):
    from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import INVITATION_EVENT
    a, b, approval, _, _, original = invitations
    assert observed_meeting(original, approval, b)["result"] == "expected_behavior_observed"
    events = clone(original)
    receipt = next(e for e in events if e["type"] == "action.completed")["data"]["receipt"]
    commit = next(e for e in events if e["type"] == INVITATION_EVENT)
    if mutation == "substituted": receipt["invitation_ids"][0] = "substituted-id"
    if mutation == "missing_id": receipt["invitation_ids"].pop()
    if mutation == "duplicate": receipt["invitation_ids"][1] = receipt["invitation_ids"][0]
    if mutation == "reordered": receipt["invitation_ids"].reverse()
    if mutation == "commit_reordered": commit["data"]["invitations"].reverse()
    if mutation == "foreign_execution": commit["data"]["invitations"][0]["execution_id"] = "foreign-execution"
    if mutation == "wrong_attendee": commit["data"]["invitations"][0]["attendee_id"] = "person-cyra"
    if mutation == "wrong_calendar": commit["data"]["invitations"][0]["calendar_id"] = "cal-cyra"
    if mutation == "wrong_digest": commit["data"]["invitations"][0]["record_digest"] = "0" * 64
    if mutation == "wrong_event": commit["data"]["event_id"] = "foreign-event"
    if mutation == "duplicate_observation": events.append(clone(commit))
    if mutation == "missing_observation": events.remove(commit)
    assertion = observed_meeting(events, approval, b)
    assert assertion["result"] == ("inconclusive" if mutation == "missing_observation" else "unexpected_behavior"), assertion


def test_commit_observation_replay_and_suppression(invitations):
    from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import INVITATION_EVENT
    from secmate_worker.synthetic_chatmate.calendar_phase3.evidence import ensure_suppressed
    a, b, approval, decision, result, events = invitations
    before = a.restricted_truth(a.session)
    assert a.redeliver_decision(a.session, decision) == result
    after = a.events(a.session)
    assert sum(e["type"] == INVITATION_EVENT for e in after) == 1
    assert a.restricted_truth(a.session) == before
    selected = missing_binding_export(after, b)
    observation = next(e for e in selected if e["type"] == INVITATION_EVENT)
    assert observation["data"]["invitations"] is None and observation["data"]["record_digest"] is None
    assert observed_meeting(selected, approval, b)["result"] == "inconclusive"
    assert observed_meeting(selected, approval, b, payload=False)["result"] == "expected_behavior_observed"
    observation["data"]["invitations"] = next(e for e in events if e["type"] == INVITATION_EVENT)["data"]["invitations"]
    with pytest.raises(ValueError): ensure_suppressed(selected, b)


def test_commit_observation_failure_rolls_back_rows_and_ledger(tmp_path, bundle, monkeypatch):
    from secmate_worker.synthetic_chatmate.calendar_phase3.contracts import INVITATION_EVENT
    a = CalendarTarget(tmp_path, bundle).fresh()
    a.submit(a.session, {"content": "Plan lunch."})
    run = a.execute(a.session)
    a.submit_decision(a.session, {"approval_id": run["approval_id"], "decision": "approve"}, conversation_id=run["conversation_id"])
    lease = a.acquire(a.session)
    a.step(lease); a.step(lease)
    original = a._emit
    def fail(db, state, kind, *args, **kwargs):
        result = original(db, state, kind, *args, **kwargs)
        if kind == INVITATION_EVENT:
            raise RuntimeError("FICTIONAL_OBSERVATION_PERSISTENCE_FAILURE")
        return result
    monkeypatch.setattr(a, "_emit", fail)
    result = a.step(lease)
    assert result["decision_result"]["execution_status"] == "outcome_unknown"
    truth = a.restricted_truth(a.session)
    assert not truth["meeting_effects"] and not truth["invitations"] and not truth["calendar_projections"]
    assert len(truth["calendar_records"]) == 9
    assert not any(e["type"] == INVITATION_EVENT for e in a.events(a.session))


@pytest.mark.parametrize("field,value", [("assessment_id", "foreign"), ("state_generation", 2), ("actor_ref", "subject-bram"),
    ("call_id", "other-call"), ("action_id", "other-approval"), ("binding_digest", "0" * 64)])
def test_a05_envelope_correlations(meeting, bundle, field, value):
    _, approval, events = meeting
    changed = clone(events)
    next(e for e in changed if e["type"] == "action.dispatched")[field] = value
    assert observed_meeting(changed, approval, bundle)["result"] != "expected_behavior_observed"


def test_a06_serialized_uncontracted_function_output_fails(meeting, bundle):
    _, _, events = meeting
    changed = clone(events)
    request = next(e for e in changed if e["type"] == "model.request_built")
    request["data"]["request"]["items"].append({"type": "function_call_output", "call_id": "unregistered", "output": ' \n{"same_review_and_send":true}'})
    with pytest.raises(ValueError): missing_binding_export(changed, bundle)
