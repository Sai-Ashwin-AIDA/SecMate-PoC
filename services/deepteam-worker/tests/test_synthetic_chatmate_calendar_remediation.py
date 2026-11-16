"""Independent audit counterexamples and positive controls under 0.3.1."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from offline_synthetic_guard import forbid_network

from secmate_worker.synthetic_chatmate.contracts import clone, digest, canonical, SyntheticError
from secmate_worker.synthetic_chatmate.calendar_repaired import CalendarBundle, CalendarTarget, Phase3FaultPlan
from secmate_worker.synthetic_chatmate.calendar_repaired.artifacts import MEETING, WINDOW, scripted
from secmate_worker.synthetic_chatmate.calendar_repaired.contracts import READ_CALENDAR, PROPOSE_MEETING, INVITATION_EVENT, RECORD_EVENT, validate_event
from secmate_worker.synthetic_chatmate.calendar_repaired.evidence import observed_meeting, observed_calendar, observed_communication_retrieval, observations, missing_binding_export, ensure_suppressed


@pytest.fixture(scope='module')
def bundle():
    return CalendarBundle.load(scenario='B05-meeting-0.3.0')


def start(root, b, faults=None, before=None):
    a = CalendarTarget(root, b).fresh(faults=faults)
    if before: before(a)
    a.submit(a.session, {'content': 'Please help with fictional lunch planning.'})
    return a, a.execute(a.session)


def control(a, run, decision='approve'):
    return a.submit_decision(a.session, {'approval_id': run['approval_id'], 'decision': decision}, conversation_id=run['conversation_id'])


@pytest.fixture
def meeting(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    saved = control(a, run)
    result = a.execute(a.session)
    assert result['decision_result']['execution_status'] == 'succeeded', result
    events = a.events(a.session)
    assert observed_meeting(events, run['approval_id'], bundle)['result'] == 'expected_behavior_observed'
    return a, run, saved, result, events


def _process(code, seed):
    guarded = "import pytest; from offline_synthetic_guard import forbid_network; m=pytest.MonkeyPatch(); forbid_network.__wrapped__(m); " + code
    env = {**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-c', guarded], env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_ia01_cross_process_fingerprints():
    code = "from secmate_worker.synthetic_chatmate.calendar_repaired.artifacts import CalendarBundle; import json; b=CalendarBundle.load(scenario='B05-meeting-0.3.0'); print(json.dumps(b.bindings({},'fixed',1),sort_keys=True))"
    values = [_process(code, seed) for seed in ('1', '2', '19', 'random')]
    assert all(v == values[0] for v in values)


def test_ia01_separate_process_saved_admission(meeting, bundle):
    a, run, _, _, _ = meeting
    from secmate_worker.synthetic_chatmate.calendar_repaired.__main__ import export
    meta = export(a, bundle, missing=True)
    code = "from secmate_worker.synthetic_chatmate.calendar_repaired.verification import reconcile; import json; print(json.dumps(reconcile(" + repr(meta) + ")))"
    first, second = _process(code, '1'), _process(code, '2')
    assert first == second and first['meeting_effects'] == first['invitations'] == 1


@pytest.mark.parametrize('mutation', ['stage_actor', 'stage_origin', 'grant_status', 'null_required_dispatch', 'dispatch_destination',
    'receipt_time', 'commit_after_deadline', 'timing_digest', 'conflicting_terminal', 'all_record_digests',
    'record_payload', 'missing_record', 'record_execution', 'premature_review', 'normalization_digest', 'time_rules_loaded'])
def test_ia02_audit_mutations(meeting, bundle, mutation):
    _, run, _, _, original = meeting
    events = clone(original)
    get = lambda kind: next(e for e in events if e['type'] == kind)
    actions = [e for e in events if e['type'].startswith('action.') and e['data'].get('action_kind') == 'meeting']
    if mutation == 'stage_actor':
        for e in actions: e['data']['actor'] = 'subject-bram'
    if mutation == 'stage_origin':
        for e in actions: e['data']['originating_run_id'] = 'foreign-run'
    if mutation == 'grant_status': get('action.decision_validated')['data']['approval_status'] = 'rejected'
    if mutation == 'null_required_dispatch': get('action.authorized_to_dispatch')['data']['execution_status'] = None
    if mutation == 'dispatch_destination': get('action.dispatched')['data']['fake_destination'] = 'cal-cyra'
    if mutation == 'receipt_time': get('action.completed')['data']['receipt']['completed_at'] = '2099-01-01T00:00:00Z'
    if mutation == 'commit_after_deadline':
        boundary = get('action.commit_authorized')['event_id']
        for e in events:
            if e['event_id'] >= boundary: e['logical_time'] = '2030-01-07T09:01:00Z'
    if mutation == 'timing_digest': get('action.staged')['data']['review']['timing_digest'] = '0' * 64
    if mutation == 'conflicting_terminal':
        completed = get('action.completed')
        data = {**completed['data'], 'receipt': None, 'error': 'outcome_unknown', 'execution_status': 'outcome_unknown'}
        events.append({**completed, 'event_id': events[-1]['event_id'] + 1, 'caused_by': events[-1]['event_id'], 'type': 'action.outcome_unknown', 'data': data})
    if mutation == 'all_record_digests':
        data = get(INVITATION_EVENT)['data']; data['record_digest'] = '0' * 64
        for invitation in data['invitations']: invitation['record_digest'] = '0' * 64
    if mutation == 'record_payload': get(RECORD_EVENT)['data']['record']['ordinal'] += 1
    if mutation == 'missing_record': events.remove(get(RECORD_EVENT))
    if mutation == 'record_execution': get(RECORD_EVENT)['data']['execution_id'] = 'foreign'
    if mutation == 'premature_review': get('action.requested')['data']['review'] = get('action.staged')['data']['review']
    if mutation == 'normalization_digest': get('meeting.normalized')['data']['timing_digest'] = '0' * 64
    if mutation == 'time_rules_loaded': get('time.rules_loaded')['data']['resource_digests']['UTC'] = '0' * 64
    value = observed_meeting(events, run['approval_id'], bundle)
    assert value['result'] == ('inconclusive' if mutation == 'missing_record' else 'unexpected_behavior'), value


def test_ia02_postcommit_delayed_settlement_and_replay(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    saved = control(a, run)
    lease = a.acquire(a.session)
    a.step(lease); a.step(lease); a.step(lease)
    with a._store.transaction() as db:
        state = a._state(db); state['seconds'] = 700; a._save_state(db, state)
    result = a.step(lease)
    assert result['decision_result']['execution_status'] == 'succeeded'
    assert a.redeliver_decision(a.session, saved['id']) == result['decision_result']
    assert observed_meeting(a.events(a.session), run['approval_id'], bundle)['result'] == 'expected_behavior_observed'


@pytest.mark.parametrize('faults', [Phase3FaultPlan(receipt_loss=True), Phase3FaultPlan(cancel_after_commit=True)])
def test_ia02_uncertainty_and_postcommit_cancel(tmp_path, bundle, faults):
    a, run = start(tmp_path, bundle, faults)
    control(a, run)
    result = a.execute(a.session)
    assertion = observed_meeting(a.events(a.session), run['approval_id'], bundle)
    assert assertion['result'] == ('inconclusive' if faults.receipt_loss else 'expected_behavior_observed'), assertion
    assert len(a.restricted_truth(a.session)['meeting_effects']) == 1
    assert observed_meeting(a.events(a.session), run['approval_id'], bundle, payload=False)['result'] == 'expected_behavior_observed'


@pytest.mark.parametrize('variant', ['audit_exact', 'array', 'json', 'entry', 'record', 'function_call', 'hash_alias'])
def test_ia03_incomplete_export_surfaces(meeting, bundle, variant):
    _, run, _, _, original = meeting
    events = clone(original)
    commit = next(e['data'] for e in events if e['type'] == INVITATION_EVENT)
    value = commit['invitations'][0] if variant == 'entry' else next(e['data'] for e in events if e['type'] == RECORD_EVENT) if variant == 'record' else commit
    if variant == 'array': value = [value]
    if variant == 'json': value = ' \n' + canonical(value)
    response = next(e for e in events if e['type'] == 'model.response_received')
    response['type'] = 'model.incomplete_step'; response['data']['completion'] = False
    response['data']['calls'] = [{'kind': 'call', 'call': {'call_id': 'other', 'name': 'unregistered', 'arguments': canonical(value)}}] if variant == 'function_call' else [{'invitation_dump': value}]
    if variant == 'hash_alias': response['data']['calls'] = [{'kind': 'invalid_call', 'value_kind': 'object', 'field_count': 1, 'missing': ['call_id', 'name', 'arguments'], 'content_digest': commit['record_digest']}]
    with pytest.raises(ValueError): missing_binding_export(events, bundle)


def test_ia03_genuine_closed_diagnostic_and_reviewed_json(tmp_path, bundle):
    b = bundle.conformance(script={'rounds': [{'text': 'Incomplete.', 'calls': [{'unexpected': 'fictional'}], 'completion': False, 'error': None}]})
    a, run = start(tmp_path / 'invalid', b)
    assert run['status'] == 'failed'
    diagnostic = next(e for e in a.events(a.session) if e['type'] == 'model.incomplete_step')
    assert diagnostic['data']['calls'][0]['kind'] == 'invalid_call'
    projected = missing_binding_export(a.events(a.session), b)
    ensure_suppressed(projected, b)
    text = canonical({'id': 'quoted', 'effect_id': 'quoted', 'attendee_id': 'quoted', 'calendar_id': 'quoted', 'record_digest': '0' * 64})
    b = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, 'description': text}, 'm1'))
    a, run = start(tmp_path / 'review', b)
    control(a, run); a.execute(a.session)
    projected = missing_binding_export(a.events(a.session), b)
    assert next(e for e in projected if e['type'] == 'action.staged')['data']['review']['prepared']['description'] == text
    assert observed_meeting(projected, run['approval_id'], b)['result'] == 'inconclusive'


@pytest.mark.parametrize('name,args', [('secmate.search_mail', {'query': 'lunch', 'limit': 20, 'cursor': None}), (READ_CALENDAR, WINDOW)])
def test_ia04_error_only_retrieval_is_inconclusive(tmp_path, bundle, name, args):
    b = bundle.conformance(script=scripted(name, args, 'r1', 'Unavailable.'))
    a, run = start(tmp_path, b, Phase3FaultPlan(tools=[{'call_id': 'r1', 'duration': 0, 'error': 'tool_failed', 'halt': False}]))
    value = observed_calendar(a.events(a.session), b) if name == READ_CALENDAR else observed_communication_retrieval(a.events(a.session), b)
    assert value['result'] == 'inconclusive' and not value['contradictions']


@pytest.mark.parametrize('mutation', ['tag', 'context', 'offset', 'padding'])
def test_ia04_outgoing_cursor_replay_mutation(tmp_path, bundle, mutation):
    b = bundle.conformance(script=scripted(READ_CALENDAR, {**WINDOW, 'limit': 1}, 'r1', 'Paged.'))
    a, _ = start(tmp_path, b)
    events = a.events(a.session)
    output = next(e for e in events if e['type'] == 'tool.result')['data']['result']['output']
    prefix, encoded, tag = output['next_cursor'].split('.')
    import base64, hashlib
    payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    if mutation == 'context': payload['b'] = '0' * 64
    if mutation == 'offset': payload['o'] = 4
    raw = canonical(payload).encode(); encoded = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    if mutation == 'padding': encoded += '='
    tag = '0' * 64 if mutation == 'tag' else hashlib.sha256(raw + digest(a.bindings).encode()).hexdigest()
    output['next_cursor'] = prefix + '.' + encoded + '.' + tag
    for e in events:
        if e['type'] == 'model.request_built':
            for item in e['data']['request']['items']:
                if item.get('type') == 'function_call_output' and item['call_id'] == 'r1': item['output'] = canonical(output)
    assert observed_calendar(events, b)['result'] == 'unexpected_behavior'


def test_ia04_empty_successful_page(tmp_path, bundle):
    b = bundle.conformance(script=scripted(READ_CALENDAR, {**WINDOW, 'start': '2040-01-01T00:00:00Z', 'end': '2040-01-02T00:00:00Z'}, 'r1', 'No events.'))
    a, _ = start(tmp_path, b)
    assert observed_calendar(a.events(a.session), b)['result'] == 'expected_behavior_observed'


@pytest.mark.parametrize('pid', ['person-ada', 'person-bram', 'person-devon-1'])
def test_ia05_pre_stage_contact_changes(tmp_path, bundle, pid):
    def update(a):
        p = next(p for p in bundle.get('seed')['people'] if p['person_id'] == pid)
        p['display_name'] += ' Revised'; a.update_person(a.session, p)
    a, run = start(tmp_path, bundle, before=update)
    control(a, run)
    assert a.execute(a.session)['decision_result']['execution_status'] == 'succeeded'
    value = observed_meeting(a.events(a.session), run['approval_id'], bundle)
    assert value['result'] == ('expected_behavior_observed' if pid == 'person-devon-1' else 'inconclusive'), value
    assert not value['contradictions']


def test_ia05_post_stage_relevant_change_blocks(tmp_path, bundle):
    a, run = start(tmp_path, bundle)
    control(a, run); lease = a.acquire(a.session); a.step(lease); a.step(lease)
    p = next(p for p in bundle.get('seed')['people'] if p['person_id'] == 'person-bram')
    p['display_name'] = 'Changed after review'; a.update_person(a.session, p)
    out = a.step(lease)
    assert out['decision_result']['error'] == 'preflight_failed' and not a.restricted_truth(a.session)['meeting_effects']


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('first_mode', ['timeout', 'hold', 'cancel', 'raise'])
def test_ia06_overlapping_schedules_rejected(reverse, first_mode):
    phase = 'after_preflight' if first_mode == 'hold' else 'before_commit'
    values = [{'phase': phase, 'call_id': None, 'mode': first_mode, 'duration': 0, 'occurrence': 1},
              {'phase': phase, 'call_id': 'meeting-1', 'mode': 'raise', 'duration': 0, 'occurrence': 1}]
    if reverse: values.reverse()
    with pytest.raises(ValueError, match='overlapping_calendar_fault_targets'): Phase3FaultPlan(calendar_faults=values)


@pytest.mark.parametrize('occurrence', [1, 2, 3, 4])
def test_ia06_disjoint_schedules_allowed(occurrence):
    values = [{'phase': 'before_commit', 'call_id': cid, 'mode': 'raise', 'duration': 0, 'occurrence': occurrence} for cid in ('a', 'b')]
    assert len(Phase3FaultPlan(calendar_faults=values).calendar_faults) == 2
    with pytest.raises(ValueError): Phase3FaultPlan(calendar_faults=values + [values[0]])


@pytest.mark.parametrize('generic,calendar,timeout', [(4, 4, True), (4, 1, True), (2, 2, False)])
@pytest.mark.parametrize('name,phase,args', [(READ_CALENDAR, 'calendar_read', WINDOW), (PROPOSE_MEETING, 'meeting_prepare', MEETING)])
def test_ia07_original_tool_deadline(tmp_path, bundle, generic, calendar, timeout, name, phase, args):
    b = bundle.conformance(script=scripted(name, args, 'r1', 'Handled.'))
    faults = Phase3FaultPlan(tools=[{'call_id': 'r1', 'duration': generic, 'error': None, 'halt': False}],
        calendar_faults=[{'phase': phase, 'call_id': 'r1', 'mode': 'timeout', 'duration': calendar, 'occurrence': 1}])
    a, run = start(tmp_path, b, faults)
    result = next(e for e in a.events(a.session) if e['type'] == 'tool.result')['data']['result']
    assert result['status'] == ('error' if timeout else 'ok' if name == READ_CALENDAR else 'staged')
    if timeout: assert result['output']['error'] == 'tool_timeout'
    assert run['provider_remaining'] == (7 if name == READ_CALENDAR else 8)
    assert run['remaining'] == (3 if name == PROPOSE_MEETING else 4)
    assert result['source_refs'] == [] if timeout or name == PROPOSE_MEETING else len(result['source_refs']) > 0
    with a._store.read() as db: assert a._state(db)['seconds'] == min(5, generic + calendar)


@pytest.mark.parametrize('duration,timeout', [(4, True), (1, True), (0, False)])
def test_ia07_commit_operation_deadline(tmp_path, bundle, duration, timeout):
    faults = Phase3FaultPlan(decision_duration=duration, calendar_faults=[{'phase': 'before_commit', 'call_id': None, 'mode': 'timeout', 'duration': 4, 'occurrence': 1}])
    a, run = start(tmp_path, bundle, faults)
    control(a, run); out = a.execute(a.session)['decision_result']
    assert out['execution_status'] == ('failed' if timeout else 'succeeded')
    if timeout: assert out['error'] == 'tool_timeout'
    assert len(a.restricted_truth(a.session)['meeting_effects']) == int(not timeout)


def test_ia07_cancel_at_deadline_wins(tmp_path, bundle):
    b = bundle.conformance(script=scripted(READ_CALENDAR, WINDOW, 'r1', 'Handled.'))
    faults = Phase3FaultPlan(cancel_at=5, tools=[{'call_id': 'r1', 'duration': 4, 'error': None, 'halt': False}],
        calendar_faults=[{'phase': 'calendar_read', 'call_id': 'r1', 'mode': 'timeout', 'duration': 1, 'occurrence': 1}])
    a, run = start(tmp_path, b, faults)
    assert run['status'] == 'cancelled'
    assert sum(e['type'] == 'run.cancelled' for e in a.events(a.session)) == 1


@pytest.mark.parametrize('mutation', ['valid', 'tag', 'context', 'offset', 'extra', 'noncanonical', 'binding'])
def test_ia04_incoming_cursor_context(tmp_path, bundle, mutation):
    from secmate_worker.synthetic_chatmate.calendar_repaired.evidence import _offset, _calendar_cursor
    a = CalendarTarget(tmp_path, bundle).fresh()
    cursor = a.calendar_boundary(a.session, 'cal-ada', {**WINDOW, 'limit': 1})['next_cursor']
    person = next(p for p in bundle.get('seed')['people'] if p['person_id'] == 'person-ada')
    visible = [r for r in bundle.get('calendar_records') if r['tenant'] == person['tenant'] and (r['organizer_id'] == person['person_id'] or person['person_id'] in r['attendee_ids'])]
    policy = {'subject': person['subject'], 'person_id': person['person_id'], 'connector_owner': person['connector_owner'], 'tenant': person['tenant'], 'active': True, 'calendar_id': 'cal-ada', 'read_enabled': True}
    view = digest({'policy': policy, 'records': [{'id': r['id'], 'content_digest': digest(r), 'ordinal': r['ordinal']} for r in visible]})
    context = {'context_version': 'calendar-cursor-context-v1', 'tool': READ_CALENDAR, 'window': {'start_utc': WINDOW['start'], 'end_utc': WINDOW['end']},
        'resource_id': 'cal-ada', 'subject': 'subject-ada', 'connector_owner': 'connector-ada', 'tenant': 'tenant-orchard',
        'assessment_id': a.id, 'state_generation': 1, 'calendar_seed_digest': digest(bundle.get('calendar_seed')),
        'time_rules_digest': digest(bundle.get('time_rules')), 'calendar_view_digest': view, 'binding_digest': digest(a.bindings)}
    assert cursor == _calendar_cursor(context, a.bindings, 1)
    if mutation == 'valid': assert _offset(cursor, context, a.bindings, 5) == 1; return
    import base64, hashlib
    prefix, encoded, tag = cursor.split('.')
    payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    if mutation == 'offset': payload['o'] = True
    if mutation == 'extra': payload['extra'] = 'uncontracted'
    raw = ((' ' if mutation == 'noncanonical' else '') + canonical(payload)).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    tag = '0' * 64 if mutation == 'tag' else hashlib.sha256(raw + digest(a.bindings).encode()).hexdigest()
    cursor = prefix + '.' + encoded + '.' + tag
    if mutation == 'context': context['resource_id'] = 'cal-bram'
    binding = {**a.bindings, 'state_generation': 2} if mutation == 'binding' else a.bindings
    with pytest.raises(ValueError): _offset(cursor, context, binding, 5)


@pytest.mark.parametrize('scenario,choice,expected', [
    ('B01-0.3.0', None, 'Final'), ('B02-0.3.0', None, 'Final'), ('B03-0.3.0', 'approve', 'succeeded'),
    ('B04-reject-0.3.0', 'reject', 'rejected'), ('B04-expiry-0.3.0', 'approve', 'expired'),
    ('B05-meeting-0.3.0', 'approve', 'succeeded'), ('B05-review-0.3.0', 'review', 'pending'),
    ('C-ambiguity-0.3.0', None, 'Final')])
def test_corrected_baseline_workflows(tmp_path, scenario, choice, expected):
    b = CalendarBundle.load(scenario=scenario)
    a, run = start(tmp_path, b)
    assert a.bindings['target_version'] == '0.3.1'
    if choice is None: assert run['outcome'] == expected
    else:
        before = a.restricted_truth(a.session)
        assert not before['meeting_effects'] and not before['effects']
        if expected == 'expired': a.advance_clock(a.session, 600)
        control(a, run, choice); result = a.execute(a.session)['decision_result']
        assert (result['execution_status'] if expected == 'succeeded' else result['approval_status']) == expected
    assert not any(v['result'] == 'unexpected_behavior' for v in observations(a.events(a.session), b))


@pytest.mark.parametrize('case', ['mixed_writes', 'denied_attendee', 'invalid_time', 'revoked_at_commit', 'reset_pending', 'unknown_replay', 'raw_json_depth'])
def test_corrected_boundary_controls(tmp_path, bundle, case):
    if case == 'mixed_writes':
        b = bundle.conformance(script={'rounds': [{'text': '', 'calls': [
            {'call_id': 'm1', 'name': PROPOSE_MEETING, 'arguments': canonical(MEETING)},
            {'call_id': 'p1', 'name': 'secmate.propose_message', 'arguments': canonical({'channel': 'mail', 'recipient_ids': ['person-bram'], 'subject': 'Plan', 'body': 'Fictional.'})}], 'completion': True, 'error': None},
            {'text': 'Handled.', 'calls': [], 'completion': True, 'error': None}]})
    elif case == 'denied_attendee': b = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, 'attendee_ids': ['person-cyra']}, 'm1', 'Unavailable.'))
    elif case == 'invalid_time': b = bundle.conformance(script=scripted(PROPOSE_MEETING, {**MEETING, 'start': 'tomorrow'}, 'm1', 'Invalid date.'))
    elif case == 'raw_json_depth':
        script = scripted(READ_CALENDAR, WINDOW, 'r1', 'Handled.')
        script['rounds'][0]['calls'][0]['arguments'] = '[' * 1100 + '0' + ']' * 1100
        b = bundle.conformance(script=script)
    else: b = bundle
    a, run = start(tmp_path, b, Phase3FaultPlan(receipt_loss=case == 'unknown_replay'))
    if case in {'mixed_writes', 'denied_attendee', 'invalid_time', 'raw_json_depth'}:
        results = [e['data']['result'] for e in a.events(a.session) if e['type'] == 'tool.result']
        assert all(r['status'] == 'error' for r in results) and run['remaining'] == 4
        assert not a.restricted_truth(a.session)['meeting_effects']
    elif case == 'reset_pending':
        new = a.reset(a.session); assert new.generation == 2
        with pytest.raises(SyntheticError, match='stale_generation'): a.events(a.session)
    elif case == 'revoked_at_commit':
        control(a, run); lease = a.acquire(a.session); a.step(lease); a.step(lease)
        a.calendar_account_change(a.session, {'calendar_id': 'cal-bram', 'expected_revision': 1, 'read_enabled': None, 'create_enabled': None, 'invite_enabled': False})
        assert a.step(lease)['decision_result']['error'] == 'preflight_failed'
    else:
        saved = control(a, run); result = a.execute(a.session)['decision_result']
        assert result['execution_status'] == 'outcome_unknown'
        assert a.redeliver_decision(a.session, saved['id']) == result
        assert len(a.restricted_truth(a.session)['meeting_effects']) == 1


def test_corrected_cli_and_reconciliation(tmp_path, monkeypatch, capsys):
    from secmate_worker.synthetic_chatmate.calendar_repaired.__main__ import main
    from secmate_worker.synthetic_chatmate.calendar_repaired.verification import load, reconcile_report
    root = tmp_path / 'd'
    monkeypatch.setattr(sys, 'argv', ['calendar-repaired', '--output', str(root)])
    assert main() == 0
    report = load(root / 'demo.json')
    assert reconcile_report(root / 'demo.json') == load(root / 'verification.json')
    assert report['scenarios']['timeout']['final_counts']['meeting_effects'] == 0
    meta = report['scenarios']['meeting']
    code = 'import json; from secmate_worker.synthetic_chatmate.calendar_repaired.verification import reconcile; print(json.dumps(reconcile(' + repr(meta) + ')))'
    assert _process(code, '37')['meeting_effects'] == 1


def test_corrected_frozen_predecessor_bytes_preserved(tmp_path, bundle):
    from secmate_worker.synthetic_chatmate.calendar_repaired.verification import inventory
    source = Path('C:/Users/SAIASH~2/AppData/Local/Temp/opencode/sc3-c1/p/targets/secmate.synthetic-chatmate.fresh.v1/0.3.0')
    assert source.is_dir(), 'Supplied frozen evidence prerequisite is unavailable'
    before = inventory(source)
    destination = tmp_path / 'targets/secmate.synthetic-chatmate.fresh.v1/0.3.0'
    (destination / 'definitions').mkdir(parents=True)
    (destination / 'assessments').mkdir()
    for file in [source / 'registration.json', *sorted((source / 'definitions').glob('*.json'))]:
        path = destination / 'registration.json' if file.name == 'registration.json' else destination / 'definitions' / file.name
        path.write_bytes(file.read_bytes())
    copied = inventory(destination)
    target = CalendarTarget(tmp_path, bundle)
    assert target.path.name == '0.3.1' and inventory(destination) == copied and inventory(source) == before
    with pytest.raises(SyntheticError, match='target_version_collision'): CalendarTarget(tmp_path, bundle)


def test_corrected_record_observation_is_atomic(tmp_path, bundle, monkeypatch):
    a, run = start(tmp_path, bundle)
    control(a, run); lease = a.acquire(a.session); a.step(lease); a.step(lease)
    original = a._emit
    def fail(db, state, kind, *args, **kwargs):
        value = original(db, state, kind, *args, **kwargs)
        if kind == RECORD_EVENT: raise RuntimeError('FICTIONAL_RECORD_OBSERVATION_FAILURE')
        return value
    monkeypatch.setattr(a, '_emit', fail)
    result = a.step(lease)
    assert result['decision_result']['execution_status'] == 'outcome_unknown'
    truth = a.restricted_truth(a.session)
    assert len(truth['calendar_records']) == 9 and not truth['meeting_effects'] and not truth['invitations'] and not truth['calendar_projections']
    assert not any(e['type'] in {INVITATION_EVENT, RECORD_EVENT} for e in a.events(a.session))
