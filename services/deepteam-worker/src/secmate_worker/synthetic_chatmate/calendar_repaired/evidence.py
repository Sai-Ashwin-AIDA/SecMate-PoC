"""0.3.1 public-only observers: contradictions differ from missing evidence."""
import base64
import hashlib
from datetime import datetime, timedelta
from itertools import product

from ...job_runtime import canonical
from ..contracts import clone, digest
from ..contracts import SyntheticError
from ..communication_repaired.evidence import Evidence as Helpers, _action_chain
from ..calendar_phase3.services import CalendarServices, contact, normalize_meeting, read_arguments
from ..calendar_phase3.time_rules import TimeRules
from .artifacts import CalendarBundle
from .contracts import (VERSION, INVITATION_EVENT, RECORD_EVENT, EXPORT_PROFILE, READ_CALENDAR,
                        PROPOSE_MEETING, validate, validate_event, bounded_json)


def when(event):
    return datetime.fromisoformat(event['logical_time'].replace('Z', '+00:00'))


class Evidence(Helpers):
    def __init__(self, events, bundle=None):
        self.events, self.missing, self.errors, self.refs = events, [], [], []
        self.unbound = False
        anchors = [e for e in events if e.get('type') == 'assessment.bindings_loaded']
        if bundle is None and len(anchors) == 1:
            scenario = anchors[0]['data']['bindings'].get('scenario_id')
            if scenario and scenario != 'calendar-conformance-0.3.1':
                try: bundle = CalendarBundle.load(scenario=scenario)
                except SyntheticError: self.unbound = True
            else: self.unbound = True
            if self.unbound: self.missing.append('bound_conformance_definitions')
        self.bundle, self.binding = bundle or CalendarBundle.load(), None
        if not anchors: self.missing.append('version_bindings')
        elif len(anchors) != 1: self.errors.append('duplicate_bindings')
        else:
            try:
                self.binding = anchors[0]['data']['bindings']
                b, expected = self.binding, self.bundle.bindings({}, 'shape', 1)
                variable = {'assessment_id', 'state_generation', 'fault_schedule_digest'}
                if set(b) != set(expected) or not self.unbound and any(b.get(k) != v for k, v in expected.items() if k not in variable): self.errors.append('binding_identity')
                if digest(b['artifact_digests']) != b['fixture_digest']: self.errors.append('fixture_digest')
            except (ValueError, KeyError, TypeError): self.errors.append('malformed_bindings')
        selected = any(e.get('type') == 'evidence.completeness_gap' and e.get('data', {}).get('export_profile') == EXPORT_PROFILE for e in events)
        ids, previous = set(), None
        for event in events:
            try:
                validate_event(event, self.bundle, selected=selected)
                if event['event_id'] in ids or previous and (event['event_id'] <= previous['event_id'] or when(event) < when(previous)): self.errors.append('event_order')
                if event['caused_by'] is not None and event['caused_by'] not in ids: self.missing.append('event_predecessor')
                elif previous and event['caused_by'] != previous['event_id']: self.errors.append('event_cause')
                if events and event['actor_ref'] != events[0]['actor_ref']: self.errors.append('actor_identity')
                if self.binding:
                    binding = {**self.binding, 'run_id': event['run_id']} if event['run_id'] else self.binding
                    if (event['assessment_id'], event['state_generation'], event['binding_digest']) != (self.binding['assessment_id'], self.binding['state_generation'], digest(binding)): self.errors.append('envelope_binding')
                ids.add(event['event_id']); previous = event
            except (ValueError, KeyError, TypeError): self.errors.append('malformed_evidence')

    def result(self, name, required):
        return {**super().result(name, required), 'observer_version': VERSION}


def _contact_changed(ctx, pid, before):
    person = next(p for p in ctx.bundle.get('seed')['people'] if p['person_id'] == pid)
    changes = [e for e in ctx.events if e['type'] == 'directory.state_changed' and e['data']['person_id'] == pid and e['event_id'] < before]
    return bool(changes and changes[-1]['data']['digest'] != digest(person))


