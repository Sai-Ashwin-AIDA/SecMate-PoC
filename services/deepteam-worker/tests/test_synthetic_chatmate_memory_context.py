"""Phase 4 eligibility, expiry, context placement, and refresh tests."""
import pytest
from offline_synthetic_guard import forbid_network

from secmate_worker.synthetic_chatmate.memory_phase4 import MemoryTarget
from secmate_worker.synthetic_chatmate.memory_phase4.artifacts import MemoryBundle
from secmate_worker.synthetic_chatmate.memory_phase4.contracts import Phase4FaultPlan
from secmate_worker.synthetic_chatmate.memory_phase4.context import extract
from secmate_worker.synthetic_chatmate.memory_phase4.services import active_facts, eligibility_reason
from secmate_worker.job_runtime import canonical


def test_exact_expiry_boundary_and_order():
    facts = [{"id": "old", "ordinal": 1, "created_at": "2029-10-09T09:00:10Z", "expires_at": "2030-01-07T09:00:10Z"},
             {"id": "new", "ordinal": 2, "created_at": "2030-01-07T09:00:00Z", "expires_at": "2030-04-07T09:00:00Z"}]
    assert [f["id"] for f in active_facts(facts, 9.999999)] == ["new", "old"]
    assert [f["id"] for f in active_facts(facts, 10)] == ["new"]


@pytest.mark.parametrize("profile,reason", [("shared", "shared"), ("multiparticipant", "multiparticipant"),
    ("project", "project"), ("deleted", "deleted"), ("conversation_disabled", "conversation_disabled")])
def test_ineligible_profiles_never_publish_memory(tmp_path, profile, reason):
    assessment = MemoryTarget(tmp_path).fresh(context_profile=profile)
    assessment.submit(assessment.session, {"content": "Check context."})
    lease = assessment.acquire(assessment.session); assessment.step(lease)
    snapshot = assessment.restricted_truth(assessment.session)["memory"]["snapshots"][0]["snapshot"]
    assert snapshot["status"] == "ineligible" and snapshot["reason"] == reason
    request = next(e["data"]["request"] for e in assessment.events(assessment.session) if e["type"] == "model.request_built")
    assert extract(request, assessment._bundle.get("prompt")["developer_guidance"]) is None


def test_basic_ineligibility_does_not_charge_fault_read_or_clock(tmp_path):
    faults = Phase4FaultPlan(memory={"loads": [{"round": 1, "attempt": 1, "duration": 5, "mode": "none"}],
        "controls": [], "failure_recording_unavailable": False})
    assessment = MemoryTarget(tmp_path).fresh(context_profile="shared", faults=faults)
    assessment.submit(assessment.session, {"content": "No private read."})
    assessment.step(assessment.acquire(assessment.session))
    truth = assessment.restricted_truth(assessment.session)["memory"]
    snapshot = truth["snapshots"][0]["snapshot"]
    assert (snapshot["status"], snapshot["reason"], snapshot["read_seconds"]) == ("ineligible", "shared", 0.0)
    assert truth["fault_hits"] == [] and truth["counters"]["checks_remaining"] == 8


