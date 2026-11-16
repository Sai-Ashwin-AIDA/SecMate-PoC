import json
import hashlib
import subprocess

import pytest
from fastapi.testclient import TestClient

from secmate_api import deepteam_catalog as catalog, deepteam_runs as runs, main, reporting, standard_reviews as reviews
from secmate_api.config import Settings
from secmate_api.contracts import DeepTeamCatalog, DeepTeamRunRecord
from secmate_api.standard_review_contracts import StandardReview, TARGET_LINKED_VERSION, TARGET_VERSION, digest


TARGET_ID = "secmate.synthetic-chatmate.fresh.v1"
SCENARIO_ID = "chatmate-direct-user-prompt-injection"
VULNERABILITY_ID = "DirectPromptInjection:direct_user_instruction"
EXPERIMENTAL_RISK_ID = "SQLInjection:blind_sql_injection"
SUPPORTED_METHODS = (
    "permission-escalation-v1", "authority-escalation-v1", "prompt-injection-v1",
    "prompt-probing-v1", "system-override-v1", "roleplay-v1", "emotional-manipulation-v1",
    "gray-box-v1", "math-problem-v1", "multilingual-v1", "linguistic-confusion-v1",
    "input-bypass-v1", "context-poisoning-v1", "goal-redirection-v1",
    "synthetic-context-injection-v1", "adversarial-poetry-v1", "base64-v1",
    "character-stream-v1", "context-flooding-v1", "embedded-json-v1", "leetspeak-v1",
    "rot13-v1", "crescendo-v1", "linear-jailbreaking-v1", "sequential-jailbreak-v1",
    "bad-likert-judge-v1",
)
EXPORTED_CATALOG = catalog.get_deepteam_catalog()


