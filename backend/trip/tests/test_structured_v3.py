"""Production grammar/capability checks against the frozen #860 examples."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from cj_trip.structured_v3 import validate_document
from cj_trip.structured import validate_document as old_v1
from cj_trip.structured_v2 import validate_document as old_v2

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT / 'contracts/trip/structured-examples.3.json').read_bytes())


def materialize(case):
    value = deepcopy(FIXTURES['dated' if case.get('dated') else 'base'])
    for change in case['changes']:
        parent = value
        for part in change['path'][:-1]:
            parent = parent[part]
        if change.get('delete'):
            del parent[change['path'][-1]]
        else:
            parent[change['path'][-1]] = deepcopy(change['value'])
    return value


@pytest.mark.parametrize('name', ['base', 'dated'])
def test_frozen_calendar_examples_and_legacy_mutual_exclusion(name):
    value = deepcopy(FIXTURES[name])
    before = deepcopy(value)
    validate_document(value)
    assert value == before
    for legacy in (old_v1, old_v2):
        with pytest.raises(ValueError):
            legacy(value)


@pytest.mark.parametrize('case', FIXTURES['schema_accept'], ids=lambda c: c['name'])
def test_calendar_boundaries_and_reported_conflicts(case):
    value = materialize(case)
    before = deepcopy(value)
    validate_document(value)
    assert value == before


@pytest.mark.parametrize('case', FIXTURES['schema_reject'] + FIXTURES['semantic_reject'], ids=lambda c: c['name'])
def test_shape_and_calendar_semantic_rejections(case):
    with pytest.raises(ValueError):
        validate_document(materialize(case))


