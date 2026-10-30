import json
import pytest
from cj_run.tool_turn import parse_turn


def value():return dict(version='MODEL-tool-turn.1',kind='tool',answer=None,calls=[dict(name='place',arguments={'version':'PLACE-query.1','query':{'kind':'Detail','provider_id':'SYNTH_EAST'}})])


def test_model_request_is_only_bounded_data_and_original_first_capture():
    turn=parse_turn(json.dumps(value()).encode(),{'place'})
    assert turn.answer_zh is None and turn.calls[0].name=='place'
    assert json.loads(turn.calls[0].arguments)['query']['provider_id']=='SYNTH_EAST'


def test_answer_requires_both_languages_and_has_no_calls():
    turn=parse_turn(json.dumps(dict(version='MODEL-tool-turn.1',kind='answer',answer={'zh':'合成答案','en':'Synthetic answer'},calls=[])).encode(),{'place'})
    assert turn.answer_zh=='合成答案' and not turn.calls


@pytest.mark.parametrize('change',[
    lambda x:x.update(owner='another'),lambda x:x.update(version='unknown'),
    lambda x:x.update(calls=[]),lambda x:x['calls'][0].update(name='http://metadata.internal'),
    lambda x:x['calls'][0].update(allow=True),lambda x:x.update(answer={'zh':'fake','en':'fake'}),
])
def test_model_cannot_supply_permissions_or_select_unregistered_exits(change):
    x=value();change(x)
    with pytest.raises(ValueError):parse_turn(json.dumps(x).encode(),{'place'})


def test_duplicate_fields_and_nan_are_rejected():
    raw=json.dumps(value()).encode()
    with pytest.raises(ValueError):parse_turn(raw.replace(b'"kind":',b'"kind":"answer","kind":',1),{'place'})
    x=value();x['calls'][0]['arguments']['nan']=float('nan')
    with pytest.raises(ValueError):parse_turn(json.dumps(x).encode(),{'place'})
