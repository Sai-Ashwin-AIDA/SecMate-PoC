"""Deterministic, additive 0.3.1 definitions; no historical re-materialization."""
import hashlib
from pathlib import Path

from ...job_runtime import canonical
from ..contracts import Script, SyntheticError, clone, digest, READ_TOOL
from ..calendar_phase3 import artifacts as old
from ..calendar_phase3.time_rules import TimeRules
from ..communication_repaired.contracts import CommunicationBudget
from .contracts import (VERSION, RECORD_EVENT, EXPORT_PROFILE, RecordCommitData, SuppressedRecordData,
                        IncompleteStep, stage_rules, stage_nulls, bounded_json)
from .acceptance import MATRIX

MEETING, WINDOW, scripted = old.MEETING, old.WINDOW, old.scripted


def deterministic(value):
    if isinstance(value, list):
        return [deterministic(v) for v in value]
    if not isinstance(value, dict):
        return value
    return {k: sorted(v) if k == 'required' else deterministic(v) for k, v in sorted(value.items())}


def revision(value):
    if isinstance(value, list): return [revision(v) for v in value]
    if isinstance(value, dict): return {k: revision(v) for k, v in value.items()}
    if value == '0.3.0': return VERSION
    if value == 'urn:secmate:synthetic-chatmate:phase3:0.3.0:schemas': return 'urn:secmate:synthetic-chatmate:phase3:0.3.1:schemas'
    if isinstance(value, str) and value in {'synchat-tools-0.3.0', 'native-map-0.3.0', 'calendar-small-0.3.0', 'calendar-source-bounded-0.3.0', 'calendar-conformance-0.3.0'}:
        return value[:-5] + VERSION
    return value


def parts(scenario='C-read-0.3.0'):
    result = old.parts(scenario)
    for key in ('schemas', 'capabilities', 'native_metadata', 'policy', 'comparison', 'prompt', 'event_schema', 'baseline', 'budget'):
        result[key] = revision(result[key])
    result['corrections'] = {
        'version': VERSION, 'findings': [f'IA{i:02d}' for i in range(1, 8)],
        'schemas': 'sorted_required_arrays_fixed_template', 'faults': 'reject_overlapping_targets_original_operation_deadline',
        'diagnostics': 'closed_call_or_invalid_shape_count_missing_fields_no_payload_hash', 'record_observation': RECORD_EVENT,
        'record_contract': 'calendar-record-observation-0.3.1',
        'record_origin': 'actual SELECT from canonical calendar row in the effect transaction; no inferred ordinal',
        'current_contacts': 'changed relevant contacts without public snapshots are inconclusive, not seed mismatches',
        'observers': 'stage_semantics_envelope_origin_deadline_terminal_payload_cursor_checks',
        'preservation': 'frozen 0.3.0 source and artifacts unchanged; no retroactive verdict rewrite',
    }
    result['acceptance_matrix'] = {'retained_historical_index': result['acceptance_matrix'], 'corrective_version_index': MATRIX}
    schemas = result['schemas']
    record_schema = clone(schemas['calendar_catalog'])
    record_schema['$defs']['RecordCommitData'] = RecordCommitData.model_json_schema()
    record_schema['$defs']['RecordCommitData']['properties']['record'] = {'$ref': '#/$defs/CalendarRecord'}
    record_schema['$ref'] = '#/$defs/RecordCommitData'
    schemas['record_commit'] = record_schema
    schemas['suppressed_record_commit'] = SuppressedRecordData.model_json_schema()
    schemas['incomplete_step'] = IncompleteStep.model_json_schema()
    schemas['meeting_stage_population'] = stage_rules()
    schemas['meeting_stage_nulls'] = stage_nulls()
    schemas['event_data']['model.incomplete_step'] = schemas['incomplete_step']
    for name in ('record_commit', 'suppressed_record_commit', 'incomplete_step'):
        old.import_schema(schemas['catalog'], 'Corrected_' + name, schemas[name])
    schemas = result['schemas'] = deterministic(schemas)
    result['export_profiles'].update(version=VERSION, selected=EXPORT_PROFILE)
    result['export_profiles']['suppressed'] += ['canonical_record', 'canonical_record_digest']
    result['export_profiles']['correction_contract_digest'] = digest(result['corrections'])
    for name, entry in result['capabilities']['enabled'].items():
        shapes = schemas['tools'][name] if name != READ_TOOL else {
            'input': schemas['read_input'], 'output': {'oneOf': [schemas['listing'], schemas['message_page']]}, 'error': schemas['error_output']}
        entry['schema_digests'] = {k: digest(v) for k, v in shapes.items()}
    result['implementation'].update({'calendar_repaired/' + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(Path(__file__).parent.glob('*.py'))})
    return result


class CalendarBundle(old.CalendarBundle):
    @classmethod
    def load(cls, repository=None, *, scenario='C-read-0.3.0'):
        return cls.from_parts(parts(scenario))

    @classmethod
    def from_parts(cls, supplied):
        try:
            value, expected = clone(supplied), parts()
            conform = value['scenario_id'] == 'calendar-conformance-0.3.1'
            variable = {'script', 'scenario_id', 'baseline'}
            if conform: variable |= {'seed', 'calendar_seed', 'calendar_records', 'record_digests', 'canary_catalog', 'budget'}
            if set(value) != set(expected) or any(value[k] != expected[k] for k in expected.keys() - variable):
                raise ValueError('definition_drift')
            baseline = clone(expected['baseline'])
            if conform: baseline['fixture_id'] = 'calendar-conformance-0.3.1'
            elif value['script'] != expected['scripts'][value['scenario_id']]: raise ValueError('unlabelled_script')
            if value['baseline'] != baseline: raise ValueError('baseline')
            Script.model_validate(value['script'])
            CommunicationBudget.model_validate(value['budget'])
            TimeRules(value['time_rules'])
            derived = clone(value)
            old.derived_sources(derived)
            if any(value[k] != derived[k] for k in ('calendar_records', 'record_digests', 'canary_catalog')):
                raise ValueError('source_metadata')
            return cls(tuple((k, canonical(v)) for k, v in sorted(value.items())))
        except (ValueError, KeyError, TypeError):
            raise SyntheticError('invalid_fixture') from None

    def conformance(self, *, script=None, seed=None, calendar_seed=None, budget=None):
        value = {k: bounded_json(v, maximum=4000000) for k, v in self.artifacts}
        for key, replacement in (('script', script), ('seed', seed), ('calendar_seed', calendar_seed), ('budget', budget)):
            if replacement is not None: value[key] = replacement.model_dump() if hasattr(replacement, 'model_dump') else replacement
        old.derived_sources(value)
        value['scenario_id'] = value['baseline']['fixture_id'] = 'calendar-conformance-0.3.1'
        return self.from_parts(value)

    def bindings(self, faults, assessment_id, generation):
        result = super().bindings(faults, assessment_id, generation)
        for key in ('target_version', 'policy_version', 'prompt_version', 'event_schema_version', 'observer_version', 'runner_version', 'fixture_version'):
            result[key] = VERSION
        result.update(native_metadata_version='native-map-0.3.1', normalized_schema_version='synchat-tools-0.3.1',
                      correction_contract_digest=digest(self.get('corrections')))
        return result
