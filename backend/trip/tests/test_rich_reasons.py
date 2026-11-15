import pytest

from cj_trip.rich_reasons import ProfileFact, brief, filter_reason_text, filter_reasons


def test_only_accepted_known_and_memory_references_remain_and_duplicates_are_reported():
    facts=tuple(ProfileFact(key,state,'value') for key,state in [('city','known'),('pace','memory'),
        ('duration_days','default'),('season','inferred'),('arrival','unknown'),('dietary','not_needed')])
    kept,removed=filter_reasons(['city','pace','duration_days','absent','season','arrival','dietary','city'],facts)
    assert kept==('city','pace')
    assert removed==('duration_days','absent','season','arrival','dietary','city')


@pytest.mark.parametrize('locale',['zh','en'])
def test_brief_code_template_separates_user_memory_and_defaults(locale):
    facts=(ProfileFact('city','known','成都 / Chengdu'),ProfileFact('pace','memory','轻松 / relaxed'),
           ProfileFact('duration_days','default','3'),ProfileFact('season','inferred','winter'),
           ProfileFact('arrival','unknown','unknown'))
    result=brief(facts,locale=locale,first_day_full=True)
    assert '成都 / Chengdu' in result and '轻松 / relaxed' in result and '3' in result
    assert 'winter' not in result and 'unknown' not in result
    assert ('按你说的' if locale=='zh' else 'what you said') in result
    assert ('已保存' if locale=='zh' else 'saved preferences') in result
    assert ('默认' if locale=='zh' else 'defaults') in result
    assert ('排满第一天' if locale=='zh' else 'full first day') in result


def test_default_only_is_not_quoted_as_a_user_statement_and_input_is_unchanged():
    facts=(ProfileFact('city','default','北京'),)
    text=brief(facts,locale='zh')
    assert '按你说的' not in text and '默认' in text and facts[0].state=='default'
    with pytest.raises(ValueError):brief(facts+facts,locale='zh')


@pytest.mark.parametrize('bad_state',['default','inferred','unknown','not_needed'])
def test_invalid_basis_removes_prose_even_when_another_factor_is_valid(bad_state):
    facts=(ProfileFact('interests','known','history'),ProfileFact('pace',bad_state,'relaxed'))
    text='Synthetic proposed sentence referring to both factors.'
    assert filter_reason_text(text,['interests','pace'],facts)==(None,('interests',),('pace',))
    assert filter_reason_text(text,['absent'],facts)==(None,(),('absent',))


def test_valid_prose_is_preserved_and_absent_prose_is_not_invented():
    facts=(ProfileFact('interests','known','history'),ProfileFact('pace','memory','relaxed'))
    text='Synthetic proposed sentence with valid factor references.'
    assert filter_reason_text(text,['interests','pace'],facts)==(text,('interests','pace'),())
    assert filter_reason_text(None,['interests'],facts)==(None,('interests',),())
    assert filter_reason_text('Generic unpersonalized note.',[],facts)==('Generic unpersonalized note.',(),())
