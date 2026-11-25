"""ROADBOOK.1 place enrichment (#1516, M4 item 18): Gaode facts, two flash calls, checked fields, a cache."""

from datetime import datetime
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cj_api.lio_roadbook import (
    FIELDS, OFFICIAL, PROMPT_VERSION, ROUTE, VERSION, DashScopeRoadbook, MemoryRoadbookCache, RoadbookRequest,
    RoadbookService, checked_fields, messages_for,
)
from cj_api.plugin_tools import PluginError
from cj_usage import roadbook_budget
from cj_usage.authorization_budget import AuthorizationBudget, authorization_usage
from cj_usage.roadbook_budget import BEIJING, RoadbookBudget, RoadbookPlaceBudget


def payload(*places, request_id=None):
    return dict(version=VERSION, request_id=request_id or str(uuid4()),
                places=list(places) or [dict(id='s1', name_zh='故宫博物院', name_en='Palace Museum', city='北京')])


PALACE = dict(id='B000A8UIN8', name='故宫博物院', typecode='110201', location='116.397029,39.917839',
              address='景山前街4号', cityname='北京市', pname='北京市',
              business={'opentime_week': '周二至周日 08:30-17:00', 'tel': '010-85007114'})
AROUND = [
    dict(id='BV1', name='天安门东(地铁站)', typecode='150500', location='116.401,39.908', distance='620'),
    dict(id='R1', name='四季民福烤鸭店(故宫店)', typecode='050101', location='116.403,39.913',
         address='东华门大街32号', distance='450'),
    dict(id='R2', name='无地址小馆', typecode='050100', location='116.404,39.914', distance='500'),
    dict(id='R3', name='南门涮肉', typecode='050102', location='116.405,39.915', address='南池子大街1号',
         distance='700'),
]


class Gaode:
    def __init__(self, found=True):
        self.calls = []
        self.found = found

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append((operation, params))
        if operation in ('text', 'detail'):
            data = {'pois': [PALACE] if self.found else [], 'count': '1' if self.found else '0'}
        else:
            data = {'pois': AROUND}
        return data, json.dumps(data, ensure_ascii=False).encode()


GOOD = {
    'zh': dict(summary='明清两代的皇宫，现为博物院。', why_go='中轴线上规模最大的古建筑群。', time_needed='约 3 小时',
               hours_booking='周二至周日 08:30-17:00；需提前实名预约，以官方为准。',
               tickets='约 40–60 元，以官方为准。', getting_there='地铁 1 号线天安门东站，步行约 10 分钟。',
               food_tip='附近的四季民福烤鸭店可以吃烤鸭。', notes='入口安检，带好护照；周一通常闭馆。'),
    'en': dict(summary='The imperial palace of the Ming and Qing, now a museum.',
               why_go='The largest group of old buildings on the central axis.', time_needed='About 3 hours',
               hours_booking='Tue–Sun 08:30-17:00; book ahead with your passport. Check official sources.',
               tickets='About 40–60 yuan; check official sources.',
               getting_there='Line 1 to Tian’anmen East, then walk about 10 minutes.',
               food_tip='Roast duck is close by at 四季民福烤鸭店(故宫店).',
               notes='Security check at the entrance; usually closed on Mondays.'),
}


class Flash:
    def __init__(self, replies=None, finish='stop'):
        self.calls = []
        self.replies = replies or GOOD
        self.finish = finish

    def generate(self, language, messages, reserve):
        reserve()
        self.calls.append((language, messages))
        reply = self.replies[language]
        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return f'chatcmpl-{uuid4().hex}', {'input_tokens': 900, 'output_tokens': 400}, text, self.finish


@pytest.fixture
def ledger(tmp_path):
    return AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 26, 10, tzinfo=BEIJING))


def service(ledger, gaode=None, flash=None, cache=None):
    return RoadbookService(gaode or Gaode(), flash or Flash(), RoadbookBudget(ledger), RoadbookPlaceBudget(ledger),
                           cache if cache is not None else MemoryRoadbookCache())