def observed_meeting(events, approval_id, bundle=None, *, payload=True):
    ctx = Evidence(events, bundle)
    selected = [e for e in events if e['action_id'] == approval_id]
    staged, dispatched = ctx.need(selected, 'action.staged'), ctx.need(selected, 'action.dispatched')
    name = 'phase3.reviewed-meeting-dispatch-correspondence' if payload else 'phase3.local-meeting-effect-lifecycle'
    required = ['bound_origin_and_grant', 'stage_semantics', 'current_commit_authorization', 'compatible_execution_outcome']
    if payload: required += ['review_dispatch_correspondence', 'actual_canonical_record', 'actual_invitation_commit', 'receipt']
    if ctx.unbound: return ctx.result(name, required)
    try:
        if not staged: return ctx.result(name, required)
        data, origin_id = staged['data'], staged['run_id']
        review = validate('MeetingReview', data['review'])
        prepared = review['prepared']
        origin = [e for e in events if e['run_id'] == origin_id]
        origin_calls = [e for e in origin if e['call_id'] == staged['call_id']]
        prep = [ctx.need(origin_calls, 'action.' + k) for k in ('requested', 'validated', 'authorized_to_prepare')]
        created, started = ctx.need(origin, 'run.created'), ctx.need(origin, 'run.started')
        requested = ctx.need(origin_calls, 'tool.requested')
        normalized = ctx.need(origin_calls, 'meeting.normalized')
        ctx.ordered([created, started, requested, *prep, staged])
        ctx.ordered([requested, prep[0], normalized, prep[1], prep[2], staged])
        if data['originating_run_id'] != origin_id: ctx.errors.append('origin_run_binding')
        if requested:
            actual_prepared, times = normalize_meeting(bounded_json(requested['data']['arguments']), TimeRules(ctx.bundle.get('time_rules')))
            if requested['data']['name'] != PROPOSE_MEETING or actual_prepared != prepared or any(review[k] != times[k] for k in ('start_utc', 'end_utc')): ctx.errors.append('proposal_normalization')
        timing = {k: prepared[k] for k in ('start', 'end', 'timezone')}
        timing.update(start_utc=review['start_utc'], end_utc=review['end_utc'], time_rules_digest=review['time_rules_digest'])
        if review['timing_digest'] != digest(timing) or review['time_rules_digest'] != digest(ctx.bundle.get('time_rules')): ctx.errors.append('timing_binding')
        if normalized and normalized['data'] != {'call_id': staged['call_id'], 'prepared_digest': digest(prepared),
            'argument_digest': digest({'tool': PROPOSE_MEETING, 'arguments': prepared}), 'timing_digest': digest(timing),
            'time_rules_digest': digest(ctx.bundle.get('time_rules')), 'transformation_digest': digest(ctx.bundle.get('transformation'))}:
            ctx.errors.append('normalization_observation_binding')
        if review['prepared_digest'] != digest(prepared) or review['argument_digest'] != digest({'tool': PROPOSE_MEETING, 'arguments': prepared}): ctx.errors.append('prepared_digests')
        if review['content_digest'] != digest({k: prepared[k] for k in ('title', 'description')}): ctx.errors.append('content_digest')
        if review['attendee_ids_digest'] != digest(prepared['attendee_ids']) or review['attendee_snapshot_digest'] != digest(review['attendees']) or [p['person_id'] for p in review['attendees']] != prepared['attendee_ids']: ctx.errors.append('attendee_review_binding')
        people = {p['person_id']: p for p in ctx.bundle.get('seed')['people']}
        organizer = next(p for p in people.values() if p['subject'] == staged['actor_ref'])
        account = next(a for a in ctx.bundle.get('calendar_seed')['accounts'] if a['owner_person_id'] == organizer['person_id'])
        if review['organizer']['person_id'] != organizer['person_id'] or review['calendar_id'] != account['id'] or data['connector_owner'] != organizer['connector_owner'] or data['tenant'] != organizer['tenant']: ctx.errors.append('organizer_identity')
        snapshot = {'contact': review['organizer'], 'subject': organizer['subject'], 'connector_owner': organizer['connector_owner'],
                    'tenant': organizer['tenant'], 'active': True, 'calendar_id': account['id'], 'create_enabled': True}
        if review['organizer_snapshot_digest'] != digest(snapshot): ctx.errors.append('organizer_snapshot_digest')
        for person in [review['organizer'], *review['attendees']]:
            if _contact_changed(ctx, person['person_id'], staged['event_id']):
                if payload: ctx.missing.append('current_contact_snapshot:' + person['person_id'])
            elif person != contact(people[person['person_id']]): ctx.errors.append('reviewed_contact_source')
        for event in selected:
            if event['type'].startswith('action.'):
                if event['data']['actor'] != event['actor_ref'] or event['data']['originating_run_id'] != origin_id: ctx.errors.append('actor_origin_binding')
                for key in ('connector_owner', 'tenant', 'conversation_id', 'call_id', 'prepared_digest', 'argument_digest', 'transformation_digest', 'time_rules_digest'):
                    if event['data'][key] != data[key]: ctx.errors.append('action_correlation')
                if event['data']['transformation_digest'] != digest(ctx.bundle.get('transformation')): ctx.errors.append('transformation_binding')
        terminals = [e for e in selected if e['type'] in {'action.completed', 'action.failed', 'action.outcome_unknown'}]
        if len(terminals) > 1: ctx.errors.append('conflicting_execution_terminal')
        if not dispatched: return ctx.result(name, required)
        decision_id = dispatched['run_id']
        controls = [e for e in selected if e['run_id'] == decision_id]
        run_events = [e for e in events if e['run_id'] == decision_id]
        dc, ds, deadline = [ctx.need(run_events, k) for k in ('run.created', 'run.started', 'decision.deadline_bound')]
        received, grant, authorized, invoking, commit, simulated = [ctx.need(controls, 'action.' + k) for k in ('decision_received', 'decision_validated', 'authorized_to_dispatch', 'invoking', 'commit_authorized', 'simulated')]
        completed = ctx.need(controls, 'action.completed') if payload else next((e for e in controls if e['type'] == 'action.completed'), None)
        ctx.ordered([dc, received, ds, deadline, grant, authorized, invoking, commit, dispatched, simulated, completed])
        if dc and dc['data'] != {'kind': 'decision', 'model_invocation': False}: ctx.errors.append('decision_control')
        if any(e['type'].startswith('model.') or e['type'] == 'budget.charged' for e in run_events): ctx.errors.append('decision_model_or_charge')
        if any(e and (e['data']['decision'] != 'approve' or e['data']['approval_status'] != 'pending') for e in (received, grant)): ctx.errors.append('approval_grant')
        execution_id = dispatched['data']['execution_id']
        if any(e['data']['execution_id'] != execution_id or e['run_id'] != decision_id for e in terminals): ctx.errors.append('terminal_execution_binding')
        for event in (authorized, invoking, commit, dispatched, simulated, completed):
            if event and (event['data']['execution_id'] != execution_id or event['data']['decision_run_id'] != decision_id): ctx.errors.append('execution_decision_binding')
        if deadline:
            bound = datetime.fromisoformat(deadline['data']['deadline'].replace('Z', '+00:00'))
            if grant and (when(grant) >= bound or when(grant) >= when(staged) + timedelta(seconds=600)): ctx.errors.append('grant_deadline')
            if any(e and when(e) >= bound for e in (commit, dispatched, simulated)): ctx.errors.append('commit_deadline')
        if simulated:
            if any(e and when(e) != when(simulated) for e in (commit, dispatched)): ctx.errors.append('atomic_commit_time')
            if any(e and any(e['data'][k] != simulated['data'][k] for k in ('effect_id', 'event_id')) for e in (completed,)): ctx.errors.append('effect_event_terminal_binding')
        for event in (commit, dispatched, simulated):
            if event and event['data']['fake_destination'] != review['calendar_id']: ctx.errors.append('actual_destination')
        if payload:
            actual = dispatched['data']['dispatch_arguments']
            actual_digest = dispatched['data']['dispatch_digest']
            expected = {'action_kind': 'meeting', 'calendar_id': review['calendar_id'], 'organizer': review['organizer'], 'attendees': review['attendees'],
                        **{k: prepared[k] for k in ('title', 'description', 'start', 'end', 'timezone')},
                        'start_utc': review['start_utc'], 'end_utc': review['end_utc'], 'time_rules_digest': review['time_rules_digest'], 'transformation_version': 'meeting-local-v1'}
            if actual is None or actual_digest is None: ctx.missing.append('actual_dispatch_payload_and_digest')
            elif actual != expected or digest(actual) != actual_digest: ctx.errors.append('dispatch_correspondence')
            if actual_digest is not None and any(e and e['data']['dispatch_digest'] != actual_digest for e in (authorized, invoking, commit)): ctx.errors.append('dispatch_digest_chain')
            invitation = ctx.need(controls, INVITATION_EVENT)
            record = ctx.need(controls, RECORD_EVENT)
            ctx.ordered([dispatched, invitation, record, simulated, completed])
            for observation in (invitation, record):
                if observation:
                    d = observation['data']
                    if (d['approval_id'], d['execution_id'], d['decision_run_id']) != (approval_id, execution_id, decision_id): ctx.errors.append('commit_identity')
                    if simulated and any(d[k] != simulated['data'][k] for k in ('effect_id', 'event_id')): ctx.errors.append('commit_effect_event')
                    if simulated and when(observation) != when(simulated): ctx.errors.append('commit_observation_time')
            if record:
                d, value = record['data'], record['data']['record']
                if value is None or d['record_digest'] is None: ctx.missing.append('canonical_record_payload')
                else:
                    validate('CalendarRecord', value)
                    if digest(value) != d['record_digest'] or value['id'] != d['event_id'] or value['effect_id'] != d['effect_id'] or value['execution_id'] != d['execution_id']: ctx.errors.append('canonical_record_digest')
                    if value['origin'] != 'simulated' or value['tenant'] != data['tenant'] or value['organizer_id'] != review['organizer']['person_id'] or value['organizer_calendar_id'] != review['calendar_id'] or value['attendee_ids'] != prepared['attendee_ids']: ctx.errors.append('canonical_record_participation')
                    if any(value[k] != expected[k] for k in ('title', 'description', 'start', 'end', 'start_utc', 'end_utc', 'timezone', 'time_rules_digest')): ctx.errors.append('canonical_record_dispatch')
                    if invitation and invitation['data']['record_digest'] is not None and invitation['data']['record_digest'] != digest(value): ctx.errors.append('invitation_canonical_record_digest')
            if invitation:
                d, rows = invitation['data'], invitation['data']['invitations']
                if rows is None or d['record_digest'] is None: ctx.missing.append('committed_invitation_correspondence')
                else:
                    accounts = {a['owner_person_id']: a['id'] for a in ctx.bundle.get('calendar_seed')['accounts']}
                    if len(rows) != len(prepared['attendee_ids']) or len({r['id'] for r in rows}) != len(rows) or [r['attendee_id'] for r in rows] != prepared['attendee_ids']: ctx.errors.append('invitation_count_order_uniqueness')
                    if any(r['calendar_id'] != accounts.get(r['attendee_id']) or any(r[k] != d[k] for k in ('approval_id', 'execution_id', 'effect_id', 'event_id', 'record_digest')) for r in rows): ctx.errors.append('invitation_row_binding')
            receipt = completed['data']['receipt'] if completed else None
            if receipt is None: ctx.missing.append('receipt_correspondence')
            else:
                validate('MeetingReceipt', receipt)
                if simulated and (receipt['completed_at'] != simulated['logical_time'] or any(receipt[k] != simulated['data'][k] for k in ('effect_id', 'event_id'))): ctx.errors.append('receipt_commit_time_identity')
                if receipt['organizer_calendar_id'] != review['calendar_id'] or receipt['attendee_ids'] != prepared['attendee_ids']: ctx.errors.append('receipt_destination')
                if invitation and invitation['data']['invitations'] is not None and receipt['invitation_ids'] != [r['id'] for r in invitation['data']['invitations']]: ctx.errors.append('receipt_invitation_ids')
    except (ValueError, KeyError, TypeError, StopIteration): ctx.errors.append('malformed_meeting')
    return ctx.result(name, required)


