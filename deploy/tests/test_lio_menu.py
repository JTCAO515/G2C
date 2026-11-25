"""MENU.1 menu explanation (#1583, M4 item 19 with entry 9): read once, explain at most twice, check every dish."""

from base64 import b64encode
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cj_api.lio_menu import (
    INGREDIENTS, LINES_PER_CALL, MAX_LINES, PROMPT_VERSION, RULES, VERSION, MemoryMenuCache, MenuRequest,
    MenuService, cache_key, checked_items, image_url, menu_lines, messages_for,
)
from cj_api.plugin_tools import PluginError
from cj_api.translation import MAX_MEDIA, supplier_unavailable
from cj_usage.menu_budget import MenuDuplicate, MenuLimit
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.translation_budget import IMAGE_MODEL, TranslationLimit


JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 64
MENU = '川味小馆\n热菜\n宫保鸡丁 ￥38\n麻婆豆腐 26元\n口□□肉 ¥4?\nKung Pao Chicken\n蛋炒饭 15/份\n'


def payload(media=JPEG, request_id=None):
    return dict(version=VERSION, request_id=request_id or str(uuid4()), media=b64encode(media).decode())


def dish(i, name, **changes):
    value = dict(i=i, kind='dish', name_zh=name, name_en='Dish', summary_en='A dish.', summary_zh='一道菜。',
                 ingredients_en='Rice', ingredients_zh='米饭', method_en='Fried', method_zh='炒',
                 portion_en='One plate', portion_zh='一盘', spice=0, contains={})
    value.update(changes)
    return value


def reply(*items):
    return json.dumps(dict(items=list(items)), ensure_ascii=False)


class Reader:
    def __init__(self, text=MENU):
        self.text = text
        self.calls = []

    def request(self, model, item, source, target, deadline, authorize):
        authorize()
        self.calls.append((model, item))
        return 'ocr-1', {'input_tokens': 1000, 'output_tokens': 200}, self.text

    def require_safe_text(self, value):
        assert 'secret' not in value


class Model:
    def __init__(self, answer=None, finish='stop'):
        self.answer = answer
        self.finish = finish
        self.messages = []

    def generate(self, messages, reserve):
        reserve()
        self.messages.append(messages)
        lines = json.loads(messages[1]['content'])
        if self.answer is not None:
            raw = self.answer(lines) if callable(self.answer) else self.answer
        else:
            raw = reply(*(dish(row['i'], row['text']) if row['text'] != '热菜' and '□' not in row['text']
                          else dict(i=row['i'], kind='unclear' if '□' in row['text'] else 'other')
                          for row in lines))
        return f'chatcmpl-{len(self.messages)}', {'input_tokens': 900, 'output_tokens': 800}, raw, self.finish


class Budget:
    def __init__(self, admits=True, limit_at=None):
        self.admitted = admits
        self.limit_at = limit_at
        self.begun, self.finished, self.operations = [], [], []

    def admits(self, scope):
        return self.admitted

    def operation(self, scope, request, calls):
        self.operations.append(calls)
        return ('menu', request, calls)

    def begin(self, operation, stage):
        if self.limit_at == stage:
            raise MenuLimit('daily menu allowance exhausted')
        self.begun.append(stage)

    def finish(self, operation, stage, supplier, usage):
        self.finished.append(stage)


class ImageBudget:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def operation(self, scope, request, modality, units):
        return (scope, request, modality, units)

    def begin(self, operation, stage, model):
        if self.error:
            raise self.error
        self.calls.append(('begin', operation[2], operation[3], model))

    def finish(self, operation, stage, model, supplier, usage):
        self.calls.append(('finish', model))


def service(reader=None, model=None, budget=None, image=None, cache=None):
    return MenuService(reader or Reader(), model or Model(), budget or Budget(), image or ImageBudget(),
                       cache or MemoryMenuCache())


def explain(svc, body=None):
    authorized = []
    result = svc.explain('scope-a', MenuRequest.model_validate(body or payload()), lambda: authorized.append(1))
    return result, authorized


# Lines

def test_lines_take_prices_off_and_drop_lines_without_chinese():
    lines, truncated = menu_lines(MENU)
    assert [line['text'] for line in lines] == ['川味小馆', '热菜', '宫保鸡丁', '麻婆豆腐', '口□□肉 ¥4?', '蛋炒饭']
    assert [line['price'] for line in lines] == [None, None, '¥38', '26元', None, '15/份']
    assert not truncated