def test_private_request_has_owned_facts_and_exactly_seven_tools(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."})
    lease = assessment.acquire(assessment.session); result = assessment.step(lease)
    assert result["status"] == "running"
    request = next(e["data"]["request"] for e in assessment.events(assessment.session) if e["type"] == "model.request_built")
    memory = extract(request, assessment._bundle.get("prompt")["developer_guidance"])
    assert [item["fact_id"] for item in memory["facts"]] == ["mem-ada-tea", "mem-ada-marker", "mem-ada-expiring"]
    assert len(request["tools"]) == 7 and all(t["name"] != "secmate.memory.control" for t in request["tools"])


def test_authenticated_memory_boundary_rejects_foreign_before_read(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    accepted = assessment.submit(assessment.session, {"content": "Boundary."})
    truth = assessment.restricted_truth(assessment.session)["memory"]
    context = truth["contexts"][0]
    eligibility = {"context": context, "memory_owner": "subject-ada", "requested_by": "subject-ada",
        "run_memory_disabled": False, "subsystem_enabled": True}
    own = assessment.memory_boundary(assessment.session, {"requested_owner": "subject-ada", "eligibility": eligibility})
    foreign = assessment.memory_boundary(assessment.session, {"requested_owner": "subject-bram", "eligibility": eligibility})
    unknown = assessment.memory_boundary(assessment.session, {"requested_owner": "subject-unknown", "eligibility": eligibility})
    assert own["status"] == "loaded" and own["payload"]["owner"] == "subject-ada"
    assert foreign == unknown and foreign["error"] == "resource_unavailable"


def test_forget_refresh_removes_only_active_slice(tmp_path):
    assessment = MemoryTarget(tmp_path).fresh()
    assessment.submit(assessment.session, {"content": "Check context."})
    lease = assessment.acquire(assessment.session); assessment.step(lease)
    assessment.memory_control(assessment.session, canonical({"operation": "forget", "expected_revision": 1, "fact_id": "mem-ada-tea"}))
    assessment.step(lease)
    requests = [e["data"]["request"] for e in assessment.events(assessment.session) if e["type"] == "model.request_built"]
    guidance = assessment._bundle.get("prompt")["developer_guidance"]
    assert "mem-ada-tea" in str(extract(requests[0], guidance))
    assert "mem-ada-tea" not in str(extract(requests[-1], guidance))
    assert "mem-ada-marker" in str(extract(requests[-1], guidance))


def test_retry_gets_distinct_fresh_snapshot_and_request(tmp_path):
    faults = Phase4FaultPlan(model=[{"round": 1, "attempt": 1, "duration": 8, "error": "model_transport_unavailable", "after_output": False}],
        memory={"loads": [{"round": 1, "attempt": 2, "duration": 1, "mode": "none"}], "controls": [], "failure_recording_unavailable": False})
    assessment = MemoryTarget(tmp_path).fresh(faults=faults)
    assessment.submit(assessment.session, {"content": "Retry context."}); assessment.step(assessment.acquire(assessment.session))
    truth = assessment.restricted_truth(assessment.session)["memory"]
    assert [(s["snapshot"]["round"], s["snapshot"]["attempt"]) for s in truth["snapshots"]] == [(1, 1), (1, 2)]
    assert truth["snapshots"][1]["snapshot"]["previous_snapshot_id"] == truth["snapshots"][0]["snapshot"]["snapshot_id"]
    events = assessment.events(assessment.session)
    requests = [e for e in events if e["type"] == "model.request_built"]
    bounds = [e for e in events if e["type"] == "memory.request_bound"]
    assert len(requests) == len(bounds) == 2 and [b["data"]["request_event_id"] for b in bounds] == [r["event_id"] for r in requests]
    memory = extract(requests[1]["data"]["request"], assessment._bundle.get("prompt")["developer_guidance"])
    assert "mem-ada-expiring" not in [f["fact_id"] for f in memory["facts"]]


def test_load_timeout_publishes_no_stale_memory(tmp_path):
    faults = Phase4FaultPlan(memory={"loads": [{"round": 1, "attempt": 1, "duration": 5, "mode": "none"}], "controls": [], "failure_recording_unavailable": False})
    assessment = MemoryTarget(tmp_path).fresh(faults=faults)
    assessment.submit(assessment.session, {"content": "Timeout context."}); assessment.step(assessment.acquire(assessment.session))
    snapshot = assessment.restricted_truth(assessment.session)["memory"]["snapshots"][0]["snapshot"]
    request = next(e["data"]["request"] for e in assessment.events(assessment.session) if e["type"] == "model.request_built")
    assert snapshot["status"] == "unavailable" and snapshot["reason"] == "memory_timeout"
    assert extract(request, assessment._bundle.get("prompt")["developer_guidance"]) is None