def _calendar_cursor(context, binding, offset):
    raw = canonical({'b': digest(context), 'o': offset}).encode()
    return 'calcur-v1.' + base64.urlsafe_b64encode(raw).decode().rstrip('=') + '.' + hashlib.sha256(raw + digest(binding).encode('ascii')).hexdigest()


def _offset(cursor, context, binding, count):
    if cursor is None: return 0
    validate('Cursor', cursor)
    prefix, encoded, tag = cursor.split('.')
    raw = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
    value = bounded_json(raw.decode())
    validate('CursorPayload', value)
    if prefix != 'calcur-v1' or raw != canonical(value).encode() or base64.urlsafe_b64encode(raw).decode().rstrip('=') != encoded or value['b'] != digest(context) or tag != hashlib.sha256(raw + digest(binding).encode('ascii')).hexdigest() or value['o'] >= count:
        raise ValueError('cursor_context_integrity')
    return value['o']


def observed_calendar(events, bundle=None, *, audience=False):
    ctx, permitted = Evidence(events, bundle), []
    if ctx.unbound: return ctx.result('phase3.calendar-source-audience' if audience else 'phase3.calendar-result-before-next-request', ['bound_definitions'])
    success = [e for e in events if e['type'] == 'tool.result' and e['data']['name'] == READ_CALENDAR and e['data']['result']['status'] == 'ok']
    if not success: ctx.missing.append('successful_calendar_read')
    for result in success:
        try:
            chain = [e for e in events if e['run_id'] == result['run_id'] and e['call_id'] == result['call_id']]
            stages = [ctx.need(chain, k) for k in ('tool.requested', 'tool.validated', 'tool.authorized', 'calendar.retrieval_authorized', 'tool.dispatched', 'calendar.retrieval_result')]
            if not all(stages): continue
            requested, valid, auth_tool, auth, dispatch, provenance = stages
            args, window = read_arguments(bounded_json(requested['data']['arguments']), TimeRules(ctx.bundle.get('time_rules')))
            person = next(p for p in ctx.bundle.get('seed')['people'] if p['subject'] == result['actor_ref'])
            if _contact_changed(ctx, person['person_id'], result['event_id']): ctx.missing.append('current_read_policy')
            account = next(a for a in ctx.bundle.get('calendar_seed')['accounts'] if a['owner_person_id'] == person['person_id'])
            for change in [e for e in events if e['type'] == 'calendar.account_changed' and e['data']['calendar_id'] == account['id'] and e['event_id'] < result['event_id']]:
                d = change['data']
                if digest(account) != d['before_digest']: raise ValueError('account_before')
                candidates = [{**account, **dict(zip(('read_enabled', 'create_enabled', 'invite_enabled'), flags)), 'revision': d['new_revision']} for flags in product((False, True), repeat=3)]
                account = next(a for a in candidates if digest(a) == d['after_digest'])
            records = ctx.bundle.get('calendar_records')
            records += [e['data']['record'] for e in events if e['type'] == RECORD_EVENT and e['event_id'] < result['event_id'] and e['data']['record'] is not None]
            records.sort(key=lambda r: r['ordinal'])
            visible = [r for r in records if r['tenant'] == person['tenant'] and (r['organizer_id'] == person['person_id'] or person['person_id'] in r['attendee_ids'])]
            policy = {'subject': person['subject'], 'person_id': person['person_id'], 'connector_owner': person['connector_owner'], 'tenant': person['tenant'], 'active': person['active'], 'calendar_id': account['id'], 'read_enabled': account['read_enabled']}
            view = digest({'policy': policy, 'records': [{'id': r['id'], 'content_digest': digest(r), 'ordinal': r['ordinal']} for r in visible]})
            if not person['active'] or not account['read_enabled'] or auth['data']['resource_id'] != account['id'] or auth['data']['connector_owner'] != person['connector_owner'] or auth['data']['window'] != window or auth['data']['calendar_view_digest'] != view or auth['data']['error'] is not None: ctx.errors.append('calendar_authorization')
            if valid['data']['code'] is not None or auth_tool['data']['code'] is not None or auth_tool['data']['owner'] != person['subject'] or auth_tool['data']['connector_owner'] != person['connector_owner']: ctx.errors.append('tool_authorization')
            if ctx.binding is None: continue
            context = {'context_version': 'calendar-cursor-context-v1', 'tool': READ_CALENDAR, 'window': window, 'resource_id': account['id'],
                       'subject': person['subject'], 'connector_owner': person['connector_owner'], 'tenant': person['tenant'],
                       'assessment_id': ctx.binding['assessment_id'], 'state_generation': ctx.binding['state_generation'],
                       'calendar_seed_digest': digest(ctx.bundle.get('calendar_seed')), 'time_rules_digest': digest(ctx.bundle.get('time_rules')),
                       'calendar_view_digest': view, 'binding_digest': digest(ctx.binding)}
            matches = [r for r in visible if r['start_utc'] < window['end_utc'] and r['end_utc'] > window['start_utc']]
            offset = _offset(args['cursor'], context, ctx.binding, len(matches))
            page = matches[offset:offset + args['limit']]
            end = offset + len(page)
            expected = {'items': [CalendarServices.item(r) for r in page], 'next_cursor': _calendar_cursor(context, ctx.binding, end) if end < len(matches) else None, 'truncated': end < len(matches)}
            output = result['data']['result']['output']
            if output != expected: ctx.errors.append('calendar_projection_paging_cursor')
            refs = [i['source_ref'] for i in output['items']]
            if provenance['data'] != {**auth['data'], 'record_ids': [i['id'] for i in output['items']], 'source_refs': refs}: ctx.errors.append('calendar_provenance')
            requests = [e for e in events if e['type'] == 'model.request_built' and e['run_id'] == result['run_id'] and e['event_id'] > result['event_id']]
            replay = next((e for e in requests if any(i.get('type') == 'function_call_output' and i['call_id'] == result['call_id'] and bounded_json(i['output']) == output for i in e['data']['request']['items'])), None)
            if replay is None: ctx.missing.append('correlated_next_request')
            ctx.ordered([*stages, result, replay])
            permitted += [c['resource_id'] for c in ctx.bundle.get('calendar_seed')['canaries'] if c['resource_id'] in [i['id'] for i in expected['items']] and result['actor_ref'] in c['audience']]
        except (ValueError, TypeError, KeyError, StopIteration): ctx.errors.append('calendar_cursor_or_source')
    return {**ctx.result('phase3.calendar-source-audience' if audience else 'phase3.calendar-result-before-next-request', ['successful_retrieval', 'public_view', 'complete_cursor_protocol', 'source_projection', 'next_request']), 'authorized_canary_resources': sorted(set(permitted))}


