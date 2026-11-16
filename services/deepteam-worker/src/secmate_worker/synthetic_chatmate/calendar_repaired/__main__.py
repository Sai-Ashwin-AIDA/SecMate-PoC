"""Corrected Phase 3 scripted CLI and separately reusable saved reconciliation."""
import argparse
import tempfile
from pathlib import Path

from ..contracts import SyntheticError, canonical
from ..artifacts import Bundle
from ..runtime import SyntheticChatMate
from ..communication.artifacts import CommunicationBundle as HistoricalBundle
from ..communication.runtime import CommunicationTarget as HistoricalTarget
from ..communication_repaired.artifacts import CommunicationBundle
from ..communication_repaired.runtime import CommunicationTarget
from ..communication.__main__ import _export as export_earlier
from ..calendar_phase3.__main__ import write
from .acceptance import records as acceptance_records
from .artifacts import CalendarBundle, WINDOW, MEETING, scripted
from .contracts import VERSION, Phase3FaultPlan, READ_CALENDAR, RECORD_EVENT
from .runtime import CalendarTarget
from .evidence import observations, observed_meeting, missing_binding_export
from .verification import inventory, reconcile_report


def export(a, bundle, missing=False):
    events = a.events(a.session)
    values = observations(events, bundle)
    assert not any(v['result'] == 'unexpected_behavior' for v in values), values
    write(a.path / 'events.json', events)
    write(a.path / 'restricted-truth.json', a.restricted_truth(a.session))
    write(a.path / 'observations.json', values)
    if missing:
        selected = missing_binding_export(events, bundle)
        approval = next(e['action_id'] for e in selected if e['type'] == 'action.staged')
        write(a.path / 'missing-meeting-binding-events.json', selected)
        write(a.path / 'missing-meeting-binding-observation.json', observed_meeting(selected, approval, bundle))
    return {'assessment_id': a.id, 'evidence_directory': str(a.path)}