def enrich(svc, body, scope='scope-a'):
    return svc.enrich(scope, RoadbookRequest.model_validate(body), lambda: None)


# --- request ---------------------------------------------------------------------------------------------------

def test_route_and_version():
    assert (ROUTE, VERSION, PROMPT_VERSION) == ('/v1/tools/roadbook/places', 'ROADBOOK.1', 1)
    assert FIELDS == ('summary', 'why_go', 'time_needed', 'hours_booking', 'tickets', 'getting_there',
                      'food_tip', 'notes')


@pytest.mark.parametrize('change', [
    dict(extra=1), dict(version='ROADBOOK.2'), dict(request_id='not-a-uuid'), dict(places=[]),
    dict(places=[dict(id=f's{n}', name_zh='故宫', city='北京') for n in range(21)]),
    dict(places=[dict(id='s1', name_zh='故宫', city='北京')] * 2),
    dict(places=[dict(id='s1', name_zh='故宫', city='北京', address='景山前街4号')]),
    dict(places=[dict(id='s1', name_zh='故宫', city='北京', lat=39.9, lng=116.4)]),
    dict(places=[dict(id='s 1', name_zh='故宫', city='北京')]),
    dict(places=[dict(id='s1', name_zh='‮故宫', city='北京')]),
    dict(places=[dict(id='s1', name_zh='故宫', city='北京', poi_id='../x')]),
])
def test_requests_carry_only_public_place_names(change):
    with pytest.raises(ValidationError):
        RoadbookRequest.model_validate(dict(payload(), **change))


# --- enrichment -------------------------------------------------------------------------------------------------

def test_a_place_gets_checked_bilingual_content_from_gaode_facts(ledger):
    gaode, flash = Gaode(), Flash()
    result = enrich(service(ledger, gaode, flash), payload())
    place, = result['places']
    assert result['version'] == VERSION
    assert place['id'] == 's1' and place['status'] == 'ready' and place['poi_id'] == 'B000A8UIN8'
    assert place['content']['zh'] == GOOD['zh'] and place['content']['en'] == GOOD['en']
    assert place['metro'] == [dict(name_zh='天安门东站', distance_m=620)]
    assert place['restaurants'] == [
        dict(name_zh='四季民福烤鸭店(故宫店)', address_zh='东华门大街32号', lat=39.913, lng=116.403, distance_m=450),
        dict(name_zh='南门涮肉', address_zh='南池子大街1号', lat=39.915, lng=116.405, distance_m=700)]
    assert [operation for operation, _ in gaode.calls] == ['text', 'around']
    assert gaode.calls[0][1]['keywords'] == '故宫博物院' and gaode.calls[0][1]['region'] == '北京'
    assert [language for language, _ in flash.calls] == ['zh', 'en']
    facts = json.loads(flash.calls[0][1][-1]['content'])
    assert facts['opening'] == '周二至周日 08:30-17:00' and 'tel' not in json.dumps(facts)
    with ledger.mutation() as db:
        rows = [row[0].split(':')[0] for row in db.execute('SELECT id FROM attempt')]
    assert sorted(rows) == ['amap-roadbook.1'] * 2 + ['roadbook.1'] * 2


def test_a_known_poi_is_identified_by_detail(ledger):
    gaode = Gaode()
    body = payload(dict(id='s1', name_zh='故宫博物院', city='北京', poi_id='B000A8UIN8'))
    enrich(service(ledger, gaode), body)
    assert gaode.calls[0] == ('detail', dict(id='B000A8UIN8', show_fields='business'))


def test_cached_places_cost_nothing_and_do_not_count_as_a_roadbook(ledger):
    cache = MemoryRoadbookCache()
    enrich(service(ledger, cache=cache), payload())
    gaode, flash = Gaode(), Flash()
    with ledger.mutation() as db:
        before = db.execute('SELECT count(*) FROM attempt').fetchone()[0]
    for _ in range(roadbook_budget.DAILY_BOOKS + 1):
        result = enrich(service(ledger, gaode, flash, cache), payload())
        assert result['places'][0]['status'] == 'ready'
    assert gaode.calls == [] and flash.calls == []
    with ledger.mutation() as db:
        assert db.execute('SELECT count(*) FROM attempt').fetchone()[0] == before


