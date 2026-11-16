import json

import pytest
import secmate_worker.deepteam_catalog as catalog_module

from secmate_worker.deepteam_catalog import (
    ATTACK_PROFILES,
    VULNERABILITY_PROFILES,
    assessment_spec_for_vulnerability,
    catalog_payload,
    ensure_profiles_applicable,
    resolve_attack_profile,
    resolve_vulnerability_profile,
)


def test_all_allowlisted_attack_profiles_are_unique_and_cover_both_turn_modes():
    assert len(ATTACK_PROFILES) == 27
    assert len({profile.profile_id for profile in ATTACK_PROFILES}) == 27
    assert {profile.turn_mode for profile in ATTACK_PROFILES} == {"SINGLE", "MULTI"}

    for profile in ATTACK_PROFILES[:22]:
        first = profile.builder(None)
        second = profile.builder(None)
        assert first.__class__.__name__ == profile.class_name
        assert second.__class__.__name__ == profile.class_name
        assert first is not second


def test_all_installed_vulnerability_subtypes_are_exposed():
    assert len(VULNERABILITY_PROFILES) >= 120
    assert len({profile.profile_id for profile in VULNERABILITY_PROFILES}) == len(VULNERABILITY_PROFILES)
    assert resolve_vulnerability_profile("ExcessiveAgency:permissions").category == "Agentic"


def test_catalog_distinguishes_registration_from_fixed_scenario_applicability():
    catalog = catalog_payload()
    applicable_attacks = [
        profile for profile in catalog["attack_profiles"]
        if profile["applicability"] == "APPLICABLE"
    ]
    applicable_vulnerabilities = [
        profile for profile in catalog["vulnerability_profiles"]
        if profile["applicability"] == "APPLICABLE"
    ]

    assert catalog["schema_version"] == "2.3"
    assert {target["name"] for target in catalog["target_profiles"]} == {
        "SocMate",
        "ChatMate",
        "ChatMate(Vuln)",
        "Synthetic ChatMate",
    }
    assert len(applicable_attacks) == 27
    assert len(applicable_vulnerabilities) == len(catalog["vulnerability_profiles"])
    assert {
        profile["capability_level"] for profile in applicable_attacks
    } == {"REGISTERED", "OFFLINE_VERIFIED"}
    assert {
        profile["id"]
        for profile in applicable_attacks
        if profile["capability_level"] == "OFFLINE_VERIFIED"
    } == {
        "crescendo-v1",
        "linear-jailbreaking-v1",
        "tree-jailbreaking-v1",
        "sequential-jailbreak-v1",
        "bad-likert-judge-v1",
    }
    assert next(
        profile for profile in applicable_vulnerabilities
        if profile["id"] == "ExcessiveAgency:permissions"
    )["capability_level"] == "OFFLINE_VERIFIED"
    assert next(
        profile for profile in applicable_vulnerabilities
        if profile["id"] == "IndirectInstruction:document_embedded_instructions"
    )["capability_level"] == "APPLICABLE"
    assert next(
        profile for profile in applicable_vulnerabilities
        if profile["id"] == "DirectPromptInjection:direct_user_instruction"
    )["capability_level"] == "OFFLINE_VERIFIED"
    assert all(
        profile["capability_level"] == "REGISTERED"
        for profile in catalog["vulnerability_profiles"]
        if profile["id"] not in {
            "ExcessiveAgency:permissions",
            "IndirectInstruction:document_embedded_instructions",
            "DirectPromptInjection:direct_user_instruction",
        }
    )
    fresh = next(
        target for target in catalog["target_profiles"]
        if target["id"] == "secmate.synthetic-chatmate.fresh.v1"
    )
    projection = fresh["experimental_catalog_projection"]
    assert projection["admission"] == "EXPERIMENTAL"
    assert set(projection["attack_profile_ids"]) == {
        profile.profile_id for profile in ATTACK_PROFILES
    }
    assert set(projection["vulnerability_profile_ids"]) == {
        profile.profile_id for profile in VULNERABILITY_PROFILES
    }


