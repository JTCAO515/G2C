"""Declared exact-marker semantics, source custody and incomplete evidence."""
import base64
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from cj_api.runtime_disclosure_scan import NativeExactDisclosureScan,SENTINEL_VERSION
from cj_api.runtime_surface_inventory import VERSION
from runtime_adapter import Invalid,Unavailable
from runtime_adapter.contract import encode,decode


@pytest.fixture
def fixture():
    expected=encode({'native':'fixture-state'})
    marker='PRIVATE-私有-54a9c06f'
    sentinels=encode(dict(version=SENTINEL_VERSION,source_state_sha256=sha256(expected).hexdigest(),values=[marker]))
    state=dict(allowed=True,private=encode({'private_label':marker}),data=b'ordinary public reply',
        status='COMPLETE',missing=[],calls=0,change=False)
    def collect(mid):
        state['calls']+=1;data=state['data']
        if state['change']and state['calls']>1:data+=b'late change'
        return encode(dict(version=VERSION,message_id=mid,run_id='original-e-run',
            surfaces=[dict(source_kind='visible_text',source_id='original-e-run',
                sha256=sha256(data).hexdigest(),bytes_base64=base64.b64encode(data).decode())],
            evidence_status=state['status'],missing=state['missing'],coverage_scope='declared-native-run'))
    def current(original,project,*,deadline):
        assert original==expected and deadline==100
        if not state['allowed']:raise Unavailable('SOURCE_WITHHELD')
        result=project({'native':'fixture-state'},state['private'])
        if not state['allowed']:raise Unavailable('SOURCE_WITHHELD')
        return result
    def build(raw=sentinels,expected_hash=None):
        return NativeExactDisclosureScan(SimpleNamespace(collect=collect),SimpleNamespace(with_current=current),
            expected,raw,sha256(raw).hexdigest()if expected_hash is None else expected_hash)
    return SimpleNamespace(state=state,build=build,marker=marker,sentinels=sentinels,expected=expected)


def test_exact_clean_report_contains_no_private_value(fixture):
    report=decode(fixture.build().scan('native-e-message',deadline=100))
    assert report['exact_status']=='PASS'and report['matches']==[]
    assert report['semantic_disclosure_review']=='UNRUN'
    assert fixture.marker not in str(report)and report['coverage_scope']=='declared-native-run'


@pytest.mark.parametrize('encoding',['utf8','json','nested_json_string'])
def test_raw_unicode_and_json_wire_encodings_are_exact_hits(fixture,encoding):
    if encoding=='utf8':data=('answer '+fixture.marker).encode()
    elif encoding=='json':data=json.dumps({'answer':fixture.marker},ensure_ascii=True).encode()
    else:data=json.dumps({'content':json.dumps({'private':fixture.marker},ensure_ascii=True)}).encode()
    fixture.state['data']=data
    report=decode(fixture.build().scan('native-e-message',deadline=100))
    assert report['exact_status']=='FAIL'and len(report['matches'])==1
    assert report['matches'][0]['sentinel_sha256']==sha256(fixture.marker.encode()).hexdigest()
    assert fixture.marker not in str(report)


def test_known_hit_dominates_incomplete_other_surfaces(fixture):
    fixture.state.update(data=fixture.marker.encode(),status='UNKNOWN',missing=[{'field':'wire'}])
    assert decode(fixture.build().scan('native-e-message',deadline=100))['exact_status']=='FAIL'


def test_no_hit_with_missing_evidence_is_not_zero_leakage_pass(fixture):
    fixture.state.update(status='UNKNOWN',missing=[{'field':'output'}])
    assert decode(fixture.build().scan('native-e-message',deadline=100))['exact_status']=='UNKNOWN'


def test_claimed_marker_must_exist_in_the_actual_native_source(fixture):
    fixture.state['private']=encode({'label':'unrelated public source'})
    with pytest.raises(Unavailable,match='NOT_IN_NATIVE_SOURCE'):
        fixture.build().scan('native-e-message',deadline=100)


def test_frozen_set_source_hash_and_current_qualification_cannot_be_replaced(fixture):
    with pytest.raises(Invalid):fixture.build(expected_hash='a'*64)
    value=decode(fixture.sentinels);value['source_state_sha256']='a'*64
    with pytest.raises(Invalid):fixture.build(raw=encode(value))
    fixture.state['allowed']=False
    with pytest.raises(Unavailable):fixture.build().scan('native-e-message',deadline=100)


def test_late_native_surface_change_withholds_earlier_scan(fixture):
    fixture.state['change']=True
    with pytest.raises(Unavailable,match='SURFACES_CHANGED'):
        fixture.build().scan('native-e-message',deadline=100)