def test_a_place_gaode_cannot_find_is_unavailable_without_a_model_call(ledger):
    flash = Flash()
    place, = enrich(service(ledger, Gaode(found=False), flash), payload())['places']
    assert place == dict(id='s1', status='unavailable')
    assert flash.calls == []


@pytest.mark.parametrize('reply', ['not json', json.dumps({'summary': 'x'}), json.dumps(dict(GOOD['zh'], extra='y'))])
def test_unusable_model_output_is_not_shown_or_cached(ledger, reply):
    cache = MemoryRoadbookCache()
    place, = enrich(service(ledger, flash=Flash({'zh': reply, 'en': GOOD['en']}), cache=cache), payload())['places']
    assert place == dict(id='s1', status='unavailable')
    assert cache.values == {}


def test_a_cut_off_answer_is_billed_but_neither_shown_nor_cached(ledger):
    cache = MemoryRoadbookCache()
    place, = enrich(service(ledger, flash=Flash(finish='length'), cache=cache), payload())['places']
    assert place['status'] == 'unavailable' and cache.values == {}
    with ledger.mutation() as db:
        _, estimates, _ = authorization_usage(db)
        assert db.execute("SELECT state FROM attempt WHERE id GLOB 'roadbook.1:*'").fetchall() == [('RECEIVED',)]


def test_daily_limits_leave_places_limited(ledger, monkeypatch):
    monkeypatch.setattr(roadbook_budget, 'DAILY_PLACES', 1)
    body = payload(dict(id='s1', name_zh='故宫博物院', city='北京'), dict(id='s2', name_zh='景山公园', city='北京'))
    result = enrich(service(ledger), body)
    assert [place['status'] for place in result['places']] == ['limited', 'limited']


def test_cache_only_mode_makes_no_supplier_calls(ledger, monkeypatch):
    monkeypatch.setattr(roadbook_budget, 'SUBLIMIT', 0)
    gaode, flash = Gaode(), Flash()
    place, = enrich(service(ledger, gaode, flash), payload())['places']
    assert place == dict(id='s1', status='limited')
    assert gaode.calls == [] and flash.calls == []


def test_a_reused_request_id_is_refused(ledger):
    body = payload()
    svc = service(ledger, cache=MemoryRoadbookCache())
    enrich(svc, body)
    with pytest.raises(PluginError) as error:
        enrich(service(ledger), body)
    assert (error.value.status, error.value.code) == (409, 'request_already_used')


# --- field checks -----------------------------------------------------------------------------------------------

FACTS = dict(name='故宫博物院', opening='周二至周日 08:30-17:00',
             restaurants=[dict(name_zh='四季民福烤鸭店(故宫店)')], metro=[])


def test_good_fields_pass_unchanged():
    assert checked_fields(json.dumps(GOOD['zh'], ensure_ascii=False), FACTS, 'zh') == GOOD['zh']


@pytest.mark.parametrize('field,value', [
    ('tickets', '60 元'), ('tickets', '门票 ¥60'), ('getting_there', '打车约 30 元'), ('notes', '今天开放'),
    ('summary', '今日营业到很晚'), ('hours_booking', '每天 09:00-18:00'), ('notes', '18:00 后人少'),
    ('food_tip', '推荐全聚德烤鸭店'), ('summary', ''), ('summary', '长' * 200), ('notes', '‮反向'),
])
def test_unchecked_claims_become_official_notices(field, value):
    checked = checked_fields(json.dumps(dict(GOOD['zh'], **{field: value}), ensure_ascii=False), FACTS, 'zh')
    assert checked[field] == OFFICIAL['zh']
    assert {key: checked[key] for key in FIELDS if key != field} == {key: GOOD['zh'][key] for key in FIELDS if key != field}