def _worker_selection_capabilities():
    script = (
        "import json; "
        "from secmate_worker.deepteam_catalog import ATTACK_PROFILES,VULNERABILITY_PROFILES,fresh_selection_capability; "
        "print(json.dumps({a.profile_id+'|'+v.profile_id:fresh_selection_capability(a,v).model_dump(mode='json') "
        "for a in ATTACK_PROFILES for v in VULNERABILITY_PROFILES},sort_keys=True))"
    )
    process = subprocess.run(
        [str(catalog.WORKER_PYTHON), "-c", script],
        cwd=catalog.WORKER_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def _catalog():
    scope = {
        "status": "AVAILABLE",
        "applicability": "APPLICABLE",
        "applicability_reason": "Dedicated fresh direct-user scope.",
        "capability_level": "APPLICABLE",
        "target_profile_ids": [TARGET_ID],
        "scenario_ids": [SCENARIO_ID],
        "required_target_capabilities": [],
        "evidence_references": [],
    }
    return DeepTeamCatalog.model_validate({
        "schema_version": "2.3",
        "scenario_id": SCENARIO_ID,
        "scenario_version": "3",
        "target_profile_id": TARGET_ID,
        "target_profile_version": "0.5.0",
        "synthetic_only": True,
        "max_cases_per_run": 1,
        "target_profiles": [{
            "id": TARGET_ID,
            "name": "Synthetic ChatMate",
            "version": "0.5.0",
            "purpose": "A bounded synthetic direct-user prompt-injection target.",
            "scenario_id": SCENARIO_ID,
            "scenario_version": "3",
            "synthetic_only": True,
            "api_selectable": True,
            "deterministic_vulnerable": False,
            "binding_version": "2.0.0",
            "target_id": TARGET_ID,
            "target_version": "0.5.0",
            "gateway_kind": "CHATMATE_FRESH",
            "api_registration": True,
            "deepteam_provider": True,
            "execution_modes": ["SINGLE", "ADAPTIVE"],
            "max_paths": 2,
            "attack_profile_ids": list(SUPPORTED_METHODS),
            "vulnerability_profile_ids": [VULNERABILITY_ID],
            "execution_profiles": [{
                "id": "phase5-smoke-v1", "version": "1.0.0", "execution_modes": ["SINGLE"],
                "max_paths": 1, "max_conversation_turns": 1,
                "attack_profile_ids": ["prompt-injection-v1"],
            }, {
                "id": "deepteam-conversation-v1", "version": "2.1.0",
                "execution_modes": ["SINGLE", "ADAPTIVE"], "max_paths": 2,
                "max_conversation_turns": 4, "fresh_state_per_path": True,
                "caller_history_authoritative": False, "attack_profile_ids": list(SUPPORTED_METHODS),
            }],
            "unsupported_attack_profiles": {"tree-jailbreaking-v1": "Tree Jailbreaking issues speculative sibling callbacks against the same history; fresh ChatMate requires one authoritative linear conversation per path."},
            "experimental_catalog_projection": {"schema_version": "1.0", "admission": "EXPERIMENTAL",
                "attack_profile_ids": [*SUPPORTED_METHODS, "tree-jailbreaking-v1"],
                "vulnerability_profile_ids": [VULNERABILITY_ID, EXPERIMENTAL_RISK_ID]},
        }],
        "attack_profiles": [{
            "id": method, "name": method, "class_name": method, "description": method,
            "turn_mode": "MULTI" if method in {"crescendo-v1", "linear-jailbreaking-v1", "sequential-jailbreak-v1", "bad-likert-judge-v1", "tree-jailbreaking-v1"} else "SINGLE",
            "max_turns": 5 if method == "tree-jailbreaking-v1" else 4 if method in {"crescendo-v1", "linear-jailbreaking-v1", "sequential-jailbreak-v1", "bad-likert-judge-v1"} else 1,
            **scope,
            "target_profile_ids": [TARGET_ID] if method in SUPPORTED_METHODS else [],
            "target_applicability": {TARGET_ID: {"applicability": "APPLICABLE" if method in SUPPORTED_METHODS else "NOT_APPLICABLE",
                "reason": "Dedicated fresh direct-user method." if method in SUPPORTED_METHODS else "Tree Jailbreaking uses speculative sibling histories; fresh ChatMate requires one authoritative linear conversation per path."}},
            "target_experimental_admission": {TARGET_ID: {"admission": "ADMITTED", "selectable": True,
                "reason": "Experimentally admitted by exact registered ID. Established applicability and execution capability remain independently reported."}},
        } for method in (*SUPPORTED_METHODS, "tree-jailbreaking-v1")],
        "vulnerability_profiles": [{
            "id": VULNERABILITY_ID,
            "name": "Direct User Prompt Injection",
            "class_name": "PromptInjection",
            "subtype": "direct_user",
            "category": "Prompt Injection",
            "description": "Direct untrusted user instruction override.",
            **scope,
            "target_applicability": {TARGET_ID: {"applicability": "APPLICABLE", "reason": "Direct-user risk."}},
            "target_experimental_admission": {TARGET_ID: {"admission": "ADMITTED", "selectable": True,
                "reason": "Experimentally admitted by exact registered ID. Established applicability and required-capability notes remain authoritative."}},
        }, {
            "id": EXPERIMENTAL_RISK_ID,
            "name": "SQL Injection / Blind Sql Injection",
            "class_name": "SQLInjection",
            "subtype": "blind_sql_injection",
            "category": "Security",
            "description": "Tests blind SQL injection behavior.",
            **scope,
            "target_profile_ids": [],
            "target_applicability": {TARGET_ID: {"applicability": "NOT_APPLICABLE", "reason": "Established scope is another target."}},
            "target_experimental_admission": {TARGET_ID: {"admission": "ADMITTED", "selectable": True,
                "reason": "Experimentally admitted by exact registered ID. Established applicability and required-capability notes remain authoritative."}},
        }],
    })


@pytest.fixture
def fresh_catalog(monkeypatch):
    value = _catalog()
    monkeypatch.setattr(catalog, "get_deepteam_catalog", lambda: value)
    monkeypatch.setattr(runs, "get_deepteam_catalog", lambda: value)
    return value


def test_http_admits_fresh_single_and_adaptive_shapes(monkeypatch):
    accepted = []
    record = DeepTeamRunRecord(
        run_id="api-run-fresh",
        status="QUEUED",
        created_at="2026-11-14T00:00:00Z",
        scenario=SCENARIO_ID,
        scenario_version="3",
        target_profile_id=TARGET_ID,
        target_profile_version="0.5.0",
        target_name="Synthetic ChatMate",
        vulnerability="Direct User Prompt Injection",
        vulnerability_profile_id=VULNERABILITY_ID,
        attack="Prompt Injection",
        attack_profile_id="prompt-injection-v1",
        artifact_available=False,
        logs=[],
    )
    def start(*args):
        if args[1] != "prompt-injection-v1":
            raise main.DeepTeamSelectionError("unsupported")
        accepted.append(args[1:])
        return record
    monkeypatch.setattr(main, "start_deepteam_run", start)
    client = TestClient(main.app)
    headers = {"X-SecMate-Local-Run": "confirmed"}

    selection = {"target_profile_id": TARGET_ID, "scenario_id": SCENARIO_ID,
                 "attack_profile_id": "prompt-injection-v1", "vulnerability_profile_id": VULNERABILITY_ID,
                 "execution_mode": "SINGLE", "max_paths": 1}
    response = client.post("/api/v1/deepteam-runs", headers=headers, json=selection)
    adaptive = client.post("/api/v1/deepteam-runs", headers=headers, json={**selection, "execution_mode": "ADAPTIVE", "max_paths": 2})
    mismatch = client.post("/api/v1/deepteam-runs", headers=headers, json={**selection, "target_profile_id": "synthetic-socmate-tier1"})
    wrong_shape = client.post("/api/v1/deepteam-runs", headers=headers, json={**selection, "execution_mode": "ADAPTIVE", "max_paths": 1})

    assert response.status_code == 202
    assert accepted[0][0:2] == ("prompt-injection-v1", VULNERABILITY_ID)
    assert adaptive.status_code == 202
    assert mismatch.status_code == wrong_shape.status_code == 422
    assert len(accepted) == 2


@pytest.mark.parametrize("method", SUPPORTED_METHODS)
def test_catalog_admits_every_worker_supported_fresh_method(fresh_catalog, method):
    target, attack, risk, capability = catalog.validate_fresh_selection(
        method, VULNERABILITY_ID, TARGET_ID, SCENARIO_ID, "SINGLE", 1)
    assert (target.id, attack.id, risk.id) == (TARGET_ID, method, VULNERABILITY_ID)
    assert capability["execution_capability"] == "EXECUTABLE"


@pytest.mark.parametrize("method", EXPORTED_CATALOG.attack_profiles, ids=lambda item: item.id)
def test_current_23_catalog_experimentally_admits_every_exported_attack(method):
    _, selected, _, capability = catalog.validate_fresh_selection(
        method.id, VULNERABILITY_ID, TARGET_ID, SCENARIO_ID, "SINGLE", 1)
    assert selected.id == method.id
    assert capability["attack_profile_id"] == method.id


@pytest.mark.parametrize("risk", EXPORTED_CATALOG.vulnerability_profiles, ids=lambda item: item.id)
def test_current_23_catalog_experimentally_admits_every_exported_risk(risk):
    _, _, selected, capability = catalog.validate_fresh_selection(
        "prompt-injection-v1", risk.id, TARGET_ID, SCENARIO_ID, "SINGLE", 1)
    assert selected.id == risk.id
    assert capability["vulnerability_profile_id"] == risk.id


def test_catalog_admits_semantic_not_applicable_but_rejects_unknown_and_invalid_modes(fresh_catalog):
    _, attack, _, capability = catalog.validate_fresh_selection(
        "tree-jailbreaking-v1", VULNERABILITY_ID, TARGET_ID, SCENARIO_ID, "SINGLE", 1)
    assert attack.target_applicability[TARGET_ID]["applicability"] == "NOT_APPLICABLE"
    assert capability["execution_capability"] == "UNSUPPORTED"
    with pytest.raises(ValueError, match="Unknown or unavailable"):
        catalog.validate_fresh_selection("prompt-injection-v1", "IndirectInstruction:document_embedded_instructions", TARGET_ID, SCENARIO_ID, "SINGLE", 1)
    for mode, paths in (("SINGLE", 2), ("ADAPTIVE", 1)):
        with pytest.raises(ValueError, match="SINGLE/1 or ADAPTIVE/2"):
            catalog.validate_fresh_selection("prompt-injection-v1", VULNERABILITY_ID, TARGET_ID, SCENARIO_ID, mode, paths)


def test_internal_rejection_precedes_lock_and_dispatch(monkeypatch, fresh_catalog, tmp_path):
    touched = []
    monkeypatch.setattr(runs, "RUN_ROOT", tmp_path / "runs")
    monkeypatch.setattr(runs, "RUN_LOCK", tmp_path / "runs" / "active-run.lock")
    monkeypatch.setattr(runs, "_claim_run_lock", lambda run_id: touched.append(("lock", run_id)))
    monkeypatch.setattr(runs.jobs, "dispatch", lambda *args, **kwargs: touched.append(("dispatch", args)))
    settings = Settings("attacker", "judge", 45, groq_critic_api_key="critic")

    with pytest.raises(runs.DeepTeamSelectionError):
        runs.start_deepteam_run(settings, "prompt-injection-v1", VULNERABILITY_ID, 50_000,
                                "SINGLE", 2, TARGET_ID, SCENARIO_ID)

    assert touched == []
    assert not runs.RUN_ROOT.exists()


def test_admitted_run_uses_catalog_metadata_and_worker_command(monkeypatch, fresh_catalog, tmp_path):
    monkeypatch.setattr(runs, "RUN_ROOT", tmp_path / "runs")
    monkeypatch.setattr(runs, "RUN_LOCK", tmp_path / "runs" / "active-run.lock")
    monkeypatch.setattr(runs, "WORKER_PYTHON", tmp_path / "python.exe")
    runs.WORKER_PYTHON.write_text("", encoding="ascii")
    monkeypatch.setattr(runs, "_runs", {})
    monkeypatch.setattr(runs.jobs, "dispatch", lambda *args, **kwargs: None)

    record = runs.start_deepteam_run(Settings("attacker", "judge", 45), "prompt-injection-v1", None,
        target_profile_id=TARGET_ID, scenario_id=SCENARIO_ID, max_total_tokens=10000)
    command = runs._worker_command(tmp_path / record.run_id, record.attack_profile_id,
        record.vulnerability_profile_id, record.max_total_tokens, record.execution_mode,
        record.max_paths, record.target_profile_id)

    assert (record.target_name, record.target_profile_version, record.scenario_version) == (
        "Synthetic ChatMate", "0.5.0", "3")
    assert command[command.index("--target-profile") + 1] == TARGET_ID
    assert command[command.index("--attack-profile") + 1] == "prompt-injection-v1"
    assert command[command.index("--vulnerability-profile") + 1] == VULNERABILITY_ID
    assert command[command.index("--execution-mode") + 1] == "SINGLE"
    assert command[command.index("--max-paths") + 1] == "1"
    assert record.execution_profile_version == "2.1.0"
    assert record.max_total_tokens == 10000
    assert command[command.index("--token-budget") + 1] == "10000"
    assert any("12,000" in entry.message and "never increased automatically" in entry.message for entry in record.logs)
    assert record.attack_target_applicability == "APPLICABLE"
    assert record.vulnerability_target_applicability == "APPLICABLE"
    assert record.attack_experimental_admission == "ADMITTED"
    assert record.vulnerability_experimental_admission == "ADMITTED"
    assert record.selection_admission == "ESTABLISHED"
    assert record.execution_capability == "EXECUTABLE"


def _bound_artifacts(directory, record):
    worker_run_id = directory.name
    path_id = f"{worker_run_id}-path-1"
    values = {
        "manifest.json": {"run_id": worker_run_id, "campaign": {
            "scenario_id": record.scenario, "scenario_version": record.scenario_version,
            "target_profile_id": record.target_profile_id, "target_profile_version": record.target_profile_version,
            "vulnerability_types": [record.vulnerability_profile_id],
            "allowed_attack_methods": [record.attack_profile_id], "budget": {"max_paths": 1}}},
        "evidence.json": {"run_id": worker_run_id, "paths": [{"path_id": path_id,
            "vulnerability_type": record.vulnerability_profile_id, "attack_method": record.attack_profile_id}]},
        "deepteam-risk.json": {"run_id": worker_run_id, "execution_mode": "SINGLE", "max_paths": 1,
            "scenario_id": record.scenario, "scenario_version": record.scenario_version,
            "target_metadata": {"target_profile_id": record.target_profile_id,
                                "target_profile_version": record.target_profile_version},
            "paths": [{"path_id": path_id, "attack_profile_id": record.attack_profile_id}]},
        "summary.json": {"run_id": worker_run_id, "final_status": "RESISTED",
            "attack_profile_id": record.attack_profile_id, "vulnerability_profile_id": record.vulnerability_profile_id,
            "target_profile_id": record.target_profile_id, "target_name": record.target_name,
            "execution_mode": "SINGLE", "max_paths": 1,
            "paths": [{"path_id": path_id, "attack_method": record.attack_profile_id, "status": "RESISTED"}]},
    }
    directory.mkdir(parents=True)
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="ascii")


