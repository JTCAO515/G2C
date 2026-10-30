"""Actual PLACE producer over a code-owned synthetic source, for local L1 only.

No network, caller URL, credentials or admission callback. The registered host
must supply the original server request reference and its canonical Meter fence.
Calling this class alone is data production, never execution permission.
"""
from datetime import datetime,timezone
import json

from .contract_v1 import decode_query,encode_result,publish_response
from .gaode import Config,PreparationError,Response,prepare
from .models import Detail,ORIGIN,Outcome,Result,RouteQuery,Search


def utc_now():return datetime.now(timezone.utc)


class LocalPlaceProducer:
    version='PLACE-SYNTHETIC@1'

    def __init__(self,config:Config,*,clock=utc_now):
        self.config,self.clock=config,clock
        self.invocations=0
        self.transport_calls=0

    def invoke(self,raw_query:bytes,request_ref:str):
        query=decode_query(raw_query)
        self.invocations+=1
        started=self.clock()
        try:
            request=prepare(self.config,query,request_ref,started)
        except PreparationError as error:
            return encode_result(Result(Outcome.UNSUPPORTED,query,str(error)),evidence_kind='synthetic')
        status,payload=self._response(query)
        self.transport_calls+=1
        raw=payload if type(payload) is bytes else json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf8')
        response=Response(request.binding_digest,request.origin,request.path,status,raw,self.clock())
        return publish_response(self.config,request,response,now=self.clock(),evidence_kind='synthetic')

    def _response(self,query):
        # These values are synthetic fixtures, not recorded provider responses.
        pois=[dict(id='SYNTH_EAST',name='合成酒店',address='合成东路一号',location='116.100000,39.100000',entr_location='116.100100,39.100100'),
              dict(id='SYNTH_WEST',name='合成酒店',address=[],location='116.200000,39.200000')]
        if type(query) is Search:
            if query.keyword=='SYNTH_RATE_LIMIT':return 429,b'SYNTHETIC_PRIVATE_SUPPLIER_BODY'
            if query.keyword=='SYNTH_BAD_JSON':return 200,b'{SYNTHETIC_PRIVATE_SUPPLIER_BODY'
            if query.keyword=='SYNTH_MISSING':items=[]
            else:items=pois[:query.page_size] if query.page==1 else []
            return 200,dict(status='1',info='OK',infocode='10000',count=str(len(items)),pois=items)
        if type(query) is Detail:
            items=[p for p in pois if p['id']==query.provider_id]
            return 200,dict(status='1',info='OK',infocode='10000',count=str(len(items)),pois=items)
        return 200,dict(status='1',info='OK',infocode='10000',count='1',route=dict(
            origin=query.origin.coordinate.raw,destination=query.destination.coordinate.raw,
            paths=[dict(distance='100',duration='90')]))
