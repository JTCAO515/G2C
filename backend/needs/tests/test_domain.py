import json
import os
import time
import pytest
from cj_needs import Command, InvalidInput
from helpers import command, known, event


def test_partial_and_four_states_no_defaults():
    fields = {'party_size': {'state':'missing'}, 'budget_total': {'state':'unknown'},
              'pace': {'state':'uncertain','note':'也许慢一些 / maybe slow'}, 'budget_per_person': known('0.00')}
    assert command(changes=fields).data['changes'] == fields
    assert 'budget_currency' not in command(changes=fields).data['changes']


@pytest.mark.parametrize('field,value', [
    ('party_size', known(0)), ('party_size', known(True)), ('budget_total', known(0)),
    ('budget_total', known('-1')), ('budget_currency', known('usd')),
    ('destination_timezone', known('unknown/place')), ('owner', 'other'),
    ('pace', {'state':'unknown','value':'slow'}),
    ('arrival', event(date='2026-02-30')), ('arrival', event(time='24:00')),
    ('arrival', event(time='09:00+08:00')),
])
def test_invalid_fields(field, value):
    with pytest.raises(InvalidInput): command(changes={field:value})


@pytest.mark.parametrize('raw', [b'{"action_id":"x","action_id":"y"}', b'\xff', b'{"x":NaN}', b'[]'])
def test_strict_original_json(raw):
    with pytest.raises(InvalidInput): Command(raw)


@pytest.mark.parametrize('source', [{'kind':'run','text':'x','run_id':'r'},
                                   {'kind':'message','text':'x'}, {'kind':'manual','text':'x','allow':True}])
def test_unbound_source_rejected(source):
    obj = command().data; obj['source'] = source
    with pytest.raises(InvalidInput): Command(json.dumps(obj).encode())


def test_local_dates_survive_device_timezone_change():
    raw = command(changes={'arrival':event(), 'overseas_departure':event('2026-11-01','17:30','America/Los_Angeles')}).raw
    old = os.environ.get('TZ')
    try:
        for tz in ('UTC', 'Pacific/Honolulu', 'Asia/Tokyo'):
            os.environ['TZ'] = tz; time.tzset()
            assert Command(raw).data['changes']['arrival']['date'] == known('2026-11-02')
            assert Command(raw).data['changes']['arrival']['time'] == known('09:30')
    finally:
        if old is None: os.environ.pop('TZ', None)
        else: os.environ['TZ'] = old
        time.tzset()


def test_decoded_mutation_cannot_change_command():
    c = command(); c.data['changes']['party_size'] = known(99)
    assert c.data['changes']['party_size'] == known(3)


def test_surrogate_and_leap_second_rejected():
    with pytest.raises(InvalidInput):
        obj = command().data
        obj['source']['text'] = chr(0xd800)
        Command(json.dumps(obj).encode())
    with pytest.raises(InvalidInput): command(changes={'arrival':event(time='23:59:60')})


def test_published_contract_examples():
    from pathlib import Path
    examples=json.loads((Path(__file__).resolve().parents[3]/'contracts/needs/examples.json').read_text())
    for obj in examples['valid']: Command(json.dumps(obj,ensure_ascii=False).encode())
    for obj in examples['invalid']:
        with pytest.raises(InvalidInput): Command(json.dumps(obj,ensure_ascii=False).encode())
