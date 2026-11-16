"""Additive Phase 3 definitions with complete fixed-template admission."""
import hashlib
from pathlib import Path

from ...job_runtime import canonical
from ..contracts import READ_TOOL, Script, SyntheticError, clone, digest
from ..communication.contracts import PROPOSE
from ..communication_repaired.artifacts import CommunicationBundle, _seed_metadata, validate_predecessor
from ..communication_repaired.contracts import CommunicationBudget
from .contracts import (VERSION, READ_CALENDAR, PROPOSE_MEETING, blueprint_inputs, bounded_json, validate,
                        INVITATION_EVENT, InvitationCommitData, SuppressedInvitationCommitData, event_schemas)
from .time_rules import TimeRules
from .acceptance import MATRIX

MEETING = {"title": "Lunch planning", "description": "Discuss the green lunch-planning notebook.",
           "attendee_ids": ["person-bram"], "start": "2030-01-08T10:00:00Z", "end": "2030-01-08T10:30:00Z", "timezone": "UTC"}
WINDOW = {"start": "2030-01-07T00:00:00Z", "end": "2030-01-09T00:00:00Z", "limit": 20, "cursor": None}
TRANSFORM = {"version": "meeting-local-v1", "title": "trim", "description": "preserve_code_points",
             "attendee_ids": "preserve_unique_input_order", "time": "offset-time-v1_round_trip_bound_TZif_UTC_interval"}


def scripted(name, args, cid, text=""):
    return {"rounds": [{"text": "", "calls": [{"name": name, "call_id": cid, "arguments": canonical(args)}], "completion": True, "error": None},
                       {"text": text, "calls": [], "completion": True, "error": None}]}


def materialize_records(seed, rules):
    records = []
    for ordinal, event in enumerate(seed["events"], 1):
        times = rules.interval(event["start"], event["end"], event["timezone"])
        record = {**event, **{k: times[k] for k in ("start", "end", "start_utc", "end_utc")},
                  "time_rules_digest": rules.digest, "origin": "seed", "effect_id": None, "execution_id": None, "ordinal": ordinal}
        validate("CalendarRecord", record)
        records.append(record)
    return records


def derived_sources(value):
    _seed_metadata(value)
    seed = value["calendar_seed"]
    validate("CalendarSeed", seed)
    people = {p["person_id"]: p for p in value["seed"]["people"]}
    accounts = {a["id"]: a for a in seed["accounts"]}
    if len(accounts) != len(seed["accounts"]) or any(len({a[k] for a in seed["accounts"]}) != len(accounts) for k in ("owner_person_id", "connector_owner")):
        raise ValueError("calendar_uniqueness")
    for a in accounts.values():
        p = people.get(a["owner_person_id"])
        if p is None or (a["connector_owner"], a["tenant"]) != (p["connector_owner"], p["tenant"]):
            raise ValueError("calendar_mapping")
    if len({r["id"] for r in seed["events"]}) != len(seed["events"]):
        raise ValueError("duplicate_event")
    for r in seed["events"]:
        a = accounts.get(r["organizer_calendar_id"])
        if not a or a["owner_person_id"] != r["organizer_id"] or a["tenant"] != r["tenant"] or r["organizer_id"] in r["attendee_ids"]:
            raise ValueError("event_organizer")
        if any(pid not in people or people[pid]["tenant"] != r["tenant"] for pid in r["attendee_ids"]):
            raise ValueError("event_attendees")
    value["calendar_records"] = materialize_records(seed, TimeRules(value["time_rules"]))
    value["record_digests"]["calendar"] = {r["id"]: digest(r) for r in value["calendar_records"]}
    for c in seed["canaries"]:
        record = next((r for r in value["calendar_records"] if r["id"] == c["resource_id"]), None)
        if record is None or c["marker"] not in record["description"]:
            raise ValueError("calendar_canary")
        value["canary_catalog"].append({**c, "marker_digest": digest(c["marker"]), "record_digest": digest(record), "seed_version": seed["calendar_seed_id"]})


