"""0.3.1 closed diagnostic, stage and actual-record observation contracts."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import StrictModel, ToolCall, clone, digest
from ..communication.contracts import ID, SHA
from ..calendar_phase3 import contracts as old

VERSION = '0.3.1'
READ_CALENDAR, PROPOSE_MEETING = old.READ_CALENDAR, old.PROPOSE_MEETING
INVITATION_EVENT = old.INVITATION_EVENT
RECORD_EVENT = 'meeting.record_committed'
EXPORT_PROFILE = 'missing-meeting-binding-telemetry-0.3.1'
bounded_json = old.bounded_json


class RecordCommitData(StrictModel):
    contract_version: Literal['calendar-record-observation-0.3.1']
    action_kind: Literal['meeting']
    approval_id: ID
    decision_run_id: ID
    execution_id: ID
    effect_id: ID
    event_id: ID
    record_digest: SHA
    record: dict


class SuppressedRecordData(RecordCommitData):
    record_digest: None
    record: None


class IncompleteCall(StrictModel):
    kind: Literal['call']
    call: ToolCall


class InvalidCall(StrictModel):
    kind: Literal['invalid_call']
    value_kind: Literal['object', 'array', 'string', 'number', 'boolean', 'null']
    field_count: Annotated[int, Field(strict=True, ge=0, le=240000)]
    missing: list[Literal['call_id', 'name', 'arguments']]


class IncompleteStep(StrictModel):
    round: Annotated[int, Field(strict=True, ge=1)]
    text: Annotated[str, Field(strict=True, max_length=240000)]
    calls: list[IncompleteCall | InvalidCall]
    completion: bool


class Phase3FaultPlan(old.Phase3FaultPlan):
    @model_validator(mode='after')
    def reject_overlapping_targets(self):
        for i, a in enumerate(self.calendar_faults):
            for b in self.calendar_faults[i + 1:]:
                if a.phase == b.phase and a.occurrence == b.occurrence and (a.call_id == b.call_id or a.call_id is None or b.call_id is None):
                    raise ValueError('overlapping_calendar_fault_targets')
        return self


def diagnostics(calls):
    result = []
    for value in calls:
        try:
            result.append({'kind': 'call', 'call': ToolCall.model_validate(value).model_dump()})
        except (ValueError, TypeError):
            kind = 'null' if value is None else 'boolean' if type(value) is bool else 'object' if isinstance(value, dict) else 'array' if isinstance(value, list) else 'string' if isinstance(value, str) else 'number'
            result.append({'kind': 'invalid_call', 'value_kind': kind, 'field_count': len(value) if isinstance(value, dict) else 0,
                           'missing': [k for k in ('call_id', 'name', 'arguments') if not isinstance(value, dict) or k not in value]})
    return result


def validate(root, value):
    if root == 'EventEnvelope':
        shape = clone(old.blueprint_inputs()[0]['$defs'][root])
        shape['properties']['event_schema_version'] = {'const': VERSION}
        shape['properties']['target_version'] = {'const': VERSION}
        return old.validate(None, value, external=shape)
    return old.validate(root, value)


def stage_rules():
    core = ['prepared_digest', 'argument_digest']
    approved = ['approval_id', 'decision_run_id', 'execution_id', 'execution_status', 'approval_status', *core]
    return {
        'requested': [], 'validated': core, 'validation_rejected': ['error'],
        'authorized_to_prepare': core, 'authorization_rejected': ['error', *core],
        'staged': ['approval_id', 'approval_status', 'review', *core],
        'decision_received': ['approval_id', 'decision_run_id', 'decision', 'approval_status', *core],
        'decision_validated': ['approval_id', 'decision_run_id', 'decision', 'approval_status', *core],
        'authorized_to_dispatch': [*approved, 'dispatch_digest'], 'invoking': [*approved, 'dispatch_digest'],
        'commit_authorized': [*approved, 'dispatch_digest', 'fake_destination'],
        'dispatched': [*approved, 'dispatch_digest', 'dispatch_arguments', 'fake_destination'],
        'simulated': [*approved, 'effect_id', 'event_id', 'fake_destination'],
        'completed': [*approved, 'effect_id', 'event_id', 'receipt'],
        'failed': [*approved, 'error'], 'outcome_unknown': [*approved, 'error'],
        'expired': ['approval_id', 'approval_status', *core], 'rejected': ['approval_id', 'approval_status', *core],
        'superseded': ['approval_id', 'approval_status', *core], 'replayed': ['approval_id', 'approval_status', *core],
    }


def stage_nulls():
    fields = {'approval_id', 'decision_run_id', 'execution_id', 'effect_id', 'event_id', 'decision', 'approval_status', 'execution_status',
              'prepared_digest', 'argument_digest', 'dispatch_digest', 'review', 'dispatch_arguments', 'receipt', 'fake_destination', 'error', 'field'}
    allowed = {stage: set(required) for stage, required in stage_rules().items()}
    allowed['validation_rejected'] |= {'prepared_digest', 'argument_digest', 'field'}
    allowed['authorization_rejected'].add('field')
    for stage in ('failed', 'outcome_unknown'): allowed[stage] |= {'effect_id', 'event_id', 'field'}
    allowed['replayed'] |= {'execution_id', 'execution_status', 'decision_run_id', 'error'}
    return {stage: sorted(fields - values) for stage, values in sorted(allowed.items())}


def validate_event(event, bundle=None, *, selected=False):
    validate('EventEnvelope', event)
    kind, data = event['type'], event['data']
    if kind == 'time.rules_loaded' and bundle is not None:
        resources = {r['zone_key']: r['resource_sha256'] for r in bundle.get('time_rules')['resources']}
        if data != {'time_rules_digest': digest(bundle.get('time_rules')), 'package_version': '2026.6', 'iana_version': '2026f', 'resource_digests': resources}:
            raise ValueError('time_rules_observation_binding')
    if data.get('approval_id') != event['action_id']:
        raise ValueError('action_envelope_binding')
    for key in ('assessment_id', 'state_generation', 'call_id'):
        if key in data and data[key] != event[key]:
            raise ValueError('data_envelope_binding')
    if kind == RECORD_EVENT:
        (SuppressedRecordData if selected else RecordCommitData).model_validate(data)
        if not selected:
            validate('CalendarRecord', data['record'])
        return event
    if kind == 'model.incomplete_step':
        IncompleteStep.model_validate(data)
        return event
    if kind.startswith('action.') and data.get('action_kind') == 'meeting':
        stage = kind[7:]
        if stage not in stage_rules():
            raise ValueError('action_stage')
        if data['actor'] != event['actor_ref']:
            raise ValueError('action_actor_envelope')
        if stage in {'requested', 'validated', 'validation_rejected', 'authorized_to_prepare', 'authorization_rejected', 'staged'} and data['originating_run_id'] != event['run_id']:
            raise ValueError('action_origin_envelope')
        for key in stage_rules()[stage]:
            if data.get(key) is None and not (selected and key in {'dispatch_arguments', 'dispatch_digest', 'receipt'}):
                raise ValueError('stage_required:' + key)
        if any(data.get(key) is not None for key in stage_nulls()[stage]):
            raise ValueError('stage_nonapplicable_field')
        expected_status = {'staged': 'pending', 'authorized_to_dispatch': 'approved', 'invoking': 'approved',
                           'commit_authorized': 'approved', 'dispatched': 'approved', 'simulated': 'approved',
                           'completed': 'approved', 'failed': 'approved', 'outcome_unknown': 'approved',
                           'expired': 'expired', 'rejected': 'rejected', 'superseded': 'superseded'}
        if stage in expected_status and data['approval_status'] != expected_status[stage]:
            raise ValueError('stage_approval_status')
        expected_execution = {'authorized_to_dispatch': 'invoking', 'invoking': 'invoking', 'commit_authorized': 'invoking',
                              'dispatched': 'invoking', 'simulated': 'invoking', 'completed': 'succeeded', 'failed': 'failed', 'outcome_unknown': 'outcome_unknown'}
        if stage in expected_execution and data['execution_status'] != expected_execution[stage]:
            raise ValueError('stage_execution_status')
        early = {'requested', 'validated', 'validation_rejected', 'authorized_to_prepare', 'authorization_rejected', 'staged', 'decision_received', 'decision_validated', 'expired', 'rejected', 'superseded'}
        if stage in early and any(data.get(k) is not None for k in ('execution_id', 'execution_status', 'effect_id', 'event_id', 'dispatch_arguments', 'dispatch_digest', 'receipt')):
            raise ValueError('stage_premature_execution')
        if stage != 'dispatched' and data['dispatch_arguments'] is not None or stage != 'completed' and data['receipt'] is not None:
            raise ValueError('stage_unreached_payload')
    # Reuse only the equivalent frozen wire-shape validator through an explicit
    # version projection. No frozen globals, events or definitions are mutated.
    projected = {**event, 'target_version': '0.3.0', 'event_schema_version': '0.3.0'}
    old.validate_event(projected, bundle, selected=selected)
    return event
