"""Unconfirmed bilingual values, explicit uncertainty, no automatic Memory/manual source."""
import base64
import json
import pytest

from cj_needs.domain import Command,InvalidInput
from cj_needs.preview import MODEL_VERSION,encode,preview,synthetic_extract


def extract(source):
    return json.loads(preview(synthetic_extract(source),message_id='original-message',run_id='original-run',source_text=source))


def test_explicit_bilingual_values_do_not_confirm_or_mix_subjects():
    source='We are 3; budget USD 1000.50 per person; paid USD 200; excludes international airfare; arrival 2026-11-02 09:30 Asia/Shanghai; fixed appointment for party 2026-11-03 10:00 Asia/Shanghai; this trip mother has a leg injury; remember I always avoid spicy'
    value=extract(source);fields=value['fields']
    assert value['version']=='NEEDS-preview.1' and value['confirmation']=='unconfirmed'
    assert base64.b64decode(value['source']['text_utf8_base64'])==source.encode()
    assert fields['budget_per_person']=={'state':'known','value':'1000.50'}
    assert fields['budget_paid']['value']=='200' and 'budget_total' not in fields
    assert fields['budget_includes']['value']==['excludes international airfare']
    assert fields['temporary_conditions'][0]['applies_to']==['companion:mother']
    assert fields['fixed_items'][0]['locked']=={'state':'known','value':True}
    assert fields['fixed_items'][0]['booking_status']=={'state':'missing'}
    assert fields['arrival']['date']['value']=='2026-11-02'
    assert value['deferred_memory_requests']==['remember I always avoid spicy']
    assert value['questions']==[]
    chinese=extract('本次3人；预算CNY1000每人；已付CNY100；不含国际机票；抵达2026-11-02 09:30 Asia/Shanghai；固定预约全体2026-11-03 10:00 Asia/Shanghai；本次母亲腿伤；请记住我长期不吃辣')
    assert chinese['fields']['party_size']['value']==3
    assert chinese['fields']['budget_basis']['value']=='per_person'
    assert chinese['fields']['temporary_conditions'][0]['applies_to']==['companion:mother']
    assert chinese['deferred_memory_requests']==['请记住我长期不吃辣']


def test_only_ambiguous_supplied_conditions_produce_questions():
    value=extract("budget USD 1000; I don't eat spicy; booked hotel for self")
    assert [q['reason'] for q in value['questions']]==['missing_basis','unclear_lifetime']
    assert 'budget_total' not in value['fields'] and 'budget_per_person' not in value['fields']
    assert value['fields']['fixed_items'][0]['locked']=={'state':'missing'}
    assert value['fields']['fixed_items'][0]['booking_status']=={'state':'known','value':'booked'}
    unknown=extract('dates undecided')
    assert unknown['fields']['arrival']['date']=={'state':'unknown'}
    assert unknown['fields']['arrival']['timezone']=={'state':'missing'}
    assert unknown['questions']==[]
    assert extract('arrival 2026-11-02')['fields']['arrival']['timezone']=={'state':'missing'}
    assert extract('fixed appointment tomorrow')['questions'][0]['reason']=='missing_subject'


def test_paid_currency_and_negation_do_not_become_assumed_amounts():
    value=extract('budget USD 1000 total; paid CNY 100')
    assert value['fields']['budget_total']['value']=='1000'
    assert value['fields']['budget_paid']=={'state':'uncertain','note':'paid CNY 100'}
    assert value['questions'][0]['reason']=='currency_mismatch'
    value=extract('not paid USD 200; not booked hotel for self')
    assert 'budget_paid' not in value['fields'] and 'fixed_items' not in value['fields']


@pytest.mark.parametrize('mutation', ['owner','source','clarification','known-question','memory'])
def test_model_cannot_supply_authority_or_unbound_sources(mutation):
    source='budget USD 1000 total'
    value=json.loads(synthetic_extract(source))
    if mutation=='owner':value['fields']['owner']='foreign'
    elif mutation=='source':value['source_kind']='manual'
    elif mutation=='clarification':value['unresolved']=[dict(field='fixed_items',reason='missing_subject',original_text='not in the accepted message')]
    elif mutation=='known-question':value['unresolved']=[dict(field='budget_basis',reason='missing_basis',original_text=source)]
    else:value['long_term_requests']=['invented long-term fact']
    with pytest.raises(InvalidInput):preview(encode(value),message_id='m',run_id='r',source_text=source)


def test_preview_cannot_be_written_as_manual_source():
    command=dict(action_id='a',needs_id='n',expected_version=0,
        source=dict(kind='unconfirmed_extraction',text='unconfirmed'),changes={'party_size':{'state':'known','value':3}})
    with pytest.raises(InvalidInput):Command(encode(command))
