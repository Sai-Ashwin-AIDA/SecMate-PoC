"""Pure ownership, eligibility, expiry, and source projection rules."""
from ..contracts import digest
from .contracts import utc_seconds


def fact_ref(fact):
    return {"resource_id": fact["id"], "source_kind": "synthetic_personal_memory", "content_digest": digest(fact)}


def owner_state(header, facts):
    return {**header, "facts": sorted(facts, key=lambda value: value["ordinal"])}


def owner_meta(header, facts):
    state = owner_state(header, facts)
    return {**header, "stored_fact_refs": [fact_ref(f) for f in state["facts"]], "state_digest": digest(state)}


def eligibility_reason(eligibility):
    context = eligibility["context"]
    if not (eligibility["memory_owner"] == context["owner"] == eligibility["requested_by"]):
        return "owner_mismatch"
    if not eligibility["subsystem_enabled"]:
        return "rollout_disabled"
    if context["deleted"]:
        return "deleted"
    if context["shared"]:
        return "shared"
    if context["participant_ids"] != [context["owner"]]:
        return "multiparticipant"
    if context["project_id"] is not None:
        return "project"
    if context["memory_disabled"] or eligibility["run_memory_disabled"]:
        return "conversation_disabled"
    return None


def active_facts(facts, seconds):
    result = [f for f in facts if utc_seconds(f["created_at"]) <= seconds < utc_seconds(f["expires_at"])]
    return sorted(result, key=lambda value: (utc_seconds(value["created_at"]), value["ordinal"]), reverse=True)


def payload(header, facts, seconds):
    selected = active_facts(facts, seconds)
    if not selected:
        return None
    return {"source_kind": "synthetic_personal_memory", "owner": header["owner"], "revision": header["revision"],
            "facts": [{"fact_id": fact["id"], "text": fact["text"], "source_ref": fact_ref(fact)} for fact in selected]}


def evaluate(eligibility, header=None, facts=None, seconds=0.0):
    reason = eligibility_reason(eligibility)
    if reason:
        return "ineligible", reason, None
    if header is None:
        return "unavailable", "memory_unavailable", None
    if not header["enabled"]:
        return "disabled", "owner_disabled", None
    value = payload(header, facts or [], seconds)
    return ("loaded", None, value) if value else ("empty", "no_active_facts", None)
