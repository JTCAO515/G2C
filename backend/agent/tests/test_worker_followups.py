"""W2-1 (#1727): the worker commits the layout before the text and fixed buttons after it."""
import json
import os
from unittest.mock import patch

from cj_agent.worker import RunWorker
from cj_message.lio_followups import FollowupHint, SAVE_CHIP
from cj_message.lio_context import FOLLOWUPS_EFFECT, LAYOUT_EFFECT, LioDestination, LioDestinationUnclear, LioLayout, LioOriginal
from cj_run.core import Binding, Service
from cj_run.fixture import MemoryRepository
from test_worker_cancel import Drafts
from test_worker_safety_lines import Messages as BaseMessages


class Messages(BaseMessages):
    """The safety-lines message fake plus a chip store that records what the worker asks for."""
    def __init__(self, text, issue=None):
        super().__init__(text)
        self.issued = []
        self.issue = issue
        if issue is not None:
            self.issue_lio_chips = self._issue

    def _issue(self, message_id, labels):
        self.issued.append((message_id, list(labels)))
        if isinstance(self.issue, Exception):
            raise self.issue
        return self.issue


class Tools:
    commits_layout = True

    def __init__(self, layout, text, destinations=()):
        self.layout, self.text, self.destinations = layout, text, destinations
    def answer(self, worker, binding, inputs, **kwargs):
        self.kwargs = kwargs
        if self.layout is not None:
            yield LioLayout(self.layout)
        yield from self.destinations
        yield self.text


def run(question, answer, layout, locale='zh', issue=None, destinations=()):
    runs = Service(MemoryRepository(), lambda _: True)
    messages = Messages(question, issue)
    worker = RunWorker(scope='scope', messages=messages, runs=runs, provider=None, tools=Tools(layout, answer, destinations),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal(locale, None))
    outcome, = worker.process()
    run.last_messages = messages
    return outcome.status, runs.snapshot(Binding('scope', 'chat', 'g', 'm', 'r', 1))


def test_split_answer_commits_layout_before_text_and_buttons_after():
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。\n\n再出示付款码。', 'split')
    assert status == 'completed'
    assert state.effects[0] == LAYOUT_EFFECT + 'split'
    assert state.effects[1].startswith(FOLLOWUPS_EFFECT)
    assert '"tool":"payment-guide"' in state.effects[1] and '打开支付开通指南' in state.effects[1]


def test_single_answer_or_no_layout_carries_no_buttons():
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。', 'single')
    assert status == 'completed' and state.effects == (LAYOUT_EFFECT + 'single',)
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。', None)
    assert status == 'completed' and state.effects == ()


def test_split_answer_without_a_matching_topic_gets_a_layout_but_no_buttons():
    status, state = run('成都有什么好吃的', '火锅。\n\n再试试串串。', 'split')
    assert status == 'completed' and state.effects == (LAYOUT_EFFECT + 'split',)


def test_english_buttons_use_the_fixed_english_labels():
    status, state = run('How do I pay with Alipay?', 'Link your card.\n\nThen show the code.', 'split', locale='en')
    assert 'Payment setup guide' in state.effects[1]


