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


def lio_fixture_model(*, empty_first_day=False):
    from cj_api.local_lio_planning import COMPACT_DRAFT, SYSTEM
    from cj_draft.needs_publisher import SYSTEM as PLAN_SYSTEM

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
                    end = '2026-11-13' if empty_first_day else '2026-11-12'
                    for edge, day in (('arrival','2026-11-11'), ('departure',end)):
                        fields[edge] = dict(date=dict(state='known', value=day), time=dict(state='missing'),
                                            timezone=dict(state='missing'), place=dict(state='missing'))
                yield json.dumps(dict(city=city, continues_trip=True, extraction=dict(
                    version='NEEDS-extraction.1', fields=fields, unresolved=[], long_term_requests=[])),
                    ensure_ascii=False)
                return
            if system.startswith(PLAN_SYSTEM):
                assert system.endswith(COMPACT_DRAFT)
                source = json.loads(messages[-1]['content'])
                before = source['current_trip']
                title = 'Beijing walk' if before is None else 'Beijing walks'
                if before is None:
                    def at(day, clock):
                        return dict(date=dict(state='known', value=day),
                                    time=dict(state='known', value=clock),
                                    timezone=dict(state='known', value='Asia/Shanghai'),
                                    utc_offset=dict(state='unknown'))
                    park_day = '2026-11-12' if empty_first_day else '2026-11-11'
                    museum_day = '2026-11-13' if empty_first_day else '2026-11-12'
                    park_hour = ('13:00','14:00') if empty_first_day else ('09:00','10:00')
                    items = [dict(id='park', text='Park walk', verification='pending', evidence=[],
                                  schedule=dict(start=at(park_day,park_hour[0]), end=at(park_day,park_hour[1])),
                                  fixed=dict(state='unknown'), source_category='unknown', source_refs=[]),
                             dict(id='museum', text='Museum visit', verification='pending', evidence=[],
                                  schedule=dict(start=at(museum_day,'13:00'), end=at(museum_day,'14:00')),
                                  fixed=dict(state='unknown'), source_category='unknown', source_refs=[])]
                    subjects = {'park':['party'],'museum':['party']}
                else:
                    items = before['content']['items']
                    subjects = {}
                yield json.dumps(dict(version='TRIP-model-plan.1', title=title, items=items,
                                      proposed_subjects=subjects))
                return
            if messages[-1]['content'] == 'Synthetic lost model outcome':
                raise ProviderUnknown()
            yield '北京有许多适合散步的公园。' if system.endswith('Reply in Chinese.') else 'Beijing has many parks for walking.'

    return LioModel(), prompts


