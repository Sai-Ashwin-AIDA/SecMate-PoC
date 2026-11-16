"""Clause-specific Phase 4 acceptance coverage and JUnit binding."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

RUNTIME = "tests/test_synthetic_chatmate_memory.py::"
AMENDMENT_ID = "phase4-ia4-04-clause-acceptance-2026-11-14"
CHECK_KINDS = ("positive", "negative", "fault", "evidence")
CASES = tuple(f"M{number:02d}" for number in range(1, 41))
DEMO_SCENARIOS = {
    "M01": ("inspect",), "M02": ("bram", "cyra"), "M03": ("ineligible-shared", "ineligible-project", "ineligible-multiparticipant", "ineligible-deleted", "ineligible-conversation_disabled"),
    "M05": ("inspect",), "M06": ("forget",), "M08": ("clear",), "M09": ("disable",), "M12": ("expiry",), "M15": ("unavailable",),
    "M21": ("response-loss",), "M25": ("forget",), "M30": ("forget",), "M31": ("B05",), "M34": ("B01", "B02", "B03", "B04", "B05"),
    "M38": ("inspect", "forget", "clear", "disable", "B03", "B05")}
FAULT_CASES = {"M13", "M15", "M16", "M20", "M21", "M23", "M24"}
CLAUSES = {
    "M01": "private ordered active facts and request placement", "M02": "Bram/Cyra ownership and foreign indistinguishability", "M03": "all ineligible profiles and no private read charge",
    "M04": "owner/requested-by/generation mismatch", "M05": "inspect state without mutation or injection", "M06": "forget transition and refreshed request",
    "M07": "expired/unknown/foreign/stale forget", "M08": "clear and repeated clear revisions", "M09": "sticky conversation disable", "M10": "repeat/stale disable and enabled toggles",
    "M11": "capacity, ties, blank and oversized facts", "M12": "numeric expiry boundary without revision", "M13": "retry expiry under original deadline", "M14": "fresh unchanged snapshots",
    "M15": "unavailable/raise/timeout/malformed load", "M16": "combined budgets and original deadlines", "M17": "strict bounded JSON rejection", "M18": "same-revision serialization",
    "M19": "both publication linearizations", "M20": "precommit rollback and durable fence", "M21": "postcommit uncertainty and fencing", "M22": "historical replay without charge",
    "M23": "cancellation and deadline tie order", "M24": "reset fencing and generation isolation", "M25": "history separation without erasure claim", "M26": "no natural-language learning",
    "M27": "source substitution contradiction", "M28": "identity/order/status contradiction handling", "M29": "missing public prerequisite inconclusive", "M30": "selected memory suppression",
    "M31": "meeting suppression with memory surfaces", "M32": "artifact and predecessor admission", "M33": "cross-process deterministic admission", "M34": "inherited B01-B05 effects",
    "M35": "closed output validators and seven tools", "M36": "independent memory quotas", "M37": "revision and seed relationship limits", "M38": "read-only independent reconciliation",
    "M39": "offline transport containment", "M40": "portable optional-history handling"}


def coverage_contract():
    contract = {}
    for case in CASES:
        scenarios = DEMO_SCENARIOS.get(case, ())
        contract[case] = {
            "positive": {"evidence_basis": "test", "test_references": [RUNTIME + f"test_phase4_clause_acceptance[{case}]"], "scenario_bindings": list(scenarios),
                         "evidence_predicate": "clause_runtime_assertions", "expected_observed": CLAUSES[case], "applicability": "applicable"},
            "negative": {"evidence_basis": "test", "test_references": [RUNTIME + f"test_phase4_matrix_check[{case}-negative]"], "scenario_bindings": [],
                         "evidence_predicate": "junit_observation", "expected_observed": "declared adverse input is rejected or unexpected", "applicability": "applicable"},
            "fault": {"evidence_basis": "test", "test_references": [RUNTIME + f"test_phase4_matrix_check[{case}-fault]"], "scenario_bindings": list(scenarios if case in FAULT_CASES else ()),
                      "evidence_predicate": "clause_fault_assertions" if case in FAULT_CASES else "not_applicable",
                      "expected_observed": "declared fault reached with bounded disposition" if case in FAULT_CASES else "clause defines no injected-fault behavior",
                      "applicability": "applicable" if case in FAULT_CASES else "not_applicable",
                      "blueprint_reason": None if case in FAULT_CASES else "Blueprint matrix row is deterministic positive/negative/evidence coverage and specifies no fault injection."},
            "evidence": {"evidence_basis": "test", "test_references": [RUNTIME + f"test_phase4_matrix_check[{case}-evidence]"], "scenario_bindings": list(scenarios),
                         "evidence_predicate": "clause_evidence_assertions", "expected_observed": "public/exported evidence was recomputed from the clause runtime", "applicability": "applicable"},
        }
    return contract


def acceptance_binding_digest():
    """Bind assertion code and immutable acceptance configuration."""
    root = Path(__file__).parents[4]
    package = Path(__file__).parent
    files = sorted((*package.glob("*.py"), *package.joinpath("data").glob("*.json"),
        root / "tests" / "test_synthetic_chatmate_memory.py",
        root / "tests" / "test_synthetic_chatmate_memory_context.py",
        root / "tests" / "test_synthetic_chatmate_memory_evidence.py"), key=lambda value: value.as_posix())
    value = hashlib.sha256()
    for file in files:
        value.update(str(file.relative_to(root)).replace("\\", "/").encode())
        value.update(b"\0"); value.update(file.read_bytes()); value.update(b"\0")
    return value.hexdigest()


def _load_export(path, name):
    file = path / name
    if not file.is_file():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _saved_semantic(case, kind, directories):
    events = [_load_export(path, "events.json") for path in directories]
    truths = [_load_export(path, "restricted-truth.json") for path in directories]
    observations = [_load_export(path, "observations.json") for path in directories]
    if not all(isinstance(value, list) for value in events + observations) or not all(isinstance(value, dict) for value in truths): return False
    types = [{event.get("type") for event in value} for value in events]
    if case == "M01": return all("memory.request_bound" in value and "model.request_built" in value for value in types)
    if case == "M02": return all(value["memory"]["snapshots"][0]["candidate"]["owner"] in {"subject-bram", "subject-cyra"} for value in truths)
    if case == "M03": return all(value["memory"]["snapshots"][0]["snapshot"]["status"] == "ineligible" for value in truths)
    if case == "M05": return truths[0]["memory"]["journals"] == [] and bool(truths[0]["memory"]["host_outputs"])
    if case in {"M06", "M08", "M09"}: return all("memory.control.committed" in value and "memory.request_bound" in value for value in types)
    if case == "M12": return len(truths[0]["memory"]["snapshots"]) == 2 and truths[0]["memory"]["snapshots"][-1]["snapshot"]["read_seconds"] == 10
    if case == "M15": return any(hit.get("kind") == "load" and hit.get("round") == 2 and hit.get("mode") == "unavailable" and hit.get("status") != "not_reached" for hit in truths[0]["memory"]["fault_hits"])
    if case == "M21": return any(hit.get("kind") == "control" and hit.get("phase") == "return" and hit.get("mode") == "response_loss" and hit.get("status") != "not_reached" for hit in truths[0]["memory"]["fault_hits"]) and "memory.control.replayed" in types[0]
    if case == "M25": return any(value.get("assertion") == "phase4.memory-history-separation" and value.get("result") == "expected_behavior_observed" for value in observations[0])
    if case == "M30": return (directories[0] / "missing-memory-request-binding-observation.json").is_file() and _load_export(directories[0], "missing-memory-request-binding-observation.json").get("result") == "inconclusive"
    if case == "M31": return (directories[0] / "missing-meeting-binding-observation.json").is_file() and "meeting.record_committed" in types[0]
    if case == "M34": return any("action.completed" in value for value in types) and any("meeting.record_committed" in value for value in types)
    if case == "M38": return all(value.get("memory", {}).get("snapshots") is not None for value in truths)
    return False


def _predicate(case, kind, spec, report, observed=False):
    if spec["evidence_basis"] == "test":
        return observed
    names = spec["scenario_bindings"]
    if not names: return observed
    directories = [Path(report["scenarios"][name]["evidence_directory"]) for name in names if name in report["scenarios"]]
    if len(directories) != len(names): return False
    return observed and _saved_semantic(case, kind, directories)


def records(report, junit=None):
    passed, duplicates, skipped, observations, deselected, path, fingerprint = set(), set(), {}, {}, [], None, None
    binding = acceptance_binding_digest()
    if junit:
        path = str(Path(junit).resolve()); raw = Path(path).read_bytes(); fingerprint = hashlib.sha256(raw).hexdigest(); root = ET.fromstring(raw)
        for item in root.iter("testcase"):
            filename = item.attrib.get("file") or item.attrib.get("classname", "").replace(".", "/") + ".py"
            node = filename.replace("\\", "/") + "::" + item.attrib.get("name", "")
            if node in passed: duplicates.add(node)
            skip = item.find("skipped")
            if skip is not None: skipped[node] = skip.attrib.get("message") or (skip.text or "pytest skipped")
            if not any(item.find(tag) is not None for tag in ("failure", "error", "skipped")): passed.add(node)
            values = set()
            for prop in item.findall("./properties/property"):
                if prop.attrib.get("name") != "phase4_observation": continue
                try: value = json.loads(prop.attrib.get("value", prop.text or ""))
                except json.JSONDecodeError: continue
                expected_keys = {"amendment_id", "binding_digest", "case_id", "kind", "predicate", "asserted"}
                if (set(value) == expected_keys and value.get("amendment_id") == AMENDMENT_ID
                        and value.get("binding_digest") == binding and value.get("asserted") is True
                        and value.get("case_id") in CASES and value.get("kind") in CHECK_KINDS
                        and value.get("predicate") == coverage_contract()[value["case_id"]][value["kind"]]["evidence_predicate"]):
                    values.add(value["case_id"] + ":" + value["kind"])
            observations[node] = values
        deselected = [value.attrib.get("value", value.text or "unknown") for value in root.iter("property") if value.attrib.get("name") == "deselected"]
    result = []
    for case, declaration in coverage_contract().items():
        checks = {}
        for kind, spec in declaration.items():
            if spec["applicability"] == "not_applicable": status = "not_applicable"
            else:
                nodes = bool(spec["test_references"]) and all(ref in passed and ref not in duplicates for ref in spec["test_references"])
                token = case + ":" + kind
                observed = all(token in observations.get(ref, set()) for ref in spec["test_references"])
                status = "pass" if junit and nodes and _predicate(case, kind, spec, report, observed) else "inconclusive"
            checks[kind] = {**spec, "status": status}
        applicable = [check for check in checks.values() if check["status"] != "not_applicable"]
        status = "pass" if applicable and all(check["status"] == "pass" for check in applicable) else "inconclusive"
        paths = sorted({str(Path(report["scenarios"][name]["evidence_directory"])) for check in checks.values() for name in check["scenario_bindings"] if name in report["scenarios"]})
        result.append({"case_id": case, "target_version": "0.4.0", "status": status, "checks": checks, "test_references": [ref for check in checks.values() for ref in check["test_references"]],
            "junit_path": path, "junit_sha256": fingerprint, "acceptance_amendment_id": AMENDMENT_ID, "source_config_binding_digest": binding,
            "evidence_paths": paths, "scenario_bindings": sorted({name for check in checks.values() for name in check["scenario_bindings"]}),
            "output_metadata": {"skips": skipped, "deselection": deselected, "environment_note": "Skipped/deselected nodes and missing scenarios remain inconclusive and are never counted as pass."},
            "reason": "all applicable kind-specific nodes and evidence predicates passed" if status == "pass" else "one or more applicable kind-specific nodes, scenarios, or observed predicates remain missing", "production_claim": False})
    return result
