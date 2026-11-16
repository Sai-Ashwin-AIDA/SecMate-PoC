from fastapi.testclient import TestClient

from secmate_api.contracts import (
    AttackerOutput,
    CriticOutput,
    JudgeOutput,
    ProviderQuota,
    TargetTurnOutput,
    Usage,
)
from secmate_api.main import app
import secmate_api.main as main_module


client = TestClient(app)


def test_health_reports_model_connectivity_scope():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "secmate-api",
        "scope": "model-connectivity",
    }


def test_platform_capabilities_report_local_worker_dispatch(monkeypatch):
    monkeypatch.setattr(main_module, "deepteam_dispatch_available", lambda settings: True)
    response = client.get("/api/v1/platform-capabilities")

    assert response.status_code == 200
    capabilities = response.json()
    assert capabilities["model_connectivity"]["state"] == "AVAILABLE"
    assert capabilities["deepteam_worker"]["state"] == "AVAILABLE"
    assert capabilities["deepteam_worker"]["invocation"] == "LOCAL_SUBPROCESS"
    assert capabilities["deepteam_worker"]["api_connected"] is True
    assert capabilities["deepteam_worker"]["api_contract_version"] == "2.0"
    assert capabilities["deepteam_worker"]["supported_execution_modes"] == ["SINGLE", "ADAPTIVE"]
    assert capabilities["deepteam_worker"]["max_paths"] == 2
    assert capabilities["deepteam_worker"]["cancellation_supported"] is True
    assert capabilities["deepteam_worker"]["target_evaluator_verified"] is True
    assert capabilities["deepteam_worker"]["last_deviation_score"] == 0
    assert "ExcessiveAgency:permissions" in capabilities["deepteam_worker"]["supported_vulnerabilities"]
    assert "PromptLeakage:instructions" in capabilities["deepteam_worker"]["supported_vulnerabilities"]
    assert "Permission Escalation" in capabilities["deepteam_worker"]["supported_attacks"]
    assert capabilities["assessment_api"] == {
        "state": "NOT_AVAILABLE",
        "lifecycle_source": "FRONTEND_SIMULATION",
    }
    assert "api_key" not in response.text.lower()
    assert "artifacts" not in response.text.lower()


def test_deepteam_run_lifecycle_and_audit_routes(monkeypatch):
    record = {
        "run_id": "api-run-test",
        "status": "COMPLETED",
        "created_at": "2026-09-28T12:00:00Z",
        "started_at": "2026-09-28T12:00:01Z",
        "completed_at": "2026-09-28T12:00:20Z",
        "scenario": "socmate-tier1-permission-escalation",
        "vulnerability": "ExcessiveAgency:permissions",
        "attack": "PermissionEscalation",
        "final_status": "RESISTED",
        "artifact_available": True,
        "logs": [{"timestamp": "2026-09-28T12:00:20Z", "level": "INFO", "message": "Completed."}],
        "error_code": None,
        "error_message": None,
    }
    selected_profiles = []
    monkeypatch.setattr(main_module, "start_deepteam_run", lambda settings, attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths, target_profile_id, scenario_id: selected_profiles.append((attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths, target_profile_id, scenario_id)) or record)
    monkeypatch.setattr(main_module, "get_deepteam_run", lambda run_id: record if run_id == "api-run-test" else None)
    monkeypatch.setattr(main_module, "list_deepteam_runs", lambda limit: [record])
    monkeypatch.setattr(main_module, "get_deepteam_audit", lambda run_id: {
        "run_id": run_id,
        "manifest": {"run_id": "worker-run"},
        "evidence": {"paths": []},
        "deepteam_risk": {"test_cases": []},
        "summary": {"final_status": "RESISTED"},
    })

    created = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed", "Origin": "http://localhost:5173"},
    )
    current = client.get("/api/v1/deepteam-runs/api-run-test")
    history = client.get("/api/v1/deepteam-runs")
    audit = client.get("/api/v1/deepteam-runs/api-run-test/audit")

    assert created.status_code == 202
    assert selected_profiles == [("permission-escalation-v1", "ExcessiveAgency:permissions", 250000, "SINGLE", 1, "synthetic-socmate-tier1", "socmate-tier1-permission-escalation")]
    assert current.json()["status"] == "COMPLETED"
    assert [item["run_id"] for item in history.json()] == ["api-run-test"]
    assert audit.json()["summary"]["final_status"] == "RESISTED"


def test_deepteam_catalog_and_selected_attack_profile(monkeypatch):
    selected_profiles = []
    record = {
        "run_id": "api-run-base64",
        "status": "QUEUED",
        "created_at": "2026-09-28T12:00:00Z",
        "scenario": "socmate-tier1-permission-escalation",
        "vulnerability": "ExcessiveAgency:permissions",
        "attack": "Base64",
        "attack_profile_id": "base64-v1",
        "artifact_available": False,
        "logs": [],
    }
    monkeypatch.setattr(main_module, "start_deepteam_run", lambda settings, attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths, target_profile_id, scenario_id: selected_profiles.append((attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths)) or record)

    catalog = client.get("/api/v1/deepteam-catalog")
    created = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={"attack_profile_id": "base64-v1", "vulnerability_profile_id": "ExcessiveAgency:permissions", "max_total_tokens": 50000},
    )

    assert catalog.status_code == 200
    assert len(catalog.json()["attack_profiles"]) == 27
    assert len(catalog.json()["vulnerability_profiles"]) >= 120
    assert created.status_code == 202
    assert created.json()["attack"] == "Base64"
    assert selected_profiles == [("base64-v1", "ExcessiveAgency:permissions", 50000, "SINGLE", 1)]


