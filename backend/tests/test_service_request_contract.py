"""SERVICE-REQUEST@1 examples run against the executable grammar (#1768)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/service_request'))
from cj_service_request.contract import (  # noqa: E402
    EVIDENCE, STATES, TERMINAL, TRANSITIONS, InvalidInput, InvalidTransition, check_transition, parse_submission)

EXAMPLES = ROOT / 'contracts/service-request/examples'
POS = json.loads((EXAMPLES / 'v1-positive.json').read_text())
NEG = json.loads((EXAMPLES / 'v1-negative.json').read_text())


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


@pytest.mark.parametrize('value', POS['submissions'])
def test_positive_submission(value):
    sub = parse_submission(raw(value))
    assert sub.original == raw(value)
    shared = sub.shared_with_escort()
    assert 'note' not in shared and 'contact_phone' in shared
    assert ('counterpart' in shared) == (value['counterpart'] is not None)


@pytest.mark.parametrize('case', NEG['submissions'], ids=lambda c: c['reason'])
def test_negative_submission(case):
    with pytest.raises(InvalidInput):
        parse_submission(json.dumps(case['submission']).encode('ascii'))


@pytest.mark.parametrize('body', [
    raw(POS['submissions'][0])[:-1] + b',"note":""}',  # duplicate key
    raw(POS['submissions'][0]).replace(b'"note": ""', b'"note": "\\u0000"'),
    b'\xff' + raw(POS['submissions'][0]),
    b'[]',
    raw({**POS['submissions'][0], 'note': 'x' * 9000}),
])
def test_negative_bytes(body):
    with pytest.raises(InvalidInput):
        parse_submission(body)


@pytest.mark.parametrize('t', POS['transitions'])
def test_positive_transition(t):
    check_transition(*t)


@pytest.mark.parametrize('t', NEG['transitions'], ids=lambda t: t[4])
def test_negative_transition(t):
    with pytest.raises((InvalidInput, InvalidTransition)):
        check_transition(*t[:4])


def test_state_machine_shape():
    assert len(STATES) == 11 and set(EVIDENCE) == set(STATES) - {'draft'}
    for state in TERMINAL - {'outcome_unknown'}:
        assert state not in TRANSITIONS
    for targets in TRANSITIONS.values():
        assert targets <= set(STATES) - {'draft', 'user_confirmed', 'submitted'}


def test_contract_lists_every_state():
    text = (ROOT / 'contracts/service-request/V1.md').read_text()
    for state in STATES:
        assert f'`{state}`' in text