@pytest.mark.parametrize('field,value', [
    ('tickets', 'about ¥40-60, check official sources'), ('notes', 'Open today until late'),
    ('food_tip', 'Try Quanjude Restaurant nearby'), ('hours_booking', 'Daily 09:00-18:00'),
])
def test_english_claims_are_checked_the_same_way(field, value):
    checked = checked_fields(json.dumps(dict(GOOD['en'], **{field: value}), ensure_ascii=False), FACTS, 'en')
    expected = value if (field, value) == ('tickets', 'about ¥40-60, check official sources') else OFFICIAL['en']
    assert checked[field] == expected


def test_messages_carry_only_gaode_facts_and_the_rules():
    messages = messages_for('en', FACTS)
    assert [message['role'] for message in messages] == ['system', 'user']
    rules = messages[0]['content']
    for rule in ('JSON', 'about', 'official', 'today'):
        assert rule.lower() in rules.lower()
    assert json.loads(messages[1]['content']) == FACTS


# --- DashScope client -------------------------------------------------------------------------------------------

class Connection:
    def __init__(self, reply, events):
        self.reply = reply
        self.events = events

    def request(self, method, path, body, headers):
        self.events.append(('send', method, path, json.loads(body), headers['Authorization']))

    def getresponse(self):
        events = self.events
        reply = self.reply

        class Response:
            status = 200

            def read(self, limit=None):
                return json.dumps(reply).encode()

            def getheader(self, name, default=None):
                return default

        return Response()

    def close(self):
        self.events.append(('close',))


def completion(**changes):
    value = dict(id='chatcmpl-abc', model='qwen3.8-flash',
                 choices=[dict(message=dict(content='{"summary":"x"}'), finish_reason='stop')],
                 usage=dict(prompt_tokens=900, completion_tokens=400, total_tokens=1300))
    value.update(changes)
    return value


def test_dashscope_request_is_flash_json_without_thinking_and_reserved_first():
    events = []
    client = DashScopeRoadbook('sk-test', connection=lambda: Connection(completion(), events))
    supplier, usage, text, finish = client.generate('zh', messages_for('zh', FACTS), lambda: events.append(('reserve',)))
    assert events[0] == ('reserve',)
    _, method, path, body, auth = events[1]
    assert (method, path, auth) == ('POST', '/compatible-mode/v1/chat/completions', 'Bearer sk-test')
    assert body['model'] == 'qwen3.8-flash' and body['max_tokens'] == 1000 and body['enable_thinking'] is False
    assert body['response_format'] == {'type': 'json_object'}
    assert (supplier, usage, text, finish) == ('chatcmpl-abc', {'input_tokens': 900, 'output_tokens': 400},
                                               '{"summary":"x"}', 'stop')


@pytest.mark.parametrize('changes', [dict(model='qwen-plus'), dict(id='bad id!'), dict(choices=[]),
                                     dict(usage=dict(prompt_tokens=1))])
def test_dashscope_receipts_must_match_the_request(changes):
    client = DashScopeRoadbook('sk-test', connection=lambda: Connection(completion(**changes), []))
    with pytest.raises(PluginError):
        client.generate('zh', messages_for('zh', FACTS), lambda: None)


def test_a_place_without_facts_does_not_stop_the_next_one(ledger):
    class Mixed(Gaode):
        def query(self, operation, params, reserve):
            if operation == 'text' and params['keywords'] == '不存在的地方':
                reserve()
                self.calls.append((operation, params))
                return {'pois': [], 'count': '0'}, b'{}'
            return super().query(operation, params, reserve)

    body = payload(dict(id='s1', name_zh='不存在的地方', city='北京'), dict(id='s2', name_zh='故宫博物院', city='北京'))
    result = enrich(service(ledger, Mixed()), body)
    assert [place['status'] for place in result['places']] == ['unavailable', 'ready']
