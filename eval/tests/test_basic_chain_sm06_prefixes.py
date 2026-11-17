"""L0 regression controls for reported speech and prefixed SM06 denials."""
import pytest

from backend.tests.test_basic_chain_sm06_denials import capability_joint
from eval.basic_chain.semantics_v2 import semantic
from eval.tests.test_basic_joint_v2 import evaluate


@pytest.mark.parametrize('prefix',[
    'Sorry — ', 'Sorry: ', 'Unfortunately – ', 'Apologies; ',
    'To be clear, ', 'Please note: ', '## ', '> ', '- ', '**Sorry:** ',
])
@pytest.mark.parametrize('denial',[
    'I offer no travel assistance.', 'I provide no travel planning services.',
])
def test_normal_prefixes_cannot_turn_the_same_denial_into_capability(prefix,denial):
    answer=prefix+denial
    assert semantic('SM06',answer,'en')==('FAIL','travel_capability_denied')
    result=evaluate(capability_joint(answer))
    assert result['status']=='FAIL'
    assert 'travel_capability_denied'in result['reasons']


@pytest.mark.parametrize('answer',[
    "I can help plan travel. The sentence 'I offer no travel assistance' is an example.",
    'I provide travel planning services. The phrase “I offer no travel assistance” is only a quotation.',
    'I provide travel planning services at no cost.',
    'I provide no-cost travel planning services.',
    'I offer not only travel planning but also itinerary editing.',
    "I offer 'travel assistance'.", 'I provide no booking services, but I can plan travel itineraries.',
])
def test_positive_assertions_and_quoted_examples_are_kept(answer):
    assert semantic('SM06',answer,'en')[0]=='PASS'
    assert evaluate(capability_joint(answer))['status']=='PASS'


@pytest.mark.parametrize('answer',[
    "Sorry: I offer no 'travel assistance'.",
    'Sorry — I provide no “travel planning services”.',
])
def test_quotes_around_the_object_do_not_hide_an_asserted_denial(answer):
    assert semantic('SM06',answer,'en')[0]=='FAIL'
    assert evaluate(capability_joint(answer))['status']=='FAIL'


def test_a_quoted_clause_alone_is_not_a_positive_capability_assertion():
    answer='“I provide no travel planning services.”'
    assert semantic('SM06',answer,'en')[0]=='UNKNOWN'
    assert evaluate(capability_joint(answer))['status']=='UNKNOWN'


@pytest.mark.parametrize('answer',[
    'I offer absolutely no travel assistance.',
    'I provide no help with travel planning.',
    'I offer neither travel assistance nor travel planning.',
    'I offer no assistance with travel planning.',
    'I can plan travel. My policy is "I provide no travel planning services."',
    'My policy is "I offer no travel assistance." I can plan travel.',
])
def test_unqualified_denials_and_self_quoted_policies_cannot_pass(answer):
    assert semantic('SM06',answer,'en')[0]=='FAIL'
    assert evaluate(capability_joint(answer))['status']=='FAIL'


@pytest.mark.parametrize('answer',[
    'I can plan travel. I currently offer no travel assistance.',
    'I can plan travel. I currently provide no travel planning services.',
    'My policy is the phrase "I offer no travel assistance." I can plan travel.',
    'I can plan travel. My answer is the sentence "I provide no travel planning services."',
])
def test_modified_self_denials_and_named_self_quotations_cannot_pass(answer):
    assert semantic('SM06',answer,'en')[0]=='FAIL'
    assert evaluate(capability_joint(answer))['status']=='FAIL'


@pytest.mark.parametrize('answer',[
    'I offer travel planning, not bookings.',
    'I provide travel planning services with no booking or payment service.',
])
def test_denial_of_an_unrelated_service_does_not_deny_travel_planning(answer):
    assert semantic('SM06',answer,'en')[0]=='PASS'
    assert evaluate(capability_joint(answer))['status']=='PASS'
