import json
import os
import re
import builtins
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from secmate_api import main
from secmate_api.target_projection import (
    TargetDetail, TargetSummary, _EXECUTION_PROFILE_PATH, _apply_execution_profile,
    _load_execution_profile, get_target,
)


TARGET_IDS = ["synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1"]


def _files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def blocked_integrations(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("read-only target projection invoked a runtime integration")

    monkeypatch.setattr(main.synthetic_chatmate_smoke, "list_runs", fail)
    monkeypatch.setattr(main.synthetic_chatmate_smoke, "get_run", fail)
    monkeypatch.setattr(main.synthetic_chatmate_smoke, "start_run", fail)
    monkeypatch.setattr(main.deepteam_runs, "start_deepteam_run", fail)
    monkeypatch.setattr(main, "start_deepteam_run", fail)
    monkeypatch.setattr(main.jobs, "launch", fail)
    monkeypatch.setattr(main.jobs, "dispatch", fail)
    monkeypatch.setattr(main, "get_deepteam_catalog", fail)
    monkeypatch.setattr(main, "clients", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    original_import = builtins.__import__

    def block_worker_import(name, *args, **kwargs):
        if name == "secmate_worker" or name.startswith("secmate_worker."):
            fail()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_worker_import)


def test_exact_summaries_order_and_detail_consistency(blocked_integrations):
    client = TestClient(main.app)
    first = client.get("/api/v1/targets")
    second = client.get("/api/v1/targets")

    assert first.status_code == 200
    assert first.content == second.content
    summaries = first.json()
    assert [item["id"] for item in summaries] == TARGET_IDS
    assert [(item["id"], item["name"], item["version"]) for item in summaries] == [
        ("synthetic-socmate-tier1", "SocMate", "1"),
        ("secmate.synthetic-chatmate.fresh.v1", "Synthetic ChatMate", "0.5.0"),
    ]
    assert [item["tool_count"] for item in summaries] == [3, 7]
    assert [item["owner"] for item in summaries] == [None, "AIDA"]
    assert {item["tool_count_basis"] for item in summaries} == {"TOTAL_INVENTORY"}
    assert {item["schema_version"] for item in summaries} == {"target-projection-v1"}
    assert {item["model_profile"]["provider"] for item in summaries} == {"OPENROUTER"}
    assert {item["model_profile"]["model"] for item in summaries} == {
        "nvidia/nemotron-3.5-super-vl:free"
    }

    for summary in summaries:
        detail_response = client.get(f"/api/v1/targets/{summary['id']}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert len(detail["tools"]) == summary["tool_count"]
        assert {key: detail[key] for key in summary} == summary
        assert detail_response.content == client.get(f"/api/v1/targets/{summary['id']}").content


def test_tool_guardrail_data_memory_and_execution_facts(blocked_integrations):
    client = TestClient(main.app)
    socmate = client.get("/api/v1/targets/synthetic-socmate-tier1").json()
    chatmate = client.get("/api/v1/targets/secmate.synthetic-chatmate.fresh.v1").json()

    assert [(tool["canonical_name"], tool["effect"], tool["execution_status"]) for tool in socmate["tools"]] == [
        ("search_alerts", "READ", "AVAILABLE"),
        ("isolate_host", "WRITE", "REQUIRES_APPROVAL"),
        ("disable_user", "WRITE", "REQUIRES_APPROVAL"),
    ]
    assert all(tool["model_exposure"] == "EXPOSED" for tool in socmate["tools"])
    assert all(tool["implementation_status"] == "IMPLEMENTED" for tool in socmate["tools"])
    assert {guardrail["id"] for guardrail in socmate["guardrails"]} == {
        "trusted-app-approval", "simulated-effects-only"
    }
    assert socmate["data_memory"]["cross_run_memory"] == "NOT_CLAIMED"
    assert socmate["execution"]["limits"][0]["execution_modes"] == ["SINGLE", "ADAPTIVE"]
    assert socmate["execution"]["limits"][0]["max_paths"] == 2

    tool_status = {tool["canonical_name"]: tool for tool in chatmate["tools"]}
    assert list(tool_status) == [
        "secmate.conversation.history.read", "secmate.search_mail", "secmate.read_teams",
        "secmate.search_directory", "secmate.propose_message", "secmate.read_calendar",
        "secmate.propose_meeting",
    ]
    assert {name for name, tool in tool_status.items() if tool["execution_status"] == "AVAILABLE"} == {
        "secmate.conversation.history.read", "secmate.read_calendar", "secmate.read_teams",
        "secmate.search_directory", "secmate.search_mail",
    }
    assert {name for name, tool in tool_status.items() if tool["execution_status"] == "REQUIRES_APPROVAL"} == {
        "secmate.propose_message", "secmate.propose_meeting",
    }
    assert {tool["execution_status"] for tool in chatmate["tools"]} == {"AVAILABLE", "REQUIRES_APPROVAL"}
    assert all(tool["model_exposure"] == "EXPOSED" for tool in chatmate["tools"])
    assert all(tool["implementation_status"] == "IMPLEMENTED" for tool in chatmate["tools"])
    assert tool_status["secmate.propose_message"]["native_names"] == ["mail_send", "chat_message_send"]
    assert tool_status["secmate.propose_message"]["native_details"]
    assert tool_status["secmate.propose_message"]["display_name"] == "Propose a message"
    assert any(ref["path"].endswith("execution_profile.json") for ref in chatmate["references"])
    assert chatmate["profile"]["binding_version"] == "2.0.0"
    assert chatmate["execution"]["profile_version"] == "2.1.0"
    assert chatmate["execution"]["provider_token_limit"] == 12000
    assert chatmate["owner"] == "AIDA"
    assert chatmate["data_memory"] == {
        "data_environment": "SYNTHETIC",
        "data_sources": ["Fictional mail", "Fictional Teams", "Fictional calendar", "Fictional directory"],
        "production_data": False,
        "memory_kind": "SEEDED_FACTS_ONLY",
        "facts_only_seeded_memory": True,
        "natural_learning": False,
        "cross_run_memory": "DISABLED",
        "assessment_state": "FRESH_ISOLATED_PER_PATH",
        "details": [
            "Seeded memory contains synthetic facts only.",
            "Natural learning is disabled.",
            "Assessment state is fresh and isolated for each path.",
        ],
    }
    limits = {profile["id"]: profile for profile in chatmate["execution"]["limits"]}
    assert set(limits) == {"smoke", "deepteam-profile", "target-runtime"}
    assert limits["smoke"]["max_tool_calls"] == 1
    assert limits["deepteam-profile"]["max_conversation_turns"] == 4
    assert limits["target-runtime"]["max_model_turns"] == 4
    assert limits["target-runtime"]["max_tool_calls"] == 3
    assert limits["target-runtime"]["max_provider_attempts"] == 4


def test_chatmate_status_is_strictly_projected_from_worker_manifest(tmp_path):
    payload = json.loads(_EXECUTION_PROFILE_PATH.read_text(encoding="utf-8"))
    payload["tools"] = [
        {**tool, "availability": "unavailable"}
        if tool["name"] == "secmate.search_mail" else tool
        for tool in payload["tools"]
    ]
    profile_path = tmp_path / "execution_profile.json"
    profile_path.write_text(json.dumps(payload), encoding="utf-8")

    profile = _load_execution_profile(profile_path)
    projected = _apply_execution_profile(get_target("secmate.synthetic-chatmate.fresh.v1"), profile)
    statuses = {tool.canonical_name: tool.execution_status for tool in projected.tools}
    assert statuses["secmate.search_mail"] == "NOT_ENABLED"
    assert statuses["secmate.propose_message"] == "REQUIRES_APPROVAL"
    assert statuses["secmate.read_calendar"] == "AVAILABLE"


@pytest.mark.parametrize("change", [
    lambda payload: payload.update(profile_version="1.0.0"),
    lambda payload: payload["tools"].pop(),
    lambda payload: payload.update(unexpected=True),
])
def test_chatmate_manifest_mismatch_fails_closed(tmp_path, change):
    payload = json.loads(_EXECUTION_PROFILE_PATH.read_text(encoding="utf-8"))
    change(payload)
    profile_path = tmp_path / "execution_profile.json"
    profile_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="unavailable or invalid"):
        _load_execution_profile(profile_path)

    with pytest.raises(RuntimeError, match="unavailable or invalid"):
        _load_execution_profile(tmp_path / "missing.json")


def test_projection_has_no_sensitive_or_uncontrolled_values(blocked_integrations):
    payload = TestClient(main.app).get("/api/v1/targets").json()
    details = [
        TestClient(main.app).get(f"/api/v1/targets/{target_id}").json()
        for target_id in TARGET_IDS
    ]
    serialized = json.dumps([payload, details], sort_keys=True)
    lowered = serialized.lower()

    for forbidden in (
        "api_key", "secret", "password", "env var", "environment variable", "request_id",
        "system prompt", "raw schema", "canary", "fixture truth", "hidden reasoning",
    ):
        assert forbidden not in lowered
    assert not re.search(r"[a-zA-Z]:[\\/]", serialized)
    assert "\\\\" not in serialized
    for detail in details:
        assert all(not ref["path"].startswith(("/", "\\")) for ref in detail["references"])
        assert all(".." not in ref["path"].split("/") for ref in detail["references"])


def test_unknown_mutations_and_storage_side_effects(blocked_integrations):
    data_root = Path(os.environ["SECMATE_API_DATA_ROOT"])
    before = _files(data_root)
    client = TestClient(main.app)

    assert client.get("/api/v1/targets/unknown").status_code == 404
    for method in ("post", "put", "patch", "delete"):
        response = client.request(method.upper(), "/api/v1/targets/synthetic-socmate-tier1", json={})
        assert response.status_code == 405
    assert _files(data_root) == before


def test_projection_contracts_reject_extras():
    summary = TestClient(main.app).get("/api/v1/targets").json()[0]
    with pytest.raises(ValidationError):
        TargetSummary.model_validate({**summary, "unexpected": True})

    detail = TestClient(main.app).get("/api/v1/targets/synthetic-socmate-tier1").json()
    detail["tools"][0]["raw_schema"] = {}
    with pytest.raises(ValidationError):
        TargetDetail.model_validate(detail)