def check_lio(api, database, auth, other, headers, conninfo, memory):
    from cj_api.local_lio_planning import LioPlanning, SYSTEM
    from cj_draft.lio_plan import LioPlanPublisher
    from cj_message import demo_dialogue
    from cj_message.domain import CommitUnknown
    from cj_message.lio_context import LioCitation, LioToolProgress
    from cj_message.lio_plan_needs import original_needs
    from cj_run.core import Binding, ResyncRequired
    from cj_trip.confirmation import ConfirmationSigner
    from cj_trip.domain import CommitUnknown as TripCommitUnknown
    from cj_api.lio_planning_grounding import (
        PlanningTurn, grounded_fields as grounded_dated_fields,
        planning_authority_complete as dated_authority_complete, stated_city,
    )
    from datetime import date

    def grounded_fields(turns, city, day):
        grounded = grounded_dated_fields(tuple(PlanningTurn(text, day) for text in turns), city)
        return grounded.fields, grounded.missing_fixed

    def planning_authority_complete(turns, city, day, *, has_fixed):
        return dated_authority_complete(tuple(PlanningTurn(text, day) for text in turns),
                                        city, has_fixed=has_fixed)

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
    assert planning_authority_complete(('Plan a trip to Beijing for three days starting tomorrow.',),
                                       'Beijing', today, has_fixed=False)
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
    first_day, reply_day = date(2026, 11, 9), date(2026, 11, 10)
    midnight = grounded_dated_fields((
        PlanningTurn('Plan three days in Beijing for two people starting tomorrow. The hotel meetup is fixed.', first_day),
        PlanningTurn('For everyone, on the first day from 09:00 to 10:00.', reply_day),
    ), 'Beijing')
    assert not midnight.missing_fixed and midnight.fields['arrival']['date']['value'] == '2026-11-10'
    assert midnight.fields['departure']['date']['value'] == '2026-11-12'
    assert midnight.fields['fixed_items'][0]['start']['date']['value'] == '2026-11-10'
    clarified = grounded_dated_fields((
        PlanningTurn('Plan a three-day trip to Beijing.', first_day),
        PlanningTurn('Starting tomorrow.', reply_day),
    ), 'Beijing')
    assert clarified.fields['arrival']['date']['value'] == '2026-11-11'
    date_reply = PlanningTurn('2026-11-11 to 2026-11-13 for 3 people.', reply_day)
    party = grounded_dated_fields((PlanningTurn('Plan a trip to Beijing.', first_day), date_reply), 'Beijing')
    assert party.fields['party_size']['value'] == 3 and not party.conflicting_party
    conflict = grounded_dated_fields(
        (PlanningTurn('Plan a trip to Beijing for 2 people.', first_day), date_reply), 'Beijing')
    assert conflict.conflicting_party and 'party_size' not in conflict.fields
    for tentative, certain in (
        ('Starting tomorrow?', 'Starting tomorrow.'),
        ('2026-11-11 to 2026-11-13?', '2026-11-11 to 2026-11-13.'),
    ):
        plan = ('Plan a three-day trip to Beijing.', tentative)
        assert not planning_authority_complete(plan, 'Beijing', today, has_fixed=False)
        assert planning_authority_complete((*plan, certain), 'Beijing', today, has_fixed=False)
    assert not planning_authority_complete((
        'Plan a three-day trip to Beijing.', 'Do those dates only work for Shanghai?', 'Starting tomorrow.',
    ), 'Beijing', today, has_fixed=False)
    for turns in (
        ('Plan a 2-day trip to Beijing starting tomorrow for 3 days.',),
        ('Plan a 2-day trip to Beijing from 2026-11-11 to 2026-11-13.',),
        ('Plan a 2-day trip to Beijing.', 'Starting tomorrow for 3 days.'),
    ):
        disputed, _ = grounded_fields(turns, 'Beijing', today)
        assert disputed['arrival']['date']['state'] == 'missing'
        assert disputed['departure']['date']['state'] == 'missing'
    consistent, _ = grounded_fields(('Plan a 3-day trip to Beijing from 2026-11-11 to 2026-11-13.',), 'Beijing', today)
    assert consistent['departure']['date']['value'] == '2026-11-13'
    fixed_prefix = ('Plan a trip to Beijing from 2026-11-11 to 2026-11-13 for 2 people. '
                    'The hotel meetup from 9 to 10 a.m. on the first day is fixed.')
    other_time = 'For everyone, on the first day from 11:00 to 12:00.'
    for turns in ((fixed_prefix + ' ' + other_time,), (fixed_prefix, other_time)):
        disputed, missing = grounded_fields(turns, 'Beijing', today)
        assert missing and 'fixed_items' not in disputed
    agreed, missing = grounded_fields(
        (fixed_prefix + ' For everyone, on the first day from 09:00 to 10:00.',), 'Beijing', today)
    assert not missing and agreed['fixed_items'][0]['start']['time']['value'] == '09:00'
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
    model, prompts = lio_fixture_model()
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
        def answer(self, worker, binding, messages, *, lio_locale, lio_question_day):
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
    calls = model.calls
    assert [outcome.status for outcome in worker.process()] == ['failed']
    assert model.calls == calls + 1
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
    stream = model.stream
    def unavailable_intake(messages, system=None):
        if system.startswith(SYSTEM):
            raise AssertionError('complete explicit plan must not dispatch the intake model')
        yield from stream(messages, system)
    with patch.object(model, 'stream', side_effect=unavailable_intake):
        assert [outcome.status for outcome in worker.process()] == ['completed']
    saved = api.get(timeline, headers=owner).json()['messages'][-1]
    assert saved['status'] == 'completed' and saved['answer'] == 'I saved your itinerary.', saved
    assert saved['trip']['title'] == 'Beijing walk'
    assert saved['trip']['days'][0]['items'][0]['fixed'] is False
    first_version = api.get('/v1/lio/trip', headers=owner).json()
    assert first_version['current'] == saved['trip']
    assert first_version['history'] == [] and first_version['undo_target'] is None

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
    check_lio_undo(api, owner, headers, cards)
    check_lio_conversational_edit(api, owner, worker, original, model, conninfo, scope)
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

    default_trip = api.get('/v1/lio/trip', headers=owner).json()
    v2_send, v2_timeline, v2_trip = '/v2/lio/messages', '/v2/lio/timeline', '/v2/lio/trip'

    def v2_original(mid, text, **fields):
        return json.dumps(dict(version='LIO-message.2', message_id=mid, text=text, locale='en', **fields)).encode()

    new_plan = v2_original('lio-new-plan', request, new_conversation=True)
    assert api.post(messages, content=new_plan, headers=owner).status_code == 400
    assert api.post(v2_send, content=raw, headers=owner).status_code == 400
    with patch.object(demo_dialogue, '_receive', side_effect=lose_commit_ack):
        created = api.post(v2_send, content=new_plan, headers=owner)
    assert created.status_code == 200, created.text
    new_chat = created.json()['conversation_id']
    assert new_chat != conversation and created.json()['version'] == 'LIO-message-receipt.2'
    assert api.post(v2_send, content=new_plan, headers=owner).json() == created.json()
    assert api.post(v2_send, content=new_plan + b' ', headers=owner).status_code == 409
    assert api.post(v2_send, content=v2_original('lio-new-invalid', request, new_conversation=True,
        conversation_id=new_chat), headers=owner).status_code == 400
    assert api.get(timeline, params=dict(conversation_id=new_chat), headers=owner).status_code == 400
    assert api.get(v2_timeline, params=dict(conversation_id=new_chat), headers=headers).status_code == 400
    assert api.post(v2_send, content=v2_original('lio-new-foreign', request, conversation_id=new_chat),
                    headers=headers).status_code == 400
    assert api.get(v2_timeline, params=dict(conversation_id=new_chat, before='lio-save'),
                   headers=owner).status_code == 400
    assert [outcome.status for outcome in worker.process()] == ['completed']
    new_card = api.get(v2_timeline, params=dict(conversation_id=new_chat), headers=owner).json()
    assert new_card['version'] == 'LIO-timeline.2'
    first_new, = new_card['messages']
    assert first_new['message_id'] == 'lio-new-plan' and first_new['trip'] is not None, first_new
    assert first_new['trip']['trip_id'] != default_trip['current']['trip_id']
    params = dict(conversation_id=new_chat)
    new_history = api.get(v2_trip, params=params, headers=owner).json()
    assert new_history['version'] == 'LIO-trip-history.2' and new_history['conversation_id'] == new_chat
    assert new_history['current'] == first_new['trip'] and not new_history['history']
    assert api.get(v2_trip, params=params, headers=headers).json()['current'] is None
    edit = v2_original('lio-new-edit', 'Replace the second afternoon with Temple of Heaven.', conversation_id=new_chat)
    assert api.post(v2_send, content=edit, headers=owner).status_code == 200
    assert [outcome.status for outcome in worker.process()] == ['completed']
    changed = api.get(v2_trip, params=params, headers=owner).json()
    assert changed['current'] != new_history['current'] and changed['history'][0] == new_history['current']
    undo = dict(version='LIO-trip-undo.2', action_id='lio-new-undo',
                conversation_id=new_chat, target=changed['undo_target'])
    assert api.post(v2_trip + '/undo', headers=owner, content=json.dumps(
        dict(undo, conversation_id=conversation)).encode()).status_code == 403
    applied = api.post(v2_trip + '/undo', headers=owner, content=json.dumps(undo).encode()).json()
    assert applied == dict(version='LIO-trip-undo-receipt.2', action_id=undo['action_id'],
                           committed=True, conversation_id=new_chat)
    query = {key: value for key, value in undo.items() if key != 'version'}
    assert api.get(v2_trip + '/undo', params=query, headers=owner).json() == applied
    assert api.get(v2_trip + '/undo', params=dict(query, conversation_id=conversation),
                   headers=owner).status_code == 403
    legacy_query = {key: value for key, value in query.items() if key != 'conversation_id'}
    assert api.get('/v1/lio/trip/undo', params=legacy_query, headers=owner).json()['committed'] is False
    assert api.get(v2_trip, params=params, headers=owner).json()['current'] == new_history['current']
    assert api.get('/v1/lio/trip', headers=owner).json() == default_trip
    default_message = v2_original('lio-default-from-v2', 'What can I see in Beijing?')
    assert api.post(v2_send, content=default_message, headers=owner).json()['conversation_id'] == conversation
    assert [outcome.status for outcome in worker.process()] == ['completed']
    v1_default = api.get(timeline, headers=owner).json()
    assert v1_default['conversation_id'] == conversation
    assert v1_default['messages'][-1]['message_id'] == 'lio-default-from-v2'
    assert api.get(v2_timeline, headers=owner).json() == dict(v1_default, version='LIO-timeline.2')
    print('PASS signed Lio v2 independent timelines and Trip, lost-ACK replay and owner/cursor isolation')
    with psycopg.connect(**conninfo) as db:
        try:
            with db.transaction():
                migrate.down(db, migrate.load(), 50)
        except psycopg.errors.RaiseException as exc:
            assert 'Lio dialogue originals must be preserved' in str(exc)
        else:
            raise AssertionError('migration down erased Lio originals')
    print('PASS signed Lio timeline, bilingual one-chat replay, ACK recovery, and retained display')


