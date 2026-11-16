from __future__ import annotations

import json
import subprocess
from functools import lru_cache

from .config import API_ROOT
from .contracts import DeepTeamAttackProfile, DeepTeamCatalog, DeepTeamVulnerabilityProfile


WORKSPACE_ROOT = API_ROOT.parents[1]
WORKER_ROOT = WORKSPACE_ROOT / "services" / "deepteam-worker"
WORKER_PYTHON = WORKER_ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_ATTACK_PROFILE_ID = "permission-escalation-v1"
DEFAULT_VULNERABILITY_PROFILE_ID = "ExcessiveAgency:permissions"
FRESH_TARGET_PROFILE_ID = "secmate.synthetic-chatmate.fresh.v1"
FRESH_SCENARIO_ID = "chatmate-direct-user-prompt-injection"
FRESH_ATTACK_PROFILE_ID = "prompt-injection-v1"
FRESH_BINDING_VERSION = "2.0.0"
FRESH_EXECUTION_PROFILE_ID = "deepteam-conversation-v1"
FRESH_EXECUTION_PROFILE_VERSION = "2.1.0"
FRESH_TARGET_TOKEN_LIMIT = 12000

_FRESH_UNSUPPORTED_RISK_CLASSES = {
    "BFLA": ("FRESH_PRIVILEGED_PROTOCOL_UNAVAILABLE", "requires a privileged function and authorization protocol that fresh ChatMate does not expose"),
    "BOLA": ("FRESH_IDENTITY_PROTOCOL_UNAVAILABLE", "requires object identity and authorization boundaries that fresh ChatMate does not expose"),
    "RBAC": ("FRESH_IDENTITY_PROTOCOL_UNAVAILABLE", "requires role and identity protocols that fresh ChatMate does not expose"),
    "DebugAccess": ("FRESH_ADMIN_PROTOCOL_UNAVAILABLE", "requires debug or administrative interfaces that fresh ChatMate does not expose"),
    "SSRF": ("FRESH_NETWORK_PROTOCOL_UNAVAILABLE", "requires outbound network or internal-service access that fresh ChatMate does not expose"),
    "ExcessiveAgency": ("FRESH_PRIVILEGED_PROTOCOL_UNAVAILABLE", "requires autonomous or privileged effects beyond approval-gated synthetic proposals"),
    "IndirectInstruction": ("FRESH_INJECTION_CHANNEL_UNAVAILABLE", "requires controlled malicious document, tool-output, RAG, or cross-context delivery that cannot be honestly supplied by the fresh target"),
    "ToolOrchestrationAbuse": ("FRESH_TOOL_PROTOCOL_UNAVAILABLE", "requires recursive or shared-state orchestration beyond the bounded linear tool loop"),
    "AgentIdentityAbuse": ("FRESH_INTER_AGENT_PROTOCOL_UNAVAILABLE", "requires delegated agent identity or cross-agent trust that fresh ChatMate does not expose"),
    "ToolMetadataPoisoning": ("FRESH_TOOL_METADATA_CHANNEL_UNAVAILABLE", "requires attacker-controlled tool metadata or registry delivery that fresh ChatMate does not expose"),
    "UnexpectedCodeExecution": ("FRESH_CODE_EXECUTION_PROTOCOL_UNAVAILABLE", "requires a code, shell, or dynamic-evaluation execution channel that fresh ChatMate does not expose"),
    "InsecureInterAgentCommunication": ("FRESH_INTER_AGENT_PROTOCOL_UNAVAILABLE", "requires an inter-agent messaging protocol that fresh ChatMate does not expose"),
    "AutonomousAgentDrift": ("FRESH_AUTONOMY_PROTOCOL_UNAVAILABLE", "requires autonomous execution, reward, or agent-collusion state that fresh ChatMate does not expose"),
    "ExploitToolAgent": ("FRESH_WRITE_PROTOCOL_UNAVAILABLE", "requires privileged or destructive effects; available proposals are synthetic and require trusted approval"),
    "ExternalSystemAbuse": ("FRESH_OUTBOUND_PROTOCOL_UNAVAILABLE", "requires real outbound delivery; available proposals stage synthetic review without delivery"),
    "CrossContextRetrieval": ("FRESH_IDENTITY_PROTOCOL_UNAVAILABLE", "requires tenant, user, or role retrieval identities that fresh ChatMate does not expose"),
    "SystemReconnaissance": ("FRESH_SYSTEM_METADATA_CHANNEL_UNAVAILABLE", "requires authoritative file, database, or retrieval-configuration metadata that fresh ChatMate cannot supply"),
}
_FRESH_UNSUPPORTED_RISK_IDS = {
    "PIILeakage:api_and_database_access": ("FRESH_DATA_PROTOCOL_UNAVAILABLE", "requires API or database access that fresh ChatMate does not expose"),
    "PIILeakage:session_leak": ("FRESH_SESSION_PROTOCOL_UNAVAILABLE", "requires cross-session state that fresh ChatMate deliberately does not expose"),
}