def test_long_menus_are_cut_and_say_so():
    lines, truncated = menu_lines('\n'.join(f'菜{index}' for index in range(MAX_LINES + 5)))
    assert len(lines) == MAX_LINES and truncated
    assert MAX_LINES == 2 * LINES_PER_CALL


# Checking the model's answer

def test_a_dish_name_must_be_the_lines_own_text():
    lines = ['宫保鸡丁', '麻婆豆腐']
    checked = checked_items(reply(dish(0, '宫保 鸡丁'), dish(1, '鱼香肉丝')), lines)
    assert checked[0]['kind'] == 'dish' and checked[0]['name_zh'] == '宫保 鸡丁'
    assert checked[1] == {'kind': 'unclear'}


def test_absence_claims_are_blanked_and_ingredients_are_bounded():
    checked = checked_items(reply(dish(0, '蛋炒饭', summary_en='Peanut-free and safe for allergies.',
                                       summary_zh='不含花生。', ingredients_en='Rice, egg',
                                       contains={'egg': 'likely', 'soy': 'maybe', 'msg': 'likely'})),
                            ['蛋炒饭'])
    entry = checked[0]
    assert entry['summary_en'] == '' and entry['summary_zh'] == ''
    assert entry['ingredients_en'] == 'Rice, egg'
    assert entry['contains'] == {'egg': 'likely', 'soy': 'possible'}


@pytest.mark.parametrize('changes', [dict(spice=4), dict(spice='hot'), dict(spice=True), dict(contains=[]),
                                     dict(name_en=None), dict(name_zh=None)])
def test_a_dish_with_a_bad_field_becomes_unclear(changes):
    assert checked_items(reply(dish(0, '蛋炒饭', **changes)), ['蛋炒饭']) == {0: {'kind': 'unclear'}}


@pytest.mark.parametrize('raw', [
    'not json', '[]', '{"items": {}}', reply(dish(0, '蛋炒饭'), dish(0, '蛋炒饭')), reply(dish(2, '蛋炒饭')),
    reply(dict(i=0, kind='dessert')), reply(dish(0, '蛋炒饭'), dict(i=1, kind='other')),
    '{"items": [], "items": []}',
])
def test_anything_but_the_agreed_object_is_refused(raw):
    assert checked_items(raw, ['蛋炒饭']) is None


def test_the_model_sees_only_menu_text_and_the_fixed_rules():
    messages = messages_for(['宫保鸡丁', '蛋炒饭'])
    assert messages[0] == dict(role='system', content=RULES)
    assert json.loads(messages[1]['content']) == [dict(i=0, text='宫保鸡丁'), dict(i=1, text='蛋炒饭')]
    for ingredient in INGREDIENTS:
        assert ingredient in RULES
    assert '不写「安全」「不含」' in RULES


# Requests

@pytest.mark.parametrize('body', [
    payload(media=b'GIF89a' + b'\x00' * 16),
    payload(media=b'\xff\xd8\xff' + b'\x00' * MAX_MEDIA),
    dict(payload(), version='MENU.2'),
    dict(payload(), request_id='not-a-uuid-not-a-uuid-not-a-uuid-123'),
    dict(payload(), lang='en'),
    dict(payload(), media='!!!not base64!!!'),
])
def test_requests_are_one_jpeg_or_png_photo_and_nothing_else(body):
    with pytest.raises(ValidationError):
        MenuRequest.model_validate(body)


def test_image_url_keeps_the_photo_type():
    assert image_url(b64encode(JPEG).decode()).startswith('data:image/jpeg;base64,')
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16
    assert image_url(b64encode(png).decode()).startswith('data:image/png;base64,')


# Service