def check_lio_undo(api, owner, foreign, cards):
    from cj_trip import lio_history
    from cj_trip.domain import CommitUnknown

    history = '/v1/lio/trip'
    undo = history + '/undo'
    before = api.get(history, headers=owner).json()
    assert before['current'] == cards[1]['trip'] and before['history'] == [cards[0]['trip']]
    assert api.get(history, headers=foreign).json()['current'] is None
    command = dict(action_id='lio-undo-original', target=before['undo_target'])
    original = json.dumps(dict(command, version='LIO-trip-undo.1')).encode()
    assert api.get(undo, headers=owner, params=command).json()['committed'] is False
    assert api.post(undo, headers=foreign, content=original).status_code == 403

    append = lio_history._append_undo

    def lose_undo_ack(*args):
        append(*args)
        raise CommitUnknown('synthetic lost undo response')

    with patch.object(lio_history, '_append_undo', side_effect=lose_undo_ack) as write:
        recovered = api.post(undo, headers=owner, content=original)
        assert recovered.status_code == 200 and recovered.json()['committed'] is True
        assert api.post(undo, headers=owner, content=original).json() == recovered.json()
        assert write.call_count == 1
    assert api.get(undo, headers=owner, params=command).json() == recovered.json()
    assert api.get(undo, headers=foreign, params=command).json()['committed'] is False
    assert api.post(undo, headers=owner, content=json.dumps(
        dict(command, version='LIO-trip-undo.1', action_id='lio-undo-stale')).encode()).status_code == 409

    after = api.get(history, headers=owner).json()
    assert after['current'] == cards[0]['trip']
    assert after['history'] == [cards[1]['trip'], cards[0]['trip']]
    assert api.post(undo, headers=owner, content=json.dumps(
        dict(command, version='LIO-trip-undo.1', target=after['undo_target'])).encode()).status_code == 409
    print('PASS signed Lio current/history, undo original receipt recovery, replay, stale target, and isolation')


def check_lio_conversational_edit(api, owner, worker, original, model, conninfo, scope):
    from cj_draft.lio_plan import LioPlanPublisher
    from cj_trip.domain import CommitUnknown

    path = '/v1/lio/trip'
    timeline = '/v1/lio/timeline'
    before = api.get(path, headers=owner).json()['current']
    for mid, text, locale in (
        ('lio-edit-qualified-en', 'Replace the afternoon of day 2 with Temple of Heaven only if it is open.', 'en'),
        ('lio-edit-qualified-zh', '把第二天下午换成颐和园，不过先别改。', 'zh'),
        ('lio-edit-deferred-en', 'Replace the afternoon of day 2 with Temple of Heaven—do not apply this change yet.', 'en'),
        ('lio-edit-deferred-zh', '把第二天下午换成颐和园但先缓一缓。', 'zh'),
        ('lio-edit-options-en', 'Replace the afternoon of day 2 with Temple of Heaven or Summer Palace.', 'en'),
        ('lio-edit-options-zh', '把第二天下午换成颐和园或者天坛。', 'zh'),
        ('lio-edit-or-zh', '把第二天下午换成颐和园或天坛。', 'zh'),
        ('lio-edit-two-stops-en', 'Replace the afternoon of day 2 with Temple of Heaven and Summer Palace.', 'en'),
        ('lio-edit-ask-first-zh', '把第二天下午换成颐和园先问问我。', 'zh'),
        ('lio-edit-approval-en', 'Replace the afternoon of day 2 with Temple of Heaven subject to my approval.', 'en'),
        ('lio-edit-approval-zh', '把第二天下午换成「颐和园」经我同意再执行。', 'zh'),
        ('lio-edit-two-places-en', 'Replace the afternoon of day 2 with Temple of Heaven & Summer Palace.', 'en'),
    ):
        calls = model.calls
        assert api.post('/v1/lio/messages', headers=owner, content=original(mid, text, locale)).status_code == 200
        assert [outcome.status for outcome in worker.process()] == ['completed'] and model.calls == calls
        assert api.get(timeline, headers=owner).json()['messages'][-1]['trip'] is None
        assert api.get(path, headers=owner).json()['current'] == before
    raw = original('lio-edit-original', '把第二天下午换成天坛，保留其他安排。', 'zh')
    accepted = api.post('/v1/lio/messages', headers=owner, content=raw)
    assert accepted.status_code == 200
    commit = LioPlanPublisher._commit

    def lose_edit_ack(publisher, *args):
        commit(publisher, *args)
        raise CommitUnknown('synthetic lost edit response')

    calls = model.calls
    with patch.object(LioPlanPublisher, '_commit', lose_edit_ack):
        assert [outcome.status for outcome in worker.process()] == ['unknown']
    assert model.calls == calls
    observed = api.get(timeline, headers=owner).json()['messages'][-1]
    after = api.get(path, headers=owner).json()
    assert observed['status'] == 'completed' and observed['trip'] == after['current']
    assert after['current']['trip_id'] == before['trip_id']
    assert after['current']['days'][0] == before['days'][0]
    old_stop, = before['days'][1]['items']
    updated_stop, = after['current']['days'][1]['items']
    assert updated_stop == dict(old_stop, label='天坛')
    assert api.post('/v1/lio/messages', headers=owner, content=raw).json() == accepted.json()
    assert worker.process() == []
    with psycopg.connect(**conninfo) as db:
        assert db.execute(
            'SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m '
            'ON (o.scope,o.run_id)=(m.scope,m.run_id) WHERE m.scope=%s AND m.message_id=%s',
            (scope, 'lio-edit-original')).fetchone() == (0,)
    undo = dict(version='LIO-trip-undo.1', action_id='lio-edit-undo', target=after['undo_target'])
    assert api.post(path + '/undo', headers=owner, content=json.dumps(undo).encode()).json()['committed'] is True
    restored = api.get(path, headers=owner).json()
    assert restored['current'] == before and restored['history'][0] == after['current']
    assert api.get(timeline, headers=owner).json()['messages'][-1]['trip'] == after['current']
    print('PASS signed Lio day-two replacement, no model operation, original edit receipt recovery, and undo')


