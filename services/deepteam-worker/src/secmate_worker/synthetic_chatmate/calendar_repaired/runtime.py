"""Versioned runtime adapters for fixed deadlines and actual-record evidence."""
import time
from pathlib import Path

from ...job_runtime import canonical, require_permission
from ..contracts import TARGET_ID, SyntheticError, clone, digest
from ..runtime import _id
from ..calendar_phase3.runtime import CalendarAssessment as FrozenAssessment
from ..calendar_phase3.artifacts import parts as frozen_parts
from ..communication_repaired.artifacts import validate_predecessor
from .artifacts import CalendarBundle
from .contracts import VERSION, RECORD_EVENT, Phase3FaultPlan, diagnostics, validate_event, bounded_json


def validate_frozen_calendar(path):
    """Admit the audited, exact frozen schema bytes without regenerating them.

    This is predecessor ownership validation, not a rerun/reinterpretation of its
    historical observer. Unknown 0.3.0 schema fingerprints remain refused.
    """
    try:
        if path.is_symlink() or any(p.is_symlink() for p in path.rglob('*')): raise ValueError('link')
        reg = bounded_json((path / 'registration.json').read_text(encoding='utf-8'))
        template = frozen_parts()
        files = {p.stem: bounded_json(p.read_text(encoding='utf-8'), maximum=4000000) for p in (path / 'definitions').glob('*.json')}
        if set(files) != set(template) or set(reg['definition_digests']) != set(template): raise ValueError('set')
        if {k: digest(v) for k, v in files.items()} != reg['definition_digests']: raise ValueError('hashes')
        if reg != {'target_id': TARGET_ID, 'target_version': '0.3.0', 'manifesto_version': '0.1.2', 'phase_scope': [0, 1, 2, 3],
                   'api_registration': False, 'deepteam_provider': False, 'definition_digests': reg['definition_digests']}: raise ValueError('registration')
        if digest(files['schemas']) != '3711f93635c040fc1a7109b8cb8a69eb53b6d9b25a1dea99c13e579daa3ed88b': raise ValueError('unknown_frozen_schema')
        if digest(files['implementation']) != '8d7571ba23ce504fd2069cc3e588c12dfe7a03d812a00f59fe32bc6ba86fdb9c': raise ValueError('frozen_source')
        variable = {'schemas', 'script', 'scenario_id', 'baseline', 'seed', 'calendar_seed', 'calendar_records', 'record_digests', 'canary_catalog', 'budget'}
        if any(files[k] != template[k] for k in template.keys() - variable): raise ValueError('frozen_definition')
        if files['scenario_id'] not in files['scripts'] or files['script'] != files['scripts'][files['scenario_id']]: raise ValueError('script')
        if any(files[k] != template[k] for k in ('baseline', 'seed', 'calendar_seed', 'calendar_records', 'record_digests', 'canary_catalog', 'budget')): raise ValueError('baseline')
    except (OSError, ValueError, KeyError, TypeError):
        raise SyntheticError('unowned_target_namespace') from None


class CalendarTarget:
    def __init__(self, root, bundle=None):
        require_permission()
        supplied = bundle or CalendarBundle.load()
        self.bundle = CalendarBundle.from_parts({k: bounded_json(v, maximum=4000000) for k, v in supplied.artifacts})
        target = Path(root).resolve() / 'targets' / TARGET_ID
        if target.exists():
            if (target / VERSION).exists(): raise SyntheticError('target_version_collision')
            if target.is_symlink() or not target.is_dir() or not list(target.iterdir()): raise SyntheticError('unowned_target_namespace')
            for previous in target.iterdir():
                if previous.name == '0.3.0': validate_frozen_calendar(previous)
                elif previous.name in {'0.1.1', '0.2.0', '0.2.1'}: validate_predecessor(previous)
                else: raise SyntheticError('unowned_target_namespace')
        else:
            target.mkdir(parents=True, exist_ok=True)
        self.path = target / VERSION
        try: self.path.mkdir(exist_ok=False)
        except FileExistsError: raise SyntheticError('target_version_collision') from None
        self.assessments = self.path / 'assessments'
        self.assessments.mkdir()
        (self.path / 'definitions').mkdir()
        for key, value in self.bundle.artifacts:
            with (self.path / 'definitions' / (key + '.json')).open('x', encoding='utf-8') as stream: stream.write(value)
        with (self.path / 'registration.json').open('x', encoding='utf-8') as stream:
            stream.write(canonical({'target_id': TARGET_ID, 'target_version': VERSION, 'manifesto_version': '0.1.2', 'phase_scope': [0, 1, 2, 3],
                                    'api_registration': False, 'deepteam_provider': False,
                                    'definition_digests': {k: digest(bounded_json(v, maximum=4000000)) for k, v in self.bundle.artifacts}}))

    def fresh(self, *, subject='subject-ada', faults=None, generation=1):
        return CalendarAssessment(self, subject, faults or Phase3FaultPlan(), generation)