def test_registered_vulnerability_is_executable_without_verification_claim():
    vulnerability = resolve_vulnerability_profile("PromptLeakage:instructions")

    ensure_profiles_applicable(resolve_attack_profile("base64-v1"), vulnerability)

    metadata = catalog_module.vulnerability_profile_metadata(vulnerability)
    assert metadata["applicability"] == "APPLICABLE"
    assert metadata["capability_level"] == "REGISTERED"


def test_vulnerable_target_is_restricted_to_reviewed_permissions_slice():
    attack = resolve_attack_profile("permission-escalation-v1")

    ensure_profiles_applicable(
        attack,
        resolve_vulnerability_profile("ExcessiveAgency:permissions"),
        "socmate-vuln",
    )
    with pytest.raises(ValueError, match="is not applicable"):
        ensure_profiles_applicable(
            attack,
            resolve_vulnerability_profile("PIILeakage:direct_disclosure"),
            "socmate-vuln",
        )


def test_assessment_specs_are_vulnerability_specific():
    permissions = assessment_spec_for_vulnerability(
        resolve_vulnerability_profile("ExcessiveAgency:permissions"),
        "Synthetic SOC assistant",
    )
    misinformation = assessment_spec_for_vulnerability(
        resolve_vulnerability_profile("Misinformation:factual_errors"),
        "Synthetic SOC assistant",
    )

    assert permissions.vulnerability_profile_id == "ExcessiveAgency:permissions"
    assert "trusted approval" in permissions.attack_objective
    assert misinformation.vulnerability_profile_id == "Misinformation:factual_errors"
    assert "Misinformation / Factual Errors" in misinformation.attack_objective
    assert misinformation.compromise_criteria != permissions.compromise_criteria
    assert misinformation.policies[0].policy_id == "SECMATE_MISINFORMATION_FACTUAL_ERRORS"

    graphic = assessment_spec_for_vulnerability(
        resolve_vulnerability_profile("GraphicContent:graphic_content"),
        "Synthetic SOC assistant",
    )
    assert "response itself" in graphic.compromise_criteria[0]
    assert "actionable" not in " ".join(graphic.compromise_criteria).lower()


def test_profile_scope_mismatch_fails_closed(monkeypatch):
    metadata = catalog_module.attack_profile_metadata(
        resolve_attack_profile("base64-v1")
    )
    monkeypatch.setattr(
        catalog_module,
        "attack_profile_metadata",
        lambda profile: {**metadata, "target_profile_ids": ["another-target"]},
    )

    with pytest.raises(ValueError, match="is not applicable"):
        catalog_module.ensure_profiles_applicable(
            resolve_attack_profile("base64-v1"),
            resolve_vulnerability_profile("ExcessiveAgency:permissions"),
        )


def test_unknown_attack_profile_fails_closed():
    with pytest.raises(ValueError, match="Unknown DeepTeam attack profile"):
        resolve_attack_profile("arbitrary-client-class")

    with pytest.raises(ValueError, match="Unknown DeepTeam vulnerability profile"):
        resolve_vulnerability_profile("ArbitraryClass:unknown")


@pytest.mark.parametrize("profile", ATTACK_PROFILES, ids=lambda profile: profile.profile_id)
def test_fresh_chatmate_attack_compatibility_is_explicit_for_every_method(profile):
    vulnerability = resolve_vulnerability_profile(
        "DirectPromptInjection:direct_user_instruction"
    )
    detail = catalog_module.attack_profile_metadata(profile)["target_applicability"][
        "secmate.synthetic-chatmate.fresh.v1"
    ]
    admission = catalog_module.attack_profile_metadata(profile)[
        "target_experimental_admission"
    ]["secmate.synthetic-chatmate.fresh.v1"]
    assert admission == {
        "admission": "ADMITTED",
        "selectable": True,
        "reason": admission["reason"],
    }
    ensure_profiles_applicable(
        profile, vulnerability, "secmate.synthetic-chatmate.fresh.v1"
    )
    if profile.profile_id == "tree-jailbreaking-v1":
        assert detail["applicability"] == "NOT_APPLICABLE"
        assert "speculative sibling histories" in detail["reason"]
        capability = catalog_module.fresh_selection_capability(profile, vulnerability)
        assert capability.execution_capability == "UNSUPPORTED"
        assert capability.capability_code == "FRESH_TREE_SPECULATIVE_HISTORY_UNSUPPORTED"
    else:
        assert detail["applicability"] == "APPLICABLE"
        capability = catalog_module.fresh_selection_capability(profile, vulnerability)
        assert capability.capability_reason == (
            "The selected risk and method can execute through bounded text conversation and "
            "the available synthetic read and approval-gated proposal tools."
        )


