"""Versioned DeepTeam onboarding truth for the fresh Phase5 target."""

import json
from pathlib import Path
from typing import Final, Iterable

from ..calendar_phase3.contracts import PROPOSE_MEETING, READ_CALENDAR
from ..communication.contracts import DIRECTORY, MAIL, PROPOSE, TEAMS
from ..contracts import READ_TOOL, clone


ONBOARDING_BINDING_VERSION: Final = "2.0.0"
TARGET_ID: Final = "secmate.synthetic-chatmate.fresh.v1"
TARGET_VERSION: Final = "0.5.0"
SMOKE_EXECUTION_PROFILE_ID: Final = "phase5-smoke-v1"
DEEPTEAM_EXECUTION_PROFILE_ID: Final = "deepteam-conversation-v1"
DEEPTEAM_EXECUTION_PROFILE_VERSION: Final = "2.1.0"
DEEPTEAM_ATTACK_PROFILE_IDS: Final = (
    "permission-escalation-v1",
    "authority-escalation-v1",
    "prompt-injection-v1",
    "prompt-probing-v1",
    "system-override-v1",
    "roleplay-v1",
    "emotional-manipulation-v1",
    "gray-box-v1",
    "math-problem-v1",
    "multilingual-v1",
    "linguistic-confusion-v1",
    "input-bypass-v1",
    "context-poisoning-v1",
    "goal-redirection-v1",
    "synthetic-context-injection-v1",
    "adversarial-poetry-v1",
    "base64-v1",
    "character-stream-v1",
    "context-flooding-v1",
    "embedded-json-v1",
    "leetspeak-v1",
    "rot13-v1",
    "crescendo-v1",
    "linear-jailbreaking-v1",
    "sequential-jailbreak-v1",
    "bad-likert-judge-v1",
)

_PROFILE_KEYS = {"schema_version", "target_id", "target_version", "profile_id", "profile_version", "budgets", "tools"}
_BUDGETS = {
    "logical_turn_limit": 4,
    "attempts_per_turn": 2,
    "provider_attempt_limit": 4,
    "output_token_limit": 500,
    "provider_token_limit": 12000,
    "request_timeout_seconds": 45,
    "real_deadline_seconds": 120,
}
_READ_HANDLERS = frozenset({READ_TOOL, MAIL, TEAMS, DIRECTORY, READ_CALENDAR})
_PROPOSAL_HANDLERS = frozenset({PROPOSE, PROPOSE_MEETING})


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_execution_profile_key")
        value[key] = item
    return value


def load_execution_profile(path: Path | None = None, *, allow_legacy: bool = False) -> dict:
    """Load and strictly validate the worker-owned effective profile."""
    source = path or Path(__file__).with_name("execution_profile.json")
    try:
        profile = json.loads(source.read_text(encoding="ascii"), object_pairs_hook=_unique_object)
        if not isinstance(profile, dict) or set(profile) != _PROFILE_KEYS:
            raise ValueError("execution_profile_shape")
        if (
            profile["schema_version"] != "1.0.0"
            or profile["target_id"] != TARGET_ID
            or profile["target_version"] != TARGET_VERSION
            or profile["profile_id"] != DEEPTEAM_EXECUTION_PROFILE_ID
            or profile["profile_version"] not in ({DEEPTEAM_EXECUTION_PROFILE_VERSION, "2.0.0"} if allow_legacy else {DEEPTEAM_EXECUTION_PROFILE_VERSION})
            or profile["budgets"] != ({**_BUDGETS, "provider_token_limit": 8000} if profile["profile_version"] == "2.0.0" else _BUDGETS)
            or any(type(value) is not int for value in profile["budgets"].values())
        ):
            raise ValueError("execution_profile_identity")
        tools = profile["tools"]
        if not isinstance(tools, list) or len(tools) != 7:
            raise ValueError("execution_profile_tools")
        names = []
        for tool in tools:
            if not isinstance(tool, dict) or set(tool) != {"name", "availability", "access"}:
                raise ValueError("execution_profile_tool_shape")
            name = tool["name"]
            if name in _READ_HANDLERS:
                expected = {"name": name, "availability": "available", "access": "read_only"}
            elif name in _PROPOSAL_HANDLERS:
                expected = {"name": name, "availability": "requires_approval", "access": "staged_only"}
            else:
                raise ValueError("execution_profile_unknown_tool")
            if tool != expected:
                raise ValueError("execution_profile_tool_policy")
            names.append(name)
        if len(set(names)) != 7 or set(names) != _READ_HANDLERS | _PROPOSAL_HANDLERS:
            raise ValueError("execution_profile_tool_set")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("invalid_execution_profile") from error
    return clone(profile)


def onboarding_binding(
    *,
    experimental_attack_profile_ids: Iterable[str] | None = None,
    experimental_vulnerability_profile_ids: Iterable[str] | None = None,
) -> dict:
    execution_profile = load_execution_profile()
    binding = {
        "binding_version": ONBOARDING_BINDING_VERSION,
        "target_id": TARGET_ID,
        "target_version": TARGET_VERSION,
        "gateway_kind": "CHATMATE_FRESH",
        "api_registration": True,
        "deepteam_provider": True,
        "execution_modes": ["SINGLE", "ADAPTIVE"],
        "max_paths": 2,
        "attack_profile_ids": list(DEEPTEAM_ATTACK_PROFILE_IDS),
        "vulnerability_profile_ids": ["DirectPromptInjection:direct_user_instruction"],
        "execution_profiles": [
            {
                "id": SMOKE_EXECUTION_PROFILE_ID,
                "version": "1.0.0",
                "execution_modes": ["SINGLE"],
                "max_paths": 1,
                "max_conversation_turns": 1,
                "attack_profile_ids": ["prompt-injection-v1"],
            },
            {
                "id": DEEPTEAM_EXECUTION_PROFILE_ID,
                "version": DEEPTEAM_EXECUTION_PROFILE_VERSION,
                "execution_modes": ["SINGLE", "ADAPTIVE"],
                "max_paths": 2,
                "max_conversation_turns": 4,
                "fresh_state_per_path": True,
                "caller_history_authoritative": False,
                "attack_profile_ids": list(DEEPTEAM_ATTACK_PROFILE_IDS),
            },
        ],
        "effective_execution_profile": execution_profile,
        "unsupported_attack_profiles": {
            "tree-jailbreaking-v1": (
                "Tree Jailbreaking issues speculative sibling callbacks against the same "
                "history; fresh ChatMate requires one authoritative linear conversation per path."
            )
        },
    }
    if (
        experimental_attack_profile_ids is not None
        and experimental_vulnerability_profile_ids is not None
    ):
        binding["experimental_catalog_projection"] = {
            "schema_version": "1.0",
            "admission": "EXPERIMENTAL",
            "attack_profile_ids": list(experimental_attack_profile_ids),
            "vulnerability_profile_ids": list(experimental_vulnerability_profile_ids),
        }
    return binding
