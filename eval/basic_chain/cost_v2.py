"""Original completion/coverage and unknown supplier price are separate.

Version1 remains unchanged. This reader computes no new authorization, releases
no hold, and never labels a supplier invoice paid from an estimated amount.
"""
from decimal import Decimal
from hashlib import sha256

from .cost import costs as legacy_costs
from .plan import Invalid,decode,is_sha,require

NIA_URL='https://en.nia.gov.cn/n147418/n147463/c183412/content.html'
ENDPOINTS={
    ('tool.lio_city.1','place'):frozenset({'https://restapi.amap.com/v3/config/district'}),
    ('tool.place','place'):frozenset({'https://restapi.amap.com/v3/place/text','https://restapi.amap.com/v3/place/detail'}),
    ('tool.place','route'):frozenset({'https://restapi.amap.com/v3/direction/walking','https://restapi.amap.com/v3/direction/driving'}),
    ('tool.weather','weather'):frozenset({'https://restapi.amap.com/v3/weather/weatherInfo'}),
    ('tool.fact','fact'):frozenset({NIA_URL}),
}


def _meter(component,expected):
    op=component['operation'];meter=component['meter']
    require(op==expected['operations'][op['operation_id']],'component differs from native inventory')
    require(op['kind']in('tool','model','memory'),'known registered operation kind required')
    command=meter['command'];receipt=meter['receipt']
    require(command['run_id']==expected['run_id']and command['kind']==op['kind']
            and command['operation_id']==op['operation_id']and command['attempt_id']==op['attempt_id'],
            'original Meter command differs')
    require(meter['state']=='settled'and meter['cancelled']is False and meter['exceeded']is False
            and receipt['attempt_id']==op['attempt_id']and receipt['unit']=='provider_call'
            and receipt['actual']==1,'original settled Meter receipt required')
    require(is_sha(command['input_digest']),'actual logical input digest required')
    return op,meter


def _original(component,expected):
    """Complete tool bytes, not a caller's tool-success or price label."""
    op,meter=_meter(component,expected);artifact=component['artifact']
    for key in ('source_commit','tool_implementation_sha256','scope_sha256','message_id','run_id'):
        require(artifact[key]==expected[key],'original source/owner/RUN differs')
    for key in ('operation_id','attempt_id','registration_id','operation_key'):
        require(artifact[key]==op[key],'original operation binding differs')
    receipt=meter['receipt'];command=meter['command']
    require(type(artifact['result_utf8'])is str and is_sha(artifact['response_sha256'])
            and sha256(artifact['result_utf8'].encode()).hexdigest()==artifact['response_sha256']
            and receipt['output']==len(artifact['result_utf8']),'complete original response/Meter differs')
    require(is_sha(command['input_digest'])and artifact['input_sha256']==command['input_digest'],
            'original logical input digest differs')
    if 'input_utf8'in artifact:
        require(sha256(artifact['input_utf8'].encode()).hexdigest()==command['input_digest'],'original input bytes differ')
    return op,meter,artifact


def _paid(row,component,expected):
    # Model billing uses its genuine original receipt and Meter metadata. This
    # does not certify model input/output payloads or a tool-result-following-
    # model chain. Those are separate #32/source proofs, not a price fallback.
    if row['kind']=='model':
        op,meter=_meter(component,expected);artifact=None
    else:op,meter,artifact=_original(component,expected)
    fee=component['fee']
    require(fee['ledger_id']==expected['ledger_id']==row['ledger_id']
            and fee['attempt_id']==row['attempt_id']==op['attempt_id']
            and fee['kind']==row['kind']and fee['state']==row['state']=='RECEIVED',
            'original financial identity/state differs')
    receipt=decode(fee['receipt_utf8'].encode())
    require(receipt==row['receipt'],'original supplier receipt differs')
    require(fee['actual_wire_input_sha256']==row['actual_wire_input_sha256'],'original financial wire differs')
    if row['kind']=='model':
        require(op['kind']in('model','memory'),'original model registration kind differs')
        require(is_sha(receipt['receipt_sha256'])and is_sha(receipt['output_sha256'])
                and meter['receipt']['receipt_id']=='live:'+receipt['receipt_sha256'],'model output/receipt identity differs')
    else:
        require(op['kind']=='tool'and artifact['version']=='G2C-tool-evidence.1','original tool output required')
        allowed=ENDPOINTS.get((op['registration_id'],row['kind']),frozenset())
        require(receipt==artifact['receipt'],'actual tool response receipt differs')
        require(receipt['endpoint']in allowed,'registered tool/kind/endpoint is not qualified')
        require(receipt['response_sha256']==artifact['response_sha256']
                and meter['receipt']['receipt_id']=='live:'+receipt['response_sha256']
                and row['actual_wire_input_sha256']==meter['command']['input_digest'],
                'tool actual input/response/receipt association differs')
    return artifact


