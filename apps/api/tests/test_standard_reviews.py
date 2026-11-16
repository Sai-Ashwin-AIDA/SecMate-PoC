import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from secmate_api import standard_reviews as reviews, deepteam_runs as runs, jobs, main, reporting
from secmate_api.config import Settings
from secmate_api.contracts import DeepTeamRunRecord
from secmate_api.run_store import digest


@pytest.fixture(scope="module")
def synthetic_audit():
    root = Path(__file__).resolve().parents[3]
    worker = root / "services/deepteam-worker"
    environment = {key: value for key, value in os.environ.items() if key not in {"GROQ_API_KEY", "GROQ_CRITIC_API_KEY", "OPENROUTER_API_KEY"}}
    script = "import sys,json; sys.path.insert(0,'tests'); from standard_review_test_data import audit_fixture; print(json.dumps(audit_fixture()))"
    return json.loads(subprocess.check_output([str(worker / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")), "-c", script],
                                             cwd=worker, env=environment, text=True, timeout=30))


@pytest.fixture
def parent(tmp_path, monkeypatch, synthetic_audit):
    audit = json.loads(json.dumps(synthetic_audit))
    root = tmp_path / "runs"
    monkeypatch.setattr(runs, "RUN_ROOT", root)
    monkeypatch.setattr(runs, "API_ROOT", tmp_path / "api")
    monkeypatch.setattr(runs, "RUN_LOCK", root / "active-run.lock")
    monkeypatch.setattr(runs, "_runs", {})
    monkeypatch.setattr(runs, "_processes", {})
    settings = Settings("synthetic-attacker", "synthetic-router", 45, groq_critic_api_key="synthetic-critic")
    monkeypatch.setattr(reviews, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "dispatch", lambda *args, **kwargs: None)
    record = DeepTeamRunRecord(run_id=audit["run_id"], status="COMPLETED", final_status="RESISTED", created_at="2026-11-06T00:00:00Z",
        completed_at="2026-11-06T00:01:00Z", scenario="socmate-tier1-permission-escalation", vulnerability="Excessive Agency / Permissions",
        attack="Permission Escalation", artifact_available=True, max_total_tokens=75000, logs=[])
    directory = root / record.run_id / audit["manifest"]["run_id"]
    directory.mkdir(parents=True)
    for key, name in {"manifest": "manifest.json", "evidence": "evidence.json", "deepteam_risk": "deepteam-risk.json", "summary": "summary.json"}.items():
        (directory / name).write_text(json.dumps(audit[key]), encoding="ascii")
    runs._persist(record)
    runs._runs[record.run_id] = record
    return record, settings


@pytest.fixture
def offline_worker(monkeypatch):
    real = subprocess.Popen
    state = {"mode": "success", "launches": 0, "allow_child": False}
    def launch(command, **kwargs):
        if command[1:3] == ["-m", "secmate_worker.catalog_export"]:
            return real(command, **kwargs)
        state["launches"] += 1
        if command[1:5] == ["-m", "secmate_worker.job_runtime", "-m", "secmate_worker.single_attack"]:
            assert state["allow_child"], "A linked Start must be explicitly requested by this test"
            assert "--generation-context" in command
            kwargs["env"].update(GROQ_API_KEY="synthetic-attacker", OPENROUTER_API_KEY="synthetic-router")
            script = """
import sys,json,os,runpy
from dataclasses import replace
from pathlib import Path
import httpx
sys.path.insert(0,'tests')
from test_deepteam_runner import FakeConstruct,FakeRisk
from secmate_worker import deepteam_runner as runner, model_clients
command=json.loads(sys.argv[1]); count=0
async def handler(request):
    global count
    count+=1
    Path(os.environ['SECMATE_JOB_DIR'],'fake-child-http-count.txt').write_text(str(count))
    payload=json.loads(request.content)
    assert payload['model']=='nvidia/nemotron-3.5-super-vl:free'
    if 'tools' in payload:
        content='I require trusted application approval.'
    else:
        evidence=json.loads(payload['messages'][-1]['content'].split('EVIDENCE_JSON: ',1)[1])
        content=json.dumps({'deviation_score':0,'confidence':0.95,'evidence_references':evidence['valid_evidence_references'][:1],
            'policy_references':evidence['valid_policy_references'][:1],'reasoning':'Synthetic target retained the boundary.','missing_evidence':[]})
    return httpx.Response(200,json={'choices':[{'message':{'content':content}}], 'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}})
original=model_clients.StructuredModelClients
class Clients(original):
    def __init__(self,*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(handler)
        super().__init__(*args,**kwargs)
runner.StructuredModelClients=Clients
class Engine(FakeConstruct):
    def __init__(self,**kwargs):
        assert sum('UNTRUSTED_PARENT_EVIDENCE_JSON' in item for item in kwargs['generation_guidelines'])==1
        super().__init__(**kwargs)
class RedTeamer:
    def __init__(self,**kwargs): pass
    async def a_red_team(self,**kwargs):
        await kwargs['model_callback']('A fresh synthetic approval-boundary probe.')
        return FakeRisk()
attack=runner.resolve_attack_profile; vulnerability=runner.resolve_vulnerability_profile
runner.resolve_attack_profile=lambda id:replace(attack(id),builder=lambda *args:FakeConstruct())
runner.resolve_vulnerability_profile=lambda id:replace(vulnerability(id),builder=lambda *args:FakeConstruct())
runner.AttackEngine=Engine; runner.RedTeamer=RedTeamer
sys.argv=['job_runtime',*command]
runpy.run_module('secmate_worker.job_runtime',run_name='__main__',alter_sys=True)
"""
            return real([command[0], "-c", script, json.dumps(command[3:])], **kwargs)
        assert command[1:5] == ["-m", "secmate_worker.job_runtime", "-m", "secmate_worker.standard_review"]
        assert kwargs["env"]["GROQ_CRITIC_API_KEY"] == "synthetic-critic"
        assert "GROQ_API_KEY" not in kwargs["env"] and "OPENROUTER_API_KEY" not in kwargs["env"]
        script = """
import json,sys,os,runpy
from pathlib import Path
import httpx
from secmate_worker import model_clients
command=json.loads(sys.argv[1]); mode=sys.argv[2]
source=json.loads(Path(command[command.index('--input')+1]).read_text())
count=0
async def handler(request):
    global count
    count+=1
    Path(os.environ['SECMATE_JOB_DIR'],'fake-http-count.txt').write_text(str(count))
    assert request.headers['authorization']=='Bearer synthetic-critic'
    assert json.loads(request.content)['max_completion_tokens']==256
    if mode=='rate-limit': return httpx.Response(429,json={'error':{'code':'rate_limit_exceeded'}})
    if mode=='timeout': raise httpx.ReadTimeout('private synthetic error',request=request)
    choices=[{'attack_profile_id': item['id'],'priority':90-i*10} for i,item in enumerate(source['allowed_methods'][:1 if mode=='single' else 2])]
    if mode=='empty': choices=[]
    return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'recommendations':choices})}}], 'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}})
original=model_clients.StructuredModelClients
class Clients(original):
    def __init__(self,*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(handler)
        super().__init__(*args,**kwargs)
model_clients.StructuredModelClients=Clients
sys.argv=['job_runtime',*command]
runpy.run_module('secmate_worker.job_runtime',run_name='__main__',alter_sys=True)
"""
        return real([command[0], "-c", script, json.dumps(command[3:]), state["mode"]], **kwargs)
    monkeypatch.setattr(subprocess, "Popen", launch)
    return state


def test_managed_standard_review_is_saved_once_and_parent_evidence_is_immutable(parent, offline_worker):
    record, settings = parent
    before = digest(runs.get_deepteam_audit(record.run_id).model_dump(mode="json"))
    accepted = reviews.start_review(settings, record.run_id)
    assert accepted.critic_attempts == 1 and accepted.status == "COMPLETED"
    assert reviews.review_view(record.run_id)["status"] == "RUNNING"
    reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    assert view["status"] == "COMPLETED", json.dumps({"view": view, "code": runs.get_deepteam_run(record.run_id).critic_error_code,
        "artifact": runs._read_json(reviews._directory(runs.get_deepteam_run(record.run_id)) / "review.json")}, indent=2)
    assert len(view["review"]["recommendations"]) == 2
    assert view["review"]["budget"]["provider_calls_attempted"] == 1
    assert view["review"]["budget"]["tokens_consumed"] == 130
    assert view["review_sha256"] == digest(view["review"])
    assert digest(runs.get_deepteam_audit(record.run_id).model_dump(mode="json")) == before
    assert runs.get_deepteam_run(record.run_id).final_status == "RESISTED"
    assert reporting.socmate_report_data(record.run_id)["standard_review"]["status"] == "COMPLETED"
    client = TestClient(main.app)
    for _ in range(2):
        assert client.get(f"/api/v1/deepteam-runs/{record.run_id}/standard-review").json()["status"] == "COMPLETED"
    runs._runs.clear()  # Reload the persisted parent and review without inference.
    runs._load_records()
    assert reviews.review_view(record.run_id)["status"] == "COMPLETED"
    reviews.start_review(settings, record.run_id)
    reviews.execute_review(record.run_id, settings)  # stale duplicate dispatch
    assert offline_worker["launches"] == 1
    assert reviews.review_view(record.run_id)["status"] == "COMPLETED"
    job = reviews._job(runs.get_deepteam_run(record.run_id))
    directory = jobs.JobLedger(runs.RUN_LOCK).root / job["directory_name"]
    assert (directory / "fake-http-count.txt").read_text() == "1"


def test_expanded_review_is_unavailable_and_budget_projection_fails_before_dispatch(parent, monkeypatch):
    record, settings = parent
    runs._runs[record.run_id] = record.model_copy(update={"execution_mode": "ADAPTIVE", "max_paths": 2})
    assert reviews.review_view(record.run_id)["status"] == "NOT_APPLICABLE"
    with pytest.raises(reviews.StandardReviewError): reviews.start_review(settings, record.run_id)
    runs._runs[record.run_id] = record
    monkeypatch.setattr(reviews, "estimated_input_tokens", lambda _: 4001)
    assert reviews.review_view(record.run_id)["status"] == "UNAVAILABLE"
    with pytest.raises(reviews.StandardReviewError, match="budget"): reviews.start_review(settings, record.run_id)
    assert jobs.JobLedger(runs.RUN_LOCK).active() == []


@pytest.mark.parametrize("mode", ["empty", "single"])
def test_new_reviews_require_at_least_one_next_method(parent, offline_worker, mode):
    record, settings = parent
    offline_worker["mode"] = mode
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    if mode == "empty":
        assert view["status"] == "FAILED" and view["can_retry"]
        assert view["review"] is None
    else:
        assert view["status"] == "COMPLETED"
        assert view["review"]["schema_version"] == "socmate-standard-review-v2"
        assert len(view["review"]["recommendations"]) == 1
    assert offline_worker["launches"] == 1
    assert runs.get_deepteam_run(record.run_id).final_status == "RESISTED"


def test_legacy_empty_review_remains_readable_after_policy_upgrade(parent, offline_worker, monkeypatch):
    record, settings = parent
    original = reviews._source
    monkeypatch.setattr(reviews, "_source", lambda record, schema_version="socmate-standard-review-v1": original(record, schema_version=schema_version))
    offline_worker["mode"] = "empty"
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    assert view["status"] == "COMPLETED"
    assert view["review"]["schema_version"] == "socmate-standard-review-v1"
    assert view["review"]["recommendations"] == []
    assert reviews.review_view(record.run_id)["review_sha256"] == view["review_sha256"]
    assert offline_worker["launches"] == 1


def test_no_unused_methods_is_unavailable_before_inference(parent, monkeypatch):
    from types import SimpleNamespace
    record, settings = parent
    profiles = reviews.get_deepteam_catalog().attack_profiles
    used = next(profile for profile in profiles if profile.id == record.attack_profile_id)
    monkeypatch.setattr(reviews, "get_deepteam_catalog", lambda: SimpleNamespace(attack_profiles=[used]))
    assert reviews.review_view(record.run_id)["status"] == "UNAVAILABLE"
    with pytest.raises(reviews.StandardReviewError, match="No unused applicable"):
        reviews.start_review(settings, record.run_id)
    assert jobs.JobLedger(runs.RUN_LOCK).active() == []


def test_definitive_failure_allows_only_one_explicit_retry(parent, offline_worker):
    record, settings = parent
    offline_worker["mode"] = "rate-limit"
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    assert reviews.review_view(record.run_id)["can_retry"] is True
    with pytest.raises(reviews.StandardReviewError): reviews.start_review(settings, record.run_id)
    reviews.start_review(settings, record.run_id, retry=True); reviews.execute_review(record.run_id, settings)
    assert reviews.review_view(record.run_id)["attempts"] == 2
    assert reviews.review_view(record.run_id)["can_retry"] is False
    assert offline_worker["launches"] == 2
    with pytest.raises(reviews.StandardReviewError): reviews.start_review(settings, record.run_id, retry=True)


def test_legacy_strict_schema_failure_allows_one_migration_retry(parent, offline_worker):
    record, settings = parent
    offline_worker["mode"] = "rate-limit"
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    reviews.start_review(settings, record.run_id, retry=True); reviews.execute_review(record.run_id, settings)
    failed = runs.get_deepteam_run(record.run_id)
    path = runs.RUN_ROOT / record.run_id / "standard-reviews" / failed.critic_review_id / "review.json"
    payload = json.loads(path.read_text(encoding="ascii"))
    payload["error_code"] = "INVALID_JSON"
    path.write_text(json.dumps(payload), encoding="ascii")

    assert reviews.review_view(record.run_id)["can_retry"] is True


def test_uncertain_provider_completion_requires_ack_before_explicit_retry(parent, offline_worker, monkeypatch):
    record, settings = parent
    offline_worker["mode"] = "timeout"
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    assert view["status"] == "UNCERTAIN" and not view["can_retry"]
    ledger = jobs.JobLedger(runs.RUN_LOCK)
    ledger.reconcile()
    assert ledger.get(view["job_id"])["state"] == "UNCERTAIN"
    monkeypatch.setattr(jobs, "_epoch", "synthetic-restarted-controller")
    runs._runs.clear()
    runs._load_records()
    ledger = jobs.JobLedger(runs.RUN_LOCK)
    ledger.reconcile({"CRITIC": runs.RUN_ROOT})
    assert reviews.review_view(record.run_id)["status"] == "UNCERTAIN"
    with pytest.raises(reviews.StandardReviewError): reviews.start_review(settings, record.run_id, retry=True)
    ledger.resolve_uncertain(view["job_id"], True)
    assert reviews.review_view(record.run_id)["can_retry"] is True
    assert offline_worker["launches"] == 1


def test_review_snapshot_redacts_captured_secrets_but_preserves_verified_target(parent):
    record, settings = parent
    audit, _ = reviews._verified_audit(record)
    response = audit["evidence"]["paths"][0]["turns"][0]
    response["target_response"] = f"{settings.groq_critic_api_key} user@example.com gsk_12345678901234567890"
    snapshot = reviews._redacted_snapshot(audit)
    text = snapshot["evidence"]["paths"][0]["turns"][0]["target_response"]
    assert text == "<redacted> <redacted> <redacted>"
    assert reviews.target_model_fingerprint(snapshot["manifest"]["campaign"]) == reviews.target_model_fingerprint(audit["manifest"]["campaign"])
    assert response["target_response"] != text


def test_linked_draft_makes_no_calls_and_start_revalidates_immutable_source(parent, offline_worker):
    record, settings = parent
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    recommendation = view["review"]["recommendations"][0]
    draft = reviews.create_linked_draft(record.run_id, view["review_id"], recommendation["attack_profile_id"])
    assert draft.status == "DRAFT" and draft.final_status is None and draft.critic_attempts == 0
    assert reviews.create_linked_draft(record.run_id, view["review_id"], recommendation["attack_profile_id"]).run_id == draft.run_id
    assert draft.run_id not in {run.run_id for run in runs.list_deepteam_runs()}
    assert offline_worker["launches"] == 1
    original = draft.linked_context
    for changed in ({"attack_profile_id": record.attack_profile_id}, {"target_profile_version": "changed"},
                    {"execution_mode": "ADAPTIVE", "max_paths": 2}):
        runs._runs[draft.run_id] = draft.model_copy(update=changed)
        with pytest.raises(reviews.StandardReviewError):
            reviews.start_linked_draft(settings, draft.run_id, 100000)
    runs._runs[draft.run_id] = draft.model_copy(update={"linked_context": original.model_copy(update={"review_sha256": "0" * 64})})
    with pytest.raises(reviews.StandardReviewError): reviews.start_linked_draft(settings, draft.run_id, 100000)
    runs._runs[draft.run_id] = draft
    queued = reviews.start_linked_draft(settings, draft.run_id, 100000)
    assert queued.status == "QUEUED" and queued.linked_context == original
    with pytest.raises(reviews.StandardReviewError): reviews.start_linked_draft(settings, draft.run_id, 100000)
    assert offline_worker["launches"] == 1
    assert runs.get_deepteam_run(record.run_id).final_status == "RESISTED"


def test_linked_start_http_replays_lost_ack_without_duplicate_dispatch(parent, offline_worker, monkeypatch):
    record, _ = parent
    settings = reviews.get_settings()
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    draft = reviews.create_linked_draft(record.run_id, view["review_id"], view["review"]["recommendations"][0]["attack_profile_id"])
    dispatches = []
    monkeypatch.setattr(jobs, "dispatch", lambda *args, **kwargs: dispatches.append(args))
    client = TestClient(main.app)
    path = f"/api/v1/deepteam-runs/{draft.run_id}/start"
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "linked-start-lost-ack"}
    first = client.post(path, json={"max_total_tokens": 75000}, headers=headers)
    second = client.post(path, json={"max_total_tokens": 75000}, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(dispatches) == 1 and offline_worker["launches"] == 1
    assert client.post(path, json={"max_total_tokens": 100000}, headers=headers).status_code == 409


def test_linked_start_rejects_changed_catalog_and_parent_evidence(parent, offline_worker, monkeypatch):
    record, settings = parent
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    draft = reviews.create_linked_draft(record.run_id, view["review_id"], view["review"]["recommendations"][0]["attack_profile_id"])
    with monkeypatch.context() as scoped:
        def unavailable(*args):
            raise ValueError("The frozen method is no longer applicable")
        scoped.setattr(reviews, "validate_profile_selection", unavailable)
        with pytest.raises(ValueError, match="no longer applicable"):
            reviews.start_linked_draft(settings, draft.run_id, 75000)
    audit = runs.get_deepteam_audit(record.run_id).model_dump(mode="json")
    path = runs.RUN_ROOT / record.run_id / audit["manifest"]["run_id"] / "evidence.json"
    evidence = json.loads(path.read_text())
    evidence["paths"][0]["turns"][0]["target_response"] = "Changed synthetic evidence"
    path.write_text(json.dumps(evidence), encoding="ascii")
    with pytest.raises(ValueError):
        reviews.start_linked_draft(settings, draft.run_id, 75000)
    assert runs.get_deepteam_run(draft.run_id).status == "DRAFT"
    assert offline_worker["launches"] == 1


def test_review_post_confirmation_and_idempotent_acceptance(parent):
    record, _ = parent
    client = TestClient(main.app)
    path = f"/api/v1/deepteam-runs/{record.run_id}/standard-review"
    assert client.post(path, json={}).status_code == 403
    headers = {"X-SecMate-Local-Run": "confirmed", "Idempotency-Key": "standard-review-test-key"}
    first = client.post(path, json={"retry": False}, headers=headers)
    second = client.post(path, json={"retry": False}, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["critic_review_id"] == second.json()["critic_review_id"]
    assert runs.get_deepteam_run(record.run_id).critic_attempts == 1
    assert client.post(path, json={"retry": True}, headers=headers).status_code == 409


def test_review_cancel_does_not_cancel_the_completed_parent_or_start_inference(parent, offline_worker):
    record, settings = parent
    reviews.start_review(settings, record.run_id)
    job_id = reviews.review_view(record.run_id)["job_id"]
    response = TestClient(main.app).post(f"/api/v1/jobs/{job_id}/cancel", headers={"X-SecMate-Local-Run": "confirmed"})
    assert response.status_code == 200
    reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    assert view["status"] == "CANCELLED" and view["can_retry"]
    assert runs.get_deepteam_run(record.run_id).status == "COMPLETED"
    assert runs.get_deepteam_run(record.run_id).final_status == "RESISTED"
    assert offline_worker["launches"] == 0


def test_sealed_standard_review_recovers_after_projection_loss_without_a_new_call(parent, offline_worker, monkeypatch):
    record, settings = parent
    original_replace, failed = os.replace, []
    def fail_once(source, target):
        if Path(target).name == "review.json" and not failed:
            failed.append(True)
            raise OSError("Synthetic interrupted projection")
        return original_replace(source, target)
    monkeypatch.setattr(os, "replace", fail_once)
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    ledger = jobs.JobLedger(runs.RUN_LOCK)
    previous = reviews._job(runs.get_deepteam_run(record.run_id))
    assert previous["state"] == "RESULT_READY"
    monkeypatch.setattr(jobs, "_epoch", "synthetic-restarted-controller")
    ledger.reconcile({"SYNTHETIC": runs.RUN_ROOT, "GENERATION": runs.RUN_ROOT / "not-the-source", "CRITIC": (runs.RUN_ROOT, runs.RUN_ROOT / "not-the-source")})
    restored = ledger.get(previous["job_id"])
    assert restored["state"] == "RESULT_READY"
    session = jobs.JobSession(ledger, restored)
    jobs._sessions[(str(runs.RUN_LOCK.resolve()), record.run_id)] = session
    reviews.execute_review(record.run_id, settings)
    assert reviews.review_view(record.run_id)["status"] == "COMPLETED"
    assert offline_worker["launches"] == 1


def test_deterministic_compromise_without_judge_is_eligible(parent):
    record, _ = parent
    audit = runs.get_deepteam_audit(record.run_id).model_dump(mode="json")
    audit["run_id"] = "api-run-333333333333"
    audit["summary"]["final_status"] = "COMPROMISED"
    audit["evidence"]["paths"][0]["status"] = "COMPROMISED"
    audit["evidence"]["paths"][0]["oracle_results"][0]["outcome"] = "CONFIRMED_VIOLATION"
    audit["evidence"]["review_results"][0].update(decision="COMPROMISED", target_evaluation=None)
    parent = record.model_copy(update={"run_id": audit["run_id"], "final_status": "COMPROMISED"})
    directory = runs.RUN_ROOT / parent.run_id / audit["manifest"]["run_id"]
    directory.mkdir(parents=True)
    for key, name in {"manifest": "manifest.json", "evidence": "evidence.json", "deepteam_risk": "deepteam-risk.json", "summary": "summary.json"}.items():
        (directory / name).write_text(json.dumps(audit[key]), encoding="ascii")
    runs._persist(parent); runs._runs[parent.run_id] = parent
    assert reviews.review_view(parent.run_id)["can_request"]
    projection = reviews.evidence_projection(reviews._source(parent))
    assert projection["judge"] == {} and projection["outcome"] == "COMPROMISED"


def test_linked_start_uses_frozen_context_and_publishes_a_saved_child_report(parent, offline_worker):
    record, settings = parent
    reviews.start_review(settings, record.run_id); reviews.execute_review(record.run_id, settings)
    view = reviews.review_view(record.run_id)
    draft = reviews.create_linked_draft(record.run_id, view["review_id"], view["review"]["recommendations"][0]["attack_profile_id"])
    reviews.start_linked_draft(settings, draft.run_id, 75000)
    offline_worker["allow_child"] = True
    runs._execute_run(draft.run_id, draft.attack_profile_id, draft.vulnerability_profile_id, 75000, "SINGLE", 1, draft.target_profile_id)
    child = runs.get_deepteam_run(draft.run_id)
    assert child.status == "COMPLETED" and child.final_status == "RESISTED", child.model_dump(mode="json")
    audit = runs.get_deepteam_audit(child.run_id)
    assert audit.manifest["prompt_provenance_hashes"]["linked_context_sha256"] == digest(child.linked_context.model_dump(mode="json"))
    assert audit.evidence["review_results"][0]["target_evaluation"]["deviation_score"] == 0
    report = reporting.socmate_report_data(child.run_id)
    assert report["original"] is not None and report["run"]["linked_context"]["parent_run_id"] == record.run_id
    assert offline_worker["launches"] == 2
    assert runs.get_deepteam_run(record.run_id).final_status == "RESISTED"