def _v2_artifacts(directory, record, fresh_catalog, methods=None, turns_per_path=1, selection_capabilities=None):
    methods = methods or [record.attack_profile_id]
    worker_run_id = directory.name
    target = next(item for item in fresh_catalog.target_profiles if item.id == TARGET_ID)
    raw_target = target.model_dump(mode="json")
    onboarding = {key: raw_target[key] for key in (
        "binding_version", "target_id", "target_version", "gateway_kind", "api_registration",
        "deepteam_provider", "execution_modes", "max_paths", "attack_profile_ids",
        "vulnerability_profile_ids", "execution_profiles", "unsupported_attack_profiles",
    )}
    onboarding["experimental_catalog_projection"] = raw_target["experimental_catalog_projection"]
    target_metadata = {"target_profile_id": TARGET_ID, "target_profile_version": "0.5.0",
                       "gateway_kind": "CHATMATE_FRESH", "model_profile_id": "openrouter-nemotron-35-super-vl-target",
                       "provider": "OPENROUTER", "model": "nvidia/nemotron-3.5-super-vl:free",
                       "onboarding": onboarding}
    baseline = (
        record.execution_mode == "SINGLE"
        and record.max_paths == 1
        and methods == ["prompt-injection-v1"]
        and record.vulnerability_profile_id == VULNERABILITY_ID
    )
    provenance = ({
        "schema_version": "baseline-execution-v1",
        "execution_mode": "BASELINE_UNENHANCED",
        "enhancement_applied": False,
        "delivery": "DIRECT_GENERATED_ATTACK",
        "generated_attack_text": "probe 1",
        "generated_attack_sha256": hashlib.sha256(b"probe 1").hexdigest(),
    } if baseline else None)
    selected_risk = next(item for item in fresh_catalog.vulnerability_profiles if item.id == record.vulnerability_profile_id)
    def selection(method):
        if selection_capabilities is not None:
            return selection_capabilities[f"{method}|{record.vulnerability_profile_id}"]
        return catalog.fresh_selection_capability(
            next(item for item in fresh_catalog.attack_profiles if item.id == method), selected_risk)

    top_selection = selection(record.attack_profile_id)
    evidence_paths, risk_paths, summary_paths, reviews = [], [], [], []
    for index, method in enumerate(methods, 1):
        path_id = f"{worker_run_id}-path-{index}"
        path_selection = selection(method)
        turns, assessments = [], []
        for turn_number in range(1, turns_per_path + 1):
            turn_id = f"{path_id}-turn-{turn_number}"
            turns.append({"turn_id": turn_id, "probe": f"probe {turn_number}",
                          "target_response": "Direct refusal.", "tool_attempts": []})
            assessments.append({"evidence_id": f"{turn_id}-phase5", "parent_path_id": path_id,
                "parent_turn_id": turn_id, "turn_binding_version": "phase5-turn-binding-v1",
                "target_id": TARGET_ID, "target_version": "0.5.0", "onboarding_binding_version": "2.0.0",
                "status": "completed", "answer_present": True,
                "binding_metadata": {"execution_profile_id": "deepteam-conversation-v1",
                                      "execution_profile_version": "2.1.0"}})
        evidence_paths.append({"path_id": path_id, "vulnerability_type": record.vulnerability_profile_id,
            "attack_method": method, "status": "RESISTED", "turns": turns,
            "phase5_assessments": assessments, "execution_provenance": provenance})
        evidence_paths[-1]["selection_provenance"] = path_selection
        risk_paths.append({"path_id": path_id, "attack_profile_id": method,
                           "execution_provenance": provenance, "selection_provenance": path_selection})
        summary_paths.append({"path_id": path_id, "attack_method": method, "status": "RESISTED",
                              "execution_provenance": provenance, "selection_provenance": path_selection})
        reviews.append({"path_id": path_id, "decision": "RESISTED"})
    if len(methods) == 2:
        reviews[0] = {"path_id": evidence_paths[0]["path_id"], "decision": "CONTINUE",
                      "next_attack_method": methods[1],
                      "critic_review": {"recommended_attack_method": methods[1]}}
    spec = {"spec_id": f"chatmate-fresh-{record.vulnerability_profile_id.replace(':', '-').replace('_', '-')}-v1",
            "target_profile_id": TARGET_ID, "vulnerability_profile_id": record.vulnerability_profile_id}
    values = {
        "manifest.json": {"run_id": worker_run_id, "target_metadata": target_metadata,
            "execution_provenance": provenance, "selection_provenance": top_selection, "campaign": {
            "scenario_id": SCENARIO_ID, "scenario_version": "3", "target_profile_id": TARGET_ID,
            "target_profile_version": "0.5.0", "vulnerability_types": [record.vulnerability_profile_id],
            "allowed_attack_methods": [record.attack_profile_id] if len(methods) == 1 else list(SUPPORTED_METHODS),
            "assessment_spec": spec, "model_profiles": [{"role": "TARGET",
                "profile_id": "openrouter-nemotron-35-super-vl-target", "provider": "OPENROUTER",
                "model": "nvidia/nemotron-3.5-super-vl:free"}], "budget": {"max_paths": len(methods)}}},
        "evidence.json": {"run_id": worker_run_id, "target_metadata": target_metadata,
                           "execution_provenance": provenance, "selection_provenance": top_selection,
                           "paths": evidence_paths, "review_results": reviews},
        "deepteam-risk.json": {"run_id": worker_run_id, "execution_mode": record.execution_mode,
            "max_paths": len(methods), "scenario_id": SCENARIO_ID, "scenario_version": "3",
            "assessment_spec_id": spec["spec_id"], "target_metadata": target_metadata,
            "execution_provenance": provenance, "selection_provenance": top_selection, "paths": risk_paths},
        "summary.json": {"run_id": worker_run_id, "final_status": "RESISTED",
            "attack_profile_id": record.attack_profile_id, "vulnerability_profile_id": record.vulnerability_profile_id,
            "target_profile_id": TARGET_ID, "target_name": "Synthetic ChatMate",
            "execution_mode": record.execution_mode, "max_paths": len(methods),
            "target_metadata": target_metadata, "execution_provenance": provenance,
            "selection_provenance": top_selection,
            "paths": summary_paths},
    }
    directory.mkdir(parents=True)
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="ascii")
    return values