def _local(component,expected):
    op,meter,artifact=_original(component,expected)
    require(op['registration_id']=='tool.visitor_fact'and op['kind']=='tool'
            and artifact['version']=='G2C-tool-evidence.1','explicit registered local visitor source required')
    receipt=artifact['receipt'];body=decode(artifact['result_utf8'].encode())
    logical=decode(artifact['input_utf8'].encode())
    require(receipt['endpoint']=='local:visitor-catalogue'and receipt['actual_cost_cny']=='0'
            and receipt['data_origin']=='maintainer_summary'
            and receipt['response_sha256']==artifact['response_sha256']
            and meter['receipt']['receipt_id']=='visitor-local:'+artifact['response_sha256']
            and body['version']in('FACT-result.2','FACT-result.3')and body['data_origin']=='maintainer_summary'
            and is_sha(body['catalogue_sha256'])and body['query']==logical['query']
            and body['request_ref']==logical['request_ref'],'positive local zero-cost source/result proof required')
    require(component['fee']['status']=='UNAVAILABLE'
            and component['fee']['reason']=='ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE',
            'local visitor must not hide an actual financial attempt')


def costs(accounting,pricing,components,expected):
    """C14 ordinary National path only; associated actor runs need a new scope.

    expected is this actual protected host/inventory binding, not client before
    state. Native full producer coverage is necessary and cannot be upgraded by
    response parsing. Missing original bytes remain UNKNOWN, including free ops.
    """
    result=legacy_costs(accounting,pricing)
    by_op={};gaps=[]
    for component in components:
        identity=component['operation']['operation_id']
        require(identity not in by_op,'duplicate native operation component')
        by_op[identity]=component
    require(set(by_op)==set(expected['operations']),'complete native operation census required')
    rows={row['attempt_id']:row for row in accounting['attempts']}
    accounted=set();proven_unpriced=[];free=[];corrected=0;known_free_prices=0
    for identity,component in by_op.items():
        op=component['operation'];attempt=op['attempt_id'];row=rows.get(attempt)
        try:
            if row is None:
                _local(component,expected);free.append(identity);continue
            accounted.add(attempt)
            _paid(row,component,expected)
            if row['kind']!='model'and row['priceable_tool_units']is None:
                hold=pricing['limits'][row['kind']]['hold_per_attempt_units']
                require(row['conservative_units']>=hold,'full original native hold must remain')
                corrected+=1
                if row['kind']=='fact':
                    require(hold==0 and row['receipt']['actual_cost_cny']=='0','registered NIA zero maximum is required')
                    body=decode(component['artifact']['result_utf8'].encode())
                    require(body['source_url']==NIA_URL and is_sha(body['original_sha256'])
                            and type(body['original_bytes'])is int and body['original_bytes']>0
                            and type(body['excerpts'])is list and bool(body['excerpts']),
                            'actual NIA public fetch original proof required')
                    known_free_prices+=1;free.append(identity)
                else:
                    require(hold>0,'unknown charged tool cannot use a zero maximum')
                    proven_unpriced.append(dict(operation_id=identity,attempt_id=attempt,kind=row['kind'],
                        original_hold_units=hold,conservative_units=row['conservative_units'],
                        price_status='UNKNOWN_PRICE_ORIGINAL_HOLD_RETAINED'))
        except (Invalid,KeyError,TypeError,ValueError):
            gaps.append(dict(operation_id=identity,reason='required_original_response_binding_unavailable'))
    require(accounted==set(rows),'all original financial attempts need their native operation')
    old_unknown_tools=result['unknown_tool_prices']
    result.update(version='LIO-basic-original-costs.2',legacy_v1_unresolved_count=result['unresolved_attempt_count'],
        legacy_v1_unknown_tool_prices=old_unknown_tools,unknown_tool_prices=old_unknown_tools-known_free_prices,
        unresolved_attempt_count=result['unresolved_attempt_count']-corrected,
        original_proof_gaps=gaps,registered_zero_cost_operations=free,unpriced_completed_tools=proven_unpriced)
    result['model_payload_scope']='ORIGINAL_BILLING_METADATA_ONLY_NOT_A_MODEL_PAYLOAD_OR_TOOL_CHAIN_CERTIFICATE'
    result['source_chain_certificate']='NOT_ISSUED_BY_FINANCIAL_READER'
    if gaps or not result['full_coverage']:
        result.update(full_coverage=False,conservative_cny=None,token_estimate_cny=None)
    elif not result['unknown_tool_prices']and not result['unknown_model_attempts']:
        result['token_estimate_cny']=str(Decimal(result['known_model_token_subtotal_cny'])+
                                         Decimal(result['known_tool_estimate_subtotal_cny']))
    result['accounting_status']='COVERED'if result['full_coverage']else'UNKNOWN_COVERAGE'
    result['price_status']='PARTLY_UNKNOWN'if result['unknown_tool_prices']or result['unknown_model_attempts']else'ESTIMATED_OR_REGISTERED_ZERO'
    result['execution_evidence_status']='COMPLETE_ORIGINALS'if not gaps and not result['unresolved_attempt_count']else'UNKNOWN'
    result['note']='Native original conservative occupation is not an estimate, invoice maximum, actual payment or released balance. Unknown price does not excuse missing original completion/coverage.'
    return result