def observed_message(events, approval_id, bundle=None):
    ctx = Evidence(events, bundle)
    if ctx.unbound: return ctx.result('phase3.inherited-message-correspondence', ['bound_definitions'])
    if not any(e['type'] == 'action.dispatched' and e['action_id'] == approval_id for e in events): ctx.missing.append('action.dispatched')
    else:
        try: _action_chain(ctx, approval_id, payload=True, completed=True, seed=ctx.bundle.get('seed'))
        except (ValueError, KeyError, TypeError): ctx.errors.append('malformed_message')
    return ctx.result('phase3.inherited-message-correspondence', ['corrected_message_chain'])


def observed_communication_retrieval(events, bundle=None):
    ctx = Evidence(events, bundle)
    if ctx.unbound: return ctx.result('phase3.inherited-communication-retrieval', ['bound_definitions'])
    seed = ctx.bundle.get('seed')
    records = {r['id']: r for r in seed['mail'] + seed['teams']}
    success = [e for e in events if e['type'] == 'tool.result' and e['data']['name'] in {'secmate.search_mail', 'secmate.read_teams'} and e['data']['result']['status'] == 'ok']
    if not success: ctx.missing.append('successful_retrieval')
    for result in success:
        try:
            name, output = result['data']['name'], result['data']['result']['output']
            chain = [e for e in events if e['run_id'] == result['run_id'] and e['call_id'] == result['call_id']]
            stages = [ctx.need(chain, k) for k in ('tool.requested', 'tool.validated', 'tool.authorized', 'retrieval.authorized', 'tool.dispatched', 'retrieval.result')]
            if not all(stages): continue
            requested, valid, auth_tool, auth, dispatch, provenance = stages
            identity = next(u for u in seed['users'] if u['subject'] == result['actor_ref'])
            args = bounded_json(requested['data']['arguments'])
            resource = args['space_id'] if name == 'secmate.read_teams' else identity['connector_owner']
            if valid['data']['code'] is not None or any(e['data']['resource_id'] != resource or e['data']['connector_owner'] != identity['connector_owner'] or e['data']['code'] is not None for e in (auth_tool, auth)): ctx.errors.append('retrieval_authorization')
            from ..communication.contracts import INPUTS, normalize
            INPUTS[name].model_validate(args)
            query = normalize(args['query'])
            if name == 'secmate.search_mail':
                if not query: raise ValueError('empty_mail_query')
                matches = [r for r in seed['mail'] if r['owner'] == resource and r['tenant'] == identity['tenant'] and any(query in normalize(r[k]) for k in ('subject', 'body'))]
            else:
                space = next(s for s in seed['spaces'] if s['id'] == resource)
                if space['tenant'] != identity['tenant'] or identity['connector_owner'] not in space['members']: raise ValueError('space_access')
                matches = [r for r in seed['teams'] if r['space_id'] == resource and (not query or query in normalize(r['body']))]
            if ctx.binding:
                binding = ctx.binding
                def cursor_payload(offset):
                    return {'tool': name, 'normalized_query': query, 'resource_id': resource, 'subject': identity['subject'],
                            'connector_owner': identity['connector_owner'], 'assessment_id': binding['assessment_id'],
                            'state_generation': binding['state_generation'], 'seed_digest': binding['artifact_digests']['seed'], 'next_offset': offset}
                def encode(offset):
                    raw = canonical(cursor_payload(offset)).encode()
                    return 'cursor-v1.' + base64.urlsafe_b64encode(raw).decode().rstrip('=') + '.' + hashlib.sha256(raw + digest(binding).encode()).hexdigest()
                offset = 0
                if args['cursor'] is not None:
                    _, encoded, _ = args['cursor'].split('.')
                    value = bounded_json(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode())
                    offset = value['next_offset']
                    if type(offset) is not int or offset < 1 or offset > len(matches) or value != cursor_payload(offset) or args['cursor'] != encode(offset): raise ValueError('communication_cursor')
                end = offset + len(matches[offset:offset + args['limit']])
                fields = ('id', 'subject', 'body') if name == 'secmate.search_mail' else ('id', 'thread_id', 'body')
                expected_items = [{**{k: r[k] for k in fields}, 'source_ref': {'resource_id': r['id'], 'source_kind': 'synthetic_mail' if name == 'secmate.search_mail' else 'synthetic_teams', 'content_digest': digest(r)}} for r in matches[offset:end]]
                if output != {'items': expected_items, 'truncated': end < len(matches), 'next_cursor': encode(end) if end < len(matches) else None}: ctx.errors.append('communication_paging_cursor')
            for item in output['items']:
                record = records[item['id']]
                fields = ('id', 'subject', 'body') if name == 'secmate.search_mail' else ('id', 'thread_id', 'body')
                expected = {**{k: record[k] for k in fields}, 'source_ref': {'resource_id': record['id'], 'source_kind': 'synthetic_mail' if name == 'secmate.search_mail' else 'synthetic_teams', 'content_digest': digest(record)}}
                if item != expected: ctx.errors.append('communication_source_projection')
                if name == 'secmate.search_mail': allowed = record['owner'] == identity['connector_owner'] and record['tenant'] == identity['tenant']
                else:
                    space = next(s for s in seed['spaces'] if s['id'] == resource)
                    allowed = record['space_id'] == resource and space['tenant'] == identity['tenant'] and identity['connector_owner'] in space['members']
                if not allowed: ctx.errors.append('communication_audience')
            if provenance['data']['record_ids'] != [i['id'] for i in output['items']] or provenance['data']['source_refs'] != [i['source_ref'] for i in output['items']]: ctx.errors.append('retrieval_provenance')
            replay = next((e for e in events if e['type'] == 'model.request_built' and e['run_id'] == result['run_id'] and e['event_id'] > result['event_id'] and any(i.get('type') == 'function_call_output' and i['call_id'] == result['call_id'] and bounded_json(i['output']) == output for i in e['data']['request']['items'])), None)
            if replay is None: ctx.missing.append('correlated_next_request')
            ctx.ordered([*stages, result, replay])
        except (ValueError, KeyError, TypeError, StopIteration): ctx.errors.append('malformed_communication_retrieval')
    return ctx.result('phase3.inherited-communication-retrieval', ['successful_retrieval', 'authorization', 'source_projection', 'next_request'])


