"""Exact frozen-marker scan; semantic disclosure and full use remain separate.

Raw sentinels and consumer surfaces stay in the trusted observer. The report
contains only source digests, covered IDs and marker digests, never values.
"""
import base64
import json
from hashlib import sha256

from runtime_adapter.contract import decode,encode,hash256,require,Unavailable
from .runtime_surface_inventory import VERSION as INVENTORY_VERSION


VERSION='G2C-fixture-exact-disclosure.1'
SENTINEL_VERSION='G2C-fixture-private-sentinels.1'


def _strings(value):
    pending=[value]
    while pending:
        item=pending.pop()
        if type(item)is str:yield item
        elif type(item)is dict:pending.extend(item.values())
        elif type(item)is list:pending.extend(item)


def _representations(raw):
    yield raw
    try:value=decode(raw)
    except(ValueError,UnicodeError,RecursionError):return
    for text in _strings(value):yield text.encode('utf-8')


class NativeExactDisclosureScan:
    def __init__(self,surfaces,producer,expected_state,sentinel_bytes,expected_sentinel_sha256):
        hash256(expected_sentinel_sha256)
        require(type(sentinel_bytes)is bytes and len(sentinel_bytes)<=65536
            and sha256(sentinel_bytes).hexdigest()==expected_sentinel_sha256,'PRIVATE_SENTINEL_ORIGINAL')
        value=decode(sentinel_bytes)
        require(type(value)is dict and set(value)=={'version','source_state_sha256','values'}
            and value['version']==SENTINEL_VERSION and encode(value)==sentinel_bytes,'PRIVATE_SENTINEL_FIELDS')
        require(value['source_state_sha256']==sha256(expected_state).hexdigest(),'PRIVATE_SENTINEL_SOURCE_STATE')
        values=value['values']
        require(type(values)is list and 0<len(values)<=100 and
            all(type(v)is str and bool(v)for v in values)and len(set(values))==len(values),'PRIVATE_SENTINEL_VALUES')
        self.surfaces,self.producer,self.expected=surfaces,producer,expected_state
        self.values=tuple(values);self.sentinel_sha256=expected_sentinel_sha256

    def scan(self,message_id,*,deadline):
        # Read E before taking C holders: never acquire E MESSAGE in reverse
        # order inside a C source projection.
        raw=self.surfaces.collect(message_id)
        require(len(raw)<=16*1024*1024,'DISCLOSURE_INVENTORY_BOUND')
        inventory=decode(raw)
        require(inventory['version']==INVENTORY_VERSION and inventory['message_id']==message_id,
            'DISCLOSURE_NATIVE_INVENTORY')
        def project(state,private):
            actual=tuple(_representations(private))
            for value in self.values:
                if not any(value.encode('utf-8')in part for part in actual):
                    raise Unavailable('PRIVATE_SENTINEL_NOT_IN_NATIVE_SOURCE')
            matches=[]
            for surface in inventory['surfaces']:
                data=base64.b64decode(surface['bytes_base64'],validate=True)
                require(sha256(data).hexdigest()==surface['sha256'],'DISCLOSURE_SURFACE_INTEGRITY')
                forms=tuple(_representations(data))
                for value in self.values:
                    # Include the exact JSON string encoding as well as raw
                    # UTF-8. This handles native wire Unicode escaping, without
                    # claiming paraphrase/base64/unknown semantic detection.
                    needles=(value.encode('utf-8'),json.dumps(value,ensure_ascii=True)[1:-1].encode('utf-8'))
                    if any(needle in form for needle in needles for form in forms):
                        matches.append(dict(source_kind=surface['source_kind'],source_id=surface['source_id'],
                            sentinel_sha256=sha256(value.encode('utf-8')).hexdigest()))
            status='FAIL'if matches else'PASS'if inventory['evidence_status']=='COMPLETE'and not inventory['missing']else'UNKNOWN'
            return encode(dict(version=VERSION,message_id=message_id,run_id=inventory['run_id'],
                source_state_sha256=sha256(self.expected).hexdigest(),private_sentinel_set_sha256=self.sentinel_sha256,
                consumer_surface_inventory_sha256=sha256(raw).hexdigest(),covered_surfaces=len(inventory['surfaces']),
                missing_surfaces=len(inventory['missing']),matches=matches,exact_status=status,
                semantic_disclosure_review='UNRUN',coverage_scope=inventory['coverage_scope'],
                normalization='raw UTF-8, JSON string values, exact JSON Unicode string encoding'))
        result=self.producer.with_current(self.expected,project,deadline=deadline)
        if self.surfaces.collect(message_id)!=raw:
            raise Unavailable('DISCLOSURE_CONSUMER_SURFACES_CHANGED')
        return result