def _v2_record(mode="SINGLE", paths=1, method="prompt-injection-v1", risk_id=VULNERABILITY_ID, catalog_value=None):
    value = catalog_value or _catalog()
    selected_attack = next(item for item in value.attack_profiles if item.id == method)
    selected_risk = next(item for item in value.vulnerability_profiles if item.id == risk_id)
    capability = catalog.fresh_selection_capability(selected_attack, selected_risk)
    return DeepTeamRunRecord(run_id="api-run-111111111111", status="RUNNING", created_at="2026-11-14T00:00:00Z",
        scenario=SCENARIO_ID, scenario_version="3", target_profile_id=TARGET_ID, target_profile_version="0.5.0",
        target_name="Synthetic ChatMate", catalog_schema_version="2.3", onboarding_binding_version="2.0.0",
        execution_profile_id="deepteam-conversation-v1", execution_profile_version="2.1.0",
        vulnerability=selected_risk.name, vulnerability_profile_id=selected_risk.id,
        attack=method, attack_profile_id=method,
        attack_target_applicability=selected_attack.target_applicability[TARGET_ID]["applicability"],
        attack_applicability_reason=selected_attack.target_applicability[TARGET_ID]["reason"],
        vulnerability_target_applicability=selected_risk.target_applicability[TARGET_ID]["applicability"],
        vulnerability_applicability_reason=selected_risk.target_applicability[TARGET_ID]["reason"],
        attack_experimental_admission="ADMITTED",
        attack_experimental_admission_reason=selected_attack.target_experimental_admission[TARGET_ID]["reason"],
        vulnerability_experimental_admission="ADMITTED",
        vulnerability_experimental_admission_reason=selected_risk.target_experimental_admission[TARGET_ID]["reason"],
        selection_admission=capability["admission"],
        execution_capability=capability["execution_capability"],
        execution_capability_code=capability["capability_code"],
        execution_capability_reason=capability["capability_reason"],
        execution_mode=mode, max_paths=paths,
        artifact_available=False, logs=[])


def test_api_and_worker_selection_provenance_match_for_complete_fresh_catalog():
    worker = _worker_selection_capabilities()
    assert len(worker) == len(EXPORTED_CATALOG.attack_profiles) * len(EXPORTED_CATALOG.vulnerability_profiles)
    for attack in EXPORTED_CATALOG.attack_profiles:
        for risk in EXPORTED_CATALOG.vulnerability_profiles:
            assert worker[f"{attack.id}|{risk.id}"] == catalog.fresh_selection_capability(attack, risk)


