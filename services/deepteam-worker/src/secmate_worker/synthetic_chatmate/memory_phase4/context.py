"""Fresh stable-block memory rendering and selected evidence projection."""
from ..contracts import clone, digest
from ...job_runtime import canonical


def render_request(base_request, guidance, memory_payload):
    request = clone(base_request)
    if not request["items"] or request["items"][0].get("role") != "developer":
        raise ValueError("stable_block_missing")
    prefix = guidance + "\n"
    content = request["items"][0]["content"]
    if not content.startswith(prefix):
        raise ValueError("stable_guidance")
    stable = __import__("json").loads(content[len(prefix):])
    if memory_payload is None:
        stable.pop("personal_memory", None)
    else:
        stable["personal_memory"] = memory_payload
    request["items"][0]["content"] = prefix + canonical(stable)
    return request


def extract(request, guidance, *, selected=False):
    prefix = guidance + "\n"
    content = request["items"][0]["content"]
    if not content.startswith(prefix):
        raise ValueError("stable_guidance")
    stable = __import__("json").loads(content[len(prefix):])
    value = stable.get("personal_memory")
    if selected and "personal_memory" not in stable:
        raise ValueError("selected_sentinel_missing")
    return value


def binding(request, guidance):
    value = extract(request, guidance)
    return value is not None, digest(value)


def suppress(events, guidance):
    result = clone(events)
    for event in result:
        if event["type"] == "model.request_built":
            request = event["data"]["request"]
            prefix = guidance + "\n"
            stable = __import__("json").loads(request["items"][0]["content"][len(prefix):])
            stable["personal_memory"] = None
            request["items"][0]["content"] = prefix + canonical(stable)
        elif event["type"] == "memory.request_bound":
            event["data"]["actual_present"] = None
            event["data"]["actual_payload_digest"] = None
    if result:
        last = result[-1]
        result.append({**last, "event_id": last["event_id"] + 1, "caused_by": last["event_id"], "type": "evidence.completeness_gap",
            "run_id": None, "call_id": None, "action_id": None, "data": {"export_profile": "missing-memory-request-binding-telemetry-0.4.0",
            "missing": ["actual_memory_input", "actual_memory_presence", "actual_memory_digest", "derived_correspondence"], "restricted_truth_modified": False}})
    return result
