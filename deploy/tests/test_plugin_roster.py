from hashlib import sha256
import json

import pytest

from cj_strict_json import compact
from deploy.hk import plugin_roster
from deploy.hk.demo_login import invitation_subject


def test_plugins_share_the_full_g2c_subjects_without_the_other_cohort():
    subjects = plugin_roster.generate_plugin_subjects()
    expected = {
        'm4-synthetic-demo-' + sha256(f'G2C@{number:02d}'.encode('ascii')).hexdigest()[:12]
        for number in range(1, 100)
    }
    excluded = {invitation_subject(f'CJ_Tester@{number:02d}') for number in range(1, 100)}
    assert len(subjects) == len(expected) == 99
    assert set(subjects) == expected
    assert not expected & excluded
    assert plugin_roster.configured_plugin_subjects(json.dumps(subjects[::-1])) == expected


@pytest.mark.parametrize('change', ['shorter', 'duplicate', 'extra', 'replace', 'non_string', 'object'])
def test_configuration_rejects_a_different_plugin_roster(change):
    good = plugin_roster.generate_plugin_subjects()
    other = invitation_subject(f'CJ_Tester@{1:02d}')
    bad = {
        'shorter': good[:-1],
        'duplicate': [*good[:-1], good[0]],
        'extra': [*good, other],
        'replace': [*good[:-1], other],
        'non_string': [*good[:-1], None],
        'object': {'subjects': good},
    }
    with pytest.raises(ValueError, match='exact_internal_plugin_roster_required'):
        plugin_roster.configured_plugin_subjects(json.dumps(bad[change]))


def test_translation_admits_only_the_existing_cohort_and_three_original_named_accounts(monkeypatch):
    cohort = plugin_roster.generate_plugin_subjects()
    named = [cohort[0], 'fixture-c-zh', 'fixture-c-en']
    extra = sorted(set(named) - set(cohort))
    monkeypatch.setattr(plugin_roster, 'EXTRA_TRANSLATION_SUBJECTS_SHA256', sha256(compact(extra)).hexdigest())
    complete = sorted(set(cohort) | set(named))
    assert len(complete) == 101
    assert plugin_roster.configured_translation_subjects(json.dumps(cohort)) == set(cohort)
    assert plugin_roster.configured_translation_subjects(json.dumps(complete[::-1])) == set(complete)
    with pytest.raises(ValueError, match='exact_internal_plugin_roster_required'):
        plugin_roster.configured_plugin_subjects(json.dumps(complete))
    for wrong in (cohort[1:] + extra, cohort + extra[:1], complete + [named[0]],
                  cohort + extra[:1] + [invitation_subject('CJ_Tester@01')]):
        with pytest.raises(ValueError, match='exact_internal_translation_roster_required'):
            plugin_roster.configured_translation_subjects(json.dumps(wrong))


@pytest.mark.parametrize('configuration', ['valid', 'other_subject', 'missing_key', 'public_counts'])
def test_hk_taxi_only_arms_with_the_full_cohort_and_private_counter(monkeypatch, tmp_path, configuration):
    from fastapi import FastAPI

    from deploy.hk import taxi_runtime
    from deploy.hk.configuration import DIDI_MCP_KEY, TAXI_INTERNAL_SUBJECTS

    enabled = configuration == 'valid'
    database = object()
    checked = []
    registered = []
    subject_list = plugin_roster.generate_plugin_subjects()
    counts = tmp_path / 'plugin-state' / 'taxi.sqlite'
    counts.parent.mkdir(mode=0o700)
    counts.touch(mode=0o600 if configuration != 'public_counts' else 0o644)
    monkeypatch.setenv(TAXI_INTERNAL_SUBJECTS, json.dumps(
        subject_list if configuration != 'other_subject'
        else [*subject_list[:-1], invitation_subject(f'CJ_Tester@{7:02d}')]))
    if configuration != 'missing_key':
        monkeypatch.setenv(DIDI_MCP_KEY, 'dummy-test-value')
    else:
        monkeypatch.delenv(DIDI_MCP_KEY, raising=False)

    def checker(auth, db, *, selected_subjects):
        assert db is database
        checked.append(selected_subjects)
        return object()

    monkeypatch.setattr(taxi_runtime, 'account_checker_for', checker)
    monkeypatch.setattr(taxi_runtime, 'register_taxi_routes', lambda app, **kw: registered.append(kw))
    taxi_runtime.register_runtime_taxi(FastAPI(), object(), database, counts_path=counts)

    if enabled:
        assert checked == [frozenset(subject_list)]
        assert registered[0]['internal'] == frozenset(subject_list)
        assert registered[0]['calls'].path == counts
    else:
        assert checked == [] and registered == [{}]


def test_deep_invalid_configuration_fails_closed_for_the_plugin():
    deep = '[' * 32_000 + 'null' + ']' * 32_000
    with pytest.raises(ValueError, match='exact_internal_plugin_roster_required'):
        plugin_roster.configured_plugin_subjects(deep)