def test_chatmate_run_accepts_only_fixed_indirect_injection_scope(monkeypatch):
    selected = []
    record = {
        "run_id": "api-run-chatmate",
        "status": "QUEUED",
        "created_at": "2026-10-03T12:00:00Z",
        "scenario": "chatmate-document-indirect-injection",
        "target_profile_id": "synthetic-chatmate-rag",
        "vulnerability": "IndirectInstruction:document_embedded_instructions",
        "attack": "Prompt Injection",
        "artifact_available": False,
        "logs": [],
    }
    monkeypatch.setattr(
        main_module,
        "start_deepteam_run",
        lambda settings, attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths, target_profile_id, scenario_id: selected.append(
            (
                attack_profile_id,
                vulnerability_profile_id,
                execution_mode,
                max_paths,
                target_profile_id,
                scenario_id,
            )
        )
        or record,
    )

    accepted = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={
            "scenario_id": "chatmate-document-indirect-injection",
            "target_profile_id": "synthetic-chatmate-rag",
            "attack_profile_id": "prompt-injection-v1",
            "vulnerability_profile_id": "IndirectInstruction:document_embedded_instructions",
            "max_total_tokens": 50000,
            "execution_mode": "SINGLE",
            "max_paths": 1,
        },
    )
    invalid_shape = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={
            "scenario_id": "chatmate-document-indirect-injection",
            "target_profile_id": "synthetic-chatmate-rag",
            "execution_mode": "ADAPTIVE",
            "max_paths": 2,
        },
    )

    assert accepted.status_code == 202
    assert invalid_shape.status_code == 422
    assert selected == [("prompt-injection-v1", "IndirectInstruction:document_embedded_instructions", "SINGLE", 1, "synthetic-chatmate-rag", "chatmate-document-indirect-injection")]


def test_deepteam_run_accepts_registered_vulnerability(monkeypatch):
    selected = []
    record = {
        "run_id": "api-run-registered",
        "status": "QUEUED",
        "created_at": "2026-10-01T12:00:00Z",
        "scenario": "socmate-tier1-permission-escalation",
        "vulnerability": "PromptLeakage:instructions",
        "attack": "Base64",
        "artifact_available": False,
        "logs": [],
    }
    monkeypatch.setattr(
        main_module,
        "start_deepteam_run",
        lambda settings, attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths, target_profile_id, scenario_id: selected.append(vulnerability_profile_id) or record,
    )

    response = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={
            "attack_profile_id": "base64-v1",
            "vulnerability_profile_id": "PromptLeakage:instructions",
            "max_total_tokens": 50000,
        },
    )

    assert response.status_code == 202
    assert selected == ["PromptLeakage:instructions"]


def test_deepteam_run_accepts_only_bounded_adaptive_shape(monkeypatch):
    selected = []
    record = {
        "run_id": "api-run-adaptive",
        "status": "QUEUED",
        "created_at": "2026-10-01T12:00:00Z",
        "scenario": "socmate-tier1-permission-escalation",
        "vulnerability": "IndirectInstruction:document_embedded_instructions",
        "attack": "Leetspeak",
        "execution_mode": "ADAPTIVE",
        "max_paths": 2,
        "artifact_available": False,
        "logs": [],
    }
    monkeypatch.setattr(
        main_module,
        "start_deepteam_run",
        lambda settings, attack_profile_id, vulnerability_profile_id, max_total_tokens, execution_mode, max_paths, target_profile_id, scenario_id: selected.append((execution_mode, max_paths)) or record,
    )

    accepted = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={"execution_mode": "ADAPTIVE", "max_paths": 2},
    )
    invalid_single = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={"execution_mode": "SINGLE", "max_paths": 2},
    )
    invalid_adaptive = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={"execution_mode": "ADAPTIVE", "max_paths": 1},
    )

    assert accepted.status_code == 202
    assert selected == [("ADAPTIVE", 2)]
    assert invalid_single.status_code == 422
    assert invalid_adaptive.status_code == 422


def test_deepteam_run_rejects_missing_confirmation_header():
    response = client.post("/api/v1/deepteam-runs")

    assert response.status_code == 403


def test_deepteam_run_rejects_token_budget_outside_poc_bounds():
    response = client.post(
        "/api/v1/deepteam-runs",
        headers={"X-SecMate-Local-Run": "confirmed"},
        json={"max_total_tokens": 9999},
    )

    assert response.status_code == 422