def test_a_tools_object_that_does_not_declare_layout_is_never_given_the_argument():
    class Strict:
        def answer(self, worker, binding, inputs, *, lio_locale, lio_question_day):
            yield '好的。'
    runs = Service(MemoryRepository(), lambda _: True)
    worker = RunWorker(scope='scope', messages=Messages('你好'), runs=runs, provider=None, tools=Strict(),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
    outcome, = worker.process()
    assert outcome.status == 'completed'
    tools = Tools('split', '好的。')
    worker = RunWorker(scope='scope', messages=Messages('你好'), runs=Service(MemoryRepository(), lambda _: True), provider=None,
                       tools=tools, drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
    worker.process()
    assert tools.kwargs['lio_layout'] is True


def payload(state):
    return json.loads(state.effects[1].removeprefix(FOLLOWUPS_EFFECT))


def test_chips_get_stored_tickets_and_ride_in_the_followups_effect():
    tickets = ['a' * 43, 'b' * 43, 'c' * 43]
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。\n\n再出示付款码。', 'split', issue=tickets)
    assert status == 'completed'
    assert run.last_messages.issued == [('m', ['付不了怎么办', '哪些地方不能用', '怎么开通地铁乘车码'])]
    body = payload(state)
    assert [chip['ticket'] for chip in body['chips']] == tickets and body['actions'][0]['tool'] == 'payment-guide'
    assert isinstance(body['issued_at'], int)


def test_a_failed_or_missing_ticket_store_leaves_the_buttons_and_no_chips():
    for issue in (None, RuntimeError('db down')):
        status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。', 'split', issue=issue)
        assert status == 'completed'
        body = payload(state)
        assert body['chips'] == [] and body['actions'][0]['tool'] == 'payment-guide'
    # a store that cannot write all of them (returns None) also offers none
    status, state = run('外国游客怎么用支付宝？', '先绑定国际银行卡。', 'split', issue=None)
    assert payload(state)['chips'] == []


def test_a_question_with_chips_but_no_button_still_gets_a_followups_record():
    # a "taxi" question with no tool destination has the plain taxi button and taxi chips
    status, state = run('怎么打车去机场', '可以用滴滴。', 'split', issue=['d' * 43, 'e' * 43, 'f' * 43])
    assert status == 'completed' and payload(state)['chips'][0]['ticket'] == 'd' * 43


PALACE = LioDestination('故宫博物院', '116.397026,39.918058', '景山前街4号', 'The Palace Museum')


def taxi_params(state):
    return payload(state)['actions'][-1]


def test_one_place_from_the_map_tools_gives_the_taxi_button_its_destination():
    status, state = run('怎么打车去故宫', '可以打车。', 'split', destinations=(PALACE,))
    button = taxi_params(state)
    assert status == 'completed' and button['tool'] == 'taxi' and button['label'] == '打车去这里'
    assert button['parameters'] == {'destination': '故宫博物院', 'lat': '39.918058', 'lng': '116.397026',
                                    'address': '景山前街4号', 'destinationEN': 'The Palace Museum'}
    # the same place twice is still one place
    assert taxi_params(run('怎么打车去故宫', '可以打车。', 'split', destinations=(PALACE, PALACE))[1])['label'] == '打车去这里'


def test_two_different_places_or_none_give_the_plain_taxi_button():
    other = LioDestination('景山公园', '116.396,39.926')
    for places in ((), (PALACE, other)):
        button = taxi_params(run('怎么打车去故宫', '可以打车。', 'split', destinations=places)[1])
        assert (button['label'], button['parameters']) == ('打车', {})


def test_a_place_does_not_make_a_button_for_a_question_that_is_not_about_a_taxi():
    status, state = run('故宫几点开门', '九点。', 'split', destinations=(PALACE,))
    assert status == 'completed' and state.effects == (LAYOUT_EFFECT + 'split',)


def test_a_later_unclear_map_result_cancels_the_destination_whatever_the_order():
    unclear = LioDestinationUnclear()
    for places in ((PALACE, unclear), (unclear, PALACE), (PALACE, unclear, PALACE), (unclear,)):
        button = taxi_params(run('怎么打车去故宫', '可以打车。', 'split', destinations=places)[1])
        assert (button['label'], button['parameters']) == ('打车', {}), places


TICKETS = ['g' * 43, 'h' * 43, 'i' * 43]


def test_every_normal_split_answer_offers_chips_from_the_table():
    # #1978: no payment or taxi topic any more still means two or three chips (a food question here)
    status, state = run('成都有什么好吃的', '火锅。\n\n再试试串串。', 'split', issue=TICKETS)
    assert status == 'completed'
    (_, labels), = run.last_messages.issued
    assert 2 <= len(labels) <= 3 and 'actions' in payload(state) and payload(state)['actions'] == []
    assert [chip['label'] for chip in payload(state)['chips']] == labels


def test_a_plan_answer_offers_the_save_chip_and_nothing_else_is_a_button():
    status, state = run('帮我规划北京三天行程', '第一天故宫。\n\n第二天长城。', 'split', issue=TICKETS)
    (_, labels), = run.last_messages.issued
    assert SAVE_CHIP[0] in labels and payload(state)['actions'] == []
    status, state = run('Plan a 3-day trip in Beijing', 'Day 1.\n\nDay 2.', 'split', locale='en', issue=TICKETS)
    assert SAVE_CHIP[1] in run.last_messages.issued[0][1]


class HintTools(Tools):
    def answer(self, worker, binding, inputs, **kwargs):
        yield LioLayout('split')
        yield FollowupHint('dates')
        yield self.text


def test_the_missing_fact_the_answer_asks_about_gets_answer_chips_first():
    runs = Service(MemoryRepository(), lambda _: True)
    messages = Messages('我想去北京玩', TICKETS)
    worker = RunWorker(scope='scope', messages=messages, runs=runs, provider=None, tools=HintTools('split', '好的。\n\n大概哪几天去？'),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
    outcome, = worker.process()
    assert outcome.status == 'completed'
    (_, labels), = messages.issued
    assert labels[:2] == ['我 12 月 5 日到', '还没定哪天到']
    # the hint is not text: the answer is exactly what the model wrote
    assert runs.snapshot(Binding('scope', 'chat', 'g', 'm', 'r', 1)).text == '好的。\n\n大概哪几天去？'


def test_the_answer_chips_survive_the_safety_lines_switch():
    # the safety-lines supplement used to share a variable name with the hint and overwrite it
    with patch.dict(os.environ, {'CJ_LIO_SAFETY_LINES': '1'}):
        runs = Service(MemoryRepository(), lambda _: True)
        messages = Messages('我想去北京玩', TICKETS)
        worker = RunWorker(scope='scope', messages=messages, runs=runs, provider=None, tools=HintTools('split', '好的。\n\n大概哪几天去？'),
                           drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
        outcome, = worker.process()
    assert outcome.status == 'completed'
    (_, labels), = messages.issued
    assert labels[:2] == ['我 12 月 5 日到', '还没定哪天到']


# --- #1989 (D-1): the entity effect --------------------------------------------------------------------------

def _doc():
    review = dict(status='approved', reviewer='t', reviewed_on='2026-11-27', note=None)
    return dict(version='g2c-places.1', city='beijing', places=[
        dict(id='pl_bj_gugong', city='beijing', category='attraction', name_zh='故宫博物院', name_en='The Palace Museum',
             aliases_zh=['故宫'], aliases_en=[], review=review)])


class CityTools(Tools):
    """The confirmed city is set on the worker that owns the message while the answer is made (as the planning path does)."""
    def __init__(self, city, text):
        super().__init__('split', text)
        self.city = city

    def answer(self, worker, binding, inputs, **kwargs):
        worker.lio_city_context = self.city
        yield from super().answer(worker, binding, inputs, **kwargs)


def _entity_run(city, switch):
    runs = Service(MemoryRepository(), lambda _: True)
    messages = Messages('故宫怎么走', TICKETS)
    worker = RunWorker(scope='scope', messages=messages, runs=runs, provider=None, tools=CityTools(city, '先去故宫。\n\n再坐地铁。'),
                       drafts=Drafts(), lio_original=lambda binding: LioOriginal('zh', None))
    env = {'CJ_LIO_ENTITIES': 'on'} if switch else {}
    with patch.dict(os.environ, env), patch('cj_message.lio_entities.library_docs', lambda name: [_doc()] if name else []):
        outcome, = worker.process()
    assert outcome.status == 'completed'
    return runs.snapshot(Binding('scope', 'chat', 'g', 'm', 'r', 1))


def test_entities_are_written_before_the_followups_for_a_confirmed_library_city():
    from types import SimpleNamespace
    state = _entity_run(SimpleNamespace(adcode='110000'), True)
    assert state.effects[0] == LAYOUT_EFFECT + 'split'
    assert state.effects[1].startswith('lio_entities:') and state.effects[2].startswith(FOLLOWUPS_EFFECT)
    assert '"pl_bj_gugong"' in state.effects[1] and '[2,4,' in state.effects[1]


def test_no_entity_effect_when_the_switch_is_off_or_there_is_no_library_city():
    from types import SimpleNamespace
    assert not any(e.startswith('lio_entities:') for e in _entity_run(SimpleNamespace(adcode='110000'), False).effects)
    assert not any(e.startswith('lio_entities:') for e in _entity_run(None, True).effects)
    assert not any(e.startswith('lio_entities:') for e in _entity_run(SimpleNamespace(adcode='330100'), True).effects)


def test_a_failing_library_never_fails_the_answer():
    from types import SimpleNamespace
    runs = Service(MemoryRepository(), lambda _: True)
    worker = RunWorker(scope='scope', messages=Messages('故宫怎么走', TICKETS), runs=runs, provider=None,
                       tools=CityTools(SimpleNamespace(adcode='110000'), '先去故宫。\n\n再坐地铁。'), drafts=Drafts(),
                       lio_original=lambda binding: LioOriginal('zh', None))

    def broken(name):
        raise RuntimeError('library unreadable')
    with patch.dict(os.environ, {'CJ_LIO_ENTITIES': 'on'}), patch('cj_message.lio_entities.library_docs', broken):
        outcome, = worker.process()
    assert outcome.status == 'completed'
