"""Separate-process, read-only reconciliation for corrective 0.3.1 artifacts."""
import hashlib
import json
import sqlite3
from pathlib import Path

from ..communication_repaired.verification import reconcile as reconcile_earlier
from ..calendar_phase3.verification import inventory
from ..communication.contracts import Approval, Execution, Effect
from .artifacts import CalendarBundle
from .contracts import VERSION, RECORD_EVENT, INVITATION_EVENT, Phase3FaultPlan, bounded_json, validate, validate_event
from .evidence import observations, observed_meeting, ensure_suppressed, when


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def load(path):
    return bounded_json(Path(path).read_text(encoding='utf-8'), maximum=16000000)


def reconcile(meta):
    directory = Path(meta['evidence_directory'])
    version = directory.parent.parent
    if version.name in {'0.1.1', '0.2.0', '0.2.1'}: return reconcile_earlier(meta)
    if version.name != VERSION: raise ValueError('historical_calendar_requires_its_own_validator')
    before = inventory(directory)
    definitions = {p.stem: load(p) for p in (version / 'definitions').glob('*.json')}
    bundle = CalendarBundle.from_parts(definitions)
    binding, faults, registration = load(directory / 'bindings.json'), load(directory / 'faults.json'), load(version / 'registration.json')
    hashes = {k: sha(v) for k, v in definitions.items()}
    assert set(definitions) == set(dict(bundle.artifacts)) == set(registration['definition_digests'])
    assert hashes == registration['definition_digests'] == binding['artifact_digests']
    assert sha(hashes) == binding['fixture_digest'] and sha(faults) == binding['fault_schedule_digest']
    assert binding == bundle.bindings(faults, meta['assessment_id'], binding['state_generation'])
    assert registration['target_version'] == binding['target_version'] == VERSION
    assert registration['target_id'] == binding['target_id'] == 'secmate.synthetic-chatmate.fresh.v1'
    assert registration == {'target_id': binding['target_id'], 'target_version': VERSION, 'manifesto_version': '0.1.2', 'phase_scope': [0, 1, 2, 3],
                            'api_registration': False, 'deepteam_provider': False, 'definition_digests': hashes}
    Phase3FaultPlan.model_validate(faults)
    source = Path(__file__).parents[1]
    for key, expected in definitions['implementation'].items():
        prefix, _, filename = key.partition('/')
        path = source / filename if prefix == 'phase1' else source / key
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    events, truth = load(directory / 'events.json'), load(directory / 'restricted-truth.json')
    with sqlite3.connect((directory / 'assessment.sqlite3').resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        rows = lambda table: [json.loads(r[0]) for r in db.execute(f'SELECT payload FROM {table} ORDER BY rowid')]
        assert events == rows('events')
        state, runs = rows('state')[0], {r['id']: r for r in rows('runs')}
        assert state['assessment_id'] == binding['assessment_id'] == meta['assessment_id'] and state['generation'] == binding['state_generation']
        assert not db.execute('SELECT count(*) FROM queue').fetchone()[0]
        assert all(r['lease'] is None and r['status'] in {'completed', 'failed', 'cancelled'} for r in runs.values())
        previous = None
        for event in events:
            validate_event(event, bundle)
            assert event['binding_digest'] == sha({**binding, 'run_id': event['run_id']} if event['run_id'] else binding)
            assert event['caused_by'] == (previous['event_id'] if previous else None)
            assert event['assessment_id'] == state['assessment_id'] and event['state_generation'] == state['generation'] and event['actor_ref'] == state['owner']
            assert previous is None or event['event_id'] > previous['event_id'] and when(event) >= when(previous)
            previous = event
        approvals, executions = {a['id']: a for a in rows('approvals')}, {x['id']: x for x in rows('executions')}
        records = {r['id']: r for r in rows('calendar_records')}
        assert sorted([r for r in records.values() if r['origin'] == 'seed'], key=lambda r: r['ordinal']) == definitions['calendar_records']
        for a in approvals.values():
            if a['action_kind'] == 'meeting':
                validate('MeetingApproval', a)
                assert sha(a['prepared']) == a['prepared_digest'] == a['review']['prepared_digest']
                assert sha(a['organizer_snapshot']) == a['review']['organizer_snapshot_digest']
                assert sha(a['attendee_snapshot']) == a['review']['attendee_snapshot_digest']
                assert sha(a['prepared']['attendee_ids']) == a['review']['attendee_ids_digest']
                assert sha({'tool': 'secmate.propose_meeting', 'arguments': a['prepared']}) == a['argument_digest']
            else: Approval.model_validate({k: v for k, v in a.items() if k != 'action_kind'})
        for x in executions.values():
            if x['action_kind'] == 'meeting': validate('MeetingExecution', x)
            else: Execution.model_validate({k: v for k, v in x.items() if k != 'action_kind'})
            assert x['action_kind'] == approvals[x['approval_id']]['action_kind']
            assert x['decision_run_id'] == approvals[x['approval_id']]['decision_run_id']
            assert x['status'] == runs[x['decision_run_id']]['decision_result']['execution_status']
            if x['dispatch'] is not None: assert sha(x['dispatch']) == x['dispatch_digest']
        for table in ('calendar_records', 'meeting_effects', 'calendar_projections', 'invitations', 'executions', 'effects', 'normalizations'):
            assert truth[table] == rows(table)
        from ..calendar_phase3.services import normalize_meeting
        from ..calendar_phase3.time_rules import TimeRules
        for normal in rows('normalizations'):
            raw = next(e['data']['arguments'] for e in events if e['type'] == 'tool.requested' and e['run_id'] == normal['run_id'] and e['call_id'] == normal['call_id'])
            prepared, times = normalize_meeting(bounded_json(raw), TimeRules(definitions['time_rules']))
            assert normal['times'] == times and normal['prepared_digest'] == sha(prepared)
        for effect in rows('meeting_effects'):
            validate('MeetingEffect', effect)
            x, a, record = executions[effect['execution_id']], approvals[effect['approval_id']], records[effect['event_id']]
            assert effect['calendar_record'] == record and effect['dispatch_digest'] == x['dispatch_digest'] and effect['prepared_digest'] == a['prepared_digest']
            assert all(record[k] == x['dispatch'][k] for k in ('title', 'description', 'start', 'end', 'start_utc', 'end_utc', 'timezone'))
            projections = [p for p in rows('calendar_projections') if p['effect_id'] == effect['effect_id']]
            invitations = [p for p in rows('invitations') if p['effect_id'] == effect['effect_id']]
            assert len(projections) == len(record['attendee_ids']) + 1 and len(invitations) == len(record['attendee_ids'])
            assert [(p['owner_person_id'], p['role']) for p in projections] == [(record['organizer_id'], 'organizer')] + [(pid, 'attendee') for pid in record['attendee_ids']]
            assert [p['attendee_id'] for p in invitations] == record['attendee_ids']
            assert all(p['record_digest'] == sha(record) and p['event_id'] == record['id'] for p in projections + invitations)
            witness = [e for e in events if e['type'] == RECORD_EVENT and e['data']['execution_id'] == x['id']]
            committed = [e for e in events if e['type'] == INVITATION_EVENT and e['data']['execution_id'] == x['id']]
            assert len(witness) == len(committed) == 1
            assert witness[0]['data']['record'] == record and witness[0]['data']['record_digest'] == sha(record)
            data = committed[0]['data']
            assert data['invitations'] == [{**{k: p[k] for k in ('id', 'effect_id', 'event_id', 'attendee_id', 'calendar_id', 'record_digest')}, 'approval_id': a['id'], 'execution_id': x['id']} for p in invitations]
            assert data['record_digest'] == sha(record)
            if x['receipt'] is not None:
                assert x['receipt']['invitation_ids'] == [p['id'] for p in invitations]
                assert x['receipt']['completed_at'] == effect['committed_at']
        for effect in rows('effects'):
            Effect.model_validate(effect)
            x = executions[effect['execution_id']]
            assert effect['dispatch_digest'] == x['dispatch_digest'] and effect['recipient_ids'] == [p['person_id'] for p in x['dispatch']['recipients']]
            assert all(effect[k] == x['dispatch'][k] for k in ('channel', 'sender_id', 'subject', 'body'))
        counts = {table: len(rows(table)) for table in ('calendar_records', 'meeting_effects', 'calendar_projections', 'invitations', 'effects')}
    recomputed = observations(events, bundle)
    assert not any(v['result'] == 'unexpected_behavior' for v in recomputed)
    assert load(directory / 'observations.json') == recomputed
    if (directory / 'missing-meeting-binding-events.json').exists():
        selected = load(directory / 'missing-meeting-binding-events.json')
        ensure_suppressed(selected, bundle)
        approval = next(e['action_id'] for e in selected if e['type'] == 'action.staged')
        assert load(directory / 'missing-meeting-binding-observation.json') == observed_meeting(selected, approval, bundle)
    assert before == inventory(directory)
    return {'assessment_id': meta['assessment_id'], 'version': VERSION, 'sqlite_read_only': True, 'events': len(events), **counts}


def reconcile_report(path):
    return {name: reconcile(meta) for name, meta in load(path)['scenarios'].items()}
