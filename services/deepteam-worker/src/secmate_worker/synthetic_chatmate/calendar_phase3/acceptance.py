"""Case-to-test evidence index; test evidence never substitutes for runtime traces."""
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

MATRIX = {
    "C01": "test_c01_c02_c04_c05_own_view_and_paging", "C02": "test_c01_c02_c04_c05_own_view_and_paging",
    "C03": "test_c03_c06_c12_c13_participation_ambiguity_overlap", "C04": "test_c01_c02_c04_c05_own_view_and_paging",
    "C05": "test_c01_c02_c04_c05_own_view_and_paging", "C06": "test_a04_read_projection_and_next_request",
    "C07": "test_c07_c08_c14_stored_meeting_local_commit_and_replay", "C08": "test_c07_c08_c14_stored_meeting_local_commit_and_replay",
    "C09": "test_c09_nonexecuting_decisions", "C10": "test_c10_bram_cannot_create", "C11": "test_c11_attendee_authorization",
    "C12": "test_c03_c06_c12_c13_participation_ambiguity_overlap", "C13": "test_c03_c06_c12_c13_participation_ambiguity_overlap",
    "C14": "test_c07_c08_c14_stored_meeting_local_commit_and_replay",
    "T01": "test_t01_strict_dates", "T02": "test_t02_nonpositive_interval", "T03": "test_t03_gap_and_mismatch",
    "T04": "test_t04_equivalent_instants_and_transition", "T05": "test_t05_wrong_resource_binding_and_no_os_fallback",
    "T06": "test_t06_half_open_windows", "T07": "test_t07_cursor_integrity", "T08": "test_t08_t09_cursor_context_and_current_visible_view",
    "T09": "test_t08_t09_cursor_context_and_current_visible_view", "T10": "test_t10_calendar_output_limit_charged_once",
    "A01": "test_a01_a02_current_contacts_at_commit", "A02": "test_a02_concurrent_mutation_linearizes",
    "A03": "test_a03_bounded_parser_every_calendar_field", "A04": "test_a04_read_projection_and_next_request",
    "A05": "test_invitation_commit_correspondence", "A06": "test_a06_unknown_alternate_surfaces_fail_closed",
    "A07": "test_a07_empty_no_plan_and_invalid_completion", "A08": "test_a08_fresh_decision_deadline",
    "A09": "test_a09_fixed_artifact_admission", "A10": "test_a10_ordinary_phase_failure",
    "A11": "test_a11_failure_recording_outage_fences", "A12": "test_a12_every_enabled_handler_output_is_validated",
    "A13": "test_a13_write_batch_and_protocol_precedence", "A14": "test_a14_dedup_and_cross_kind_supersession",
    "A15": "test_a15_interrupted_saved_decision_no_duplicate", "A16": "test_a16_cancellation_and_a18_reset",
    "A17": "test_a17_exact_tool_timeouts", "A18": "test_a18_barrier_reset_immutability_and_cancel_tie",
    "A19": "test_a19_extra_fields_rejected", "A20": "test_a20_offline_guard_rejects_ordinary_network",
}
for number, case in enumerate(("A01", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10", "A12"), 1):
    MATRIX[f"F{number:02d}"] = MATRIX[case]


def records(report, junit=None):
    tests, path, fingerprint = [], None, None
    if junit is not None:
        path = str(Path(junit).resolve())
        raw = Path(path).read_bytes()
        fingerprint = hashlib.sha256(raw).hexdigest()
        tests = list(ET.fromstring(raw).iter("testcase"))
        if not tests or any(list(t.iter("failure")) or list(t.iter("error")) or list(t.iter("skipped")) for t in tests):
            raise ValueError("acceptance_test_gate_failed")
    rows = []
    for case, prefix in MATRIX.items():
        selected = [t for t in tests if t.attrib.get("name", "").split("[")[0] == prefix]
        if junit is not None and not selected:
            raise ValueError("missing_acceptance_test:" + prefix)
        rows.append({"case_id": case, "status": "pass" if selected else "inconclusive",
                     "test_references": [t.attrib["name"] for t in selected] or [prefix],
                     "junit_path": path, "junit_sha256": fingerprint,
                     "scenario_evidence": [m["evidence_directory"] for m in report["scenarios"].values()],
                     "reason": "Guarded test gate and separately reconciled scripted scenarios" if selected else "Runtime demo retained; separate complete pytest gate required",
                     "production_claim": False})
    return rows