def check_lio_provider_wire(root, database, auth, runtime, actor, api, headers):
    import httpx

    from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
    from cj_api.local_app import load_confirmation_signer
    from cj_api.real_services import RealServices, RealTools
    from cj_memory_jobs.model_v2 import SYSTEM as MEMORY_SYSTEM
    from cj_usage.authorization_budget import AuthorizationBudget
    from cj_usage.codec import decode as decode_ledger

    scope = scope_for(ISSUER,actor)
    subjects = frozenset({actor})
    question = 'I prefer quieter entrances at attractions.'
    answer = 'I can suggest a relaxed route. The entrance hours are UNKNOWN.'
    attempts = []
    key = 'synthetic-wire-fixture-key-only'
    journal = AuthorizationBudget(root/'lio-wire-journal')

    def reply(request):
        assert str(request.url) == M4_BASE+'/chat/completions'
        assert request.headers['Authorization'] == 'Bearer '+key
        payload = json.loads(request.content)
        attempts.append(payload)
        if len(attempts) == 1:
            assert payload['tools'] and payload['messages'][-1] == dict(role='user',content=question)
            instructions = payload['messages'][0]['content']
            assert 'You are Lio' in instructions and 'what you could not verify' in instructions
            assert 'UNKNOWN' not in instructions
            content = answer
        else:
            assert len(attempts) == 2 and 'tools' not in payload and 'tool_choice' not in payload
            assert payload['response_format'] == dict(type='json_object')
            system, data = payload['messages']
            assert system['role'] == 'system' and system['content'].startswith(MEMORY_SYSTEM)
            assert data['role'] == 'user'
            entry, = json.loads(data['content'])['messages']
            assert entry['text'] == question
            content = json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',
                slot='quiet.entrance',kind='preference',text=question,extent='long_term',occurred_at='date unknown',
                evidence=[dict(ref=entry['ref'],quote=question)])]))
        identity = dict(id='synthetic-lio-wire-'+str(len(attempts)),model=M4_MODEL)
        events = [dict(**identity,choices=[dict(index=0,delta=dict(content=content),finish_reason=None)]),
                  dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
                  dict(**identity,choices=[],usage=dict(prompt_tokens=40,completion_tokens=10,total_tokens=50))]
        stream = ''.join('data: '+json.dumps(event)+'\n\n' for event in events)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(stream.encode()))

    model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,key),journal,transport=httpx.MockTransport(reply))
    services = RealServices(model,key,subjects,demo_subjects=subjects)
    tools = RealTools(services,buffered_streaming_subjects=subjects)
    signer = load_confirmation_signer(auth)

    def process():
        return run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
            memory_configuration_for_scope=lambda owner:runtime if owner==scope else None,
            account_admission=True,hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)

    mid = 'lio-memory-wire-original'
    payload = json.dumps(dict(version='LIO-message.1',message_id=mid,text=question,locale='en')).encode()
    send = '/v1/lio/messages'
    accepted = api.post(send,headers=headers,content=payload)
    assert accepted.status_code == 200, accepted.text
    assert [(outcome.message_id,outcome.status) for outcome in process()] == [(mid,'completed')]
    read = api.get('/v1/lio/timeline',headers=headers)
    assert read.status_code == 200, read.text
    turn, = [row for row in read.json()['messages'] if row['message_id'] == mid]
    assert turn['answer'] == answer.replace('UNKNOWN','not yet verified') and turn['status'] == 'completed'
    tag, = turn['memory']['tags']
    assert tag['text'] == question
    assert api.post(send,headers=headers,content=payload).json() == accepted.json()
    assert process() == [] and model.calls == 2 and len(attempts) == 2
    with database.connect(scope) as db:
        rows = db.execute("""SELECT o.attempt_id,o.kind,o.registration_id FROM cj_run_metered_operation o
            JOIN cj_message_receipt m USING(scope,run_id) WHERE m.message_id=%s""",(mid,)).fetchall()
        ledger = decode_ledger(db.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchone()[0])
        original_answer = db.execute('''SELECT e.value FROM cj_run_event e
            JOIN cj_message_receipt m USING(scope,run_id) WHERE m.message_id=%s AND e.kind='text_delta'
            ORDER BY e.sequence''',(mid,)).fetchall()
        assert ''.join(value for value, in original_answer) == answer
    assert {(kind,registration) for _,kind,registration in rows} == {
        ('model','model.tool_turn'),('memory','memory.lio_extract.1')}
    assert all(ledger.attempts[key].state == 'settled' for key,_,_ in rows)
    assert {(row['attempt_id'],row['kind'],row['state']) for row in journal.inspect()} == {
        (key,'model','RECEIVED') for key,_,_ in rows}
    print('PASS signed HK-style worker, offline DashScope wire, matched original Meter and authorization receipts')
    return mid