def test_exported_target_budget_matches_current_api_binding():
    target = next(item for item in EXPORTED_CATALOG.target_profiles if item.id == TARGET_ID)
    profile = target.effective_execution_profile
    assert profile["profile_version"] == catalog.FRESH_EXECUTION_PROFILE_VERSION == "2.1.0"
    assert profile["budgets"]["provider_token_limit"] == catalog.FRESH_TARGET_TOKEN_LIMIT == 12000


def test_worker_authored_sql_emotional_selection_provenance_publishes(tmp_path):
    worker = _worker_selection_capabilities()
    record = _v2_record(
        method="emotional-manipulation-v1",
        risk_id="SQLInjection:blind_sql_injection",
        catalog_value=EXPORTED_CATALOG,
    )
    directory = tmp_path / "run-worker-provenance"
    _v2_artifacts(
        directory,
        record,
        EXPORTED_CATALOG,
        selection_capabilities=worker,
    )
    runs._validate_artifact_binding(directory, record, "RESISTED")


@pytest.mark.parametrize("method,turns", [("prompt-injection-v1", 1), ("linear-jailbreaking-v1", 3)])
def test_v2_sealed_single_and_multi_turn_publication(fresh_catalog, tmp_path, method, turns):
    record = _v2_record(method=method)
    directory = tmp_path / f"run-{method[:6]}"
    _v2_artifacts(directory, record, fresh_catalog, turns_per_path=turns)
    runs._validate_artifact_binding(directory, record, "RESISTED")


def test_historical_two_point_zero_budget_binding_still_publishes(fresh_catalog, tmp_path):
    historical = fresh_catalog.model_copy(deep=True)
    for profile in historical.target_profiles[0].execution_profiles:
        if profile["id"] == "deepteam-conversation-v1":
            profile["version"] = "2.0.0"
    record = _v2_record().model_copy(update={"execution_profile_version": "2.0.0"})
    directory = tmp_path / "run-historical-budget"
    values = _v2_artifacts(directory, record, historical)
    for payload in values.values():
        for path in payload.get("paths", []):
            for assessment in path.get("phase5_assessments", []):
                assessment["binding_metadata"]["execution_profile_version"] = "2.0.0"
    for name, payload in values.items():
        (directory / name).write_text(json.dumps(payload), encoding="ascii")
    runs._validate_artifact_binding(directory, record, "RESISTED")


def test_v2_baseline_provenance_tamper_is_rejected(fresh_catalog, tmp_path):
    record = _v2_record()
    directory = tmp_path / "run-baseline-tamper"
    _v2_artifacts(directory, record, fresh_catalog)
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="ascii"))
    summary["execution_provenance"]["enhancement_applied"] = True
    summary_path.write_text(json.dumps(summary), encoding="ascii")

    with pytest.raises(runs.DeepTeamRunError, match="Baseline execution provenance"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def test_v2_sealed_adaptive_publication_and_tamper_rejection(fresh_catalog, tmp_path):
    record = _v2_record("ADAPTIVE", 2)
    directory = tmp_path / "run-adaptive"
    _v2_artifacts(directory, record, fresh_catalog, ["prompt-injection-v1", "system-override-v1"])
    runs._validate_artifact_binding(directory, record, "RESISTED")

    evidence_path = directory / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="ascii"))
    evidence["review_results"][0]["critic_review"]["recommended_attack_method"] = "base64-v1"
    evidence_path.write_text(json.dumps(evidence), encoding="ascii")
    with pytest.raises(runs.DeepTeamRunError, match="Critic recommendation"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def _unsupported_artifacts(directory, record, fresh_catalog):
    values = _v2_artifacts(directory, record, fresh_catalog, turns_per_path=0)
    capability = values["summary.json"]["selection_provenance"]
    error = {"type": "FreshTargetUnsupportedCapability", "message": capability["capability_reason"],
             "code": capability["capability_code"], "retryable": False, "unsupported": True}
    evidence = values["evidence.json"]
    evidence["paths"][0].update(status="ERROR", turns=[], phase5_assessments=[], engine_result={
        "native_score": None, "native_reason": None, "native_evaluator_profile_id": None,
        "normalized_status": "ERROR", "raw_result": {"error": error},
    })
    evidence["review_results"] = [{"path_id": evidence["paths"][0]["path_id"], "decision": "ERROR",
                                    "target_evaluation": None, "critic_review": None}]
    values["deepteam-risk.json"]["paths"][0].update(status="ERROR", result={"error": error, "test_cases": [],
        "selection_provenance": capability})
    summary = values["summary.json"]
    summary.update(final_status="ERROR", turns=0, budget={"provider_calls_attempted": 0,
        "turns_consumed": 0, "tokens_consumed": 0}, model_attempts=[])
    summary["paths"][0]["status"] = "ERROR"
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="ascii")
    return values


def test_v23_sealed_unsupported_is_scoreless_and_uses_stable_failure(fresh_catalog, tmp_path):
    record = _v2_record(method="tree-jailbreaking-v1")
    directory = tmp_path / "run-unsupported"
    values = _unsupported_artifacts(directory, record, fresh_catalog)

    runs._validate_artifact_binding(directory, record, "ERROR")
    code, message = runs._worker_failure_details([], values["summary.json"])

    assert code == "FRESH_TREE_SPECULATIVE_HISTORY_UNSUPPORTED"
    assert message == record.execution_capability_reason
    assert values["summary.json"]["budget"]["provider_calls_attempted"] == 0
    assert values["evidence.json"]["paths"][0]["engine_result"]["native_score"] is None


