import pytest
from cj_run.core import Binding,State,Event,advance,Conflict,DRAFT_OUTCOMES
from cj_run.scoped_result import effect,parse,descriptor
from types import SimpleNamespace

B=Binding('owner','chat','generation','message','run',1)


def add(state,kind,value=''):
    return advance(state,Event(B,state.sequence+1,str(state.sequence+1),kind,value),lambda _:True)


def test_both_results_are_distinct_original_effects_and_complete_only():
    for kind in ('clarification_required','expansion_required'):
        state=add(State(B),'started');state=add(state,'result_committed',effect(kind,'original:result'))
        assert state.effects==(effect(kind,'original:result'),) and state.draft_outcome is None
        assert state.scoped_result==(kind,'original:result') and kind not in DRAFT_OUTCOMES
        for forbidden,value in [('cancelled',''),('unknown',''),('text_delta','late'),('effect_committed','trip_proposal:p'),('draft_outcome','validation_failed'),('result_committed',effect(kind,'another'))]:
            with pytest.raises(Conflict):add(state,forbidden,value)
        state=add(state,'completed')
        pointer=descriptor(state,SimpleNamespace(receipt=SimpleNamespace(input_sha256='a'*64)))
        assert pointer==dict(version='RUN-scoped-result.1',kind=kind,result_id='original:result',message_id='message',run_id='run',input_sha256='a'*64)
        with pytest.raises(Conflict):add(state,'result_committed',effect(kind,'another'))


@pytest.mark.parametrize('kind,value',[('validation_failed','result'),('expansion_required','path/id'),('clarification_required',''),('clarification_required','a'*129)])
def test_result_payload_boundary(kind,value):
    with pytest.raises(ValueError):effect(kind,value)
    with pytest.raises(ValueError):Event(B,1,'1','result_committed','scoped_result:'+kind+':'+value)


def test_no_result_after_failure_proposal_cancel_or_unknown():
    for kind,value in [('draft_outcome','validation_failed'),('effect_committed','trip_proposal:p'),('cancelled',''),('unknown','')]:
        state=add(add(State(B),'started'),kind,value)
        with pytest.raises(Conflict):add(state,'result_committed',effect('clarification_required','result'))
    with pytest.raises(ValueError):Event(B,1,'1','effect_committed',effect('expansion_required','result'))
    assert parse(effect('expansion_required','a:b'))==('expansion_required','a:b')