def check_lio_item_erasure(root, database, auth, path, context, scope, headers, chosen, sibling, consumer, preference):
    from cj_api.local_cleanup import Configuration
    from cj_cleanup.core import encode
    from cj_cleanup.memory_payloads import hooks, hold_payloads
    from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
    from cj_memory_withdrawal.erasure_service import ORDER
    from memory_withdrawal.tests.memory_test_inventory import write_inventory

    def input_for(db, mid, kind):
        return db.execute(
            """SELECT o.attempt_id,o.command_bytes,o.input_bytes FROM cj_run_metered_operation o
            JOIN cj_message_receipt m USING (scope,run_id) WHERE m.message_id=%s AND o.kind=%s""",
            (mid,kind)).fetchone()

    with database.connect(scope) as db:
        version, = db.execute('SELECT version FROM cj_memory_item WHERE item_id=%s',
                              (chosen['candidate_id'],)).fetchone()
        sibling_before = db.execute('SELECT status,version,original_input FROM cj_memory_item WHERE item_id=%s',
                                    (sibling['candidate_id'],)).fetchone()
        original = input_for(db,chosen['message_id'],'memory')
        recalled = input_for(db,consumer,'model')
        ledger, = db.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchone()
    assert original[2] is not None and preference.encode() in bytes(recalled[2])

    inventory = root/'lio-item-erasure-registry.json'
    write_inventory(inventory,'private-lio-pub4-erasure')
    config = Configuration({'local':b'lio-pub4-fixture-erasure-key-0001'},'local',3600,ORDER,inventory)
    erasure = create_erasure_app_v2(conninfo_path=path,auth_dir=auth,resolve_collection=lambda _:None,
        cleanup_configuration=config,resolve_backend_hooks=hooks,hold_payloads=hold_payloads,run_context=context)
    raw = encode(dict(version='MEMORY-ERASURE@1',action_id='lio-delete-original',
        item_id=chosen['candidate_id'],expected_version=version,derived_range='owned_trip_derived_scope'))
    with TestClient(erasure) as client:
        result = client.post('/v1/memory-erasures',content=raw,headers=headers)
        assert result.status_code == 200 and result.json()['result']['online_status'] == 'complete', result.text
        assert client.post('/v1/memory-erasures',content=raw,headers=headers).json()['result'] == result.json()['result']
    with database.connect(scope) as db:
        assert input_for(db,chosen['message_id'],'memory') == (*original[:2],None)
        assert input_for(db,consumer,'model') == (*recalled[:2],None)
        assert db.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchone() == (ledger,)
        assert db.execute('SELECT 1 FROM cj_memory_item WHERE item_id=%s',(chosen['candidate_id'],)).fetchone() is None
        assert db.execute('SELECT status,version,original_input FROM cj_memory_item WHERE item_id=%s',
                          (sibling['candidate_id'],)).fetchone() == sibling_before


