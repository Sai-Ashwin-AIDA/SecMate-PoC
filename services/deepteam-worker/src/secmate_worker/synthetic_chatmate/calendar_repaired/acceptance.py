"""Separate corrected-version evidence from the retained historical test index."""
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

MATRIX = {
    'IA01': ['test_ia01_cross_process_fingerprints', 'test_ia01_separate_process_saved_admission'],
    'IA02': ['test_ia02_audit_mutations', 'test_ia02_postcommit_delayed_settlement_and_replay', 'test_ia02_uncertainty_and_postcommit_cancel'],
    'IA03': ['test_ia03_incomplete_export_surfaces', 'test_ia03_genuine_closed_diagnostic_and_reviewed_json'],
    'IA04': ['test_ia04_error_only_retrieval_is_inconclusive', 'test_ia04_outgoing_cursor_replay_mutation', 'test_ia04_empty_successful_page', 'test_ia04_incoming_cursor_context'],
    'IA05': ['test_ia05_pre_stage_contact_changes', 'test_ia05_post_stage_relevant_change_blocks'],
    'IA06': ['test_ia06_overlapping_schedules_rejected', 'test_ia06_disjoint_schedules_allowed'],
    'IA07': ['test_ia07_original_tool_deadline', 'test_ia07_commit_operation_deadline', 'test_ia07_cancel_at_deadline_wins'],
    'corrected_workflows': ['test_corrected_baseline_workflows', 'test_corrected_boundary_controls', 'test_corrected_cli_and_reconciliation'],
}


def records(report, junit=None):
    tests, fingerprint, path = [], None, None
    if junit:
        path = str(Path(junit).resolve()); raw = Path(path).read_bytes()
        fingerprint = hashlib.sha256(raw).hexdigest()
        tests = list(ET.fromstring(raw).iter('testcase'))
        if not tests or any(list(t.iter(k)) for t in tests for k in ('failure', 'error', 'skipped')): raise ValueError('failed_corrective_test_gate')
    result = []
    for case, required in MATRIX.items():
        names = [t.attrib['name'] for t in tests if t.attrib.get('classname', '').endswith('test_synthetic_chatmate_calendar_remediation') and t.attrib['name'].split('[')[0] in required]
        present = {name.split('[')[0] for name in names}
        if junit and not set(required) <= present: raise ValueError('missing_corrective_cases:' + case)
        result.append({'case_id': case, 'target_version': '0.3.1', 'status': 'pass' if tests else 'inconclusive',
                       'test_references': names or required, 'junit_path': path, 'junit_sha256': fingerprint,
                       'evidence_paths': [m['evidence_directory'] for m in report['scenarios'].values()],
                       'production_claim': False, 'scope': 'corrective adapter and audit regressions; retained tests remain separate historical compatibility evidence'})
    return result
