from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest
from cj_trip.domain import packed
from cj_feasibility.trip_time_v3 import evaluate

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT / 'contracts/trip/structured-examples.3.json').read_bytes())


def codes(report):
    return {c.code: c.status for c in report.checks}


def test_undated_order_is_relative_and_date_checks_remain_unknown():
    raw = packed(FIXTURES['base'])
    report = evaluate(raw)
    assert report.version == 'FEASIBILITY-TRIP@3.0'
    assert report.content_sha256 == sha256(raw).hexdigest()
    assert report.status == 'UNKNOWN'
    assert codes(report)['ITEM_RELATIVE_ORDER'] == 'PASS'
    assert codes(report)['DATE_WEATHER'] == codes(report)['DATE_DAY_OPENING'] == 'UNKNOWN'
    assert json.loads(raw)['calendar'] == {'state': 'undated'}


def test_cross_day_is_explicit_not_inferred_from_clock_order():
    value = deepcopy(FIXTURES['base'])
    item = value['items'][0]
    item['schedule']['start']['time']['value'] = '23:00'
    item['schedule']['end']['time']['value'] = '00:30'
    assert codes(evaluate(packed(value)))['ITEM_RELATIVE_REVERSED'] == 'CONFLICT'
    item['schedule']['end']['day_index'] = 2
    assert codes(evaluate(packed(value)))['ITEM_RELATIVE_ORDER'] == 'PASS'


def test_unknown_clock_or_zone_is_not_defaulted():
    for name in ('time', 'timezone'):
        value = deepcopy(FIXTURES['base'])
        value['items'][0]['schedule']['start'][name] = {'state': 'unknown'}
        assert codes(evaluate(packed(value)))['ITEM_TIME_UNKNOWN'] == 'UNKNOWN'


def test_dated_instants_and_evidence_backed_soft_conflict():
    value = deepcopy(FIXTURES['dated'])
    raw = packed(value)
    assert codes(evaluate(raw))['ITEM_TIME_ORDER'] == 'PASS'
    value['date_checks'][1].update(state='conflict', reason='synthetic_closed_day',
                                  evidence_refs=['synthetic:original-receipt'])
    report = evaluate(packed(value))
    assert report.status == 'CONFLICT'
    assert codes(report)['DATE_DAY_OPENING'] == 'CONFLICT'
    assert value['items'] == FIXTURES['dated']['items']


def test_noncanonical_bytes_do_not_gain_a_report():
    with pytest.raises(ValueError):
        evaluate(json.dumps(FIXTURES['base'], ensure_ascii=False, indent=2).encode())