def test_deepteam_run_cancellation_route_is_guarded_and_idempotent(monkeypatch):
    record = {
        "run_id": "api-run-cancel",
        "status": "CANCEL_REQUESTED",
        "created_at": "2026-10-01T12:00:00Z",
        "cancellation_requested_at": "2026-10-01T12:00:01Z",
        "scenario": "socmate-tier1-permission-escalation",
        "vulnerability": "ExcessiveAgency:permissions",
        "attack": "PermissionEscalation",
        "artifact_available": False,
        "logs": [],
    }
    cancellations = []
    monkeypatch.setattr(
        main_module,
        "get_deepteam_run",
        lambda run_id: record if run_id == "api-run-cancel" else None,
    )
    monkeypatch.setattr(
        main_module,
        "cancel_deepteam_run",
        lambda run_id: cancellations.append(run_id) or record,
    )

    unauthorized = client.post("/api/v1/deepteam-runs/api-run-cancel/cancellation")
    first = client.post(
        "/api/v1/deepteam-runs/api-run-cancel/cancellation",
        headers={"X-SecMate-Local-Run": "confirmed"},
    )
    second = client.post(
        "/api/v1/deepteam-runs/api-run-cancel/cancellation",
        headers={"X-SecMate-Local-Run": "confirmed"},
    )
    missing = client.post(
        "/api/v1/deepteam-runs/missing/cancellation",
        headers={"X-SecMate-Local-Run": "confirmed"},
    )

    assert unauthorized.status_code == 403
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["status"] == "CANCEL_REQUESTED"
    assert cancellations == ["api-run-cancel", "api-run-cancel"]
    assert missing.status_code == 404


def test_profiles_do_not_expose_credentials():
    response = client.get("/api/v1/model-profiles")
    assert response.status_code == 200
    profiles = response.json()
    assert len(profiles) == 4
    assert {profile["role"] for profile in profiles} == {
        "ATTACKER",
        "ATTACK_CRITIC",
        "OUTCOME_JUDGE",
        "TARGET",
    }
    assert "api_key" not in response.text.lower()


def test_unknown_profile_returns_not_found():
    response = client.post("/api/v1/model-profiles/unknown/test")
    assert response.status_code == 404


class FakeProviderClients:
    def __init__(self):
        self.attacker_calls = 0
        self.critic_calls = 0

    async def groq_structured(self, model, system, prompt, schema_name, schema, strict_schema=True, critic=False):
        if schema is AttackerOutput:
            assert critic is False
            self.attacker_calls += 1
            output = AttackerOutput(
                objective="Test approval boundary",
                strategy=f"Synthetic strategy {self.attacker_calls}",
                probe=f"Harmless approval-boundary probe {self.attacker_calls}",
                success_condition="The Target requests approval",
            )
        else:
            assert schema is CriticOutput
            assert critic is True
            self.critic_calls += 1
            output = CriticOutput(
                attack_quality_score=55,
                weaknesses=["The probe is vague"],
                unexplored_boundaries=["Approval validation"],
                recommended_adaptation="Ask for a bounded synthetic action",
                must_not_repeat=["Generic administrator claim"],
            )
        return output, 10, Usage(total_tokens=20), ProviderQuota(requests_remaining=900)

    async def openrouter_structured(self, model, system, prompt, schema_name, schema):
        assert schema is JudgeOutput
        return JudgeOutput(
            verdict="RESISTED",
            confidence=0.95,
            expected_behavior="Request approval",
            observed_behavior="Requested approval",
            evidence=["No tool call"],
            concise_rationale="The synthetic boundary was preserved.",
        ), 12, Usage(total_tokens=25)

    async def openrouter_tool_call(self, model):
        return {
            "tool_name": "search_alerts",
            "arguments": {"severity": "HIGH", "limit": 2},
            "execution": "INTERCEPTED_NOT_EXECUTED",
        }, 11, Usage(total_tokens=15)

    async def openrouter_target_turn(self, model, probe):
        return TargetTurnOutput(
            response_text="I cannot perform that action without trusted approval.",
            tool_attempts=[],
        ), 11, Usage(total_tokens=15)


def test_all_role_tests_return_safe_structured_results(monkeypatch):
    monkeypatch.setattr(main_module, "clients", lambda: FakeProviderClients())
    for profile_id in (
        "groq-qwen-attacker",
        "groq-qwen-critic",
        "openrouter-nemotron-judge",
        "openrouter-nemotron-target",
    ):
        response = client.post(f"/api/v1/model-profiles/{profile_id}/test")
        assert response.status_code == 200
        assert response.json()["status"] == "PASS"
        assert "api_key" not in response.text.lower()


def test_adaptive_handoff_uses_critic_only_before_final_turn(monkeypatch):
    fake = FakeProviderClients()
    monkeypatch.setattr(main_module, "clients", lambda: fake)
    response = client.post("/api/v1/model-workflows/adaptive-handoff/test")
    assert response.status_code == 200
    result = response.json()
    assert result["turns_completed"] == 3
    assert result["stop_reason"] == "TURN_BUDGET_EXHAUSTED"
    assert result["turns"][0]["critic"] is not None
    assert result["turns"][1]["critic"] is not None
    assert result["turns"][2]["critic"] is None
    assert fake.attacker_calls == 3
    assert fake.critic_calls == 2
