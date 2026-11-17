"""SM06 L0 controls: denial is not capability; no real App/provider witness."""
from hashlib import sha256
import json

import pytest

from eval.basic_chain.judge import semantic as legacy_semantic
from eval.basic_chain.native import observation
from eval.basic_chain.semantics_v2 import CODEBANK, semantic
from eval.tests.test_basic_joint_v2 import write_fixture, evaluate
from eval.tests.test_basic_native_v2 import fixture, add_read


DENIALS = (
    'I offer no travel assistance.',
    'I provide no travel planning services.',
    'Sorry, I offer no travel assistance.',
    'Unfortunately, I provide no travel planning services.',
    '**I offer no travel assistance.**',
    '*I provide no travel planning services.*',
    'I can plan travel. I provide no travel planning services.',
)


@pytest.mark.parametrize('answer', DENIALS)
def test_v2_rejects_first_person_travel_denial(answer):
    assert semantic('SM06', answer, 'en') == ('FAIL', 'travel_capability_denied')


@pytest.mark.parametrize('answer', (
    'I offer travel assistance.',
    'I provide travel planning services.',
    'I provide no booking services, but I can plan travel itineraries.',
    "I can help plan travel. The sentence 'I offer no travel assistance' is an example.",
))
def test_actual_positive_capability_is_not_rejected(answer):
    assert semantic('SM06', answer, 'en')[0] == 'PASS'


@pytest.mark.parametrize('locale', ('zh', 'en'))
def test_complete_frozen_positive_codebank_stays_accepted(locale):
    assert semantic('SM06', CODEBANK['cases'][locale]['raw_utf8'], locale) == (
        'PASS', 'complete_frozen_accepted_capabilities')


def test_old_rejection_unknown_and_other_gates_keep_their_oracle():
    for answer in ('I cannot help with travel planning.', 'I do not offer travel planning services.'):
        assert semantic('SM06', answer, 'en') == legacy_semantic('SM06', answer, 'en')
    assert semantic('SM06', 'Hello!', 'en')[0] == 'UNKNOWN'
    for gate, locale in (('SM02', 'en'), ('SM05', 'en'), ('SM06', 'zh')):
        assert semantic(gate, DENIALS[0], locale) == legacy_semantic(gate, DENIALS[0], locale)


def capability_joint(answer):
    """Bind the same synthetic answer through C's native parser and joint gate."""
    host, point, expected, plan, _ = fixture()
    step = next(s for s in plan['steps'] if s['gate_id'] == 'SM06' and s['locale'] == 'en')
    original = host['original']
    original['nonce'] = step['nonce']
    message = original['message']
    message.update(text=step['text'], locale='en', answer=answer,
        answer_sha256=sha256(answer.encode()).hexdigest())
    outer = original['outer_request']
    request = json.loads(outer['outer_utf8'])
    request.update(text=step['text'], locale='en')
    raw = json.dumps(request, ensure_ascii=False)
    digest = sha256(raw.encode()).hexdigest()
    outer.update(slot_id='en.SM06', outer_utf8=raw, input_sha256=digest)
    original['claim'].update(slot_id='en.SM06', input_sha256=digest)
    message['input_sha256'] = digest
    for exchange in original['http']['post_exchanges']:
        if exchange['phase'] == 'finished':
            exchange['input_sha256'] = digest
    add_read(host, expected)
    record = original['http']['actual_reads'][0]
    view = json.loads(record['response_utf8'])
    view['messages'] = [dict(message_id=message['message_id'], text=message['text'],
        answer=answer, status='completed', failure=None, trip=None)]
    record['response_utf8'] = json.dumps(view, ensure_ascii=False)
    record['response_sha256'] = sha256(record['response_utf8'].encode()).hexdigest()
    original['http']['read_exchanges'][1]['response_sha256'] = record['response_sha256']
    native = observation(host, point, expected, plan, step)
    _, _, _, _, ui, conversations, money = write_fixture()
    ui.update(gate_id='SM06', locale='en', nonce=step['nonce'], submitted_text=step['text'])
    ui['after']['transcript'] = [dict(question=step['text'], answer=answer, visible_failure=False)]
    return plan, step, point, native, ui, conversations, money


@pytest.mark.parametrize('answer', DENIALS[:2])
def test_original_false_pass_cannot_pass_the_joint_gate(answer):
    result = evaluate(capability_joint(answer))
    assert result['status'] == 'FAIL'
    assert 'travel_capability_denied' in result['reasons']


@pytest.mark.parametrize('answer,expected', (
    ('I provide travel planning services.', 'PASS'),
    ('I cannot help with travel planning.', 'FAIL'),
))
def test_joint_positive_and_old_rejection_controls(answer, expected):
    assert evaluate(capability_joint(answer))['status'] == expected
