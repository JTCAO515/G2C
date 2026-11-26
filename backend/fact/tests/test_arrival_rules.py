"""The server copy of the arrival rules is the App's file, generated from one source (#1730)."""
from datetime import timedelta
import importlib.util
import json
from pathlib import Path

import pytest

from cj_fact.arrival import RULES_PATH, load_rules, review_due
from cj_fact.policy import FactFailure

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'knowledge/arrival/arrival-rules.v1.json'
APP_COPY = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioArrivalRules.v1.json'


def test_server_and_app_copies_are_byte_identical_to_the_source():
    raw = SOURCE.read_bytes()
    assert RULES_PATH.read_bytes() == raw, 'server copy differs; run knowledge/arrival/sync_copies.py'
    assert APP_COPY.read_bytes() == raw, 'App copy differs; run knowledge/arrival/sync_copies.py'


def test_sync_script_check_mode_agrees():
    spec = importlib.util.spec_from_file_location('arrival_sync', ROOT / 'knowledge/arrival/sync_copies.py')
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    assert sync.stale() == []
    assert sync.main(['--check']) == 0


def test_server_copy_loads_with_the_app_shape():
    rules = load_rules()
    assert rules['data_version'] == 1
    assert {country['code'] for country in rules['countries']} >= {'US', 'GB'}
    assert all(policy['id'] and policy['checked_at'] for policy in rules['policies'])
    assert review_due(rules) - timedelta(days=rules['review_every_days']) == \
        __import__('datetime').date.fromisoformat(rules['checked_at'])


@pytest.mark.parametrize('mutate', [
    lambda raw: raw.replace(b'"data_version": 1', b'"data_version": 2', 1),
    lambda raw: raw.replace(b'{', b'{"data_version": 1, ', 1),  # duplicate key
    lambda raw: raw[:-20],
    lambda raw: b'',
])
def test_reshaped_or_broken_copy_fails_closed(tmp_path, mutate):
    path = tmp_path / 'arrival_rules.v1.json'
    path.write_bytes(mutate(RULES_PATH.read_bytes()))
    with pytest.raises(FactFailure):
        load_rules(path)


def test_missing_copy_fails_closed(tmp_path):
    with pytest.raises(FactFailure):
        load_rules(tmp_path / 'absent.json')


def test_source_is_valid_json_object():
    assert type(json.loads(SOURCE.read_text(encoding='utf-8'))) is dict
