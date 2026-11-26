"""The server copy of the Guangzhou business entries is the catalogue, byte for byte (#1859)."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path

import pytest

from cj_fact.business import CATALOGUE_PATH, TOPICS, by_id, by_topic, load_catalogue
from cj_fact.policy import FactFailure

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'knowledge/business/guangzhou.v1.json'


def validator():
    spec = importlib.util.spec_from_file_location('business_knowledge', ROOT / 'knowledge/business/validate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checked_day(doc):
    # Observe on the latest check day, not the wall clock, so CI never turns red on a calendar day.
    return max(date.fromisoformat(entry['checked_on']) for entry in doc['entries'])


def test_server_copy_is_byte_identical_to_the_catalogue():
    assert CATALOGUE_PATH.read_bytes() == SOURCE.read_bytes(), 'run python3 -B knowledge/business/validate.py --write'
    assert validator().SERVER_COPIES == {SOURCE: CATALOGUE_PATH}


def test_validator_fails_on_a_stale_copy(tmp_path, capsys):
    module = validator()
    assert module.main([]) == 0
    stale = tmp_path / 'copy.json'
    stale.write_bytes(SOURCE.read_bytes() + b' ')
    module.SERVER_COPIES = {SOURCE: stale}
    assert module.main([]) == 1
    assert 'out of date' in capsys.readouterr().err


def test_the_server_reads_what_the_validator_accepts():
    assert load_catalogue() == validator().load(SOURCE)


def test_entries_by_topic_carry_official_sources_and_check_day():
    doc = load_catalogue()
    today = checked_day(doc)
    for topic in ('trade_fair_registration', 'venue_transport', 'visa_channel'):
        entries = by_topic(doc, topic, today=today)
        assert [entry['topic'] for entry in entries] == [topic], topic
        assert entries[0]['source_urls'] and entries[0]['checked_on'] <= today.isoformat()
    # Fair payment has no S1 source yet (#1759), so the topic exists but nothing official is returned.
    assert by_topic(doc, 'business_payment', today=today) == []
    assert by_id(doc, 'business.guangzhou.visa-channel', today=today)['topic'] == 'visa_channel'
    assert by_id(doc, 'business.guangzhou.absent', today=today) is None


def test_entry_on_or_after_its_review_deadline_is_not_returned():
    doc = load_catalogue()
    entry = doc['entries'][0]
    deadline = date.fromisoformat(entry['expires_on'])
    assert by_id(doc, entry['id'], today=deadline - timedelta(days=1)) is entry
    assert entry in by_topic(doc, entry['topic'], today=deadline - timedelta(days=1))
    assert by_id(doc, entry['id'], today=deadline) is None
    assert entry not in by_topic(doc, entry['topic'], today=deadline)


@pytest.mark.parametrize('call', [
    lambda doc: by_topic(doc, 'visa_policy', today=date(2026, 11, 26)),
    lambda doc: by_topic(doc, None, today=date(2026, 11, 26)),
    lambda doc: by_topic(doc, 'visa_channel', today='2026-11-26'),
    lambda doc: by_id(doc, 'business.guangzhou.visa-channel', today='2026-11-26'),
    lambda doc: by_id(doc, 'business.guangzhou.absent', today=None),
])
def test_bad_arguments_fail_closed(call):
    with pytest.raises(FactFailure):
        call(load_catalogue())


def test_topics_match_the_validator():
    assert TOPICS == validator().TOPICS


@pytest.mark.parametrize('mutate', [
    lambda raw: raw.replace(b'"g2c-business-knowledge.1"', b'"g2c-business-knowledge.2"', 1),
    lambda raw: raw.replace(b'"guangzhou"', b'"shenzhen"', 1),
    lambda raw: raw.replace(b'{', b'{"version": "g2c-business-knowledge.1", ', 1),  # duplicate key
    lambda raw: raw.replace(b'"checked_on": "', b'"checked_on": "x', 1),
    lambda raw: raw.replace(b'"expires_on": "2026-12', b'"expires_on": "2026-10', 1),
    lambda raw: raw.replace(b'"topic": "', b'"topic": "x', 1),
    lambda raw: raw.replace(b'"source_urls": [', b'"source_urls": ["http://example.com/a", ', 1),
    lambda raw: raw.replace(b'"text_en": "', b'"text_en": " ', 1),
    lambda raw: raw.replace(b'"title"', b'"extra": 1, "title"', 1),
    lambda raw: raw[:-40],
    lambda raw: b'',
    lambda raw: b'NaN',
])
def test_broken_copy_fails_closed(tmp_path, mutate):
    path = tmp_path / 'business.json'
    path.write_bytes(mutate(CATALOGUE_PATH.read_bytes()))
    with pytest.raises(FactFailure):
        load_catalogue(path)


def test_missing_copy_fails_closed(tmp_path):
    with pytest.raises(FactFailure):
        load_catalogue(tmp_path / 'absent.json')
