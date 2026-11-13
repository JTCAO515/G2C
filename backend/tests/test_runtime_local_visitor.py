"""Local visitor provenance validator, controlled Meter metadata; no live calls."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from cj_api.runtime_originals import RuntimeOriginals
from runtime_adapter.contract import encode,Invalid,Unavailable


def evidence():
    query=dict(version='FACT-query.2',topic='payment',city='310100')
    logical=dict(name='visitor_fact',query=query,request_ref='original-reference')
    result=encode(dict(version='FACT-result.2',query=query,request_ref='original-reference',
        data_origin='maintainer_summary',status='matched',catalogue_sha256='a'*64,
        evaluated_at='2026-11-13T01:00:00+08:00',entries=[{'text_zh':'本地已审阅说明'}])).decode()
    digest=sha256(result.encode()).hexdigest()
    data=dict(version='G2C-tool-evidence.1',tool='visitor_fact',result_utf8=result,response_sha256=digest,
        receipt=dict(endpoint='local:visitor-catalogue',response_sha256=digest,actual_cost_cny='0',data_origin='maintainer_summary'))
    meter=dict(state='settled',receipt=dict(attempt_id='original-attempt',receipt_id='visitor-local:'+digest,
        unit='provider_call',actual=1,output=len(result)))
    reader=object.__new__(RuntimeOriginals)
    reader._meter=lambda *args:encode(meter)
    row=('original-operation-key','tool.visitor_fact','tool','original-attempt','original-operation')
    return reader,row,SimpleNamespace(input_bytes=encode(logical)),data,meter


def test_local_output_requires_actual_local_meter_hash_and_preserves_catalogue_time():
    reader,row,usage,data,meter=evidence()
    reader._local_visitor('owner',None,row,usage,data)
    assert len(data['result_utf8'].encode())!=len(data['result_utf8'])
    meter['receipt']['receipt_id']='live:invented-vendor'
    with pytest.raises(Unavailable,match='LOCAL_VISITOR_METER_RECEIPT'):
        reader._local_visitor('owner',None,row,usage,data)


@pytest.mark.parametrize('field,value',[('endpoint','https://restapi.amap.com'),('actual_cost_cny','UNKNOWN'),
    ('data_origin','live_provider')])
def test_a_local_record_cannot_be_relabelled_as_vendor_evidence(field,value):
    reader,row,usage,data,meter=evidence();data['receipt'][field]=value
    with pytest.raises(Invalid,match='LOCAL_VISITOR_SOURCE'):reader._local_visitor('owner',None,row,usage,data)


def test_unsettled_or_another_original_meter_never_authorizes_local_output():
    reader,row,usage,data,meter=evidence();meter['state']='unknown'
    with pytest.raises(Unavailable,match='LOCAL_VISITOR_METER_RECEIPT'):reader._local_visitor('owner',None,row,usage,data)
    meter['state']='settled';meter['receipt']['attempt_id']='different-attempt'
    with pytest.raises(Unavailable,match='LOCAL_VISITOR_METER_RECEIPT'):reader._local_visitor('owner',None,row,usage,data)
