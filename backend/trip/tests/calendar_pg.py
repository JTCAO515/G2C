"""Signed calendar read/storage over real limited-role PG, not seeded rows."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import re
from contextlib import contextmanager
import unittest
from unittest.mock import patch
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'backend/trip/tests'), str(ROOT/'backend/draft/tests'),
               str(ROOT/'backend/agent/tests'), str(ROOT/'backend/cj_api/tests'), str(ROOT/'scripts')]
import needs_actions_pg as needs_fixture
from e2e_local import Harness, CONNINFO
from registered_host_support import RegisteredHost
from cj_trip.local_calendar_read import create_local_calendar_read_app, VERSION
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_trip.postgres import Repository
from cj_trip.domain import Conflict, Proposal, packed
from cj_trip.confirmation import ConfirmationSigner
from cj_agent.draft import trip_scope_for
from cj_api.local_app import scope_for, ISSUER
from cj_message.travel import ABI
import dev_auth

FIXTURES = json.loads((ROOT/'contracts/trip/structured-examples.3.json').read_bytes())


class CalendarReadChecks(unittest.TestCase):
    headers = Harness.headers
    setup_source = needs_fixture.NeedsActionChecks.setup_source
    worker = needs_fixture.NeedsActionChecks.worker
    plan = needs_fixture.NeedsActionChecks.plan
    action = needs_fixture.NeedsActionChecks.action
    post = needs_fixture.NeedsActionChecks.post

    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host = RegisteredHost(cls.auth/'calendar', Path(CONNINFO),
            {s: (12, 2, 30000) for s in ('calendar', 'calendar-foreign', 'calendar-revoke')})
        cls.env = dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1', CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer = ConfirmationSigner(b'synthetic-calendar-pg-signer-123456789')
        for subject in cls.host.subjects:
            dev_auth.activate_travel(Path(CONNINFO), subject, cls.host.profiles[subject][1], ABI)

    tearDownClass = classmethod(Harness.tearDownClass.__func__)

    def reader(self, subject='calendar', **options):
        return create_local_calendar_read_app(conninfo_path=CONNINFO, auth_dir=self.host.auth,
            run_context=self.host.profiles[subject][1], **options)

    def saved(self):
        app, outcome, database = self.plan('calendar')
        with TestClient(app) as writer:
            accepted = self.post(writer, 'calendar', self.action('calendar', outcome, 'accept'))
            self.assertEqual(accepted.status_code, 200, accepted.text)
            legacy_id = accepted.json()['receipt']['trip_id']
        owner = scope_for(ISSUER, 'calendar')
        repository = Repository(lambda: database.connect(owner), trip_scope_for(owner), self.signer,
                                structured=True, calendar=True)
        content = packed(FIXTURES['base'])
        proposal = Proposal('calendar-pg-'+uuid.uuid4().hex, 'calendar-trip-'+uuid.uuid4().hex,
                            0, 'synthetic-calendar-read', int(time.time())+300, content)
        digest = repository.publish(proposal)
        signed = self.signer.issue(repository.scope, repository.proposal_detail(proposal.proposal_id),
            action_id='calendar-save-'+uuid.uuid4().hex, kind='accept', candidate_hash=digest)
        receipt = repository.act(signed.action)
        self.assertEqual(receipt.committed_version, 1)
        return legacy_id, proposal.trip_id, content

    def test_actual_signed_read_retains_three_days_legacy_and_owner_partition(self):
        legacy_id, trip_id, raw = self.saved()
        with TestClient(self.reader()) as client:
            response = client.get('/v6/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar'])
            self.assertEqual(response.status_code, 200, response.text)
            trip = response.json()['trip']
            self.assertEqual(trip['content_sha256'], sha256(raw).hexdigest())
            self.assertEqual(packed(trip['content']), raw)
            self.assertEqual(trip['content']['days'], [{'day_index': 1}, {'day_index': 2}, {'day_index': 3}])
            page = client.get('/v2/trip-structured-list', headers=self.host.headers['calendar']).json()
            self.assertEqual(page['version'], VERSION)
            rows = {r['trip_id']: r for r in page['trips']}
            self.assertEqual(rows[trip_id]['calendar'], {'state': 'undated'})
            self.assertEqual(rows[trip_id]['day_count'], 3)
            self.assertIsNone(rows[legacy_id]['calendar'])
            self.assertIsNone(rows[legacy_id]['day_count'])
            foreign = client.get('/v6/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar-foreign'])
            self.assertEqual(foreign.status_code, 200, foreign.text)
            self.assertIsNone(foreign.json()['trip'])
        old = create_local_structured_read_app(conninfo_path=CONNINFO, auth_dir=self.host.auth,
                                               run_context=self.host.profiles['calendar'][1])
        with TestClient(old) as client:
            unsupported = client.get('/v5/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar'])
            self.assertEqual(unsupported.status_code, 503)
            self.assertNotIn('trip', unsupported.json())
            self.assertEqual(client.get('/v5/trip-structured', params={'trip_id': legacy_id}, headers=self.host.headers['calendar']).status_code, 200)
        with TestClient(self.reader(max_response_bytes=1)) as bounded:
            result = bounded.get('/v6/trip-structured', params={'trip_id': trip_id}, headers=self.host.headers['calendar'])
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(trip_id, result.text)

    def test_revoked_identity_after_encoding_withholds_the_whole_page(self):
        from cj_trip import local_calendar_read as api
        invited = self.host.auth/'invited.json'
        original = invited.read_bytes()
        encode = api.compact

        def revoke(value):
            raw = encode(value)
            if value.get('version') == VERSION:
                invited.write_text(json.dumps([s for s in json.loads(original) if s != 'calendar-revoke']))
            return raw

        try:
            with TestClient(self.reader('calendar-revoke')) as client, patch.object(api, 'compact', revoke):
                response = client.get('/v2/trip-structured-list', headers=self.host.headers['calendar-revoke'])
                self.assertEqual(response.status_code, 503, response.text)
                self.assertNotIn('trips', response.json())
        finally:
            invited.write_bytes(original)


class CalendarPublicationChecks(unittest.TestCase):
    """Real B MESSAGE/NEEDS leases and sole C commit; fixture-only L compiler port."""
    worker = needs_fixture.NeedsActionChecks.worker

    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host = RegisteredHost(cls.auth/'calendar-publication', Path(CONNINFO),
                                 {s: (12, 2, 30000) for s in ('calendar-plan', 'calendar-stale', 'calendar-date',
                                  'calendar-edit', 'calendar-soft', 'calendar-hard', 'calendar-relative',
                                  'calendar-rollback', 'calendar-ack', 'calendar-final', 'calendar-unselected')})
        cls.env = dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1', CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer = ConfirmationSigner(b'synthetic-calendar-publication-key-123456')
        for subject in cls.host.subjects:
            dev_auth.activate_travel(Path(CONNINFO), subject, cls.host.profiles[subject][1], ABI)

    tearDownClass = classmethod(Harness.tearDownClass.__func__)

    def setup(self, subject, *, fixed_date=None, fixed_mutable=False):
        from cj_needs.domain import validate_fields
        fields = deepcopy(json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())['needs_basis']['fields'])
        if fixed_date is not None:
            for edge in ('start', 'end'):
                fields['fixed_items'][0][edge]['date'] = dict(state='known', value=fixed_date)
        if fixed_mutable:
            fields['fixed_items'][0]['locked'] = dict(state='known', value=False)
        validate_fields(fields, complete=True)
        with patch.dict(__import__('os').environ, self.env), self.host.api(subject) as client:
            source = dict(action_id='source-'+subject, needs_id='visit', expected_version=0,
                          source=dict(kind='manual', text='explicit original constraints'), changes=fields)
            saved = client.post('/v1/needs-actions', content=packed(source), headers={
                **self.host.headers[subject], 'Content-Type': 'application/octet-stream'})
            self.assertEqual(saved.status_code, 200, saved.text)
            chat = client.put('/v1/conversations', params={'conversation_id': subject}, headers=self.host.headers[subject]).json()
            message = dict(version='MESSAGE-send.2', conversation_id=subject, message_id='message-'+subject,
                text='Plan Chengdu for 3 days. Day 1 hotel meetup 09:00-10:00. Dates and party size are not set.',
                trip_id=None, creation_intent='consider_trip', expected_generation=chat['generation'], expected_sequence=0,
                travel_context=None, needs_reference=dict(id='visit', expected_version=1))
            result = client.post('/v2/messages', content=json.dumps(message).encode(), headers={
                **self.host.headers[subject], 'Content-Type': 'application/octet-stream'})
            self.assertEqual(result.status_code, 200, result.text)
            return result.json()['receipt']

    def configured(self, subject, *, stale=False, expected_head=None, operation='plan', soft=False):
        from cj_agent.provider import FakeProvider
        from cj_api.local_worker_context import checker_for
        from cj_draft.needs_context import publisher
        from cj_draft.lio_calendar import LioCalendarPublisher
        from cj_draft.calendar_source import CalendarBasis
        from cj_draft.calendar_plan import FIRST_PLAN, REPLAN_DELTA
        from cj_needs.revision_lease import LeaseUnavailable

        class Port:
            valid = True

            def capture(self, binding, message, needs):
                self.stored = message.original_message()
                reference = message.reference.public_value()
                self.reference = {k: reference[k] for k in ('conversation_id', 'generation', 'message_id', 'run_id',
                                                           'sequence', 'input_sha256', 'message_version')}
                self.reference['lio_protocol'] = 'LIO-message.2'  # Fixture L admission, not a native transport claim.
                snapshot, _ = needs.records()
                text = json.loads(self.stored.raw)['text']
                self.day_count = int(re.search(r'for ([0-9]+) days', text)[1])
                self.question = datetime.now(ZoneInfo('Asia/Shanghai')).date()
                dated = re.search(r'\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b', text)
                from datetime import timedelta
                self.start_date = dated[0] if dated else (self.question+timedelta(days=1)).isoformat() if 'tomorrow' in text else None
                self.quote = dated[0] if dated else 'tomorrow' if 'tomorrow' in text else None
                value = dict(version='LIO-fixed-day-bindings.1', needs_id=snapshot.needs_id,
                    needs_version=snapshot.version, needs_content_sha256=sha256(snapshot.content).hexdigest(),
                    reference=self.reference, bindings=[dict(item_id=i['item_id'], day_index=1, end_day_index=1,
                        quote='Day 1', source_reference=self.reference) for i in snapshot.fields.get('fixed_items', ())])
                return CalendarBasis(self.day_count, self.start_date, packed(value))

            @contextmanager
            def hold(self, binding, basis, message):
                self.message, self.binding = message, binding
                yield self

            def check(self):
                self.message.check(self.binding)
                if not self.valid:
                    raise LeaseUnavailable('fixture compiled source revoked during model IO')

            def original(self, reference):
                self.check()
                if reference != self.reference:
                    raise LeaseUnavailable('fixture source reference differs')
                return self.stored, 'LIO-message.2'

            def fixed_day_indices(self, item_id, reference, quote):
                self.check()
                if quote != 'Day 1' or quote not in json.loads(self.stored.raw)['text']:
                    raise LeaseUnavailable('fixture original does not declare an ordinal')
                return 1, 1

            def question_day(self, reference):
                self.original(reference)
                return self.question

            def compiled_date(self, reference, quote, question_day):
                original, _ = self.original(reference)
                if quote not in json.loads(original.raw)['text'] or question_day != self.question:
                    raise LeaseUnavailable('fixture original date source differs')
                return date.fromisoformat(self.start_date)

            def selected_item_ids(self, reference, request_raw):
                original, _ = self.original(reference)
                text = json.loads(original.raw)['text']
                if json.loads(request_raw)['text'] != text or 'Chengdu Museum' not in text:
                    raise LeaseUnavailable('fixture original has no unambiguous named selection')
                return ('museum',)

        port = Port()

        class DayModel(FakeProvider):
            def stream(self, messages, system=None):
                if system is None or FIRST_PLAN not in system and REPLAN_DELTA not in system:
                    yield from super().stream(messages, system)
                    return
                self.calls += 1
                value = dict(version=FIRST_PLAN, title='Chengdu three days', items=[dict(id='museum',
                    text='Chengdu Museum', day_index=2, start_time='13:00', end_time='15:00', timezone='Asia/Shanghai')],
                    proposed_subjects={'museum': ['self']})
                if stale:
                    port.valid = False
                yield json.dumps(value)

        class DateReader:
            calls = 0

            def read(self, *args):
                if operation != 'date':
                    raise AssertionError('undated plan must not read date-dependent evidence')
                self.calls += 1
                document = args[-1]
                checks = [dict(kind=k, state='unknown', day_indices=[d['day_index'] for d in document['days']],
                    item_ids=[], reason='synthetic_provider_has_no_availability', evidence_refs=[])
                    for k in ('weather', 'day_opening')]
                if soft:
                    checks[1].update(state='conflict', reason='synthetic_closure', evidence_refs=['synthetic:closure'])
                return checks

        def original_needs(cursor, binding):
            return cursor.execute('SELECT needs_id,needs_version,content_sha256 FROM cj_message_needs_binding '
                'WHERE message_scope=%s AND message_id=%s AND run_id=%s',
                (binding.scope, binding.message_id, binding.run_id)).fetchone()

        class FixturePublisher(LioCalendarPublisher):
            def publish_for_message(self, *args, before_publish):
                def final(*, check_trip):
                    check_trip()
                    before_publish()  # Original generic worker deadline remains last.
                if operation == 'date':
                    binding, original, current, reply, capture = args
                    trip = self.source.contexts[binding].trip
                    value = dict(version='TRIP-date-convert.1', action_id='date-'+binding.run_id,
                        trip_id=trip.trip_id, expected_version=trip.version, original_hash=sha256(trip.content).hexdigest(),
                        start_date=port.start_date, date_source=dict(reference=port.reference,
                            quote=port.quote, question_day=port.question.isoformat()))
                    self.original_conversion = packed(value)
                    self.date_result = self.convert_for_message(binding, original, current,
                        self.original_conversion, capture, before_publish=final)
                    return self.repository.query_action(value['action_id'])
                if operation == 'edit':
                    from cj_draft.calendar_edit import VERSION
                    binding, original, current, reply, capture = args
                    trip = self.source.contexts[binding].trip
                    base = dict(request_id='replace-'+binding.run_id, trip_id=trip.trip_id,
                        expected_version=trip.version, original_hash=sha256(trip.content).hexdigest())
                    request = packed(dict(version='TRIP-scoped-request.1', **base,
                        text=json.loads(original.raw)['text'], language='en', selection=dict(kind='items', item_ids=['museum'])))
                    edit = packed(dict(version=VERSION, **base, title=None, order=None,
                        changes=[dict(item_id='museum', field='text', value='Renmin Park 人民公园')]))
                    return self.publish_edit_for_message(binding, original, current, request, edit, capture,
                        limits=None, before_publish=final)
                return super().publish_for_message(*args, before_publish=final)

        worker, database = self.worker(subject, DayModel())
        owner = scope_for(ISSUER, subject)
        base = publisher(database, checker_for(self.host.auth), worker.message_context,
                         lambda: self.host.headers[subject]['Authorization'][7:], owner)
        worker.drafts = FixturePublisher(base, self.signer, original_needs,
            lambda binding, original, expected: binding.message_id == 'message-'+subject
                and original.receipt.run_id == binding.run_id and expected == expected_head,
            port, DateReader())
        worker.fixture_database = database
        return worker

    def followup(self, subject, before, text, *, operation='date', soft=False, needs_version=1):
        from cj_trip.lio_history import TripHead
        with patch.dict(__import__('os').environ, self.env), self.host.api(subject) as client:
            chat = client.put('/v1/conversations', params={'conversation_id': subject+'-followup'},
                              headers=self.host.headers[subject]).json()
            value = dict(version='MESSAGE-send.2', conversation_id=subject+'-followup', message_id='follow-'+subject,
                text=text+' Plan Chengdu for 3 days. Day 1 hotel meetup.', trip_id=None,
                creation_intent='consider_trip', expected_generation=chat['generation'], expected_sequence=0,
                travel_context=None, needs_reference=dict(id='visit', expected_version=needs_version))
            result = client.post('/v2/messages', content=packed(value), headers={
                **self.host.headers[subject], 'Content-Type':'application/octet-stream'})
            self.assertEqual(result.status_code, 200, result.text)
        worker = self.configured(subject, expected_head=TripHead.from_trip(before), operation=operation, soft=soft)
        worker.drafts.check_lio_original = lambda binding, original, expected: (
            binding.message_id == value['message_id'] and original.receipt.run_id == binding.run_id
            and expected == TripHead.from_trip(before))
        return worker

    def first_trip(self, subject, **options):
        from cj_trip.lio_history import plan_action_id
        first = self.setup(subject, **options)
        worker = self.configured(subject)
        self.assertEqual(worker.process()[0].status, 'completed')
        receipt = worker.drafts.repository.query_action(plan_action_id(first['run_id']))
        return worker, worker.drafts.repository.detail(receipt.trip_id)

    def undo_host(self, worker):
        from cj_api.local_needs import protected_reader
        from cj_api.local_worker_context import checker_for
        from cj_trip.current_needs_source import CurrentNeedsSource
        from cj_trip.needs_edit_store import NeedsEdits
        checker, database = checker_for(self.host.auth), worker.fixture_database
        worker.drafts.repository.needs_edits = NeedsEdits(CurrentNeedsSource(database, checker,
            worker.drafts.source.token_supplier(), protected_reader(database, checker)))
        return worker.drafts.repository

    def test_undated_named_replacement_and_undo_retains_exact_original(self):
        from cj_trip.calendar_history import CalendarUndo
        from cj_trip.lio_history import edit_action_id
        _, before = self.first_trip('calendar-edit')
        worker = self.followup('calendar-edit', before,
            'Replace Chengdu Museum with Renmin Park 人民公园.', operation='edit')
        outcome = worker.process()[0]
        self.assertEqual(outcome.status, 'completed')
        repository = self.undo_host(worker)
        receipt = repository.query_action(edit_action_id(outcome.run_id))
        self.assertEqual(receipt.committed_version, 2)
        after = repository.detail(before.trip_id)
        document, old = json.loads(after.content), json.loads(before.content)
        expected = deepcopy(old)
        expected['items'][1].update(text='Renmin Park 人民公园', source_category='unknown', evidence=[], source_refs=[], verification='pending')
        self.assertEqual(document, expected)
        request = CalendarUndo.parse(packed(dict(version='TRIP-lio-undo.2', action_id='undo-edit',
            trip_id=before.trip_id, expected_version=2, original_hash=sha256(after.content).hexdigest())))
        self.assertEqual(repository.undo_calendar(request).committed_version, 3)
        self.assertEqual(repository.detail(before.trip_id).content, before.content)

    def test_soft_closure_commits_with_conflict_and_relative_date_keeps_question_day(self):
        for subject, text, soft in (('calendar-soft','Start 2026-12-01.',True), ('calendar-relative','Start tomorrow.',False)):
            _, before = self.first_trip(subject)
            worker = self.followup(subject, before, text, soft=soft)
            self.assertEqual(worker.process()[0].status, 'completed')
            result = worker.drafts.date_result
            self.assertTrue(result['committed'])
            self.assertEqual(bool(result['conflicts']), soft)
            if not soft:
                from datetime import timedelta
                question = json.loads(worker.drafts.original_conversion)['date_source']['question_day']
                self.assertEqual(result['calendar']['start_date'], (date.fromisoformat(question)+timedelta(days=1)).isoformat())

    def test_hard_fixed_date_conflict_retains_version_and_reconciles_original_rejection(self):
        from cj_trip.calendar_conversion import DateConvert
        _, before = self.first_trip('calendar-hard', fixed_date='2026-12-02')
        worker = self.followup('calendar-hard', before, 'Start 2026-12-01.')
        self.assertEqual(worker.process()[0].status, 'completed')
        result = worker.drafts.date_result
        self.assertIs(result['committed'], False)
        self.assertEqual(result['conflicts'][0]['kind'], 'hard_fixed')
        self.assertEqual(worker.drafts.repository.detail(before.trip_id), before)
        self.assertEqual(worker.drafts.repository.calendar_conversion_receipt(DateConvert.parse(worker.drafts.original_conversion)), result)

    def test_date_commit_failure_and_lost_ack_keep_original_action_and_history(self):
        from cj_api.local_app import LocalDatabase
        from cj_trip.calendar_conversion import DateConvert
        for subject in ('calendar-rollback', 'calendar-ack'):
            _, before = self.first_trip(subject)
            worker = self.followup(subject, before, 'Start 2026-12-01.')
            connect = LocalDatabase.connect

            class Cursor:
                def __init__(self, base, connection): self.base, self.connection = base, connection
                def __getattr__(self, name): return getattr(self.base, name)
                def execute(self, query, *args, **kwargs):
                    if query.startswith('INSERT INTO cj_trip_needs_action'):
                        self.connection.saved = True
                        if subject == 'calendar-rollback': raise OSError('synthetic precommit failure')
                    self.base.execute(query, *args, **kwargs)
                    return self

            class Connection:
                def __init__(self, base): self.base, self.saved = base, False
                def __getattr__(self, name): return getattr(self.base, name)
                def __enter__(self): return self.base.__enter__()
                def __exit__(self, *args): return self.base.__exit__(*args)
                def cursor(self, *args, **kwargs): return Cursor(self.base.cursor(*args, **kwargs), self)
                def commit(self):
                    self.base.commit()
                    if self.saved: raise OSError('synthetic ACK loss')

            with patch.object(LocalDatabase, 'connect', lambda database,*a,**k: Connection(connect(database,*a,**k))):
                if subject == 'calendar-rollback':
                    with self.assertRaises(OSError): worker.process()
                else:
                    worker.process()
            repository = worker.drafts.repository
            original = DateConvert.parse(worker.drafts.original_conversion)
            receipt = repository.calendar_conversion_receipt(original)
            if subject == 'calendar-rollback':
                self.assertIsNone(receipt)
                self.assertEqual(repository.detail(before.trip_id), before)
            else:
                self.assertIsNone(worker.drafts.date_result['committed'])
                self.assertEqual(worker.drafts.date_result['outcome'], 'unknown')
                self.assertTrue(receipt['committed'])
                self.assertEqual(repository.detail(before.trip_id).version, 2)
                self.assertEqual(repository.calendar_conversion_receipt(original), receipt)

    def test_final_eligibility_is_required_before_append(self):
        _, before = self.first_trip('calendar-final')
        worker = self.followup('calendar-final', before, 'Start 2026-12-01.')
        original = worker.drafts.convert_for_message
        worker.drafts.convert_for_message = lambda *args, **kwargs: original(*args, before_publish=lambda **kw: None)
        worker.process()
        self.assertEqual(worker.drafts.repository.detail(before.trip_id), before)

    def test_newer_unselected_mutable_needs_cannot_be_restored_by_a_museum_edit(self):
        from cj_trip.lio_history import edit_action_id
        subject = 'calendar-unselected'
        _, before = self.first_trip(subject, fixed_mutable=True)
        fields = deepcopy(json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())['needs_basis']['fields'])
        fixed = fields['fixed_items']
        fixed[0]['locked'] = dict(state='known', value=False)
        fixed[0]['start']['time'] = dict(state='known', value='11:00')
        fixed[0]['end']['time'] = dict(state='known', value='12:00')
        with patch.dict(__import__('os').environ, self.env), self.host.api(subject) as client:
            response = client.post('/v1/needs-actions', content=packed(dict(action_id='correct-unselected',
                needs_id='visit', expected_version=1, source=dict(kind='manual',text='Hotel is now 11 to 12'),
                changes=dict(fixed_items=fixed))), headers={**self.host.headers[subject],
                                                          'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code, 200, response.text)
        worker = self.followup(subject, before, 'Replace Chengdu Museum with Renmin Park 人民公园.',
                               operation='edit', needs_version=2)
        with self.assertRaisesRegex(Conflict, 'current NEEDS/protected constraints rejected'):
            worker.process()
        repository = worker.drafts.repository
        stored = worker.messages.query('follow-'+subject)
        self.assertIsNone(repository.query_action(edit_action_id(stored.receipt.run_id)))
        self.assertEqual(repository.detail(before.trip_id), before)

    def test_actual_worker_saves_undated_formal_trip_without_party_or_date(self):
        from cj_trip.lio_history import plan_action_id
        message = self.setup('calendar-plan')
        worker = self.configured('calendar-plan')
        outcome = worker.process()[0]
        self.assertEqual(outcome.status, 'completed')
        receipt = worker.drafts.repository.query_action(plan_action_id(message['run_id']))
        self.assertIsNotNone(receipt)
        document = json.loads(worker.drafts.repository.detail(receipt.trip_id).content)
        self.assertEqual(document['calendar'], {'state': 'undated'})
        self.assertEqual(len(document['days']), 3)
        self.assertEqual(document['items'][0]['fixed'], {'state': 'known', 'value': True})
        self.assertEqual(document['items'][0]['schedule']['start']['time'], {'state': 'known', 'value': '09:00'})
        self.assertEqual(document['date_checks'][0]['state'], 'not_checked')

    def test_source_withdrawn_during_model_io_cannot_publish(self):
        from cj_trip.lio_history import plan_action_id
        message = self.setup('calendar-stale')
        worker = self.configured('calendar-stale', stale=True)
        outcome = worker.process()[0]
        self.assertNotEqual(outcome.status, 'completed')
        self.assertIsNone(worker.drafts.repository.query_action(plan_action_id(message['run_id'])))
        self.assertEqual(worker.drafts.repository.list_trips(), [])

    def test_absolute_date_appends_same_trip_and_original_receipt_is_reconciled(self):
        from cj_trip.lio_history import plan_action_id, TripHead
        from cj_trip.calendar_conversion import DateConvert
        subject = 'calendar-date'
        first = self.setup(subject)
        original_worker = self.configured(subject)
        self.assertEqual(original_worker.process()[0].status, 'completed')
        first_receipt = original_worker.drafts.repository.query_action(plan_action_id(first['run_id']))
        before = original_worker.drafts.repository.detail(first_receipt.trip_id)
        with patch.dict(__import__('os').environ, self.env), self.host.api(subject) as client:
            chat = client.put('/v1/conversations', params={'conversation_id': subject+'-date'},
                              headers=self.host.headers[subject]).json()
            value = dict(version='MESSAGE-send.2', conversation_id=subject+'-date', message_id='message-'+subject,
                text='Start 2026-12-01. Plan Chengdu for 3 days. Day 1 hotel meetup 09:00-10:00.', trip_id=None,
                creation_intent='consider_trip', expected_generation=chat['generation'], expected_sequence=0,
                travel_context=None, needs_reference=dict(id='visit', expected_version=1))
            # The MID must be new; fixture admission receives that exact original.
            value['message_id'] += '-date'
            response = client.post('/v2/messages', content=packed(value), headers={
                **self.host.headers[subject], 'Content-Type': 'application/octet-stream'})
            self.assertEqual(response.status_code, 200, response.text)
        worker = self.configured(subject, expected_head=TripHead.from_trip(before), operation='date')
        # The stand-in L admission is per original accepted MID, not a model value.
        worker.drafts.check_lio_original = lambda binding, original, expected: (
            binding.message_id == value['message_id'] and original.receipt.run_id == binding.run_id
            and expected == TripHead.from_trip(before))
        outcome = worker.process()[0]
        self.assertEqual(outcome.status, 'completed')
        result = worker.drafts.date_result
        self.assertTrue(result['committed'])
        self.assertEqual((result['trip_id'], result['trip_version']), (before.trip_id, 2))
        after = worker.drafts.repository.detail(before.trip_id)
        document = json.loads(after.content)
        self.assertEqual([d['date'] for d in document['days']], ['2026-12-01', '2026-12-02', '2026-12-03'])
        self.assertEqual(document['items'], json.loads(before.content)['items'])
        self.assertEqual(document['sources'], json.loads(before.content)['sources'])
        request = DateConvert.parse(worker.drafts.original_conversion)
        self.assertEqual(worker.drafts.repository.calendar_conversion_receipt(request), result)
        self.assertEqual(worker.drafts.date_reader.calls, 1)
        from cj_api.local_needs import protected_reader
        from cj_api.local_worker_context import checker_for
        from cj_trip.current_needs_source import CurrentNeedsSource
        from cj_trip.needs_edit_store import NeedsEdits
        from cj_trip.calendar_history import CalendarUndo
        checker = checker_for(self.host.auth)
        database = worker.fixture_database
        token = self.host.headers[subject]['Authorization'][7:]
        repository = worker.drafts.repository
        repository.needs_edits = NeedsEdits(CurrentNeedsSource(database, checker, token,
                                                             protected_reader(database, checker)))
        undo = CalendarUndo.parse(packed(dict(version='TRIP-lio-undo.2', action_id='calendar-date-undo',
            trip_id=after.trip_id, expected_version=2, original_hash=sha256(after.content).hexdigest())))
        self.assertEqual(repository.undo_calendar(undo).committed_version, 3)
        self.assertEqual(repository.detail(after.trip_id).content, before.content)
        self.assertEqual(repository.undo_calendar(undo).committed_version, 3)
        self.assertEqual([t.version for t in repository.lio_revisions(after.trip_id, None, 10)], [3, 2, 1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
