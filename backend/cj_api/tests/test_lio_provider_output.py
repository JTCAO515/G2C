"""Complete provider projection bounds; no authorization or publication grant."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from types import SimpleNamespace
import unittest

from cj_api.local_lio_provider_sources import RegisteredProviderSources,POI2_REGISTRATION
from cj_place.gaode import Config,Response
from cj_place.gaode_v2 import TextSearch,prepare


class ProviderOutput(unittest.TestCase):
    def observe(self,rows):
        binding=object()
        worker=SimpleNamespace(budget_exit=SimpleNamespace(config=object()),runs=object())
        sources=RegisteredProviderSources(worker,binding)
        operation=SimpleNamespace(binding=binding,registration_id=POI2_REGISTRATION,
            command=SimpleNamespace(kind='tool',operation_id='fixture-operation',attempt_id='fixture-attempt'))
        sources.begin(operation)
        config=Config('https://restapi.amap.com',8192,65536,20,60)
        request=prepare(config,TextSearch('合成博物馆','北京',25),'fixture-query',datetime.now(timezone.utc))
        raw=json.dumps(dict(status='1',infocode='10000',count=str(len(rows)),pois=rows),ensure_ascii=False).encode()
        response=Response(request.binding_digest,request.origin,request.path,200,raw,datetime.now(timezone.utc))
        reply,metadata=sources.observe_poi2(operation,config,request,response)
        return sources,operation,raw,reply,metadata

    def test_complete_escaped_projection_over_limit_is_unavailable_without_partial_records(self):
        rows=[dict(id='B'+str(n)+'x'*198,name='\\'*500,cityname='北京市',adcode='110101',
            location='116.400000000001,39.900000000001',address='"'*1024,
            business=dict(opentime_today='"'*1024,opentime_week='"'*1024))for n in range(3)]
        sources,operation,raw,reply,metadata=self.observe(rows)
        value=json.loads(reply)
        self.assertLessEqual(len(reply.decode()),8192)
        self.assertEqual(value['status'],'unavailable')
        self.assertEqual(value['items'],[])
        self.assertEqual(value['raw_response_sha256'],sha256(raw).hexdigest())
        self.assertEqual(metadata['unavailable_reason'],'normalized_output_limit')
        self.assertEqual(json.loads(sources._observed[operation.command.operation_id].records),[])
        self.assertEqual(sources.receipt('fixture-attempt','provider_call',len(reply.decode())).output,len(reply.decode()))

    def test_unicode_output_uses_registered_character_unit_and_keeps_all_eligible_records(self):
        rows=[dict(id='B'+str(n),name='合成博物馆'+str(n),cityname='北京市',adcode='110101',
            location='116.4,39.9',address='京'*300,business=dict(opentime_today='开'*300,opentime_week='周'*300))for n in range(3)]
        sources,operation,_,reply,metadata=self.observe(rows)
        self.assertGreater(len(reply),8192)
        self.assertLess(len(reply.decode()),8192)
        self.assertEqual(json.loads(reply)['status'],'ok')
        self.assertEqual(len(json.loads(reply)['items']),3)
        self.assertEqual(len(json.loads(sources._observed[operation.command.operation_id].records)),3)
        self.assertNotIn('unavailable_reason',metadata)


if __name__=='__main__':unittest.main()
