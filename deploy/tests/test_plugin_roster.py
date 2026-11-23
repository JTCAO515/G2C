from hashlib import sha256
import json

import pytest

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


@pytest.mark.parametrize('valid', [True, False])
def test_hk_taxi_gets_only_the_configured_full_cohort(monkeypatch, valid):
    from types import SimpleNamespace

    from fastapi import FastAPI
    import uvicorn

    from cj_api import taxi_tools
    from deploy.hk.configuration import TAXI_INTERNAL_SUBJECTS
    from deploy.hk.entrypoint import api

    observed = []
    monkeypatch.setattr(taxi_tools, 'register_taxi_routes', lambda app, *, internal: observed.append(internal))
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: None)
    subjects = plugin_roster.generate_plugin_subjects()
    monkeypatch.setenv(TAXI_INTERNAL_SUBJECTS, json.dumps(subjects if valid else subjects[:-1]))
    api(SimpleNamespace(app=FastAPI, database=object))
    assert observed == [frozenset(subjects if valid else [])]


def test_deep_invalid_configuration_fails_closed_for_the_plugin():
    deep = '[' * 32_000 + 'null' + ']' * 32_000
    with pytest.raises(ValueError, match='exact_internal_plugin_roster_required'):
        plugin_roster.configured_plugin_subjects(deep)
