"""Complete template admission and verified predecessor ownership for 0.2.1."""
import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from ...job_runtime import canonical
from ..artifacts import Bundle as Phase1Bundle
from ..communication.artifacts import CommunicationBundle as LegacyBundle
from ..contracts import READ_TOOL, Script, SyntheticError, digest, clone
from ..communication.contracts import Person, MailRecord, Space, TeamsRecord, DirectChat
from .contracts import CommunicationBudget, Event, Snapshot, Canary, VERSION, MAX_JSON_DEPTH, bounded_json


def _parts(scenario="B02", repository=None):
    old = LegacyBundle.load(repository, scenario=scenario)
    parts = {k: bounded_json(v, maximum=4000000) for k, v in old.artifacts}
    parts["budget"] = CommunicationBudget().model_dump()
    parts["baseline"]["fixture_id"] = "communication-source-bounded-0.2.1"
    parts["baseline"]["version"] = VERSION
    parts["baseline"]["remediation"] = [f"F{i:02d}" for i in range(1, 11)]
    parts["baseline"]["json_depth"] = MAX_JSON_DEPTH
    parts["capabilities"]["version"] = VERSION
    for tool in parts["capabilities"]["enabled"].values():
        tool["handler_version"] = VERSION
    parts["schemas"]["event"] = Event.model_json_schema()
    parts["schemas"]["snapshot_seed"] = Snapshot.model_json_schema()
    parts["schemas"]["canary_seed"] = Canary.model_json_schema()
    for key in ("policy", "comparison", "prompt", "event_schema"):
        parts[key]["version"] = VERSION
    parts["comparison"].update(envelope="bound-unique-ordered-v1", export="closed-event-surfaces-v1",
                               assertions=["retrieval-chain", "source-projection-audience", "approved-payload-chain", "local-effect-chain"])
    parts["policy"].update(commit="atomic_current_state_revalidation", decision_errors="durable_phase_aware_settlement",
                           json_depth=MAX_JSON_DEPTH)
    for entry in parts["native_metadata"].values():
        entry["normalized_schema_version"] = "synchat-tools-0.2.1"
    parts["implementation"].update({f"communication_repaired/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(Path(__file__).parent.glob("*.py"))})
    return parts


def _seed_metadata(parts):
    seed = parts["seed"]
    validators = {"people": Person, "mail": MailRecord, "spaces": Space, "teams": TeamsRecord, "chats": DirectChat}
    if set(seed) != {"seed_id", "clock_origin", "users", "snapshots", *validators, "canaries"}:
        raise ValueError("seed_fields")
    for collection, model in validators.items():
        for record in seed[collection]:
            model.model_validate(record)
        ids = [r["person_id"] if collection == "people" else r["id"] for r in seed[collection]]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_record")
    # Exercise the frozen identity/snapshot validator using a separately derived
    # Phase 1 fixture; never alter its definitions or historical readers.
    base = Phase1Bundle.load()
    base.conformance(seed={k: seed[k] for k in ("seed_id", "clock_origin", "users", "snapshots")})
    original = LegacyBundle.load().get("seed")
    if seed["users"] != original["users"]:
        raise ValueError("host_identity_drift")
    people = seed["people"]
    for u in seed["users"]:
        if sum((p["subject"], p["connector_owner"], p["tenant"]) ==
               (u["subject"], u["connector_owner"], u["tenant"]) for p in people) != 1:
            raise ValueError("person_identity")
    spaces = {s["id"]: s for s in seed["spaces"]}
    if not seed["clock_origin"].endswith("Z"):
        raise ValueError("clock_origin")
    datetime.fromisoformat(seed["clock_origin"].replace("Z", "+00:00"))
    for snapshot in seed["snapshots"]:
        Snapshot.model_validate(snapshot)
    connectors = {p["connector_owner"]: p for p in people}
    if any(r["owner"] not in connectors or connectors[r["owner"]]["tenant"] != r["tenant"] for r in seed["mail"]):
        raise ValueError("mail_owner")
    if any(len(s["members"]) != len(set(s["members"])) or not set(s["members"]) <= connectors.keys() for s in seed["spaces"]):
        raise ValueError("space_members")
    if any(r["space_id"] not in spaces for r in seed["teams"]):
        raise ValueError("space_reference")
    pids = {p["person_id"] for p in people}
    if any(len(c["members"]) != 2 or len(set(c["members"])) != 2 or not set(c["members"]) <= pids for c in seed["chats"]):
        raise ValueError("chat_membership")
    parts["record_digests"] = {c: {r.get("person_id", r.get("id")): digest(r) for r in seed[c]} for c in validators}
    records = {r["id"]: r for r in seed["mail"] + seed["teams"]}
    for canary in seed["canaries"]:
        Canary.model_validate(canary)
        if canary["resource_id"] not in records or canary["marker"] not in records[canary["resource_id"]]["body"] or not set(canary["audience"]) <= {u["subject"] for u in seed["users"]}:
            raise ValueError("canary_reference")
    parts["canary_catalog"] = [{**c, "marker_digest": digest(c["marker"]), "record_digest": digest(records[c["resource_id"]]),
                               "owner_resource": records[c["resource_id"]].get("owner", records[c["resource_id"]].get("space_id")),
                               "seed_version": seed["seed_id"]} for c in seed["canaries"]]


class CommunicationBundle(LegacyBundle):
    @classmethod
    def load(cls, repository=None, *, scenario="B02"):
        return cls.from_parts(_parts(scenario, repository))

    @classmethod
    def from_parts(cls, supplied):
        try:
            parts = clone(supplied)
            expected = _parts()
            if set(parts) != set(expected):
                raise ValueError("artifact_set")
            conform = parts["scenario_id"] == "negative-conformance"
            baseline = clone(expected["baseline"])
            if conform:
                baseline["fixture_id"] = "communication-negative-conformance-0.2.1"
            if parts["baseline"] != baseline:
                raise ValueError("baseline_drift")
            for key in expected.keys() - {"baseline", "scenario_id", "script", "seed", "budget", "record_digests", "canary_catalog"}:
                if parts[key] != expected[key]:
                    raise ValueError("definition_drift")
            if not conform:
                scenario = parts["scenario_id"]
                if scenario not in parts["scripts"] or parts["script"] != parts["scripts"][scenario] or parts["seed"] != expected["seed"] or parts["budget"] != expected["budget"]:
                    raise ValueError("unlabelled_conformance")
            Script.model_validate(parts["script"])
            CommunicationBudget.model_validate(parts["budget"])
            _seed_metadata(parts)
            return cls(tuple((k, canonical(v)) for k, v in sorted(parts.items())))
        except (ValueError, TypeError, KeyError, ValidationError, RecursionError, SyntheticError):
            raise SyntheticError("invalid_fixture") from None

    def conformance(self, *, script=None, budget=None, seed=None):
        parts = {k: bounded_json(v, maximum=4000000) for k, v in self.artifacts}
        for name, value in (("script", script), ("seed", seed), ("budget", budget.model_dump() if budget else None)):
            if value is not None:
                parts[name] = value
        parts["baseline"]["fixture_id"] = "communication-negative-conformance-0.2.1"
        parts["scenario_id"] = "negative-conformance"
        return self.from_parts(parts)

    def bindings(self, faults, assessment_id, generation):
        result = super().bindings(faults, assessment_id, generation)
        for name in ("target_version", "policy_version", "prompt_version", "event_schema_version", "observer_version", "runner_version", "fixture_version"):
            result[name] = VERSION
        result.update(native_metadata_version="native-map-0.2.1", normalized_schema_version="synchat-tools-0.2.1")
        return result


def validate_predecessor(path):
    """Validate complete actual definitions, not an empty self-declared hash map."""
    try:
        version = path.name
        cls = {"0.1.1": Phase1Bundle, "0.2.0": LegacyBundle, VERSION: CommunicationBundle}[version]
        if path.is_symlink() or (path / "definitions").is_symlink():
            raise ValueError("namespace_link")
        registration = bounded_json((path / "registration.json").read_text(encoding="utf-8"))
        expected_reg = {"target_id", "target_version", "manifesto_version", "phase_scope", "definition_digests", "api_registration", "deepteam_provider"}
        if version == "0.1.1":
            expected_reg |= {"source_revision", "mapper_blob_id"}
        if set(registration) != expected_reg or registration["target_version"] != version:
            raise ValueError("registration")
        expected = cls.load()
        required = set(dict(expected.artifacts))
        if set(registration["definition_digests"]) != required or {p.stem for p in (path / "definitions").glob("*.json")} != required:
            raise ValueError("definition_set")
        parts = {k: bounded_json((path / "definitions" / f"{k}.json").read_text(encoding="utf-8"), maximum=4000000) for k in required}
        if any(digest(v) != registration["definition_digests"][k] for k, v in parts.items()):
            raise ValueError("digest")
        # Frozen original validators allow conformance script/budget/seed changes;
        # enforce every other approved artifact and source mapping independently.
        conform = parts["baseline"]["fixture_id"] in {"phase1-conformance-0.1.1", "communication-negative-conformance-0.2.0", "communication-negative-conformance-0.2.1"}
        template = {k: bounded_json(v, maximum=4000000) for k, v in expected.artifacts}
        variable = {"script", "budget", "seed", "record_digests", "canary_catalog", "scenario_id", "baseline"}
        if any(parts[k] != template[k] for k in required - variable):
            raise ValueError("predecessor_drift")
        baseline = clone(template["baseline"])
        if conform:
            baseline["fixture_id"] = parts["baseline"]["fixture_id"]
        if parts["baseline"] != baseline:
            raise ValueError("baseline")
        validated = cls.from_parts(clone(parts))
        normalized = {k: bounded_json(v, maximum=4000000) for k, v in validated.artifacts}
        if any(parts.get(k) != normalized.get(k) for k in ("record_digests", "canary_catalog")):
            raise ValueError("derived_source_metadata")
        if not conform:
            if parts["seed"] != template["seed"] or parts["budget"] != template["budget"]:
                raise ValueError("unlabelled_fixture")
            if version == "0.1.1" and parts["script"] != template["script"]:
                raise ValueError("script")
            if version != "0.1.1" and parts["script"] != parts["scripts"][parts["scenario_id"]]:
                raise ValueError("script")
        if registration["target_id"] != "secmate.synthetic-chatmate.fresh.v1" or registration["manifesto_version"] != "0.1.2" or registration["phase_scope"] != ([0, 1] if version == "0.1.1" else [0, 1, 2]) or registration["api_registration"] is not False or registration["deepteam_provider"] is not False:
            raise ValueError("identity")
        if version == "0.1.1":
            native = template["native_metadata"]
            if registration["source_revision"] != native["source_revision"] or registration["mapper_blob_id"] != native["mapper_blob_id"]:
                raise ValueError("source")
    except (OSError, ValueError, TypeError, KeyError, SyntheticError):
        raise SyntheticError("unowned_target_namespace") from None
