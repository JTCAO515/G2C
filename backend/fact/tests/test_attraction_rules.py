"""The server copy of the attraction booking rules is the App table's source, byte for byte (#1826)."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path

import pytest

from cj_fact.attraction import RULES_PATH, load_rules, match, review_due
from cj_fact.policy import FactFailure

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'knowledge/attractions/booking-rules.v1.json'


def generator():
    spec = importlib.util.spec_from_file_location('attraction_rules', ROOT / 'knowledge/attractions/generate_ios.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_server_copy_is_byte_identical_to_the_source():
    assert RULES_PATH.read_bytes() == SOURCE.read_bytes(), 'run knowledge/attractions/generate_ios.py'
    assert generator().SERVER_COPY == RULES_PATH


def test_generator_check_covers_the_server_copy():
    assert generator().main(['--check']) == 0


def fresh_day(doc, rule):
    return date.fromisoformat(rule['checked_on'])


def test_matches_name_and_aliases_like_the_app():
    doc = load_rules()
    palace = next(rule for rule in doc['rules'] if rule['id'] == 'beijing.palace-museum')
    day = fresh_day(doc, palace)
    for name in ('故宫博物院', '故宫', 'Forbidden City', '  the forbidden city ', 'THE PALACE MUSEUM'):
        assert match(doc, name, today=day)['id'] == 'beijing.palace-museum', name
    # Tried in order: the Chinese name first, then the English one.
    assert match(doc, '', 'Terracotta Warriors', today=day)['id'] == 'xian.qin-mausoleum-museum'
    assert match(doc, '故宫附近的咖啡馆', 'Palace Museum Café', today=day) is None
    assert match(doc, today=day) is None


def test_rule_past_its_review_period_is_not_returned():
    doc = load_rules()
    palace = next(rule for rule in doc['rules'] if rule['id'] == 'beijing.palace-museum')
    due = review_due(doc, palace)
    assert due == date.fromisoformat(palace['checked_on']) + timedelta(days=doc['review_days'])
    assert match(doc, '故宫', today=due - timedelta(days=1)) is palace
    assert match(doc, '故宫', today=due) is None


def test_today_must_be_a_calendar_day():
    with pytest.raises(FactFailure):
        match(load_rules(), '故宫', today='2026-11-26')


@pytest.mark.parametrize('mutate', [
    lambda raw: raw.replace(b'"attraction-booking-rules.1"', b'"attraction-booking-rules.2"', 1),
    lambda raw: raw.replace(b'{', b'{"version": "attraction-booking-rules.1", ', 1),  # duplicate key
    lambda raw: raw.replace(b'"checked_on": "', b'"checked_on": "x', 1),
    lambda raw: raw[:-40],
    lambda raw: b'',
])
def test_broken_copy_fails_closed(tmp_path, mutate):
    path = tmp_path / 'rules.json'
    path.write_bytes(mutate(RULES_PATH.read_bytes()))
    with pytest.raises(FactFailure):
        load_rules(path)


def test_missing_copy_fails_closed(tmp_path):
    with pytest.raises(FactFailure):
        load_rules(tmp_path / 'absent.json')