def check_lio_memory(root, database, auth, path, context, foreign, actor, unknown_actor):
    from cj_api.lio_memory_routes import LioMemoryCards, _decode_target, _encode_target
    from cj_api.local_lio_memory import lio_candidates
    from cj_memory.domain import CommitUnknown as MemoryCommitUnknown
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from cj_memory_jobs.publication_result import VERSION_DEMO
    from cj_memory_jobs.service import OperationWithheld
    from cj_memory_jobs.model_v2 import SYSTEM as MEMORY_SYSTEM
    from cj_usage.codec import decode as decode_ledger

    def encoded(value):
        return json.dumps(value, ensure_ascii=False).encode()

    quiet, pace = 'I usually prefer quiet entrances.', 'I prefer fewer stops in a day.'
    text = quiet + ' ' + pace
    selected = frozenset({actor,unknown_actor})
    unknown_text = 'I prefer a quiet place, but the extraction response was lost.'
    expiry = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile = dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={
        slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True)
        for slot in ('quiet.entrance','travel.pace')})
    collection = dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at=expiry,
                        profiles={subject:profile for subject in selected}),
        travel_contexts={subject:[] for subject in selected})
    runtime = TypedRuntimeConfiguration.from_bytes(encoded(dict(version='local-memory-run.2',
        collection=collection,selections={subject:dict(subject='self',slots=['quiet.entrance','travel.pace'],
                                                        max_bytes=1000) for subject in selected})))
    model_inputs = []

    class MemoryModel(FakeProvider):
        def stream(self, messages, system=None):
            if system != MEMORY_SYSTEM:
                yield from super().stream(messages, system)
                return
            self.calls += 1
            evidence, = json.loads(messages[0]['content'])['messages']
            model_inputs.append(evidence['text'])
            if evidence['text'] == unknown_text:
                raise ProviderUnknown()
            entries = []
            if evidence['text'] == text:
                entries = [dict(subject='self',slot=slot,kind='preference',text=quote,extent='long_term',
                    occurred_at='date unknown',evidence=[dict(ref=evidence['ref'],quote=quote)])
                    for slot,quote in (('quiet.entrance',quiet),('travel.pace',pace))]
            yield encoded(dict(version='MEMORY-EXTRACT@2',entries=entries)).decode()
    candidates = None

    def memory_host(boundary):
        nonlocal candidates
        candidates = lio_candidates(database, boundary, selected, runtime.collection)
        return LioMemoryCards(candidates.collection, candidates.current)

    scope = scope_for(ISSUER, actor)
    local_run_context.provision_budget(path, context, actor)
    dev_auth.activate_travel(path, actor, context, ABI)
    token = dev_auth.token(auth,actor,30)
    owner = {'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    app = create_local_app(conninfo_path=None,auth_dir=auth,run_context=context,database=database,
        account_admission=True,demo_dialogue_subjects=selected,lio_dialogue_subjects=selected,
        lio_memory_factory=memory_host)
    service = candidates.collection
    with TestClient(app) as api:
        mid = 'lio-memory-original'
        originals = [('lio-before-memory', 'Tell me about a park.'), (mid, text),
                     ('lio-after-memory', 'Which metro station is nearby?')]
        for message, question in originals:
            sent = api.post('/v1/lio/messages', headers=owner, content=encoded(dict(
                version='LIO-message.1',message_id=message,text=question,locale='en')))
            assert sent.status_code == 200, sent.text
        stored = service.boundary.with_history_context(token,lambda current:current.query_lio_message(mid))
        receipt = stored.receipt
        worker = run_worker._worker_for_scope(database,MemoryModel(),auth,scope,checker_for(auth),
                                             memory_configuration=runtime,demo_planning=True,lio_memory_enabled=True)
        worker_candidates = worker.lio_memory.candidates
        with_history = worker_candidates.collection.boundary.with_history_context
        lost_publications = []

        def lose_publication_ack(token, operation):
            response = with_history(token, operation)
            if b'MEMORY-PUBLICATION-result@4' in response and json.loads(response)['receipts'] and not lost_publications:
                lost_publications.append(response)
                raise MemoryCommitUnknown()
            return response

        with patch.object(worker_candidates.collection.boundary,'with_history_context',side_effect=lose_publication_ack), \
                patch.object(worker_candidates,'query_publication_in_context',
                             wraps=worker_candidates.query_publication_in_context) as read_receipt:
            assert [outcome.status for outcome in worker.process()] == ['completed'] * 3
            assert len(lost_publications) == 1 and read_receipt.call_count == 1
        assert model_inputs == [question for _,question in originals]
        assert worker.process() == [] and len(model_inputs) == 3
        timeline = '/v1/lio/timeline'

        def displayed():
            response = api.get(timeline,headers=owner)
            assert response.status_code == 200, response.text
            before, selected_turn, after = response.json()['messages']
            assert [row['message_id'] for row in (before, selected_turn, after)] == [row[0] for row in originals]
            assert before['memory'] is None and after['memory'] is None
            return selected_turn['memory']

        original = json.loads(candidates.prepare(token,mid,receipt.run_id,max_payload_bytes=32768))
        assert (original['source']['after'],original['source']['through'],original['state']) == (1,2,'completed')
        assert original['prepared_input_utf8'] is None
        result = json.loads(service.boundary.with_history_context(token,lambda current:
            candidates.query_publication_in_context(current,token,original['job_id'],original['attempt_id'],
                                                    message_id=mid,run_id=receipt.run_id)))
        assert result['version'] == VERSION_DEMO and [item['status'] for item in result['receipts']] == ['candidate'] * 2
        tags = {tag['text']:tag for tag in displayed()['tags']}
        assert set(tags) == {quiet, pace}
        with database.connect(scope) as db:
            assert db.execute('SELECT status FROM cj_memory_item ORDER BY status').fetchall() == [('candidate',),('candidate',)]
            assert db.execute('SELECT count(*) FROM cj_memory_history_consent').fetchone() == (0,)
            assert db.execute('SELECT count(*) FROM cj_memory_history_job').fetchone() == (3,)
            attempts = db.execute("SELECT attempt_id FROM cj_run_metered_operation WHERE kind='memory' "
                                  "AND registration_id='memory.lio_extract.1'").fetchall()
            ledger = decode_ledger(db.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchone()[0])
            assert len(attempts) == 3 and all(ledger.attempts[key].state == 'settled' for key, in attempts)

        actions = '/v1/lio/memory/actions'
        receipts = '/v1/lio/memory/receipt'
        remember = dict(version='LIO-memory-action.1',action_id='remember-quiet',operation='remember',
                        target=tags[quiet]['target'])
        reject = dict(version='LIO-memory-action.1',action_id='dismiss-pace',operation='dismiss',
                      target=tags[pace]['target'])
        assert api.post(receipts,headers=owner,content=encoded(remember)).json()['status'] == 'pending'
        assert api.post(actions,headers=foreign,content=encoded(remember)).status_code == 403
        tampered = _decode_target(tags[quiet]['target'])
        tampered['text'] = 'Forged preference'
        assert api.post(actions,headers=owner,content=encoded(
            dict(remember,target=_encode_target(tampered)))).status_code == 409

        apply = service.apply_candidate
        def lose_ack(*args):
            apply(*args)
            raise OperationWithheld('synthetic lost memory response')

        with patch.object(service,'apply_candidate',side_effect=lose_ack) as writer:
            saved = api.post(actions,headers=owner,content=encoded(remember))
            assert saved.status_code == 200 and saved.json()['status'] == 'remembered', saved.text
            assert api.post(actions,headers=owner,content=encoded(remember)).json() == saved.json()
            assert writer.call_count == 1
        assert api.post(receipts,headers=owner,content=encoded(remember)).json() == saved.json()
        assert api.post(receipts,headers=owner,content=encoded(dict(remember,operation='dismiss'))).status_code == 409
        changed_message = dict(_decode_target(remember['target']),message_id='lio-before-memory')
        for endpoint in (actions,receipts):
            assert api.post(endpoint,headers=owner,content=encoded(
                dict(remember,target=_encode_target(changed_message)))).status_code == 409
        assert api.post(actions,headers=owner,content=encoded(reject)).status_code == 409
        refreshed, = displayed()['tags']
        assert refreshed['text'] == pace
        dismiss = dict(reject,target=refreshed['target'])
        dismissed = api.post(actions,headers=owner,content=encoded(dismiss))
        assert dismissed.status_code == 200 and dismissed.json()['status'] == 'dismissed'
        assert api.post(receipts,headers=owner,content=encoded(dismiss)).json() == dismissed.json()
        assert api.post(actions,headers=owner,content=encoded(dismiss)).json() == dismissed.json()
        for key,value in (
            ('message_id','lio-after-memory'), ('kind','fact'),
            ('text','Forged preference'), ('occurred_at','another date'),
        ):
            tampered = dict(_decode_target(dismiss['target']),**{key:value})
            for endpoint in (actions,receipts):
                assert api.post(endpoint,headers=owner,content=encoded(
                    dict(dismiss,target=_encode_target(tampered)))).status_code == 409
        assert displayed() is None
        with database.connect(scope) as db:
            assert db.execute('SELECT status FROM cj_memory_item ORDER BY status').fetchall() == [('active',),('withdrawn',)]
        unknown_scope = scope_for(ISSUER,unknown_actor)
        unknown_token = dev_auth.token(auth,unknown_actor,30)
        unknown_headers = {**owner,'Authorization':'Bearer '+unknown_token}
        unknown_id = 'lio-memory-provider-unknown'
        payload = encoded(dict(version='LIO-message.1',message_id=unknown_id,text=unknown_text,locale='en'))
        assert api.post('/v1/lio/messages',headers=unknown_headers,content=payload).status_code == 200

        def unknown_worker():
            return run_worker._worker_for_scope(database,MemoryModel(),auth,unknown_scope,checker_for(auth),
                memory_configuration=runtime,demo_planning=True,lio_memory_enabled=True)

        assert [outcome.status for outcome in unknown_worker().process()] == ['completed']
        assert model_inputs.count(unknown_text) == 1
        assert api.post('/v1/lio/messages',headers=unknown_headers,content=payload).status_code == 200
        assert unknown_worker().process() == [] and model_inputs.count(unknown_text) == 1
        received = api.get(timeline,headers=unknown_headers)
        assert received.status_code == 200, received.text
        turn, = [row for row in received.json()['messages'] if row['message_id'] == unknown_id]
        assert turn['status'] == 'completed' and turn['answer'] and turn['memory'] is None
        unknown_original = service.boundary.with_history_context(unknown_token,lambda current:
            current.query_lio_message(unknown_id)).receipt
        held = json.loads(candidates.prepare(unknown_token,unknown_id,unknown_original.run_id,max_payload_bytes=32768))
        assert held['state'] == 'unknown' and held['prepared_input_utf8'] is None
        with database.connect(unknown_scope) as db:
            attempt, = db.execute("SELECT attempt_id FROM cj_run_metered_operation WHERE run_id=%s AND kind='memory'",
                                  (unknown_original.run_id,)).fetchone()
            ledger = decode_ledger(db.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchone()[0])
            assert ledger.attempts[attempt].state == 'unknown'
        consumer = check_lio_provider_wire(root,database,auth,runtime,actor,api,owner)
        recall = 'lio-new-memory-recall'
        def new_memory_question(mid):
            return api.post('/v2/lio/messages', headers=owner, content=encoded(dict(
                version='LIO-message.2', message_id=mid, text='What travel preference do I have?',
                locale='en', new_conversation=True)))

        def answer_input(db, mid):
            raw, = db.execute(
                "SELECT o.input_bytes FROM cj_run_metered_operation o JOIN cj_message_receipt m USING(scope,run_id) "
                "WHERE m.message_id=%s AND o.kind='model'", (mid,)).fetchone()
            return raw

        new_chat = new_memory_question(recall).json()['conversation_id']
        assert new_chat != api.get(timeline, headers=owner).json()['conversation_id']
        assert [outcome.status for outcome in worker.process()] == ['completed']
        with database.connect(scope) as db:
            assert quiet.encode() in bytes(answer_input(db, recall))
        check_lio_item_erasure(root,database,auth,path,context,scope,owner,
            _decode_target(remember['target']),_decode_target(dismiss['target']),consumer,quiet)
        after_erase = 'lio-after-item-erasure'
        assert api.post('/v1/lio/messages',headers=owner,content=encoded(dict(
            version='LIO-message.1',message_id=after_erase,text='What should I see near the metro?',locale='en'))).status_code == 200
        assert [outcome.status for outcome in worker.process()] == ['completed']
        with database.connect(scope) as db:
            original_after_erase, = db.execute(
                """SELECT o.input_bytes FROM cj_run_metered_operation o JOIN cj_message_receipt m USING(scope,run_id)
                WHERE m.message_id=%s AND o.kind='model'""",(after_erase,)).fetchone()
            assert quiet.encode() not in bytes(original_after_erase)
        print('PASS signed Lio item erasure clears Pub4 and recalled Meter payloads, preserves ledger and sibling, and stops recall')
        post_delete = 'lio-new-memory-after-erasure'
        assert new_memory_question(post_delete).json()['conversation_id'] != new_chat
        assert [outcome.status for outcome in worker.process()] == ['completed']
        with database.connect(scope) as db:
            assert answer_input(db, recall) is None
            assert quiet.encode() not in bytes(answer_input(db, post_delete))
        print('PASS signed Lio v2 recalls saved Memory across conversations and preserves the erasure fence')

        direct_id = 'lio-direct-pilot-pace'
        direct_text = '请记住，我旅行时喜欢慢节奏。'
        assert api.post('/v1/lio/messages', headers=owner, content=encoded(dict(
            version='LIO-message.1', message_id=direct_id, text=direct_text, locale='zh'))).status_code == 200
        assert [outcome.status for outcome in worker.process()] == ['completed']
        received = api.get(timeline, headers=owner)
        assert received.status_code == 200, received.text
        direct_turn, = [row for row in received.json()['messages'] if row['message_id'] == direct_id]
        tag, = direct_turn['memory']['tags']
        assert tag['text'] == '我旅行时喜欢慢节奏。'
        with database.connect(scope) as db:
            assert db.execute('SELECT status FROM cj_memory_item WHERE item_id=%s', (tag['id'],)).fetchone() == ('candidate',)
            assert db.execute(
                "SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m USING(scope,run_id) "
                "WHERE m.message_id=%s AND o.kind='memory'", (direct_id,)).fetchone() == (0,)
        direct_choice = dict(version='LIO-memory-action.1', action_id='remember-direct-pace',
                             operation='remember', target=tag['target'])
        assert api.post(actions, headers=owner, content=encoded(direct_choice)).json()['status'] == 'remembered'
        assert api.post(receipts, headers=owner, content=encoded(direct_choice)).json()['status'] == 'remembered'
        with database.connect(scope) as db:
            assert db.execute('SELECT status FROM cj_memory_item WHERE item_id=%s', (tag['id'],)).fetchone() == ('active',)
        assert direct_text not in model_inputs
        print('PASS signed exact pilot preference uses original quote, zero external extraction and explicit confirmation')
    print('PASS signed Lio Meter and middle-turn Pub4, explicit remember/dismiss, stale choice, isolation, ACK recovery and original UNKNOWN')
    return app, remember


