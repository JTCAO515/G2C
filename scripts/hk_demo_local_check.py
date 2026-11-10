"""Private PostgreSQL and real JWT/Unix socket; no external model or account."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,NoEncryption,PrivateFormat,PublicFormat
from fastapi.testclient import TestClient
from cj_api.local_app import ISSUER,LocalDatabase,create_local_app,scope_for
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider, ProviderFailed, ProviderUnknown
from cj_api.local_run_context import load_run_context
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.travel import ABI
from deploy.hk import checkpoint,demo_accounts,demo_login,demo_schema,schema,staging
from deploy.hk.configuration import Runtime,demo_periods
from cj_run.step_usage import ledger_scope_for
from cj_usage.authorization_budget import DEADLINE,DEMO_DEADLINE
import dev_auth
import local_run_context
import migrate
import pg_suites
import run_worker

SUBJECT='m4-synthetic-demo-0123456789ab'
CODE='D1-0123456789ab.'+'x'*22
NEW_CODE='D1-0123456789ab.'+'y'*22


def digest(code):return hashlib.sha256(code.encode('ascii')).hexdigest()


def verify_upgrade(root, blueprint, target):
    root.mkdir(mode=0o700)
    schema_root=root/'schema'
    schema.generate(blueprint,schema_root)
    control=root/'upgrade-control'
    backups=root/'upgrade-backups'
    backups.mkdir(mode=0o700)
    prior=backups/'previous'
    prior.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    env=dict(CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',
        CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())
    with pg_suites.cluster('demo-upgrade',port=55650,role='cj_demo_upgrade',root=root/'old',socket=root/'old-s') as config:
        with psycopg.connect(**config,autocommit=True) as db:
            migrate.up(db,migrate.load(),target-1)
            original=checkpoint.local.fence_state(db)

        @contextmanager
        def operator():
            with psycopg.connect(**config,autocommit=True) as db:
                yield db,config

        with patch.dict(os.environ,env),patch.object(checkpoint,'operator',operator),                patch.object(staging,'PG17',pg_suites.bindir()):
            with patch.object(checkpoint,'versions',return_value=list(range(1,target))):
                checkpoint.bootstrap(control,lambda _:None)
            old=checkpoint.verified(control/'release.json')
            checkpoint.atomic(control/'b2.json',dict(version='g2c-hk-local.1',state='FORWARD_ONLY'))
            checkpoint.atomic(prior/'manifest.json',dict(schema=list(range(1,target)),
                lineage=old['lineage'],fences=original))
            demo_schema.upgrade(control,backups,target=target,schema_root=schema_root)
            base=demo_schema.daily_base(control,backups,'previous')
            assert base==backups/f'demo-schema{target}'
            result=checkpoint.verified(base/'manifest.json')
            assert result['fences']==original and result['lineage']==old['lineage']
            with operator() as (db,_):
                checkpoint.require_release(db,control)
            try:
                demo_schema.upgrade(control,backups,target=target,schema_root=schema_root)
            except ValueError as exc:
                assert 'reconcile original' in str(exc)
            else:
                raise AssertionError('schema upgrade accepted a second application')


def check_lio(api, database, auth, other, headers, conninfo, memory):
    from cj_api.local_lio_planning import LioPlanning, SYSTEM
    from cj_draft.lio_plan import LioPlanPublisher
    from cj_draft.needs_publisher import SYSTEM as PLAN_SYSTEM
    from cj_message import demo_dialogue
    from cj_message.domain import CommitUnknown
    from cj_message.lio_context import LioCitation, LioToolProgress
    from cj_message.lio_plan_needs import original_needs
    from cj_run.core import Binding, ResyncRequired
    from cj_trip.confirmation import ConfirmationSigner
    from cj_trip.domain import CommitUnknown as TripCommitUnknown
    from cj_api.lio_planning_grounding import grounded_fields, planning_authority_complete, stated_city
    from datetime import date
    fixed_words = 'The hotel meetup from 9 to 10 a.m. on the first day is fixed'
    sample = f'Plan three days in Beijing for two people starting tomorrow. {fixed_words}.'
    today = date(2026, 11, 9)
    grounded, missing = grounded_fields((sample,), 'Beijing', today)
    assert not missing and len(grounded['fixed_items']) == 1
    assert grounded['arrival']['date']['value'] == '2026-11-10'
    assert grounded['departure']['date']['value'] == '2026-11-12'
    assert grounded['fixed_items'][0]['start']['time']['value'] == '09:00'
    assert grounded['fixed_items'][0]['booking_status'] == {'state':'unknown'}
    english = ('Plan a three-day trip to Beijing.', 'Starting tomorrow.')
    from_tomorrow = ('Plan a trip to Beijing.', 'From tomorrow, for three days.')
    chinese_reply = ('帮我规划三天的北京行程。', '北京，从明天开始，玩三天。')
    for turns, city in ((english, 'Beijing'), (from_tomorrow, 'Beijing'), (chinese_reply, '北京')):
        assert stated_city(turns, city)
        reply_fields, _ = grounded_fields(turns, city, today)
        assert reply_fields['arrival']['date']['value'] == '2026-11-10'
        assert reply_fields['departure']['date']['value'] == '2026-11-12'
    one_turn, _ = grounded_fields(
        ('Plan a trip to Beijing for three days starting tomorrow.',), 'Beijing', today)
    assert one_turn['departure']['date']['value'] == '2026-11-12'
    changed_city, _ = grounded_fields(
        ('Plan a trip to Shanghai from 2026-12-01 to 2026-12-03.',
         'Beijing, from 2026-12-11 to 2026-12-13.'), 'Beijing', today)
    assert changed_city['arrival']['date']['value'] == '2026-12-11'
    assert changed_city['departure']['date']['value'] == '2026-12-13'
    unstated, _ = grounded_fields(
        ('Plan a trip to Shanghai from 2026-12-01 to 2026-12-03.',
         '2026-12-04 to 2026-12-06.', 'Beijing.'), 'Beijing', today)
    assert unstated['arrival']['date']['state'] == 'missing'
    separate_clauses, _ = grounded_fields(
        ('Plan a trip to Shanghai from 2026-12-01 to 2026-12-03. Plan a Beijing itinerary.',), 'Beijing', today)
    assert separate_clauses['arrival']['date']['state'] == 'missing'
    attributed_dates, _ = grounded_fields((
        'Plan a Beijing itinerary. Trip dates from 2026-12-01 to 2026-12-03 are for Shanghai only.',
    ), 'Beijing', today)
    assert attributed_dates['arrival']['date']['state'] == 'missing'
    affirmed_dates, _ = grounded_fields(
        ('Plan a trip to Beijing from 2026-12-01 to 2026-12-03 and save it to my account.',), 'Beijing', today)
    assert affirmed_dates['arrival']['date']['value'] == '2026-12-01'
    unrelated, _ = grounded_fields(
        ('Plan a trip to Beijing starting tomorrow, but we have a 7 day Shanghai trip later.',), 'Beijing', today)
    assert unrelated['departure']['date']['state'] == 'missing'
    tickets, missing = grounded_fields(
        ('Plan a trip to Beijing from 2026-12-01 to 2026-12-03. '
         'We have tickets for a museum on 2026-12-02 from 09:00 to 11:00.',), 'Beijing', today)
    assert not missing and tickets['fixed_items'][0]['locked'] == dict(state='known',value=True)
    negative = 'We have not actually booked a hotel for the first day 09:00 to 10:00.'
    unconfirmed, _ = grounded_fields((negative,), 'Beijing', today)
    assert 'fixed_items' not in unconfirmed
    rejected_dates, _ = grounded_fields(
        ('I cannot travel on 2026-11-10. Travel from 2026-11-11 to 2026-11-12.',), 'Beijing', today)
    assert rejected_dates['arrival']['date']['value'] == '2026-11-11'
    foreign_appointment, missing = grounded_fields(
        ('My daughter has an already booked appointment on 2026-11-11 from 09:00 to 10:00.',),
        'Beijing', today)
    assert missing and 'fixed_items' not in foreign_appointment
    assert not stated_city(('Plan a trip from Beijing to Shanghai.',), 'Beijing')
    assert not stated_city(('Plan a trip to Shanghai. I live in Beijing.',), 'Beijing')
    assert not stated_city(('Plan a trip to Shanghai with a short visit to Beijing.',), 'Beijing')
    assert not stated_city(('帮我规划上海行程，途经北京，从 2026-11-11 到 2026-11-12',
                            '2026-11-11 到 2026-11-12'), '北京')
    for turns, city in (
        (('Plan a trip to Beijing starting tomorrow for three days, but those dates are for Shanghai only.',), 'Beijing'),
        (('帮我规划从明天开始的北京三天行程，但明天是上海的出发日。',), '北京'),
        (('Plan a three-day trip to Beijing.', 'Starting tomorrow?'), 'Beijing'),
        (('Plan a Beijing itinerary.', 'Travel from 2026-11-11 to 2026-11-12?'), 'Beijing'),
        (('Plan a trip to Beijing starting tomorrow for three days. Those dates are for Shanghai only.',), 'Beijing'),
        (('Plan a trip to Beijing from 2026-11-11 to 2026-11-12. Those dates apply only to Shanghai.',), 'Beijing'),
        (('帮我规划从明天开始的北京三天行程。明天是上海的出发日。',), '北京'),
        (('Plan a three-day trip to Beijing. Those dates are for Shanghai only.', 'Starting tomorrow.'), 'Beijing'),
    ):
        tentative, _ = grounded_fields(turns, city, today)
        assert tentative['arrival']['date']['state'] == 'missing', turns
        assert tentative['departure']['date']['state'] == 'missing', turns
    polite, _ = grounded_fields(('Could you plan a trip to Beijing starting tomorrow for three days?',),
                                'Beijing', today)
    assert polite['departure']['date']['value'] == '2026-11-12'
    assert planning_authority_complete(('Could you plan a trip to Beijing starting tomorrow for three days?',),
                                       'Beijing', today, has_fixed=False)
    for scope_clause in ('Those are Shanghai dates only.', 'Tomorrow is the departure day for Shanghai only.',
                         'Please put everything on hold.'):
        assert not planning_authority_complete((
            'Plan a trip to Beijing from 2026-11-11 to 2026-11-12. ' + scope_clause,
        ), 'Beijing', today, has_fixed=False)
    for tail in (', but please put this on hold.', ', but those are Shanghai dates only.'):
        assert not planning_authority_complete((sample[:-1] + tail,), 'Beijing', today, has_fixed=True)
    assert planning_authority_complete((sample,), 'Beijing', today, has_fixed=True)
    for qualifier in ('Those dates still need approval and are for Beijing.',
                      'Those dates are tentative but are for Beijing.'):
        assert not planning_authority_complete((
            'Plan a trip to Beijing from 2026-11-11 to 2026-11-12. ' + qualifier,
        ), 'Beijing', today, has_fixed=False)
    for timed in ('Plan only a preview of the trip to Beijing from 2026-11-11 to 2026-11-12.',
                  'Plan an unsaved trip to Beijing from 2026-11-11 to 2026-11-12.'):
        assert not planning_authority_complete((timed,), 'Beijing', today, has_fixed=False)
    for prefix in ('Those are Shanghai dates only, and ', 'This is just a hypothetical and '):
        joined = 'Plan a trip to Beijing from 2026-11-11 to 2026-11-12 for two people. ' + prefix + fixed_words + '.'
        assert not planning_authority_complete((joined,), 'Beijing', today, has_fixed=True)
    assert not planning_authority_complete((
        'Plan a trip to Shanghai from 2026-12-01 to 2026-12-03.',
        'Please put this on hold. Beijing, from 2026-12-11 to 2026-12-13.',
    ), 'Beijing', today, has_fixed=False)
    meetings, _ = grounded_fields(('The trip dates are undecided. The meeting is from 2026-11-11 to 2026-11-12.',),
                                   'Beijing', today)
    assert meetings['arrival']['date']['state'] == 'missing'
    suggested, _ = grounded_fields(('Plan a trip to Beijing and suggest dates around my meeting from 2026-11-11 to 2026-11-12.',),
                                    'Beijing', today)
    assert suggested['arrival']['date']['state'] == 'missing'
    conference, _ = grounded_fields((
        'Plan a trip to Beijing around my conference in Beijing from 2026-11-11 to 2026-11-12. When should I travel?',
    ), 'Beijing', today)
    assert conference['arrival']['date']['state'] == 'missing'
    hypothetical, _ = grounded_fields(('If I have already booked a hotel meetup from 09:00 to 10:00 on the first day.',),
                                       'Beijing', today)
    assert 'fixed_items' not in hypothetical
    supposed, _ = grounded_fields(('Suppose we have already booked a hotel meetup from 09:00 to 10:00 on the first day.',
        'For everyone, on the first day from 09:00 to 10:00.'), 'Beijing', today)
    assert 'fixed_items' not in supposed
    filled, missing = grounded_fields(('Plan a trip to Beijing from 2026-11-11 to 2026-11-12. The hotel meetup is fixed.',
        'For everyone, on the first day from 09:00 to 10:00.'), 'Beijing', today)
    assert not missing and filled['fixed_items'][0]['applies_to'] == ['party']
    dated, missing = grounded_fields(('Plan a trip to Beijing from 2026-11-11 to 2026-11-12. The hotel meetup is fixed.',
        'For everyone, on 2026-11-12 from 09:00 to 10:00.'), 'Beijing', today)
    assert not missing and dated['fixed_items'][0]['start']['date']['value'] == '2026-11-12'
    chinese = '帮我为两个人规划从明天开始的北京三天游，第一天 9:00–10:00 的酒店集合已经定好。'
    zh, missing = grounded_fields((chinese,), '北京', today)
    assert not missing and zh['departure']['date']['value'] == '2026-11-12'

    messages = '/v1/lio/messages'
    timeline = '/v1/lio/timeline'
    scope = scope_for(ISSUER, other)
    owner = {**headers, 'Authorization': 'Bearer ' + dev_auth.token(auth, other, 300)}
    legacy_only = {**headers, 'Authorization': 'Bearer ' + dev_auth.token(auth, 'legacy-dialogue-only', 300)}
    assert api.get(timeline, headers=legacy_only).status_code == 403
    assert api.get(timeline, headers=owner).json() == dict(
        version='LIO-timeline.1', conversation_id=None, messages=[], next_before=None)

    def original(mid, text, locale, **extra):
        return json.dumps(dict(version='LIO-message.1', message_id=mid, text=text,
                               locale=locale, **extra), ensure_ascii=False).encode()

    raw = original('lio-first', '北京有哪些公园？', 'zh')
    assert api.post('/v1/demo-dialogue/messages', content=raw, headers=owner).status_code == 400
    foreign_chat = original('lio-invalid-first', 'Hello', 'en', conversation_id='lio-dialogue-'+'0'*32)
    assert api.post(messages, content=foreign_chat, headers=owner).status_code == 400
    with psycopg.connect(**conninfo) as db:
        assert db.execute('SELECT 1 FROM cj_run_scope WHERE scope=%s', (scope,)).fetchone() is None
    receive = demo_dialogue._receive

    def lose_commit_ack(service, command, *, prepare_scope):
        receive(service, command, prepare_scope=prepare_scope)
        raise CommitUnknown()

    with patch.object(demo_dialogue, '_receive', side_effect=lose_commit_ack):
        first = api.post(messages, content=raw, headers=owner)
    assert first.status_code == 200, first.text
    assert api.post(messages, content=raw, headers=owner).json() == first.json()
    assert api.get('/v1/demo-dialogue/messages', params=dict(message_id='lio-first'),
                   headers=owner).json()['receipt'] is None
    assert api.post(messages, content=raw+b' ', headers=owner).status_code == 409
    assert set(first.json()) == {'version', 'message_id', 'conversation_id'}
    conversation = first.json()['conversation_id']
    assert api.get(timeline, params=dict(conversation_id=conversation), headers=headers).status_code == 400
    assert api.get(timeline, headers=headers).json()['messages'] == []
    assert api.post(messages, content=original('lio-owner-check','Hello','en',
        conversation_id=conversation), headers=headers).status_code == 400
    second = api.post(messages, content=original('lio-second','What should I see in Beijing?','en',
        conversation_id=conversation), headers=owner)
    assert second.status_code == 200 and second.json()['conversation_id'] == conversation
    pending_response = api.get(timeline, headers=owner)
    assert pending_response.status_code == 200, pending_response.text
    pending = pending_response.json()['messages']
    assert [entry['status'] for entry in pending] == ['sending', 'sending']
    assert [entry['message_id'] for entry in pending] == ['lio-first', 'lio-second']
    prompts = []
    class LioModel(FakeProvider):
        def stream(self, messages, system=None):
            self.calls += 1
            prompts.append(system)
            if system.startswith(SYSTEM):
                fields = {}
                city = None
                if len(messages) == 2:
                    assert messages[0]['content'] == '帮我规划旅行'
                    assert messages[1]['content'] == '北京，2026-11-11 到 2026-11-12'
                if '2026-11-11' in messages[-1]['content']:
                    city = '北京' if '北京' in messages[-1]['content'] else 'Beijing'
                    for edge, day in (('arrival','2026-11-11'), ('departure','2026-11-12')):
                        fields[edge] = dict(date=dict(state='known', value=day), time=dict(state='missing'),
                                            timezone=dict(state='missing'), place=dict(state='missing'))
                yield json.dumps(dict(city=city, continues_trip=True, extraction=dict(
                    version='NEEDS-extraction.1', fields=fields, unresolved=[], long_term_requests=[])),
                    ensure_ascii=False)
                return
            if system.startswith(PLAN_SYSTEM):
                source = json.loads(messages[-1]['content'])
                before = source['current_trip']
                title = 'Beijing walk' if before is None else 'Beijing walks'
                if before is None:
                    def at(clock):
                        return dict(date=dict(state='known', value='2026-11-11'),
                                    time=dict(state='known', value=clock),
                                    timezone=dict(state='known', value='Asia/Shanghai'),
                                    utc_offset=dict(state='unknown'))
                    items = [dict(id='park', text='Park walk', verification='pending', evidence=[],
                                  schedule=dict(start=at('09:00'), end=at('10:00')),
                                  fixed=dict(state='unknown'), source_category='unknown', source_refs=[])]
                    subjects = {'park':['party']}
                else:
                    items = before['content']['items']
                    subjects = {}
                yield json.dumps(dict(version='TRIP-model-plan.1', title=title, items=items,
                                      proposed_subjects=subjects))
                return
            if messages[-1]['content'] == 'Synthetic lost model outcome':
                raise ProviderUnknown()
            yield '北京有许多适合散步的公园。' if system.endswith('Reply in Chinese.') else 'Beijing has many parks for walking.'

    model = LioModel()
    worker = run_worker._worker_for_scope(database, model, auth, scope, checker_for(auth),
                                         demo_planning=True)
    assert [outcome.status for outcome in worker.process()] == ['completed', 'completed']
    ready = api.get(timeline, headers=owner).json()['messages']
    assert [entry['status'] for entry in ready] == ['completed', 'completed']
    assert model.calls == 2 and all(entry['answer'] and entry['failure'] is None for entry in ready)
    assert prompts[0].endswith('Reply in Chinese.') and prompts[1].endswith('Reply in English.')
    assert all(prompt.startswith('You are Lio, a lion-dance mascot') for prompt in prompts)
    assert all(set(entry) == {'message_id','text','answer','status','failure','activity','sources','trip','memory'} for entry in ready)
    assert api.get(timeline, params=dict(before='lio-second'), headers=owner).json()['messages'] == ready[:1]
    assert api.get(timeline, params=dict(before='first'), headers=owner).status_code == 400
    unknown = original('lio-unknown', 'Synthetic lost model outcome', 'en')
    accepted = api.post(messages, content=unknown, headers=owner)
    assert accepted.status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['unknown']
    for _ in range(2):
        failed = api.get(timeline, headers=owner).json()['messages'][-1]
        assert (failed['status'], failed['failure']) == ('failed', 'unavailable')
    assert api.post(messages, content=unknown, headers=owner).json() == accepted.json()
    assert worker.process() == [] and model.calls == 3
    assert api.post(messages, content=original('lio-followup', 'Any nearby museums?', 'en'),
                    headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    assert model.calls == 4

    class ObservedTools:
        def answer(self, worker, binding, messages, *, lio_locale):
            assert lio_locale == 'en'
            yield LioToolProgress('tool.0.0', 'checking_places')
            with database.run_repository(scope).transaction():
                response = api.get(timeline, headers=owner)
                assert response.status_code == 200, response.text
                active = response.json()['messages'][-1]
                assert (active['status'], active['activity']) == ('answering', 'checking_places')
            yield LioToolProgress('tool.0.0', None)
            yield LioCitation('tool.0.0', 'Synthetic place evidence',
                              'https://example.test/place', '2026-11-09T12:00:00+00:00')
            yield 'There is a park nearby.'

    worker.tools = ObservedTools()
    assert api.post(messages, content=original('lio-with-source', 'Find a park nearby', 'en'),
                    headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    sourced = api.get(timeline, headers=owner).json()['messages'][-1]
    assert sourced['activity'] is None and sourced['sources'] == [dict(
        title='Synthetic place evidence', url='https://example.test/place',
        observed_at='2026-11-09T12:00:00+00:00')]
    worker.tools = None
    with psycopg.connect(**conninfo) as db:
        generation, run_id, sequence = db.execute(
            'UPDATE cj_run_record SET expires_at=clock_timestamp()-interval \'1 second\' '
            'WHERE scope=%s AND message_id=%s RETURNING generation,run_id,message_sequence',
            (scope, 'lio-first')).fetchone()
    binding = Binding(scope, conversation, generation, 'lio-first', run_id, sequence)
    try:
        database.run_repository(scope).snapshot_optional(binding)
    except ResyncRequired:
        pass
    else:
        raise AssertionError('retained display relaxed the original operational recovery deadline')
    assert api.get(timeline, headers=owner).json()['messages'][0] == ready[0]

    no_signer = original('lio-no-signer', 'Plan a trip to Beijing from 2026-11-11 to 2026-11-12.', 'en')
    assert api.post(messages, content=no_signer, headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    no_save = api.get(timeline, headers=owner).json()['messages'][-1]
    assert no_save['status'] == 'completed' and no_save['answer'] and no_save['trip'] is None

    seen = []
    def validate_intake(worker, plan, state, details, locale):
        with database.connect(scope) as connection:
            with connection.cursor() as cursor:
                needs_id, revision, digest = original_needs(cursor, plan)
                assert len(digest) == 64
                assert original_needs(cursor, binding) is None
                seen.append((needs_id, revision, details.city, locale))
        # This tests the B admission and intake boundary in isolation.
        # An unavailable save must never look like a completed trip.
        raise ProviderFailed('synthetic C save unavailable')

    worker = run_worker._worker_for_scope(database, model, auth, scope, checker_for(auth),
                                         memory_configuration=memory, demo_planning=True)
    worker.lio_planning = LioPlanning(database, validate_intake)
    assert api.post(messages, content=original('lio-plan-ask', '帮我规划旅行', 'zh'),
                    headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    ask = api.get(timeline, headers=owner).json()['messages'][-1]
    assert '哪座城市' in ask['answer'] and '几天' in ask['answer'] and ask['trip'] is None
    assert not seen
    reply = original('lio-plan-detail', '北京，2026-11-11 到 2026-11-12', 'zh')
    assert api.post(messages, content=reply, headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['failed']
    assert len(seen) == 1 and seen[0][1:] == (1, '北京', 'zh')
    unavailable = api.get(timeline, headers=owner).json()['messages'][-1]
    assert (unavailable['status'], unavailable['failure'], unavailable['trip']) == ('failed', 'unavailable', None)
    assert api.post(messages, content=reply, headers=owner).status_code == 200
    assert worker.process() == [] and len(seen) == 1

    confirmation = ConfirmationSigner((auth/'trip-confirmation.key').read_bytes())
    worker = run_worker._worker_for_scope(database, model, auth, scope, checker_for(auth),
                                         memory_configuration=memory, draft_profile='needs-structured.1', demo_planning=True,
                                         lio_confirmation=confirmation)
    request = 'Plan a trip to Beijing from 2026-11-11 to 2026-11-12 for our party.'
    assert api.post(messages, content=original('lio-save', request, 'en'), headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    saved = api.get(timeline, headers=owner).json()['messages'][-1]
    assert saved['status'] == 'completed' and saved['answer'] == 'I saved your itinerary.', saved
    assert saved['trip']['title'] == 'Beijing walk'
    # PR725 makes a newly generated suggestion editable.
    assert saved['trip']['days'][0]['items'][0]['fixed'] is False

    commit_plan = LioPlanPublisher._commit
    def lose_save_ack(publisher, *args):
        commit_plan(publisher, *args)
        raise TripCommitUnknown()

    change = original('lio-save-without-ack', request, 'en')
    assert api.post(messages, content=change, headers=owner).status_code == 200
    with patch.object(LioPlanPublisher, '_commit', lose_save_ack):
        assert [outcome.status for outcome in worker.process()] == ['unknown']
    cards = api.get(timeline, headers=owner).json()['messages'][-2:]
    assert cards[0] == saved
    assert cards[1]['status'] == 'completed' and cards[1]['failure'] is None, cards[1]
    assert cards[1]['trip']['trip_id'] == saved['trip']['trip_id']
    assert cards[1]['trip']['title'] == 'Beijing walks'
    assert api.post(messages, content=change, headers=owner).status_code == 200
    assert worker.process() == []
    withdrawals = ('Do not save it.', "Please don't save it yet.", 'Show me a draft without saving.',
                   "Please don't save this itinerary to my account.", 'I do not want this itinerary saved.',
                   'Can you show me before saving?', 'Cancel it.', 'Actually, cancel it.',
                   'Please leave it as a draft.', 'Please cancel this request.', 'Please put this on hold.', '取消吧。', '请不要把行程保存到我的账户。')
    for i, withdrawal in enumerate(withdrawals):
        assert api.post(messages, headers=owner, content=original(
            f'lio-withdrawal-{i}', 'Plan a trip to Beijing from 2026-12-01 to 2026-12-03. ' + withdrawal, 'en')).status_code == 200
        calls = model.calls
        assert [outcome.status for outcome in worker.process()] == ['completed'] and model.calls == calls
        canceled = api.get(timeline, headers=owner).json()['messages'][-1]
        assert canceled['trip'] is None and "won't save" in canceled['answer']
    assert api.post(messages, headers=owner, content=original(
        'lio-withdrawal-intake', '帮我规划旅行', 'zh')).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    assert api.post(messages, headers=owner, content=original(
        'lio-withdrawal-reply', '北京。算了，不要保存。', 'zh')).status_code == 200
    calls = model.calls
    assert [outcome.status for outcome in worker.process()] == ['completed'] and model.calls == calls
    canceled = api.get(timeline, headers=owner).json()['messages'][-1]
    assert canceled['trip'] is None and '不保存' in canceled['answer']
    with psycopg.connect(**conninfo) as db:
        try:
            with db.transaction():
                migrate.down(db, migrate.load(), 50)
        except psycopg.errors.RaiseException as exc:
            assert 'Lio dialogue originals must be preserved' in str(exc)
        else:
            raise AssertionError('migration down erased Lio originals')
    print('PASS signed Lio timeline, bilingual one-chat replay, ACK recovery, and retained display')


def exercise(root,conninfo):
    auth=root/'auth'
    other='other-dialogue-owner'
    dev_auth.init(auth,[SUBJECT,other,'invited-outside-dialogue','legacy-dialogue-only'])
    path=root/'conn.json'
    path.write_text(json.dumps(conninfo))
    now=int(time.time())
    context_path=root/'meter.json'
    context_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',
        budget=100,period_start=now-60,period_end=int(DEADLINE.timestamp()),max_steps=8,max_tools=2,max_output=60000,max_seconds=600),
        output_limits=dict(model=4000,tool=2000,memory=1000)),history=[])))
    context=load_run_context(context_path)
    _,following=demo_periods(context,now)
    assert demo_periods(context,int(DEADLINE.timestamp()))==(following,None)
    assert following.history==(context.current,) and following.current.meter.period_end==int(DEMO_DEADLINE.timestamp())
    database=LocalDatabase(path,run_context=context,travel_context=True,needs_context=True)
    profile=dict(subjects=['self'],slots={'quiet.entrance':dict(kind='preference',collection_allowed=True,
        semantic_resolved=True)},extents=['long_term'],context_ids=[])
    collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={SUBJECT:profile,other:profile}),
        travel_contexts={SUBJECT:[],other:[]})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=collection,
        selections={subject:dict(subject='self',slots=['quiet.entrance'],max_bytes=1000)
                    for subject in (SUBJECT,other)})).encode())
    runtime=Runtime(auth,context,context_path,[],memory_runtime=memory,subjects=frozenset({SUBJECT}),
        demo_subjects=frozenset({SUBJECT}),demo_next_context=following)
    runtime._database=database
    control=root/'control';operation=root/'operation';operation.mkdir(mode=0o700)
    endpoint=root/'signer';endpoint.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    env=dict(CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',
        CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',CJ_BETA_DEMO_SUBJECTS_JSON=json.dumps([SUBJECT]),
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())

    @contextmanager
    def operator():
        with psycopg.connect(**conninfo,autocommit=True) as connection:
            yield connection,conninfo

    with patch.dict(os.environ,env),patch.object(checkpoint,'operator',operator),patch.object(demo_login,'SOCKET',endpoint/'login.sock'):
        checkpoint.bootstrap(control,lambda _:None)
        expiry=datetime.now(timezone.utc)+timedelta(hours=1)
        assert demo_accounts.manage(runtime,'bootstrap',SUBJECT,control,operation,(digest(CODE),expiry))=='bootstrapped'
        assert demo_accounts.manage(runtime,'insert',SUBJECT,control,operation)=='activated'
        assert demo_accounts.manage(runtime,'insert',SUBJECT,control,operation)=='existing'
        local_run_context.provision_budget(path,context,other)
        dev_auth.activate_travel(path,other,context,ABI)
        app=create_local_app(conninfo_path=None,auth_dir=auth,run_context=context,database=database,account_admission=True,
            demo_dialogue_subjects=frozenset({SUBJECT,other,'legacy-dialogue-only'}),
            lio_dialogue_subjects=frozenset({SUBJECT,other}))
        demo_login.register_demo_login(app)
        with demo_login.signing_socket(runtime),TestClient(app) as api:
            def login(code,consent=True):
                return api.post('/v1/demo-invite-sessions',json=dict(version=demo_login.VERSION,invite_code=code,consent=consent))
            assert login(CODE,False).status_code==400
            assert login(CODE[:-1]+'z').status_code==401
            signed=login(CODE)
            assert signed.status_code==200 and signed.headers['cache-control']=='no-store'
            assert login(CODE).status_code==200
            old={'Authorization':'Bearer '+signed.json()['access_token'],'Content-Type':'application/octet-stream'}
            params={'conversation_id':'demo-original'}
            assert api.put('/v1/conversations',params=params,headers=old).status_code==200
            with patch.object(dev_auth,'time',SimpleNamespace(time=lambda:time.time()-7202)):
                expired=dev_auth.token(auth,SUBJECT,120)
            assert api.put('/v1/conversations',params=params,headers={**old,'Authorization':'Bearer '+expired}).status_code==401
            route='/v1/demo-dialogue/messages'
            def dialogue(mid, **extra):
                return json.dumps(dict(version='DEMO-dialogue-message.1',message_id=mid,text='虚构北京行程',
                                       locale='zh',**extra),ensure_ascii=False).encode()
            assert api.post(route,content=dialogue('outside'),headers={
                **old,'Authorization':'Bearer '+dev_auth.token(auth,'invited-outside-dialogue',30)}).status_code==403
            assert api.post(route,content=dialogue('invalid',new_conversation=True,
                conversation_id='demo-dialogue-'+'0'*32),headers=old).status_code==400
            assert api.post(route,content=dialogue('client-owner',owner='forged'),headers=old).status_code==400
            first_raw=dialogue('first')
            with ThreadPoolExecutor(max_workers=3) as pool:
                responses=list(pool.map(lambda raw: api.post(route,content=raw,headers=old),
                    (first_raw,first_raw,dialogue('second'))))
            assert all(response.status_code==200 for response in responses),[(r.status_code,r.text) for r in responses]
            first, replay, second=(response.json()['receipt'] for response in responses)
            assert first==replay and first['input_sha256']==hashlib.sha256(first_raw).hexdigest()
            assert first['run_id']!=second['run_id'] and first['conversation_id']==second['conversation_id']
            lookup=api.get(route,params={'message_id':'first'},headers=old)
            assert lookup.status_code==200 and lookup.json()['receipt']==first
            foreign={**old,'Authorization':'Bearer '+dev_auth.token(auth,other,30)}
            assert api.get(route,params={'message_id':'first'},headers=foreign).json()['receipt'] is None
            assert api.post(route,content=dialogue('foreign-resume',
                conversation_id=first['conversation_id']),headers=foreign).status_code==503
            conflict=api.post(route,content=first_raw+b' ',headers=old)
            assert conflict.status_code==409 and conflict.json()['error']['code']=='INPUT_CONFLICT'
            new=api.post(route,content=dialogue('new',new_conversation=True),headers=old)
            assert new.status_code==200 and new.json()['receipt']['conversation_id']!=first['conversation_id']
            resumed=api.post(route,content=dialogue('continued',
                conversation_id=new.json()['receipt']['conversation_id']),headers=old)
            assert resumed.status_code==200 and resumed.json()['receipt']['conversation_id']==new.json()['receipt']['conversation_id']
            with psycopg.connect(**conninfo) as db:
                rows=db.execute("""SELECT f.context_id,f.context_version,r.demo_dialogue_input_sha256,r.input_sha256,
                    r.raw_input,d.acknowledged FROM cj_message_receipt r
                    JOIN cj_message_travel_reference f USING(scope,message_id,run_id)
                    JOIN cj_message_delivery d USING(scope,message_id,run_id)
                    WHERE r.scope=%s AND r.demo_dialogue_locale='zh'""",(scope_for(ISSUER,SUBJECT),)).fetchall()
                assert len(rows)==4 and len({row[0] for row in rows})==1
                assert all(version==1 and sha==hashlib.sha256(bytes(raw)).hexdigest()
                    and outer!=sha and not ack and json.loads(raw)['version']=='MESSAGE-send.2'
                    for _,version,outer,sha,raw,ack in rows)
                assert db.execute("SELECT count(*) FROM cj_travel_context_action WHERE scope=%s AND context_id=%s",
                    (scope_for(ISSUER,SUBJECT),rows[0][0])).fetchone()==(1,)
                try:
                    with db.transaction():
                        migrate.down(db,migrate.load(),49)
                except psycopg.errors.RaiseException as exc:
                    assert 'demo dialogue originals must be preserved' in str(exc)
                else:
                    raise AssertionError('migration down erased original dialogue evidence')
            model=FakeProvider()
            worker=run_worker._worker_for_scope(database,model,auth,scope_for(ISSUER,SUBJECT),
                checker_for(auth),memory_configuration=memory)
            outcomes=worker.process()
            assert len(outcomes)==4 and all(outcome.status=='completed' for outcome in outcomes)
            assert model.calls==4
            with psycopg.connect(**conninfo) as db:
                assert db.execute('SELECT count(*) FROM cj_message_delivery WHERE scope=%s AND acknowledged',
                    (scope_for(ISSUER,SUBJECT),)).fetchone()==(4,)
            check_lio(api, database, auth, other, old, conninfo, memory)
            assert login(CODE).status_code==200
            assert demo_accounts.manage(runtime,'revoke',SUBJECT,control,operation)=='revoked'
            assert login(CODE).status_code==401
            assert api.get(route,params={'message_id':'first'},headers=old).status_code==403
            assert api.post(route,content=dialogue('revoked'),headers=old).status_code==403
            assert api.put('/v1/conversations',params=params,headers=old).status_code==403
            assert demo_accounts.manage(runtime,'rotate',SUBJECT,control,operation,(digest(NEW_CODE),expiry))=='active'
            time.sleep(1.05)
            assert login(CODE).status_code==401 and api.put('/v1/conversations',params=params,headers=old).status_code==403
            renewed=login(NEW_CODE)
            assert renewed.status_code==200,renewed.status_code
            headers={**old,'Authorization':'Bearer '+renewed.json()['access_token']}
            opened=api.put('/v1/conversations',params=params,headers=headers)
            assert opened.status_code==200
            generation=opened.json()['generation']
            def command(number):
                return json.dumps(dict(version='MESSAGE-send.2',conversation_id=params['conversation_id'],
                    message_id='demo-'+str(number),text='Fictional trip',trip_id=None,creation_intent='none',
                    expected_generation=generation,expected_sequence=number-1,travel_context=None,needs_reference=None)).encode()
            receipts=[]
            for number in range(1,37):
                response=api.post('/v2/messages',content=command(number),headers=headers)
                assert response.status_code==200,(number,response.status_code,response.text)
                receipts.append(response.json()['receipt'])
            limited=api.post(route,content=dialogue('daily-limit'),headers=headers)
            assert limited.status_code==429 and limited.json()['error']['code']=='DEMO_DAILY_LIMIT',limited.text
            lio_limited=api.post('/v1/lio/messages',content=dialogue('lio-limit').replace(
                b'DEMO-dialogue-message.1', b'LIO-message.1'),headers=headers)
            assert lio_limited.status_code==429 and lio_limited.json()=={'failure':'quota'}
            replay=api.post('/v2/messages',content=command(1),headers=headers)
            assert replay.status_code==200 and replay.json()['receipt']==receipts[0]
            scope=scope_for(ISSUER,SUBJECT)
            with psycopg.connect(**conninfo) as db:
                assert db.execute("SELECT count(*) FROM public.cj_message_receipt WHERE scope=%s AND demo_question_day=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date",(scope,)).fetchone()==(40,)
                assert db.execute("SELECT has_table_privilege('cj_m1_runtime','cj_message_context_profile','INSERT')").fetchone()==(False,)
                periods=[ledger_scope_for(scope,p.meter) for p in following.profiles]
                assert db.execute('SELECT count(*) FROM public.cj_usage_ledger_candidate WHERE scope_id=ANY(%s)',(periods,)).fetchone()==(2,)
                for label,sql,parameters in (
                    ('invitation update','UPDATE public.cj_message_scope SET demo_revoked_at=clock_timestamp(),demo_session_floor=123 WHERE scope=%s',(scope,)),
                    ('receipt day update','UPDATE public.cj_message_receipt SET demo_question_day=demo_question_day-1 WHERE scope=%s',(scope,)),
                    ('invitation insert','INSERT INTO public.cj_message_scope(scope,demo_invite_digest,demo_invite_expires_at,demo_session_floor) VALUES (%s,%s,%s,0)',
                        (scope_for(ISSUER,'m4-synthetic-demo-001122334455'),digest(NEW_CODE),expiry)),
                ):
                    try:
                        with database.connect(parameters[0]) as runtime_connection:
                            runtime_connection.execute(sql,parameters)
                    except psycopg.errors.InsufficientPrivilege:pass
                    else:raise AssertionError('runtime changed protected state: '+label)
                db.execute("UPDATE public.cj_message_receipt SET demo_question_day=demo_question_day-1 WHERE scope=%s",(scope,))
            assert api.post('/v2/messages',content=command(37),headers=headers).status_code==200
            with psycopg.connect(**conninfo) as db:
                assert db.execute("SELECT count(*) FROM public.cj_message_receipt WHERE scope=%s AND demo_question_day=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date",(scope,)).fetchone()==(1,)
    print('PASS signed zero-setup dialogue, concurrent original replay, default Travel, no downgrade, revoke, 40/day, migration data protection and Beijing day rollover')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-demo-',dir='/tmp') as temp:
        root=Path(temp)
        with pg_suites.cluster('demo',port=55649,role='cj_demo_init',root=root/'pg',socket=root/'s') as conninfo:
            with psycopg.connect(**conninfo,autocommit=True) as connection:
                migrations=migrate.load();migrate.up(connection,migrations,migrations[-1]['version'])
            with patch.object(migrate,'load',return_value=migrations[:50]):
                with pg_suites.cluster('old-blueprint',port=55651,role='cj_demo_blueprint',
                        root=root/'old-blueprint',socket=root/'old-blueprint-s') as previous:
                    with psycopg.connect(**previous,autocommit=True) as connection:
                        migrate.up(connection,migrations,50)
                    verify_upgrade(root/'upgrade-50',previous,50)
            verify_upgrade(root/'upgrade-51',conninfo,51)
            exercise(root,conninfo)