def test_v23_unsupported_audit_report_and_reload_do_not_dispatch(fresh_catalog, tmp_path, monkeypatch):
    root = tmp_path / "isolated-unsupported-runs"
    monkeypatch.setattr(runs, "RUN_ROOT", root)
    monkeypatch.setattr(runs, "RUN_LOCK", root / "active-run.lock")
    monkeypatch.setattr(runs, "_runs", {})
    launches = []
    monkeypatch.setattr(runs.jobs, "launch", lambda *args, **kwargs: launches.append(args))
    base = _v2_record(method="tree-jailbreaking-v1")
    record = base.model_copy(update={"status": "FAILED", "completed_at": "2026-11-15T00:01:00Z",
        "final_status": "ERROR", "artifact_available": True,
        "error_code": base.execution_capability_code, "error_message": base.execution_capability_reason})
    directory = root / record.run_id / "run-unsupported-sealed"
    _unsupported_artifacts(directory, record, fresh_catalog)
    runs._validate_artifact_binding(directory, record, "ERROR")
    runs._runs[record.run_id] = record
    runs._persist(record)

    first_audit = runs.get_deepteam_audit(record.run_id)
    first_report = reporting.socmate_report_data(record.run_id)
    assert first_audit is not None
    assert first_report["run"]["status"] == "FAILED"
    assert first_report["run"]["artifact_available"] is True
    assert first_report["audit"]["summary"]["selection_provenance"]["execution_capability"] == "UNSUPPORTED"

    runs._runs = {}
    runs._load_records()
    assert runs.get_deepteam_audit(record.run_id).model_dump(mode="json") == first_audit.model_dump(mode="json")
    assert reporting.socmate_report_data(record.run_id) == first_report
    assert launches == []


@pytest.mark.parametrize("schema_version", ["2.1", "2.2"])
def test_historical_fresh_records_keep_additive_defaults(schema_version):
    record = _v2_record().model_dump(mode="json")
    record["catalog_schema_version"] = schema_version
    for field in ("vulnerability_target_applicability", "vulnerability_applicability_reason",
                  "vulnerability_experimental_admission", "vulnerability_experimental_admission_reason",
                  "attack_target_applicability", "attack_applicability_reason",
                  "attack_experimental_admission", "attack_experimental_admission_reason",
                  "selection_admission", "execution_capability", "execution_capability_code",
                  "execution_capability_reason"):
        record.pop(field, None)

    loaded = DeepTeamRunRecord.model_validate(record)

    assert loaded.catalog_schema_version == schema_version
    assert loaded.attack_target_applicability == "UNREVIEWED"
    assert loaded.selection_admission is None
    assert loaded.execution_capability is None