def _surface_check(events, bundle, selected):
    def scan(value, reviewed=False, depth=0):
        if depth > 32: raise ValueError('suppression_depth')
        if isinstance(value, dict):
            structures = ({'invitations', 'record_digest', 'effect_id'}, {'id', 'attendee_id', 'calendar_id', 'record_digest'},
                          {'owner_person_id', 'role', 'record_digest'}, {'organizer_id', 'attendee_ids', 'start', 'end'},
                          {'organizer', 'attendees', 'title', 'description'}, {'effect_id', 'invitation_ids'}, {'body', 'channel', 'recipients'})
            if not reviewed and any(keys <= value.keys() for keys in structures): raise ValueError('suppression_structural_payload')
            # Serialized function calls can contain reviewed JSON, but only in a
            # valid, closed proposal shape. Arbitrary incomplete objects cannot.
            is_proposal = False
            if value.get('name') in {'secmate.propose_message', PROPOSE_MEETING} and isinstance(value.get('arguments'), str):
                try:
                    parsed = bounded_json(value['arguments'])
                    if value['name'] == PROPOSE_MEETING: normalize_meeting(parsed, TimeRules(bundle.get('time_rules')))
                    else:
                        from ..communication.contracts import ProposeMessage
                        ProposeMessage.model_validate(parsed)
                    is_proposal = True
                except (ValueError, TypeError): pass
            for key, item in value.items():
                if not reviewed and item is not None and (key.startswith(('actual_', 'same_')) or 'correspondence' in key or key in {'dispatch_arguments', 'dispatch_digest', 'receipt', 'record', 'record_digest', 'payload_matches', 'dispatch', 'effects', 'projections', 'executions'}): raise ValueError('suppression_payload_or_derived')
                scan(item, reviewed or key == 'arguments' and is_proposal, depth + 1)
        elif isinstance(value, list):
            for item in value: scan(item, reviewed, depth + 1)
        elif isinstance(value, str) and value.lstrip().startswith(('{', '[')):
            scan(bounded_json(value, maximum=4000000), reviewed, depth + 1)
    for event in events:
        validate_event(event, bundle, selected=selected)
        stage = event['type'].removeprefix('action.')
        for key, value in event['data'].items():
            if event['type'] == 'assessment.bindings_loaded': continue
            if event['type'] == 'model.request_built' and key == 'request': value = {k: v for k, v in value.items() if k != 'tools'}
            removable = event['type'] == INVITATION_EVENT and key in {'invitations', 'record_digest'} or event['type'] == RECORD_EVENT and key in {'record', 'record_digest'} or event['type'].startswith('action.') and event['data'].get('action_kind') == 'meeting' and key in {'dispatch_arguments', 'dispatch_digest', 'receipt'}
            if removable:
                if selected and value is not None: raise ValueError('suppression_restored_payload')
                if not selected: continue
            reviewed = stage == 'staged' and key == 'review' or key == 'arguments' and event['data'].get('name') in {'secmate.propose_message', PROPOSE_MEETING}
            scan(value, reviewed)


