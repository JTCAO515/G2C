from datetime import date
import json
from types import SimpleNamespace
import pytest
from cj_api.lio_city import CityReference
from cj_api.lio_national_intake import parse,fields_for
from cj_needs.domain import InvalidInput


def sample(text='计划桂林三日豪华游，从2026-11-20开始，两个人'):
    fields=dict(arrival=dict(date=dict(state='known',value='2026-11-20')),
                party_size=dict(state='known',value=2))
    value=dict(version='LIO-planning-intake.1',intent='plan',reply='可以安排这趟旅行。',needs_tools=False,
        city=dict(query='桂林',normalized_name='桂林市',province=None,source_index=0,quote='桂林'),
        duration_days=3,extraction=dict(version='NEEDS-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),
        field_sources={k:[dict(source_index=0,quote=q)] for k,q in [('arrival.date','2026-11-20'),('duration_days','三日'),('party_size','两个人')]},
        current_request=text)
    return value,[SimpleNamespace(text=text,question_day=date(2026,11,11))]


def test_original_city_and_fields_are_model_data_then_server_checked():
    value,turns=sample();intake=parse(json.dumps(value,ensure_ascii=False),turns)
    city=CityReference('450300','桂林市','广西壮族自治区','桂林市','city','Asia/Shanghai')
    fields,result=fields_for(intake,city,message_id='original-message',run_id='original-run',source_text=turns[0].text)
    assert fields['arrival']['place']==dict(state='known',value='桂林市')
    assert fields['departure']['date']==dict(state='known',value='2026-11-22')
    assert fields['destination_timezone']==dict(state='known',value='Asia/Shanghai')
    assert fields['party_size']==dict(state='known',value=2)


@pytest.mark.parametrize('tail',['，不要保存','，先聊聊','; do not save','; show a draft only','; only if it is open'])
def test_old_nonpersistent_holds_override_model_publish_intent(tail):
    value,turns=sample('计划桂林三日豪华游，从2026-11-20开始，两个人'+tail)
    assert parse(json.dumps(value,ensure_ascii=False),turns).intent=='discuss'


def test_unbound_fields_and_mismatched_calendar_do_not_publish():
    value,turns=sample();value['field_sources']['arrival.date'][0]['quote']='2026-12-01'
    with pytest.raises(InvalidInput):parse(json.dumps(value,ensure_ascii=False),turns)
    value,turns=sample();value['extraction']['fields']['departure']=dict(date=dict(state='known',value='2026-11-25'))
    value['field_sources']['departure.date']=[dict(source_index=0,quote='2026-11-20')]
    parsed=parse(json.dumps(value,ensure_ascii=False),turns)
    with pytest.raises(InvalidInput):fields_for(parsed,CityReference('450300','桂林市','广西','桂林市','city','Asia/Shanghai'),message_id='m',run_id='r',source_text=turns[0].text)