@pytest.mark.parametrize("projection", ["manifest.json", "evidence.json", "deepteam-risk.json", "summary.json"])
def test_v23_selection_capability_tamper_is_rejected(fresh_catalog, tmp_path, projection):
    record = _v2_record(method="base64-v1")
    directory = tmp_path / f"run-capability-{projection.split('.')[0]}"
    _v2_artifacts(directory, record, fresh_catalog)
    path = directory / projection
    payload = json.loads(path.read_text(encoding="ascii"))
    payload["selection_provenance"]["capability_code"] = "FORGED"
    path.write_text(json.dumps(payload), encoding="ascii")

    with pytest.raises(runs.DeepTeamRunError, match="selection capability provenance"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def test_v23_forged_baseline_on_transformed_method_is_rejected(fresh_catalog, tmp_path):
    record = _v2_record(method="base64-v1")
    directory = tmp_path / "run-forged-baseline"
    values = _v2_artifacts(directory, record, fresh_catalog)
    forged = {"schema_version": "baseline-execution-v1", "execution_mode": "BASELINE_UNENHANCED",
              "enhancement_applied": False, "delivery": "DIRECT_GENERATED_ATTACK",
              "generated_attack_text": "probe 1", "generated_attack_sha256": hashlib.sha256(b"probe 1").hexdigest()}
    for payload in values.values():
        payload["execution_provenance"] = forged
    for payload in (values["evidence.json"], values["deepteam-risk.json"], values["summary.json"]):
        payload["paths"][0]["execution_provenance"] = forged
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="ascii")

    with pytest.raises(runs.DeepTeamRunError, match="forbidden"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def test_v23_unsupported_rejects_manufactured_native_score(fresh_catalog, tmp_path):
    record = _v2_record(method="tree-jailbreaking-v1")
    directory = tmp_path / "run-unsupported-score"
    values = _unsupported_artifacts(directory, record, fresh_catalog)
    values["evidence.json"]["paths"][0]["engine_result"]["native_score"] = 1
    (directory / "evidence.json").write_text(json.dumps(values["evidence.json"]), encoding="ascii")

    with pytest.raises(runs.DeepTeamRunError, match="Empty fresh evidence|contains a score"):
        runs._validate_artifact_binding(directory, record, "ERROR")


@pytest.mark.parametrize("field,value", [("parent_path_id", "forged-path"), ("parent_turn_id", "forged-turn")])
def test_v2_phase5_parent_binding_tamper_rejected(fresh_catalog, tmp_path, field, value):
    record = _v2_record()
    directory = tmp_path / f"run-{field}"
    _v2_artifacts(directory, record, fresh_catalog)
    path = directory / "evidence.json"
    evidence = json.loads(path.read_text(encoding="ascii"))
    evidence["paths"][0]["phase5_assessments"][0][field] = value
    path.write_text(json.dumps(evidence), encoding="ascii")
    with pytest.raises(runs.DeepTeamRunError, match="parent path and turn"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def test_v2_failed_phase5_cannot_publish_a_score(fresh_catalog, tmp_path):
    record = _v2_record()
    directory = tmp_path / "run-failed-phase5"
    _v2_artifacts(directory, record, fresh_catalog)
    path = directory / "evidence.json"
    evidence = json.loads(path.read_text(encoding="ascii"))
    evidence["paths"][0]["phase5_assessments"][0].update(status="failed", answer_present=False)
    evidence["paths"][0]["engine_result"] = {"native_score": 1}
    path.write_text(json.dumps(evidence), encoding="ascii")
    with pytest.raises(runs.DeepTeamRunError, match="parent path and turn"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def test_v2_attacker_schema_failure_keeps_sanitized_diagnostics_without_score(fresh_catalog, tmp_path, monkeypatch):
    root = tmp_path / "isolated-runs"
    record = _v2_record().model_copy(update={
        "status": "FAILED", "completed_at": "2026-11-14T00:01:00Z", "final_status": "ERROR",
        "error_code": "WORKER_RUN_FAILED", "error_message": "The worker returned a fail-closed result.",
    })
    directory = root / record.run_id / "run-schemafailure"
    values = _v2_artifacts(directory, record, fresh_catalog)
    error = {"type": "RuntimeError", "message": "DeepTeam execution failed unexpectedly.",
             "code": "UNEXPECTED_ERROR", "retryable": False}
    evidence = values["evidence.json"]
    evidence["paths"][0].update(status="ERROR", turns=[], phase5_assessments=[], engine_result={
        "native_score": None, "native_reason": None, "normalized_status": "ERROR",
        "raw_result": {"error": error},
    })
    evidence["review_results"] = [{"path_id": evidence["paths"][0]["path_id"],
                                     "decision": "ERROR", "target_evaluation": None}]
    risk = values["deepteam-risk.json"]
    risk["paths"][0].update(status="ERROR", result={"error": error, "test_cases": []})
    summary = values["summary.json"]
    summary.update(final_status="ERROR", model_attempts=[{
        "provider": "GROQ", "role": "ATTACKER", "outcome": "FAILURE",
        "error_code": "SCHEMA_VALIDATION", "schema_name": "EnhancedInjection",
    }] * 3)
    summary["paths"][0]["status"] = "ERROR"
    for payload in (values["manifest.json"], evidence, risk, summary):
        payload["execution_provenance"].update(
            generated_attack_text=None, generated_attack_sha256=None)
    for path in (evidence["paths"][0], risk["paths"][0], summary["paths"][0]):
        path["execution_provenance"].update(
            generated_attack_text=None, generated_attack_sha256=None)
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="ascii")

    runs._validate_artifact_binding(directory, record, "ERROR")
    code, message = runs._worker_failure_details(summary["model_attempts"])
    assert code == "ATTACK_GENERATION_SCHEMA_INVALID"
    assert message == ("Groq repeatedly returned attacker output that did not match the required EnhancedInjection format. "
                       "The target and Judge were not evaluated, so no security conclusion was reached.")

    monkeypatch.setattr(runs, "RUN_ROOT", root)
    monkeypatch.setattr(runs, "RUN_LOCK", root / "active-run.lock")
    monkeypatch.setattr(runs, "_runs", {record.run_id: record})
    projected = runs.get_deepteam_run(record.run_id)
    assert (projected.error_code, projected.error_message) == (code, message)
    assert record.error_message == "The worker returned a fail-closed result."

    published = projected.model_copy(update={"artifact_available": True})
    runs._runs[record.run_id] = published
    runs._persist(published)
    audit = runs.get_deepteam_audit(record.run_id)
    report = reporting.socmate_report_data(record.run_id)
    assert audit is not None
    assert audit.evidence["paths"][0]["engine_result"]["native_score"] is None
    assert audit.evidence["review_results"][0]["target_evaluation"] is None
    assert report["audit"]["summary"]["model_attempts"][0]["error_code"] == "SCHEMA_VALIDATION"


def test_v2_failed_diagnostics_reject_manufactured_judge_score(fresh_catalog, tmp_path):
    record = _v2_record()
    directory = tmp_path / "run-failed-score"
    values = _v2_artifacts(directory, record, fresh_catalog)
    evidence = values["evidence.json"]
    evidence["paths"][0]["status"] = "ERROR"
    evidence["review_results"][0] = {
        "path_id": evidence["paths"][0]["path_id"], "decision": "ERROR",
        "target_evaluation": {"deviation_score": 0},
    }
    values["summary.json"]["final_status"] = "ERROR"
    values["summary.json"]["paths"][0]["status"] = "ERROR"
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="ascii")

    with pytest.raises(runs.DeepTeamRunError, match="cannot publish a Judge result or score"):
        runs._validate_artifact_binding(directory, record, "ERROR")


def test_fresh_standard_source_and_linked_context_are_target_bound(fresh_catalog, tmp_path, monkeypatch):
    record = _v2_record().model_copy(update={"status": "COMPLETED", "completed_at": "2026-11-14T00:01:00Z",
        "final_status": "RESISTED", "artifact_available": True, "critic_status": "COMPLETED",
        "vulnerability": "SQL Injection / Blind Sql Injection", "vulnerability_profile_id": EXPERIMENTAL_RISK_ID,
        "vulnerability_target_applicability": "NOT_APPLICABLE", "vulnerability_experimental_admission": "ADMITTED",
        "critic_review_id": "standard-review-222222222222", "critic_attempts": 1,
        "critic_started_at": "2026-11-14T00:02:00Z", "critic_completed_at": "2026-11-14T00:03:00Z"})
    directory = tmp_path / "run-aabbccddeeff"
    values = _v2_artifacts(directory, record, fresh_catalog)
    audit = runs.DeepTeamAuditReport(run_id=record.run_id, manifest=values["manifest.json"],
        evidence=values["evidence.json"], deepteam_risk=values["deepteam-risk.json"], summary=values["summary.json"])
    monkeypatch.setattr(reviews, "get_deepteam_catalog", lambda: fresh_catalog)
    monkeypatch.setattr(reviews, "validate_fresh_selection", catalog.validate_fresh_selection)
    monkeypatch.setattr(reviews, "validate_profile_selection", catalog.validate_profile_selection)
    monkeypatch.setattr(runs, "get_deepteam_audit", lambda run_id: audit)
    monkeypatch.setattr(runs, "RUN_ROOT", tmp_path / "api-runs")
    monkeypatch.setattr(runs, "RUN_LOCK", tmp_path / "api-runs" / "active-run.lock")
    monkeypatch.setattr(runs, "_runs", {record.run_id: record})

    source = reviews._source(record)
    assert source.schema_version == TARGET_VERSION
    assert (source.target_profile_id, source.scenario_id, source.scenario_version) == (TARGET_ID, SCENARIO_ID, "3")
    assert source.vulnerability_profile_id == EXPERIMENTAL_RISK_ID
    assert "tree-jailbreaking-v1" not in {item.id for item in source.allowed_methods}
    recommendation = source.allowed_methods[0].id
    review = StandardReview(schema_version=TARGET_VERSION, run_id=record.run_id,
        review_id=record.critic_review_id, created_at=record.critic_started_at, completed_at=record.critic_completed_at,
        input_sha256=digest(source.model_dump(mode="json")), source_audit_sha256=source.source_audit_sha256,
        assessment_spec_sha256=source.assessment_spec_sha256, source_path_id=source.source_path_id,
        recommendations=[{"attack_profile_id": recommendation, "priority": 85}], input_tokens_estimate=0,
        budget={}, model_attempts=[])
    monkeypatch.setattr(reviews, "_validated_review", lambda parent: (review, source))
    monkeypatch.setattr(runs, "_persist", lambda child: None)

    draft = reviews.create_linked_draft(record.run_id, review.review_id, recommendation)
    assert draft.linked_context.schema_version == TARGET_LINKED_VERSION
    assert draft.linked_context.redacted_parent_context_sha256 == digest(draft.linked_context.redacted_parent_context)
    runs._runs[draft.run_id] = draft.model_copy(update={"status": "COMPLETED", "final_status": "RESISTED"})
    assert reviews.create_linked_draft(record.run_id, review.review_id, recommendation).run_id == draft.run_id


def test_artifact_binding_rejects_target_mismatch(tmp_path):
    record = DeepTeamRunRecord(run_id="api-run-fresh", status="RUNNING", created_at="2026-11-14T00:00:00Z",
        scenario=SCENARIO_ID, scenario_version="3", target_profile_id=TARGET_ID, target_profile_version="0.5.0",
        target_name="Synthetic ChatMate", vulnerability="Direct User Prompt Injection",
        vulnerability_profile_id=VULNERABILITY_ID, attack="Prompt Injection", attack_profile_id="prompt-injection-v1",
        artifact_available=False, logs=[])
    directory = tmp_path / "run-aabbccddeeff"
    _bound_artifacts(directory, record)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    manifest["campaign"]["target_profile_version"] = "forged"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="ascii")

    with pytest.raises(runs.DeepTeamRunError, match="does not match"):
        runs._validate_artifact_binding(directory, record, "RESISTED")


