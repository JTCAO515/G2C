"""The App's attraction booking table is generated from the one JSON source (#1755)."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('attraction_rules', ROOT / 'knowledge/attractions/generate_ios.py')
rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rules)


def test_committed_swift_table_is_exactly_the_generated_one():
    doc = rules.load()
    assert rules.SWIFT.read_text(encoding='utf-8') == rules.render(doc), \
        'LioAttractionBookingRules.swift differs from booking-rules.v1.json; run knowledge/attractions/generate_ios.py'


def test_review_period_matches_the_app_constant():
    assert rules.load()['review_days'] == rules.app_review_days()


def test_every_rule_has_sources_a_check_day_and_both_languages():
    for rule in rules.load()['rules']:
        assert rule['sources'] and rule['checked_on'] >= '2026-11-01', rule['id']
        assert len(rule['limits']['en']) == len(rule['limits']['zh']), rule['id']
        assert len(rule['notes']['en']) == len(rule['notes']['zh']), rule['id']


def _broken(tmp_path, change):
    doc = json.loads(rules.SOURCE.read_text(encoding='utf-8'))
    change(doc['rules'][0])
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    return path


@pytest.mark.parametrize('change', [
    lambda r: r.update(sources=[]),
    lambda r: r.update(checked_on='2026-13-01'),
    lambda r: r.update(release_time='20:00', window_days=None),
    lambda r: r.update(requirement='not_required'),  # keeps a window and release time
    lambda r: r['notes']['zh'].pop(),
    lambda r: r.update(closed_weekdays=['funday']),
    lambda r: r.update(aliases=['Shanghai Museum']),  # already another rule's alias
    lambda r: r['sources'].append('ftp://example.invalid/x'),
    lambda r: r.update(extra=True),
])
def test_invalid_source_is_rejected(tmp_path, change):
    with pytest.raises(rules.Invalid):
        rules.load(_broken(tmp_path, change))


def test_a_changed_fact_without_regeneration_is_detected(tmp_path):
    doc = copy.deepcopy(rules.load())
    doc['rules'][0]['window_days'] += 1
    assert rules.render(doc) != rules.SWIFT.read_text(encoding='utf-8')