@pytest.mark.parametrize("profile", VULNERABILITY_PROFILES, ids=lambda profile: profile.profile_id)
def test_every_registered_risk_is_experimentally_admitted_without_rewriting_applicability(profile):
    metadata = catalog_module.vulnerability_profile_metadata(profile)
    established = metadata["target_applicability"][
        "secmate.synthetic-chatmate.fresh.v1"
    ].copy()
    admission = metadata["target_experimental_admission"][
        "secmate.synthetic-chatmate.fresh.v1"
    ]

    assert admission["admission"] == "ADMITTED"
    assert admission["selectable"] is True
    ensure_profiles_applicable(
        resolve_attack_profile("prompt-injection-v1"),
        profile,
        "secmate.synthetic-chatmate.fresh.v1",
    )
    assert metadata["target_applicability"][
        "secmate.synthetic-chatmate.fresh.v1"
    ] == established


def test_fresh_capability_policy_and_specs_match_execution_profile_two():
    attack = resolve_attack_profile("emotional-manipulation-v1")
    executable = resolve_vulnerability_profile("SQLInjection:blind_sql_injection")
    assert catalog_module.fresh_selection_capability(attack, executable).capability_reason.endswith(
        "available synthetic read and approval-gated proposal tools."
    )

    unsupported_reasons = {
        "ExcessiveAgency:permissions": "approval-gated synthetic proposals",
        "ToolOrchestrationAbuse:recursive_tool_calls": "bounded linear tool loop",
        "ExploitToolAgent:data_destruction": "require trusted approval",
        "ExternalSystemAbuse:communications_spam": "stage synthetic review without delivery",
    }
    for profile_id, expected in unsupported_reasons.items():
        capability = catalog_module.fresh_selection_capability(
            attack, resolve_vulnerability_profile(profile_id)
        )
        assert capability.execution_capability == "UNSUPPORTED"
        assert expected in capability.capability_reason

    for profile_id in (
        "DirectPromptInjection:direct_user_instruction",
        "SQLInjection:blind_sql_injection",
    ):
        spec = assessment_spec_for_vulnerability(
            resolve_vulnerability_profile(profile_id),
            catalog_module.CHATMATE_FRESH_PROFILE.purpose,
            "secmate.synthetic-chatmate.fresh.v1",
        )
        serialized = json.dumps(spec.model_dump(mode="json"))
        assert "mail and Teams retrieval" not in serialized
        assert "read-only allowlist" not in serialized
        assert "approval" in serialized


@pytest.mark.parametrize(
    "profile_id",
    ["Misinformation:factual_errors", "Bias:religion", "PromptLeakage:instructions"],
)
def test_fresh_specs_use_exact_selected_risk_and_fresh_category_criteria(profile_id):
    profile = resolve_vulnerability_profile(profile_id)
    spec = assessment_spec_for_vulnerability(
        profile,
        "Fresh synthetic company chat assistant",
        "secmate.synthetic-chatmate.fresh.v1",
    )
    payload = spec.model_dump_json()

    assert spec.vulnerability_profile_id == profile.profile_id
    assert spec.vulnerability_name == profile.name
    assert spec.vulnerability_category == profile.category
    assert profile.profile_id in spec.attack_objective
    assert profile.name in spec.attack_objective
    assert profile.category in spec.attack_objective
    assert profile.profile_id in spec.policies[0].statement
    assert spec.compromise_criteria == catalog_module._category_assessment_criteria(profile)["compromise_criteria"]
    assert "fresh Synthetic ChatMate" in payload
    assert "SOCMate" not in payload
    assert "CHATMATE_DIRECT_USER_INSTRUCTION_BOUNDARY" not in payload
    assert "direct user prompt injection" not in payload.lower()
