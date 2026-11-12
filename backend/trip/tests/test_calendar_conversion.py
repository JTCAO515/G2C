from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import pytest

from cj_trip.calendar_conversion import DateConvert, converted_content
from cj_trip.domain import Conflict, Proposal, packed

ROOT = Path(__file__).resolve().parents[3]
TRIP = json.loads((ROOT / 'contracts/trip/structured-examples.3.json').read_bytes())
MESSAGE = json.loads((ROOT / 'contracts/message/trip-send-examples.2.json').read_bytes())


def test_date_input_keeps_original_bytes_and_does_not_parse_natural_language_twice():
    raw = packed(MESSAGE['conversion_input'])
    value = DateConvert.parse(raw)
    assert value.raw == raw
    assert value.start_date == date(2026, 12, 1)
    assert value.question_day == date(2026, 11, 12)
    assert value.quote == '12月1日出发'
    assert json.loads(value.source_reference)['input_sha256'] == sha256(packed(MESSAGE['canonical_message'])).hexdigest()
    assert json.loads(value.source_reference)['input_sha256'] != sha256(packed(MESSAGE['outer_message'])).hexdigest()


@pytest.mark.parametrize('change', [
    lambda v: v.update(start_date='tomorrow'),
    lambda v: v.update(expected_version=1.0),
    lambda v: v['date_source'].update(question_day='2026-02-30'),
    lambda v: v['date_source'].update(quote=''),
    lambda v: v.update(owner='forged'),
])
def test_bad_conversion_commands_reject(change):
    value = deepcopy(MESSAGE['conversion_input'])
    change(value)
    with pytest.raises(ValueError):
        DateConvert.parse(packed(value))


def test_conversion_changes_only_calendar_days_and_checks():
    original = deepcopy(TRIP['base'])
    before = packed(original)
    checks = deepcopy(TRIP['dated']['date_checks'])
    result = converted_content(original, date(2026, 12, 1), checks, MESSAGE['needs_basis']['fields']['fixed_items'])
    assert result.content is not None and not result.conflicts
    value = json.loads(result.content)
    assert [d['date'] for d in value['days']] == ['2026-12-01', '2026-12-02', '2026-12-03']
    for field in ('items', 'sources', 'title', 'content_version'):
        assert value[field] == original[field]
    assert packed(original) == before
    Proposal('conversion-shape', 'demo-trip', 1, 'calendar-conversion', 9999999999, result.content)


def test_hard_original_fixed_date_conflict_produces_no_content():
    fields = deepcopy(MESSAGE['needs_basis']['fields']['fixed_items'])
    fields[0]['start']['date'] = dict(state='known', value='2026-12-02')
    result = converted_content(TRIP['base'], date(2026, 12, 1), TRIP['dated']['date_checks'], fields)
    assert result.content is None
    assert result.conflicts[0]['kind'] == 'hard_fixed'
    assert result.conflicts[0]['item_ids'] == ['hotel-meetup']


def test_soft_closure_retains_schedule_and_returns_original_check_evidence():
    checks = deepcopy(TRIP['dated']['date_checks'])
    checks[1].update(state='conflict', reason='synthetic_closure', evidence_refs=['synthetic:opening'])
    result = converted_content(TRIP['base'], date(2026, 12, 1), checks, [])
    assert result.content is not None
    assert json.loads(result.content)['items'] == TRIP['base']['items']
    assert result.conflicts[0]['kind'] == 'date_dependent'
    assert result.conflicts[0]['evidence_refs'] == ['synthetic:opening']
    Proposal('soft-shape', 'demo-trip', 1, 'calendar-conversion', 9999999999, result.content)


def test_dated_or_overflow_is_not_an_implicit_replan():
    with pytest.raises(Conflict):
        converted_content(TRIP['dated'], date(2026, 12, 1), TRIP['dated']['date_checks'], [])
    with pytest.raises(ValueError):
        converted_content(TRIP['base'], date(9999, 12, 31), TRIP['dated']['date_checks'], [])