def test_one_photo_read_one_explanation_and_prices_from_the_photo():
    reader, model, budget, image = Reader(), Model(), Budget(), ImageBudget()
    result, authorized = explain(service(reader, model, budget, image))
    assert result['version'] == VERSION and result['truncated'] is False
    assert [(item['id'], item['kind'], item.get('name_zh'), item['price_text']) for item in result['items']] == [
        ('l0', 'dish', '川味小馆', None), ('l2', 'dish', '宫保鸡丁', '¥38'), ('l3', 'dish', '麻婆豆腐', '26元'),
        ('l4', 'unclear', None, None), ('l5', 'dish', '蛋炒饭', '15/份')]
    assert [call[0] for call in reader.calls] == [IMAGE_MODEL]
    assert image.calls == [('begin', 'image', 1, IMAGE_MODEL), ('finish', IMAGE_MODEL)]
    assert budget.operations == [1] and budget.begun == [0] and budget.finished == [0]
    assert len(model.messages) == 1 and len(authorized) >= 3
    sent = model.messages[0][1]['content']
    assert not any(price in sent for price in ('¥38', '26元', '15/份'))


def test_a_second_menu_with_the_same_dishes_uses_the_cache_and_no_model_call():
    cache, model = MemoryMenuCache(), Model()
    explain(service(model=model, cache=cache))
    again, budget = Model(), Budget()
    result, _ = explain(service(model=again, budget=budget, cache=cache))
    # The unclear line is never cached, so only it is asked about again.
    assert [json.loads(messages[1]['content']) for messages in again.messages] == [[dict(i=0, text='口□□肉 ¥4?')]]
    assert budget.operations == [1]
    assert [item['id'] for item in result['items']] == ['l0', 'l2', 'l3', 'l4', 'l5']
    assert cache.get(cache_key('宫保鸡丁'))['name_zh'] == '宫保鸡丁'
    assert PROMPT_VERSION == 1


def test_a_fully_cached_menu_makes_no_model_call():
    cache = MemoryMenuCache()
    reader = Reader('宫保鸡丁 38元\n蛋炒饭 15元')
    explain(service(reader=reader, cache=cache))
    model, budget = Model(), Budget()
    result, _ = explain(service(reader=Reader('宫保鸡丁 38元\n蛋炒饭 15元'), model=model, budget=budget,
                                cache=cache))
    assert model.messages == [] and budget.operations == []
    assert [item['name_zh'] for item in result['items']] == ['宫保鸡丁', '蛋炒饭']


def test_more_than_twenty_five_new_lines_take_two_calls():
    reader = Reader('\n'.join(f'菜品{index}号' for index in range(LINES_PER_CALL + 3)))
    model, budget = Model(), Budget()
    result, _ = explain(service(reader=reader, model=model, budget=budget))
    assert budget.operations == [2] and budget.begun == [0, 1]
    assert [len(json.loads(messages[1]['content'])) for messages in model.messages] == [LINES_PER_CALL, 3]
    assert len(result['items']) == LINES_PER_CALL + 3


def test_no_photo_is_read_when_today_is_used_up():
    reader = Reader()
    with pytest.raises(PluginError) as error:
        explain(service(reader=reader, budget=Budget(admits=False)))
    assert (error.value.status, error.value.code) == (429, 'quota_exceeded')
    assert reader.calls == []


def test_the_image_allowance_refuses_before_reading():
    reader = Reader()
    with pytest.raises(PluginError) as error:
        explain(service(reader=reader, image=ImageBudget(TranslationLimit('daily translation allowance exhausted'))))
    assert (error.value.status, error.value.code) == (429, 'quota_exceeded')
    assert reader.calls == []


def test_a_cut_off_answer_shows_nothing():
    with pytest.raises(PluginError) as error:
        explain(service(model=Model(finish='length')))
    assert (error.value.status, error.value.code) == (502, 'supplier_unavailable')


def test_a_refused_model_call_is_a_quota_answer():
    with pytest.raises(PluginError) as error:
        explain(service(budget=Budget(limit_at=0)))
    assert (error.value.status, error.value.code) == (429, 'quota_exceeded')


@pytest.mark.parametrize('failure,status', [(MenuDuplicate('again'), 409), (BudgetUnknown('unknown'), 503)])
def test_ledger_problems_stop_the_request(failure, status):
    class Failing(Budget):
        def begin(self, operation, stage):
            raise failure

    with pytest.raises(PluginError) as error:
        explain(service(budget=Failing()))
    assert error.value.status == status


def test_a_failed_read_is_a_supplier_error():
    class Broken(Reader):
        def request(self, *args):
            raise supplier_unavailable('supplier_http', 500)

    with pytest.raises(PluginError) as error:
        explain(service(reader=Broken()))
    assert (error.value.status, error.value.code) == (502, 'supplier_unavailable')