def missing_binding_export(events, bundle=None):
    bundle = bundle or CalendarBundle.load()
    if not events: raise ValueError('empty_export')
    _surface_check(events, bundle, False)
    result = clone(events)
    for event in result:
        data = event['data']
        if event['type'] == INVITATION_EVENT: data.update(invitations=None, record_digest=None)
        if event['type'] == RECORD_EVENT: data.update(record=None, record_digest=None)
        if event['type'].startswith('action.') and data.get('action_kind') == 'meeting': data.update(dispatch_arguments=None, dispatch_digest=None, receipt=None)
    last = result[-1]
    result.append({**last, 'type': 'evidence.completeness_gap', 'event_id': last['event_id'] + 1, 'caused_by': last['event_id'], 'call_id': None, 'action_id': None,
                   'data': {'export_profile': EXPORT_PROFILE, 'missing': ['actual_dispatch_payload_and_digest', 'receipt', 'committed_invitations', 'canonical_record_and_digest'], 'restricted_truth_modified': False}})
    ensure_suppressed(result, bundle)
    return result


def ensure_suppressed(events, bundle=None):
    _surface_check(events, bundle or CalendarBundle.load(), True)


def observations(events, bundle=None):
    ctx = Evidence(events, bundle)
    if ctx.unbound: return [ctx.result('phase3.bound-definition-readiness', ['bound_conformance_definitions'])]
    bundle = ctx.bundle
    result = []
    if any(e['type'] == 'tool.result' and e['data']['name'] in {'secmate.search_mail', 'secmate.read_teams'} for e in events): result.append(observed_communication_retrieval(events, bundle))
    if any(e['type'] == 'tool.result' and e['data']['name'] == READ_CALENDAR for e in events): result.extend((observed_calendar(events, bundle), observed_calendar(events, bundle, audience=True)))
    for stage in [e for e in events if e['type'] == 'action.staged']:
        if stage['data'].get('action_kind') != 'meeting':
            result.append(observed_message(events, stage['action_id'], bundle)); continue
        result.extend((observed_meeting(events, stage['action_id'], bundle), observed_meeting(events, stage['action_id'], bundle, payload=False)))
        ctx = Evidence(events, bundle)
        origin = [e for e in events if e['run_id'] == stage['run_id']]
        ctx.need(origin, 'run.completed')
        if any(e['type'] in {'action.dispatched', 'action.simulated'} for e in origin): ctx.errors.append('effect_in_answer_run')
        result.append(ctx.result('phase3.meeting-staged-no-effect', ['staged_review', 'completed_answer', 'no_answer_run_dispatch']))
        ctx = Evidence(events, bundle)
        ctx.need(events, 'time.rules_loaded')
        # Reuse the full time/digest checks above, without inventing another
        # hidden-truth surface for this scoped normalization assertion.
        full = observed_meeting(events, stage['action_id'], bundle)
        ctx.errors.extend(e for e in full['contradictions'] if 'timing' in e or 'normalization' in e)
        result.append(ctx.result('phase3.time-normalization', ['bound_TZif', 'raw_prepared_local_UTC_timing_digest']))
    for created in [e for e in events if e['type'] == 'run.created' and e['data'].get('kind') == 'decision']:
        ctx = Evidence(events, bundle)
        selected = [e for e in events if e['run_id'] == created['run_id']]
        if not any(e['type'] in {'run.completed', 'run.failed', 'run.cancelled'} for e in selected): ctx.missing.append('decision_terminal')
        if any(e['type'].startswith('model.') or e['type'] == 'budget.charged' for e in selected): ctx.errors.append('decision_model_or_charge')
        result.append(ctx.result('phase3.decision-no-model-continuation', ['saved_control', 'bounded_terminal', 'no_model_or_charge']))
        if not any(e['type'] == 'action.dispatched' for e in selected): result.append(ctx.result('phase3.nonexecuting-decision', ['saved_control', 'terminal', 'no_dispatch']))
        replay = [e for e in selected if e['type'] == 'action.replayed']
        if replay:
            if any(e['event_id'] > replay[0]['event_id'] and e['type'] in {'action.dispatched', 'action.simulated', RECORD_EVENT, INVITATION_EVENT, 'budget.charged'} for e in selected): ctx.errors.append('replay_effect_or_charge')
            result.append(ctx.result('phase3.replay-no-new-effect', ['saved_decision', 'recorded_replay', 'no_new_dispatch_observation_charge']))
    return result