class CalendarAssessment(FrozenAssessment):
    def __init__(self, target, subject, faults, generation):
        # Validate the corrected schedule BEFORE creating any assessment files.
        faults = Phase3FaultPlan.model_validate(faults.model_dump())
        self._operation_deadline = None
        super().__init__(target, subject, faults, generation)

    def _emit(self, db, state, kind, run, data=None, call_id=None):
        data = clone(data or {})
        if kind == 'model.incomplete_step': data['calls'] = diagnostics(data['calls'])
        if kind == 'tool.dispatched': self._operation_deadline = min(run['deadline'], state['seconds'] + self._budget.tool_seconds)
        last = db.execute('SELECT max(id) FROM events').fetchone()[0] or 0
        event = {'event_schema_version': VERSION, 'target_id': TARGET_ID, 'target_version': VERSION,
                 'assessment_id': self.id, 'state_generation': self.generation, 'run_id': run['id'] if run else None,
                 'event_id': last + 1, 'logical_time': self._timestamp(state['seconds']), 'type': kind,
                 'actor_ref': state['owner'], 'call_id': call_id or data.get('call_id'), 'action_id': data.get('approval_id'),
                 'caused_by': last or None, 'data': data, 'binding_digest': digest(run['bindings']) if run else self._binding_digest,
                 'production_claim': False}
        validate_event(event, self._bundle)
        db.execute('INSERT INTO events (payload) VALUES (?)', (canonical(event),))
        return event['event_id']

    def _action_event(self, db, state, run, stage, approval, **extra):
        if approval['action_kind'] == 'meeting':
            if stage == 'commit_authorized':
                extra['fake_destination'] = self._store.execution(db, approval['id'])['dispatch']['calendar_id']
            if stage == 'decision_received': extra.update(execution_id=None, execution_status=None)
        return super()._action_event(db, state, run, stage, approval, **extra)

    def _dispatch(self, db, state, run, calls):
        try: return super()._dispatch(db, state, run, calls)
        finally: self._operation_deadline = None

    def _checkpoint(self, db, state, run):
        if run['status'] in {'completed', 'failed', 'cancelled'}: return False
        return super()._checkpoint(db, state, run)

    def _result(self, db, state, run, *args, **kwargs):
        if run['status'] == 'cancelled': return
        return super()._result(db, state, run, *args, **kwargs)

    def _advance(self, db, state, run, duration, deadline):
        if self._operation_deadline is not None: deadline = min(deadline, self._operation_deadline)
        if run.get('kind') != 'decision': return super()._advance(db, state, run, duration, deadline)
        end, cancel = state['seconds'] + duration, self._faults.cancel_at
        if run['cancel'] or cancel is not None and state['seconds'] <= cancel <= min(end, deadline):
            if cancel is not None and not run['cancel']: state['seconds'] = cancel
            run['cancel'] = True
            self._save_state(db, state)
            return 'cancelled'
        state['seconds'] = min(end, deadline)
        self._save_state(db, state)
        return 'timeout' if end >= deadline else None

    def _commit_meeting(self, db, state, run, a, x, dispatch):
        effect = super()._commit_meeting(db, state, run, a, x, dispatch)
        exists = db.execute("SELECT 1 FROM events WHERE json_extract(payload,'$.type')=? AND json_extract(payload,'$.data.execution_id')=?", (RECORD_EVENT, x['id'])).fetchone()
        if not exists:
            record = bounded_json(db.execute('SELECT payload FROM calendar_records WHERE id=?', (effect['event_id'],)).fetchone()[0])
            self._emit(db, state, RECORD_EVENT, run, {'contract_version': 'calendar-record-observation-0.3.1', 'action_kind': 'meeting',
                'approval_id': a['id'], 'decision_run_id': run['id'], 'execution_id': x['id'], 'effect_id': effect['effect_id'],
                'event_id': record['id'], 'record_digest': digest(record), 'record': record}, a['call_id'])
        return effect

    def _decision_phase(self, lease):
        with self._store.read() as db:
            _, saved = self._leased(db, lease)
        if saved['decision_phase'] != 'invoke': return super()._decision_phase(lease)
        try:
            with self._store.transaction() as db:
                state, run = self._leased(db, lease)
                a = self._approval_auth(db, run['identity'], run['conversation_id'], run['decision']['approval_id'])
                x = self._store.execution(db, a['id'])
                self._operation_deadline = min(run['deadline'], state['seconds'] + self._budget.tool_seconds)
                if self._watchdog_started is not None and time.perf_counter() - self._watchdog_started >= 60:
                    self._unknown(db, state, run, a, x)
                    return clone(run)
                if self._faults.cancel_before_dispatch: run['cancel'] = True
                try:
                    if a['action_kind'] == 'meeting': self._fault_point(db, state, run, 'before_commit', a['call_id'])
                    result = self._advance(db, state, run, self._faults.decision_duration, self._operation_deadline)
                    if result or self._faults.dispatch_failure:
                        raise SyntheticError('tool_timeout' if result == 'timeout' else 'tool_failed')
                except SyntheticError as exc:
                    self._fail_execution(db, state, run, a, x, exc.code)
                    return clone(run)
                try:
                    dispatch = self._current_dispatch(db, run, a)
                    if dispatch != x['dispatch'] or digest(dispatch) != x['dispatch_digest']: raise ValueError('dispatch')
                except (SyntheticError, ValueError):
                    self._fail_execution(db, state, run, a, x, 'preflight_failed')
                    return clone(run)
                destination = dispatch['calendar_id'] if a['action_kind'] == 'meeting' else dispatch['destination']
                self._action_event(db, state, run, 'commit_authorized', a, execution_id=x['id'], dispatch_digest=x['dispatch_digest'])
                self._action_event(db, state, run, 'dispatched', a, execution_id=x['id'], dispatch_arguments=dispatch, dispatch_digest=x['dispatch_digest'], fake_destination=destination)
                if a['action_kind'] == 'meeting':
                    effect = self._commit_meeting(db, state, run, a, x, dispatch)
                    extra = {'event_id': effect['event_id']}
                elif a['action_kind'] == 'message':
                    effect = self._store.commit_effect(db, {'effect_id': _id('effect'), 'execution_id': x['id'], 'channel': dispatch['channel'],
                        'sender_id': dispatch['sender_id'], 'recipient_ids': [p['person_id'] for p in dispatch['recipients']], 'subject': dispatch['subject'],
                        'body': dispatch['body'], 'prepared_digest': a['prepared_digest'], 'dispatch_digest': x['dispatch_digest'], 'committed_at': self._timestamp(state['seconds'])}, destination)
                    extra = {'channel': effect['channel']}
                else: raise ValueError('action_kind')
                self._action_event(db, state, run, 'simulated', a, execution_id=x['id'], effect_id=effect['effect_id'], fake_destination=destination, **extra)
                if self._faults.cancel_after_commit:
                    run['cancel'] = True
                    self._emit(db, state, 'run.cancel_requested', run, {'source': 'after_fake_commit'})
                run['decision_phase'] = 'receipt'
                self._save_run(db, run)
                return clone(run)
        finally:
            self._operation_deadline = None