def check_lio_retirement(root, database, auth, conninfo, context, memory, clean_actor, unsettled_actor, memory_app, memory_choice):
    from cj_agent.draft import trip_scope_for
    from cj_api.local_app import load_confirmation_signer
    from cj_api.local_cleanup import Configuration
    from cj_cleanup.core import encode
    from cj_memory_withdrawal.account_cleanup import account_hooks
    from cj_message.needs_binding import needs_scope_for

    # Use the real online content hooks. Device, external-processing and
    # backup evidence have separate acceptance gates.
    registry = json.loads((ROOT/'backend/storage-registry.json').read_bytes())
    registry['stores'] = [store for store in registry['stores'] if store['id'] in ('business','checkpoints','memory-derived')]
    business = next(store for store in registry['stores'] if store['id']=='business')
    business['objects'] = [item for item in business['objects'] if item['id']!='cleanup-metadata']
    inventory = tuple(target for store in registry['stores'] for target in (
        [store['id']+'/'+item['id'] for item in store['objects'] if isinstance(item,dict)] or [store['id']]))
    registry_path = root/'lio-online-retirement-registry.json'
    registry_path.write_bytes(encode(registry))
    key = 'lio-local-cleanup'
    options = Configuration({key:b'lio-local-cleanup-fixture-key000'},key,3600,inventory,registry_path,
                            extra_hooks=account_hooks)
    selected = frozenset({clean_actor,unsettled_actor})
    signer = load_confirmation_signer(auth)
    app = create_local_app(conninfo_path=None,auth_dir=auth,run_context=context,database=database,
        confirmation_signer=signer,account_admission=True,cleanup_configuration=options,cleanup_subjects=selected,
        demo_dialogue_subjects=selected,lio_dialogue_subjects=selected)

    def footprint(owner):
        needs, trip = needs_scope_for(owner), trip_scope_for(owner)
        tables = [('cj_message_receipt','scope',owner),('cj_message_delivery','scope',owner),
                  ('cj_run_record','scope',owner),('cj_run_event','scope',owner),
                  ('cj_message_needs_binding','message_scope',owner),('cj_needs_revision','scope',needs),
                  ('cj_trip_record','scope',trip),('cj_trip_receipt','scope',trip),
                  ('cj_trip_needs_basis','scope',trip),('cj_trip_needs_action','scope',trip),
                  ('cj_memory_item','scope',owner),('cj_memory_operation','scope',owner),
                  ('cj_memory_history_job','scope',owner),('cj_memory_history_candidate_action','scope',owner),
                  ('cj_usage_ledger_candidate','scope_id',ledger_scope_for(owner,context.current.meter))]
        with psycopg.connect(**conninfo) as db:
            return {table:db.execute(f'SELECT count(*) FROM {table} WHERE {key}=%s',(scope,)).fetchone()[0]
                    for table,key,scope in tables}

    def actor_headers(actor):
        return {'Authorization':'Bearer '+dev_auth.token(auth,actor,30),'Content-Type':'application/octet-stream'}

    def send(api, headers, mid, text):
        return api.post('/v1/lio/messages',headers=headers,content=encode(dict(
            version='LIO-message.1',message_id=mid,text=text,locale='en')))

    def retire(api, headers, actor):
        binding = api.post('/v1/cleanup-devices',headers=headers,content=encode(dict(
            version='CLEANUP-DEVICE@1',action_id='register',device_id=actor+'-device',state_ref=digest(actor)))).json()
        prepared = api.post('/v1/account-cleanup-operations',headers=headers,content=encode(dict(
            version='CLEANUP-API@1',action_id='prepare',binding_id=binding['binding_id']))).json()
        path = '/v1/account-cleanup-operations/'+prepared['operation_id']
        confirmed = api.post(path+'/confirmation',headers=headers,content=encode(dict(
            version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT')))
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()['business_access'] == 'revoked', confirmed.json()
        assert api.get('/v1/lio/timeline',headers=headers).status_code == 403
        assert api.get('/v1/lio/trip',headers=headers).status_code == 403
        assert send(api,headers,'lio-retired-message','An old account cannot send again.').status_code == 403
        assert api.get(path,headers={'Authorization':'Cleanup '+prepared['progress_token']}).json()['online_status'] == confirmed.json()['online_status']
        return confirmed.json()

    clean, unsettled = scope_for(ISSUER,clean_actor), scope_for(ISSUER,unsettled_actor)
    clean_headers, unsettled_headers = actor_headers(clean_actor), actor_headers(unsettled_actor)
    with TestClient(app) as api:
        model, _ = lio_fixture_model(empty_first_day=True)
        worker = run_worker._worker_for_scope(database,model,auth,clean,checker_for(auth),
            memory_configuration=memory,draft_profile='needs-structured.1',demo_planning=True,lio_confirmation=signer)
        assert send(api,clean_headers,'lio-clean-plan',
                    'Plan a trip to Beijing from 2026-11-11 to 2026-11-13 for our party.').status_code == 200
        assert [outcome.status for outcome in worker.process()] == ['completed']
        before = api.get('/v1/lio/trip',headers=clean_headers).json()
        assert [day['date'] for day in before['current']['days']] == ['2026-11-12','2026-11-13']
        assert send(api,clean_headers,'lio-clean-edit-relative',
                    'Replace the afternoon of day 2 with Temple of Heaven.').status_code == 200
        calls = model.calls
        assert [outcome.status for outcome in worker.process()] == ['completed'] and model.calls == calls
        clarified = api.get('/v1/lio/timeline',headers=clean_headers).json()['messages'][-1]
        assert clarified['trip'] is None and 'exact date' in clarified['answer']
        assert api.get('/v1/lio/trip',headers=clean_headers).json() == before
        assert send(api,clean_headers,'lio-clean-edit',
                    'Replace the afternoon of 2026-11-12 with Temple of Heaven.').status_code == 200
        assert [outcome.status for outcome in worker.process()] == ['completed'] and model.calls == calls
        trip = api.get('/v1/lio/trip',headers=clean_headers).json()
        assert trip['current']['days'][0]['items'][0]['label'] == 'Temple of Heaven'
        assert trip['current']['days'][1] == before['current']['days'][1]
        print('PASS signed Lio sparse itinerary asks for a date and replaces only the named date')
        assert api.post('/v1/lio/trip/undo',headers=clean_headers,content=encode(dict(
            version='LIO-trip-undo.1',action_id='lio-clean-undo',target=trip['undo_target']))).json()['committed'] is True
        assert all(footprint(clean).values()), footprint(clean)

        unresolved = footprint(unsettled)
        assert unresolved['cj_trip_record'] and unresolved['cj_usage_ledger_candidate']
        withheld = retire(api, unsettled_headers, unsettled_actor)
        assert withheld['reason'] == 'original_usage_outcome_unresolved', withheld
        assert footprint(unsettled) == unresolved

        result = retire(api, clean_headers, clean_actor)
        assert result['online_status'] == 'complete', result
        assert not any(footprint(clean).values()), footprint(clean)
        assert footprint(unsettled) == unresolved
    with TestClient(memory_app) as api:
        assert api.post('/v1/lio/memory/receipt',headers=clean_headers,content=encode(memory_choice)).status_code == 403
    with psycopg.connect(**conninfo) as db:
        assert db.execute('SELECT public.cj_account_scope_current(%s)',(clean,)).fetchone() == (False,)
        assert db.execute('SELECT erased FROM cj_memory_history_fence WHERE scope_digest=%s',
                          (hashlib.sha256(clean.encode()).hexdigest(),)).fetchone() == (True,)
    print('PASS signed Lio retirement, original UNKNOWN preserves evidence, clean online erasure and cross-owner isolation')


def exercise(root,conninfo):
    auth=root/'auth'
    other='other-dialogue-owner'
    memory_actor='m4-synthetic-lio-memory'
    dev_auth.init(auth,[SUBJECT,other,'invited-outside-dialogue','legacy-dialogue-only',memory_actor])
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
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={
            subject:profile for subject in (SUBJECT,other,memory_actor)}),
        travel_contexts={subject:[] for subject in (SUBJECT,other,memory_actor)})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=collection,
        selections={subject:dict(subject='self',slots=['quiet.entrance'],max_bytes=1000)
                    for subject in (SUBJECT,other,memory_actor)})).encode())
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
        from cj_api.local_app import load_confirmation_signer
        app=create_local_app(conninfo_path=None,auth_dir=auth,run_context=context,database=database,account_admission=True,
            confirmation_signer=load_confirmation_signer(auth),
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
            memory_app, memory_choice = check_lio_memory(root, database, auth, path, context, old, memory_actor, other)
            check_lio_retirement(root, database, auth, conninfo, context, memory, memory_actor, other,
                                 memory_app, memory_choice)
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