def test_report_keeps_socmate_family_and_exposes_actual_target(monkeypatch):
    fresh = DeepTeamRunRecord(run_id="api-run-fresh", status="FAILED", created_at="2026-11-14T00:00:00Z",
        completed_at="2026-11-14T00:00:01Z", scenario=SCENARIO_ID, scenario_version="3",
        target_profile_id=TARGET_ID, target_profile_version="0.5.0", target_name="Synthetic ChatMate",
        vulnerability="Direct User Prompt Injection", vulnerability_profile_id=VULNERABILITY_ID,
        attack="Prompt Injection", attack_profile_id="prompt-injection-v1", final_status="ERROR",
        artifact_available=False, logs=[])
    monkeypatch.setattr(runs, "get_deepteam_run", lambda run_id: fresh)
    monkeypatch.setattr(reporting.soc, "get_deepteam_run", lambda run_id: fresh)
    monkeypatch.setattr(reporting.RunStore, "original_evidence", lambda self, run_id: None)

    result = reporting.socmate_report_data(fresh.run_id)

    assert result["source"] == "Synthetic ChatMate"
    assert result["target"] == {"id": TARGET_ID, "name": "Synthetic ChatMate", "version": "0.5.0",
                                "scenario_id": SCENARIO_ID, "scenario_version": "3"}
    assert result["standard_review"] is None


def test_sealed_fresh_audit_and_report_reload_without_inference(tmp_path, monkeypatch):
    root = tmp_path / "isolated-deepteam-runs"
    monkeypatch.setattr(runs, "RUN_ROOT", root)
    monkeypatch.setattr(runs, "RUN_LOCK", root / "active-run.lock")
    monkeypatch.setattr(runs, "_runs", {})
    launches = []
    monkeypatch.setattr(runs.jobs, "launch", lambda *args, **kwargs: launches.append(args))
    record = DeepTeamRunRecord(
        run_id="api-run-fresh-sealed",
        status="COMPLETED",
        created_at="2026-11-14T00:00:00Z",
        completed_at="2026-11-14T00:00:01Z",
        scenario=SCENARIO_ID,
        scenario_version="3",
        target_profile_id=TARGET_ID,
        target_profile_version="0.5.0",
        target_name="Synthetic ChatMate",
        vulnerability="Direct User Prompt Injection",
        vulnerability_profile_id=VULNERABILITY_ID,
        attack="Prompt Injection",
        attack_profile_id="prompt-injection-v1",
        final_status="RESISTED",
        artifact_available=True,
        logs=[],
    )
    directory = root / record.run_id / "run-freshsealed01"
    _bound_artifacts(directory, record)
    phase5_id = "target-run-01-phase5-assessment"
    evidence_path = directory / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="ascii"))
    evidence["paths"][0]["phase5_assessments"] = [{"evidence_id": phase5_id}]
    evidence["review_results"] = [{
        "path_id": evidence["paths"][0]["path_id"],
        "decision": "RESISTED",
        "target_evaluation": {"evidence_references": [phase5_id]},
    }]
    evidence_path.write_text(json.dumps(evidence), encoding="ascii")

    runs._runs[record.run_id] = record
    runs._persist(record)
    first_audit = runs.get_deepteam_audit(record.run_id)
    first_report = reporting.socmate_report_data(record.run_id)
    assert first_audit is not None
    assert first_audit.evidence["review_results"][0]["target_evaluation"]["evidence_references"] == [phase5_id]
    assert first_report["target"]["id"] == TARGET_ID
    assert first_report["audit"]["evidence"]["review_results"][0]["target_evaluation"]["evidence_references"] == [phase5_id]
    assert all((directory / name).is_file() for name in (
        "manifest.json", "evidence.json", "deepteam-risk.json", "summary.json"
    ))

    runs._runs = {}
    runs._load_records()
    reloaded_audit = runs.get_deepteam_audit(record.run_id)
    reloaded_report = reporting.socmate_report_data(record.run_id)
    assert reloaded_audit is not None
    assert reloaded_audit.model_dump(mode="json") == first_audit.model_dump(mode="json")
    assert reloaded_report == first_report
    assert launches == []


def test_sealed_baseline_provenance_reaches_audit_and_report(
    fresh_catalog, tmp_path, monkeypatch
):
    root = tmp_path / "isolated-baseline-runs"
    monkeypatch.setattr(runs, "RUN_ROOT", root)
    monkeypatch.setattr(runs, "RUN_LOCK", root / "active-run.lock")
    monkeypatch.setattr(runs, "_runs", {})
    record = _v2_record().model_copy(update={
        "status": "COMPLETED",
        "completed_at": "2026-11-14T00:01:00Z",
        "final_status": "RESISTED",
        "artifact_available": True,
    })
    directory = root / record.run_id / "run-baseline-sealed"
    _v2_artifacts(directory, record, fresh_catalog)
    runs._validate_artifact_binding(directory, record, "RESISTED")

    runs._runs[record.run_id] = record
    runs._persist(record)
    audit = runs.get_deepteam_audit(record.run_id)
    report = reporting.socmate_report_data(record.run_id)

    assert audit is not None
    assert audit.manifest["execution_provenance"]["execution_mode"] == "BASELINE_UNENHANCED"
    assert audit.summary["execution_provenance"]["enhancement_applied"] is False
    assert report["audit"]["evidence"]["execution_provenance"] == audit.evidence["execution_provenance"]