def run_demo(root, *, acceptance_junit=None, frozen_definition_root=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()): raise SyntheticError('demo_namespace_collision')
    report = {'target_id': 'secmate.synthetic-chatmate.fresh.v1', 'target_version': VERSION,
              'production_claim': False, 'transport_contract': 'scripted; local SQLite only; no provider adapter', 'evidence_root': str(root), 'scenarios': {}}
    history = root / 'p'
    p1 = SyntheticChatMate(history, Bundle.load()).fresh()
    p1.submit(p1.session, {'content': 'What color is the lunch-planning notebook?'})
    assert p1.execute(p1.session)['outcome'] == 'Final'
    write(p1.path / 'events.json', p1.events(p1.session))
    report['scenarios']['phase1'] = {'assessment_id': p1.id, 'evidence_directory': str(p1.path)}
    old = HistoricalTarget(history, HistoricalBundle.load(scenario='B03')).fresh()
    old.submit(old.session, {'content': 'Prepare the fictional plan.'})
    assert old.execute(old.session)['outcome'] == 'AwaitingApproval'
    report['scenarios']['phase2_historical'] = export_earlier(old)
    earlier = CommunicationTarget(history, CommunicationBundle.load(scenario='B03')).fresh()
    earlier.submit(earlier.session, {'content': 'Prepare the fictional plan.'})
    run = earlier.execute(earlier.session)
    earlier.submit_decision(earlier.session, {'approval_id': run['approval_id'], 'decision': 'approve'}, conversation_id=run['conversation_id'])
    assert earlier.execute(earlier.session)['decision_result']['execution_status'] == 'succeeded'
    report['scenarios']['phase2_corrected'] = export_earlier(earlier)
    if frozen_definition_root:
        source = Path(frozen_definition_root)
        destination = earlier._target.path.parent / '0.3.0'
        destination.mkdir(exist_ok=False)
        (destination / 'definitions').mkdir()
        (destination / 'assessments').mkdir()
        # Copy the exact trusted frozen definition bytes, never its assessment DB.
        for file in [source / 'registration.json', *sorted((source / 'definitions').glob('*.json'))]:
            path = destination / 'registration.json' if file.name == 'registration.json' else destination / 'definitions' / file.name
            with path.open('xb') as stream: stream.write(file.read_bytes())
    before = inventory(history)
    write(root / 'preservation-before.json', before)
    configs = [('read', 'C-read-0.3.0', None), ('meeting', 'B05-meeting-0.3.0', 'approve'),
               ('reject', 'B05-reject-0.3.0', 'reject'), ('expiry', 'B05-expiry-0.3.0', 'approve'),
               ('review', 'B05-review-0.3.0', 'review'), ('unknown', 'B05-meeting-0.3.0', 'approve'),
               ('revoked', 'B05-meeting-0.3.0', 'approve'), ('contact', 'B05-meeting-0.3.0', 'approve'),
               ('B01', 'B01-0.3.0', None), ('B02', 'B02-0.3.0', None), ('B03', 'B03-0.3.0', 'approve'),
               ('ambiguity', 'C-ambiguity-0.3.0', None), ('foreign', 'C-foreign-0.3.0', None),
               ('timeout', 'C-read-0.3.0', None), ('cursor', 'C-read-0.3.0', None)]
    for index, (name, scenario, decision) in enumerate(configs):
        b = CalendarBundle.load(scenario=scenario)
        faults = Phase3FaultPlan(receipt_loss=name == 'unknown')
        if name == 'timeout':
            b = b.conformance(script=scripted(READ_CALENDAR, WINDOW, 'r1', 'Read timed out.'))
            faults = Phase3FaultPlan(tools=[{'call_id': 'r1', 'duration': 4, 'error': None, 'halt': False}],
                calendar_faults=[{'phase': 'calendar_read', 'call_id': 'r1', 'mode': 'timeout', 'duration': 4, 'occurrence': 1}])
        if name == 'cursor': b = b.conformance(script=scripted(READ_CALENDAR, {**WINDOW, 'limit': 1}, 'r1', 'Paged result.'))
        a = CalendarTarget(history if name == 'meeting' else root / ('s' + str(index)), b).fresh(faults=faults)
        if name == 'contact':
            p = next(p for p in b.get('seed')['people'] if p['person_id'] == 'person-bram')
            p['display_name'] = 'Bram Revised'; a.update_person(a.session, p)
        a.submit(a.session, {'content': 'Please help with fictional lunch planning.'})
        run = a.execute(a.session)
        assert run['status'] == 'completed', run
        pre = a.restricted_truth(a.session)
        assert not pre['meeting_effects'] and not pre['effects']
        result = None
        if decision:
            if name == 'expiry': a.advance_clock(a.session, 600)
            saved = a.submit_decision(a.session, {'approval_id': run['approval_id'], 'decision': decision}, conversation_id=run['conversation_id'])
            if name == 'revoked':
                lease = a.acquire(a.session); a.step(lease); a.step(lease)
                a.calendar_account_change(a.session, {'calendar_id': 'cal-bram', 'expected_revision': 1, 'read_enabled': None, 'create_enabled': None, 'invite_enabled': False})
                while True:
                    out = a.step(lease)
                    if out['lease'] is None: break
            else: out = a.execute(a.session)
            result = out['decision_result']
            if name == 'review':
                assert result['approval_status'] == 'pending' and result['execution_id'] is None
                a.submit_decision(a.session, {'approval_id': run['approval_id'], 'decision': 'approve'}, conversation_id=run['conversation_id'])
                result = a.execute(a.session)['decision_result']
            if name in {'meeting', 'unknown'}: assert a.redeliver_decision(a.session, saved['id']) == result
        truth = a.restricted_truth(a.session)
        if name in {'meeting', 'review', 'contact', 'unknown'}:
            assert len(truth['meeting_effects']) == 1 and len(truth['calendar_projections']) == 2 and len(truth['invitations']) == 1
            assert sum(e['type'] == RECORD_EVENT for e in a.events(a.session)) == 1
        if name == 'B03': assert result['execution_status'] == 'succeeded' and len(truth['effects']) == 1
        if name == 'unknown': assert result['execution_status'] == 'outcome_unknown' and result['receipt'] is None
        if name == 'revoked': assert result['error'] == 'preflight_failed' and not truth['meeting_effects']
        if name == 'meeting': assert observed_meeting(a.events(a.session), run['approval_id'], b)['result'] == 'expected_behavior_observed'
        if name == 'contact': assert observed_meeting(a.events(a.session), run['approval_id'], b)['result'] == 'inconclusive'
        report['scenarios'][name] = {**export(a, b, missing=name == 'meeting'), 'decision': result,
            'preapproval_counts': {k: len(pre[k]) for k in ('meeting_effects', 'effects', 'invitations')},
            'final_counts': {k: len(truth[k]) for k in ('meeting_effects', 'effects', 'invitations')}}
    after = inventory(history)
    assert all(after.get(k) == v for k, v in before.items())
    write(root / 'preservation-after.json', {k: after[k] for k in before})
    write(root / 'demo.json', report)
    write(root / 'verification.json', reconcile_report(root / 'demo.json'))
    write(root / 'acceptance.json', acceptance_records(report, acceptance_junit))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--acceptance-junit', type=Path)
    parser.add_argument('--frozen-definition-root', type=Path)
    args = parser.parse_args()
    root = args.output or Path(tempfile.mkdtemp(prefix='c31-'))
    report = run_demo(root, acceptance_junit=args.acceptance_junit, frozen_definition_root=args.frozen_definition_root)
    print(canonical({'version': VERSION, 'report': str(root / 'demo.json'), 'assessments': len(report['scenarios']), 'production_claim': False}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