@lru_cache(maxsize=1)
def get_deepteam_catalog() -> DeepTeamCatalog:
    if not WORKER_PYTHON.exists():
        raise RuntimeError("The isolated Python 3.11 worker environment is unavailable.")
    process = subprocess.Popen(
        [str(WORKER_PYTHON), "-m", "secmate_worker.catalog_export"],
        cwd=WORKER_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise RuntimeError("The DeepTeam catalog could not be loaded.") from error
    if process.returncode != 0:
        raise RuntimeError("The DeepTeam catalog could not be loaded.")
    return DeepTeamCatalog.model_validate(json.loads(stdout))


def attack_profile(profile_id: str) -> DeepTeamAttackProfile:
    profile = next(
        (item for item in get_deepteam_catalog().attack_profiles if item.id == profile_id),
        None,
    )
    if profile is None:
        raise ValueError("Unknown or unavailable DeepTeam attack profile.")
    return profile


def vulnerability_profile(profile_id: str) -> DeepTeamVulnerabilityProfile:
    profile = next(
        (item for item in get_deepteam_catalog().vulnerability_profiles if item.id == profile_id),
        None,
    )
    if profile is None:
        raise ValueError("Unknown or unavailable DeepTeam vulnerability profile.")
    return profile


def attack_profile_name(profile_id: str) -> str:
    return attack_profile(profile_id).name


def vulnerability_profile_name(profile_id: str) -> str:
    return vulnerability_profile(profile_id).name


def target_profile(profile_id: str):
    profile = next(
        (item for item in get_deepteam_catalog().target_profiles if item.id == profile_id),
        None,
    )
    if profile is None or not profile.api_selectable:
        raise ValueError("Unknown or unavailable DeepTeam target profile.")
    return profile


def fresh_vulnerability_profile(profile_id: str | None = None) -> DeepTeamVulnerabilityProfile:
    if profile_id is None:
        profile_id = "DirectPromptInjection:direct_user_instruction"
    return vulnerability_profile(profile_id)


def fresh_selection_capability(attack, vulnerability) -> dict:
    attack_detail = attack.target_applicability.get(FRESH_TARGET_PROFILE_ID, {})
    vulnerability_detail = vulnerability.target_applicability.get(FRESH_TARGET_PROFILE_ID, {})
    established = (
        attack_detail.get("applicability") == "APPLICABLE"
        and vulnerability_detail.get("applicability") == "APPLICABLE"
    )
    unsupported = None
    if attack.id == "tree-jailbreaking-v1":
        unsupported = (
            "FRESH_TREE_SPECULATIVE_HISTORY_UNSUPPORTED",
            "Tree Jailbreaking requires speculative sibling histories, which conflict with fresh ChatMate's authoritative linear conversation per path.",
        )
    unsupported = unsupported or _FRESH_UNSUPPORTED_RISK_IDS.get(vulnerability.id)
    unsupported = unsupported or _FRESH_UNSUPPORTED_RISK_CLASSES.get(vulnerability.class_name)
    code, reason = unsupported or (
        "FRESH_BOUNDED_TEXT_EXECUTABLE",
        "The selected risk and method can execute through bounded text conversation and the available synthetic read and approval-gated proposal tools.",
    )
    return {
        "schema_version": "fresh-selection-capability-v1",
        "target_profile_id": FRESH_TARGET_PROFILE_ID,
        "attack_profile_id": attack.id,
        "attack_name": attack.name,
        "attack_turn_mode": attack.turn_mode,
        "vulnerability_profile_id": vulnerability.id,
        "vulnerability_name": vulnerability.name,
        "vulnerability_category": vulnerability.category,
        "admission": "ESTABLISHED" if established else "EXPERIMENTAL",
        "established_applicability": established,
        "execution_capability": "UNSUPPORTED" if unsupported else "EXECUTABLE",
        "capability_code": code,
        "capability_reason": reason,
    }


def validate_fresh_selection(
    attack_profile_id: str,
    vulnerability_profile_id: str | None,
    target_profile_id: str,
    scenario_id: str,
    execution_mode: str,
    max_paths: int,
):
    if target_profile_id != FRESH_TARGET_PROFILE_ID or scenario_id != FRESH_SCENARIO_ID:
        raise ValueError("Only the fresh ChatMate direct prompt-injection target and scenario are supported.")
    if (execution_mode, max_paths) not in {("SINGLE", 1), ("ADAPTIVE", 2)}:
        raise ValueError("Fresh ChatMate execution must be SINGLE/1 or ADAPTIVE/2.")
    catalog = get_deepteam_catalog()
    if catalog.schema_version != "2.3":
        raise ValueError("Fresh ChatMate experimental admission requires worker catalog schema 2.3.")
    target = target_profile(target_profile_id)
    profiles = target.execution_profiles or []
    execution_profile = next((item for item in profiles if item.get("id") == FRESH_EXECUTION_PROFILE_ID), None)
    if (
        target.scenario_id != scenario_id
        or target.version != "0.5.0"
        or target.binding_version != FRESH_BINDING_VERSION
        or target.target_id != target_profile_id
        or target.target_version != target.version
        or target.api_registration is not True
        or target.deepteam_provider is not True
        or execution_mode not in (target.execution_modes or [])
        or target.max_paths != 2
        or target.gateway_kind != "CHATMATE_FRESH"
        or not isinstance(execution_profile, dict)
        or execution_profile.get("version") != FRESH_EXECUTION_PROFILE_VERSION
        or execution_mode not in execution_profile.get("execution_modes", [])
        or execution_profile.get("max_paths") != 2
        or execution_profile.get("max_conversation_turns") != 4
        or execution_profile.get("fresh_state_per_path") is not True
        or execution_profile.get("caller_history_authoritative") is not False
    ):
        raise ValueError("The worker catalog target metadata does not match the admitted fresh ChatMate contract.")
    projection = target.experimental_catalog_projection
    all_attack_ids = [profile.id for profile in catalog.attack_profiles]
    all_vulnerability_ids = [profile.id for profile in catalog.vulnerability_profiles]
    if (not isinstance(projection, dict)
            or projection.get("schema_version") != "1.0"
            or projection.get("admission") != "EXPERIMENTAL"
            or projection.get("attack_profile_ids") != all_attack_ids
            or projection.get("vulnerability_profile_ids") != all_vulnerability_ids
            or len(all_attack_ids) != len(set(all_attack_ids))
            or len(all_vulnerability_ids) != len(set(all_vulnerability_ids))):
        raise ValueError("The worker catalog experimental projection is not the exact bounded 2.3 catalog.")
    selected_attack = attack_profile(attack_profile_id)
    selected_vulnerability = fresh_vulnerability_profile(vulnerability_profile_id)
    for profile, projected_ids in ((selected_attack, all_attack_ids), (selected_vulnerability, all_vulnerability_ids)):
        admission = profile.target_experimental_admission.get(target_profile_id, {})
        if (profile.id not in projected_ids or admission.get("admission") != "ADMITTED"
                or admission.get("selectable") is not True or not isinstance(admission.get("reason"), str)):
            raise ValueError(f"Profile {profile.id} is not experimentally admitted for fresh ChatMate.")
    if execution_mode == "ADAPTIVE" and len(all_attack_ids) < 2:
        raise ValueError("ADAPTIVE/2 requires at least two distinct experimentally admitted attack methods.")
    return target, selected_attack, selected_vulnerability, fresh_selection_capability(selected_attack, selected_vulnerability)


def validate_profile_selection(
    attack_profile_id: str,
    vulnerability_profile_id: str,
    target_profile_id: str,
    scenario_id: str,
) -> tuple[DeepTeamAttackProfile, DeepTeamVulnerabilityProfile]:
    selected_attack = attack_profile(attack_profile_id)
    selected_vulnerability = vulnerability_profile(vulnerability_profile_id)
    for profile_type, profile in (
        ("attack", selected_attack),
        ("vulnerability", selected_vulnerability),
    ):
        detail = profile.target_applicability.get(target_profile_id)
        if (
            profile.applicability != "APPLICABLE"
            or target_profile_id not in profile.target_profile_ids
            or scenario_id not in profile.scenario_ids
            or detail is not None and detail.get("applicability") != "APPLICABLE"
        ):
            raise ValueError(
                f"DeepTeam {profile_type} profile {profile.id} is not applicable to "
                f"{target_profile_id} / {scenario_id}: {(detail or {}).get('reason', profile.applicability_reason)}"
            )
    return selected_attack, selected_vulnerability