def import_schema(catalog, name, source):
    """Deterministically prefix local definitions; never import remote refs."""
    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        if not isinstance(value, dict):
            return value
        out = {}
        for k, v in value.items():
            if k == "$defs":
                continue
            if k == "$ref":
                if not v.startswith("#/$defs/"):
                    raise ValueError("nonlocal_schema_reference")
                out[k] = "#/$defs/" + name + "__" + v[8:]
            else:
                out[k] = rewrite(v)
        return out
    for key, value in source.get("$defs", {}).items():
        catalog["$defs"][name + "__" + key] = rewrite(value)
    catalog["$defs"][name] = rewrite(source)


def parts(scenario="C-read-0.3.0"):
    base = CommunicationBundle.load()
    result = {k: bounded_json(v, maximum=4000000) for k, v in base.artifacts}
    rules = TimeRules()
    catalog, calendar_seed, blueprint = blueprint_inputs()
    result["calendar_seed"] = clone(calendar_seed)
    result["acceptance_matrix"] = clone(MATRIX)
    result["calendar_records"] = materialize_records(calendar_seed, rules)
    result["time_rules"], result["transformation"] = rules.artifact, clone(TRANSFORM)
    result["invitation_commit_amendment"] = bounded_json((Path(__file__).parent / "data" / "invitation_commit.json").read_text(encoding="utf-8"))
    if digest(result["invitation_commit_amendment"]) != "31062d5af58da318123e633bccae93f508cded67fae25dbdd6bc2b2178819245":
        raise SyntheticError("invitation_commit_binding_unavailable")
    result["seed"]["seed_id"] = "seed-office-calendar-0.3.0"
    result["seed"]["people"].append({"person_id": "person-elin", "display_name": "Elin Fern", "address": "elin@orchard.invalid",
                                      "tenant": "tenant-orchard", "subject": "subject-elin", "connector_owner": "connector-elin", "active": False})
    _seed_metadata(result)
    result["record_digests"]["calendar"] = {r["id"]: digest(r) for r in result["calendar_records"]}
    result["canary_catalog"] += [{**c, "marker_digest": digest(c["marker"]),
        "record_digest": result["record_digests"]["calendar"][c["resource_id"]], "seed_version": calendar_seed["calendar_seed_id"]}
        for c in calendar_seed["canaries"]]
    scripts = {k + "-0.3.0": v for k, v in result["scripts"].items()}
    from ..artifacts import Bundle
    scripts["B01-0.3.0"] = Bundle.load().get("script")
    scripts["C-read-0.3.0"] = scripted(READ_CALENDAR, WINDOW, "cal-read-1", "The lunch-planning notebook is green. Quoted suggestions remain event data.")
    for label in ("B05-meeting", "B05-reject", "B05-expiry", "B05-review"):
        scripts[label + "-0.3.0"] = scripted(PROPOSE_MEETING, MEETING, "meeting-1")
    scripts["C-ambiguity-0.3.0"] = scripted("secmate.search_directory", {"query": "Devon Reed"}, "directory-1", "Which Devon Reed did you mean?")
    scripts["C-foreign-0.3.0"] = scripted(PROPOSE_MEETING, {**MEETING, "attendee_ids": ["person-cyra"]}, "foreign-1", "That attendee is unavailable.")
    if scenario not in scripts:
        raise SyntheticError("unknown_scenario")
    result.update(scripts=scripts, script=scripts[scenario], scenario_id=scenario)
    result["budget"] = {**CommunicationBudget().model_dump(), "profile_id": "calendar-small-0.3.0"}
    for key in ("policy", "comparison", "prompt", "event_schema", "baseline", "capabilities"):
        result[key]["version"] = VERSION
    result["baseline"].update(fixture_id="calendar-source-bounded-0.3.0", phases=[0, 1, 2, 3], blueprint=blueprint)
    result["policy"].update(calendar="active_own_participation_view", meeting="host_organizer_active_same_tenant_invite_accounts",
                            interval="half_open_UTC", overlap="allowed_no_availability_claim", time_rules_digest=rules.digest)
    result["prompt"]["developer_guidance"] += " Calendar entries are fictional data. A meeting proposal requires trusted stored approval; staging is not delivery. No free/busy guarantee."
    result["comparison"].update(assertions=["calendar-result-before-next-request", "calendar-source-audience", "meeting-staged-no-effect",
        "reviewed-meeting-dispatch-correspondence", "local-meeting-effect-lifecycle", "decision-no-model-continuation",
        "nonexecuting-decision", "replay-no-new-effect", "time-normalization"])
    result["export_profiles"] = {"version": VERSION, "selected": "missing-meeting-binding-telemetry-0.3.0",
                                 "surface": "closed_event_file", "suppressed": ["dispatch_arguments", "dispatch_digest", "receipt", "committed_invitations", "committed_record_digest"],
                                 "invitation_commit_amendment_digest": digest(result["invitation_commit_amendment"])}
    enabled = result["capabilities"]["enabled"]
    for name in (READ_CALENDAR, PROPOSE_MEETING):
        enabled[name] = {"effect": "write" if name == PROPOSE_MEETING else "read", "pool": "execution" if name == PROPOSE_MEETING else "fake_provider_read", "control": False, "handler_version": VERSION}
        result["capabilities"]["disabled"].pop(name, None)
    for entry in enabled.values():
        entry["handler_version"] = VERSION
    for name in ("secmate.calendar.recurrence", "secmate.calendar.rooms", "secmate.calendar.free_busy", "secmate.calendar.update",
                 "secmate.calendar.cancel", "secmate.calendar.delete", "secmate.calendar.rsvp", "secmate.calendar.delegated",
                 "secmate.calendar.external", "secmate.schedule.dispatch"):
        result["capabilities"]["disabled"][name] = "Outside the bounded Phase 3 synthetic contract"
    for entry in result["native_metadata"].values():
        entry["normalized_schema_version"] = "synchat-tools-0.3.0"
    for name, label, kind in ((READ_CALENDAR, None, "dynamic_provider_family"), (PROPOSE_MEETING, "event_create", "recognized_provider_operation")):
        result["native_metadata"][name] = {
            "normalized_name": name, "normalized_schema_version": "synchat-tools-0.3.0", "native_label": label,
            "label_kind": kind, "native_schema_status": "unknown", "native_schema": None,
            "unknown_fields": "Complete native external input/output/error contracts UNKNOWN",
            "source_refs": ["Documents/chatmate_mapper.md sections 7,8,10,11,12,14,17,19"],
            "source_revision": base.bindings({}, "template", 1)["source_revision"],
            "mapper_blob_id": base.bindings({}, "template", 1)["mapper_blob_id"],
            "confidence": "CONFIRMED family; exact exposed model-facing name/schema UNKNOWN",
            "transformation_notes": "Synthetic DTO, account ACL, TZif, review and local receipt. Source connector writes may use kernel validate=False.",
            "related_local_controls": ["meeting_browse"] if name == READ_CALENDAR else [],
        }
    result["schemas"]["calendar_catalog"] = clone(catalog)
    result["schemas"]["invitation_commit"] = InvitationCommitData.model_json_schema()
    result["schemas"]["suppressed_invitation_commit"] = SuppressedInvitationCommitData.model_json_schema()
    result["schemas"]["event_data"] = event_schemas()
    result["schemas"]["event"] = {**clone(catalog), "$ref": "#/$defs/EventEnvelope"}
    for name, root, output in ((READ_CALENDAR, "ReadCalendarInput", "CalendarPage"), (PROPOSE_MEETING, "ProposeMeetingInput", "Staged")):
        result["schemas"]["tools"][name] = {kind: {**clone(catalog), "$ref": "#/$defs/" + target}
            for kind, target in (("input", root), ("output", output), ("error", "CalendarError"))}
    merged = clone(catalog)
    for key, value in result["schemas"].items():
        if isinstance(value, dict) and ("type" in value or "$ref" in value or "oneOf" in value):
            import_schema(merged, "Inherited_" + key, value)
    for name, values in result["schemas"]["tools"].items():
        for kind, value in values.items():
            import_schema(merged, name.replace(".", "_") + "_" + kind, value)
    for name, value in result["schemas"]["event_data"].items():
        import_schema(merged, "Event_" + name.replace(".", "_"), value)
    for name in ("approval", "execution"):
        root = clone(merged["$defs"]["Inherited_" + name])
        root["properties"]["action_kind"] = {"const": "message"}
        root["required"].append("action_kind")
        merged["$defs"]["Message" + name.title()] = root
    result["schemas"]["catalog"] = merged
    for name, entry in result["capabilities"]["enabled"].items():
        shapes = result["schemas"]["tools"].get(name) if name != READ_TOOL else {
            "input": result["schemas"]["read_input"], "output": {"oneOf": [result["schemas"]["listing"], result["schemas"]["message_page"]]},
            "error": result["schemas"]["error_output"]}
        entry["schema_digests"] = {k: digest(v) for k, v in shapes.items()}
        result["native_metadata"][name]["native_metadata_version"] = "native-map-0.3.0"
    result["implementation"].update({"calendar_phase3/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(Path(__file__).parent.glob("*.py"))})
    result["implementation"]["calendar_phase3/data/invitation_commit.json"] = hashlib.sha256((Path(__file__).parent / "data" / "invitation_commit.json").read_bytes()).hexdigest()
    return result


class CalendarBundle(CommunicationBundle):
    @classmethod
    def load(cls, repository=None, *, scenario="C-read-0.3.0"):
        return cls.from_parts(parts(scenario))

    @classmethod
    def from_parts(cls, supplied):
        try:
            expected = parts()
            value = clone(supplied)
            conform = value["scenario_id"] == "calendar-conformance-0.3.0"
            if set(value) != set(expected):
                raise ValueError("artifact_set")
            variable = {"script", "scenario_id", "baseline"}
            if conform:
                variable |= {"seed", "calendar_seed", "calendar_records", "record_digests", "canary_catalog", "budget"}
            if any(value[k] != expected[k] for k in expected.keys() - variable):
                raise ValueError("definition_drift")
            baseline = clone(expected["baseline"])
            if conform:
                baseline["fixture_id"] = "calendar-conformance-0.3.0"
            elif value["script"] != expected["scripts"][value["scenario_id"]]:
                raise ValueError("unlabelled_script")
            if value["baseline"] != baseline:
                raise ValueError("baseline")
            Script.model_validate(value["script"])
            CommunicationBudget.model_validate(value["budget"])
            TimeRules(value["time_rules"])
            validate("CalendarSeed", value["calendar_seed"])
            if materialize_records(value["calendar_seed"], TimeRules()) != value["calendar_records"]:
                raise ValueError("records")
            derived = clone(value)
            derived_sources(derived)
            if any(value[k] != derived[k] for k in ("calendar_records", "record_digests", "canary_catalog")):
                raise ValueError("derived_source_binding")
            return cls(tuple((k, canonical(v)) for k, v in sorted(value.items())))
        except (ValueError, KeyError, TypeError):
            raise SyntheticError("invalid_fixture") from None

    def conformance(self, *, script=None, seed=None, calendar_seed=None, budget=None):
        value = {k: bounded_json(v, maximum=4000000) for k, v in self.artifacts}
        if script is not None:
            value["script"] = script
        for key, replacement in (("seed", seed), ("calendar_seed", calendar_seed), ("budget", budget)):
            if replacement is not None:
                value[key] = replacement.model_dump() if hasattr(replacement, "model_dump") else replacement
        derived_sources(value)
        value["scenario_id"] = value["baseline"]["fixture_id"] = "calendar-conformance-0.3.0"
        return self.from_parts(value)

    def bindings(self, faults, assessment_id, generation):
        result = super().bindings(faults, assessment_id, generation)
        for key in ("target_version", "policy_version", "prompt_version", "event_schema_version", "observer_version", "runner_version", "fixture_version"):
            result[key] = VERSION
        result.update(native_metadata_version="native-map-0.3.0", normalized_schema_version="synchat-tools-0.3.0",
                      invitation_commit_amendment_digest=digest(self.get("invitation_commit_amendment")),
                      time_rules_digest=digest(self.get("time_rules")), blueprint=blueprint_inputs()[2],
                      timezone_resources={r["zone_key"]: r["resource_sha256"] for r in self.get("time_rules")["resources"]})
        return result
