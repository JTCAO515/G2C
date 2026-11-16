"""Version2 monetary evidence controls only, never real service scores."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from eval.basic_chain.cost import costs as costs_v1
from eval.basic_chain.cost_v2 import costs
from eval.basic_chain.plan import Invalid

H='a'*64
PRICE=dict(scale=10_000_000,source_sha256=H,model_input_per_token=8,model_output_per_token=27,
    model_id='qwen3.8-flash',endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1',region='cn-beijing',
    limits={'model':{'hold_per_attempt_units':10_000_000},'place':{'hold_per_attempt_units':10_000_000},
            'fact':{'hold_per_attempt_units':0}})


def fixture(kind='place'):
    source='b'*40
    expected=dict(source_commit=source,tool_implementation_sha256=H,scope_sha256='c'*64,
                  message_id='original-mid',run_id='original-run',ledger_id='original-ledger')
    op=dict(operation_id='original-op',attempt_id='original-attempt',kind='tool'if kind!='model'else'model',
            registration_id={'place':'tool.lio_city.1','fact':'tool.fact','model':'model.tool_turn'}[kind],
            operation_key='original-step',input_erased=False)
    expected['operations']={op['operation_id']:deepcopy(op)}
    nia='https://en.nia.gov.cn/n147418/n147463/c183412/content.html'
    body=({'source_url':nia,'original_sha256':H,'original_bytes':100,
           'excerpts':[{'text':'synthetic'}]}if kind=='fact'else{'status':'confirmed'})
    raw=json.dumps(body,ensure_ascii=False);response_sha=sha256(raw.encode()).hexdigest()
    logical='{"version":"synthetic-input"}';logical_sha=sha256(logical.encode()).hexdigest()
    receipt=dict(endpoint='https://restapi.amap.com/v3/config/district'if kind=='place'else nia,
                 response_sha256=response_sha,actual_cost_cny='0'if kind=='fact'else'UNKNOWN')
    if kind=='model':
        receipt=dict(model_id=PRICE['model_id'],endpoint=PRICE['endpoint'],region=PRICE['region'],
                     usage=dict(prompt_tokens=10,completion_tokens=4,total_tokens=14),
                     receipt_sha256='d'*64,output_sha256=response_sha)
    wire_sha='e'*64 if kind=='model'else logical_sha
    row=dict(ledger_id=expected['ledger_id'],attempt_id=op['attempt_id'],operation_id=op['operation_id'],
        kind=kind,state='RECEIVED',conservative_units=200 if kind=='model'else 0 if kind=='fact'else 10_000_000,
        actual_wire_input_sha256=wire_sha,native_binding_verified=True,receipt=deepcopy(receipt),priceable_tool_units=None)
    meter=dict(state='settled',cancelled=False,exceeded=False,
        command=dict(run_id=expected['run_id'],operation_id=op['operation_id'],attempt_id=op['attempt_id'],
                     kind=op['kind'],input_digest=logical_sha),
        receipt=dict(attempt_id=op['attempt_id'],unit='provider_call',actual=1,output=len(raw),
            receipt_id='live:'+(receipt['receipt_sha256']if kind=='model'else response_sha)))
    artifact={k:expected[k]for k in('source_commit','tool_implementation_sha256','scope_sha256','message_id','run_id')}
    artifact.update({k:op[k]for k in('operation_id','attempt_id','registration_id','operation_key')})
    artifact.update(version='G2C-tool-evidence.1',receipt=deepcopy(receipt),response_sha256=response_sha,
                    result_utf8=raw,input_sha256=logical_sha,input_utf8=logical)
    fee=dict(ledger_id=expected['ledger_id'],attempt_id=op['attempt_id'],kind=kind,state='RECEIVED',
             actual_wire_input_sha256=wire_sha,receipt_utf8=json.dumps(receipt))
    component=dict(operation=op,meter=meter,fee=fee)
    if kind!='model':component['artifact']=artifact
    accounting=dict(attempts=[row],coverage='complete',producer_closure_verified=True,
                    closure_ref='actual-original-producer-and-ledger-proof',missing=[])
    return accounting,[component],expected


def test_v1_is_preserved_and_v2_separates_completed_district_from_unknown_price():
    account,components,expected=fixture()
    assert costs_v1(account,PRICE)['unresolved_attempt_count']==1
    result=costs(account,PRICE,components,expected)
    assert result['version']=='LIO-basic-original-costs.2'
    assert result['full_coverage']and result['unresolved_attempt_count']==0
    assert result['conservative_cny']=='1'and result['token_estimate_cny']is None
    assert result['actual_paid_cny']is None and result['price_status']=='PARTLY_UNKNOWN'
    assert result['unpriced_completed_tools'][0]['original_hold_units']==10_000_000


def test_zero_hold_p1_still_rejects_unknown_paid_tool():
    account,components,expected=fixture();account['attempts'][0]['conservative_units']=0
    with pytest.raises(Invalid):costs(account,PRICE,components,expected)


def test_registered_fact_zero_requires_actual_source_and_receipt():
    account,components,expected=fixture('fact')
    result=costs(account,PRICE,components,expected)
    assert result['full_coverage']and result['conservative_cny']=='0'
    assert result['token_estimate_cny']=='0'and result['unknown_tool_prices']==0
    assert result['registered_zero_cost_operations']==['original-op']
    components[0]['artifact']['result_utf8']='{}'
    bad=costs(account,PRICE,components,expected)
    assert not bad['full_coverage']and bad['conservative_cny']is None


@pytest.mark.parametrize('mutation',[
    lambda c:c['artifact'].update(scope_sha256='f'*64),
    lambda c:c['artifact'].update(source_commit='f'*40),
    lambda c:c['artifact'].update(tool_implementation_sha256='f'*64),
    lambda c:c['artifact'].update(result_utf8='not the actual original'),
    lambda c:c['meter'].update(state='pending'),
    lambda c:c['meter'].update(cancelled=True),
    lambda c:c['meter']['receipt'].update(receipt_id='another receipt'),
    lambda c:c['fee'].update(actual_wire_input_sha256='f'*64),
    lambda c:c.pop('artifact'),
])
def test_unknown_price_does_not_excuse_missing_original_or_wrong_binding(mutation):
    account,components,expected=fixture();mutation(components[0])
    result=costs(account,PRICE,components,expected)
    assert not result['full_coverage']and result['unresolved_attempt_count']==1
    assert result['observed_conservative_cny']=='1'


def test_completed_tool_proof_cannot_close_uncovered_background_or_wrong_census():
    account,components,expected=fixture();account.update(coverage='UNKNOWN',missing=[{'background':'uncovered'}])
    assert not costs(account,PRICE,components,expected)['full_coverage']
    expected['operations']['missing-op']=deepcopy(expected['operations']['original-op'])
    with pytest.raises(Invalid):costs(account,PRICE,components,expected)


def test_model_identity_and_usage_remain_strict_and_no_payload_certificate_is_issued():
    account,components,expected=fixture('model')
    result=costs(account,PRICE,components,expected)
    assert result['token_estimate_cny']=='0.0000188'and not result['unresolved_attempt_count']
    assert result['source_chain_certificate']=='NOT_ISSUED_BY_FINANCIAL_READER'
    account['attempts'][0].update(conservative_units=10_000_000)
    for receipt in(account['attempts'][0]['receipt'],):receipt['model_id']='not-qualified-model'
    components[0]['fee']['receipt_utf8']=json.dumps(account['attempts'][0]['receipt'])
    bad=costs(account,PRICE,components,expected)
    assert bad['unresolved_attempt_count']==1 and bad['token_estimate_cny']is None


def test_intent_is_never_upgraded_to_completed_when_hold_is_present():
    account,components,expected=fixture();account['attempts'][0].update(state='INTENT',receipt=None)
    result=costs(account,PRICE,components,expected)
    assert result['unresolved_attempt_count']==1 and not result['full_coverage']
