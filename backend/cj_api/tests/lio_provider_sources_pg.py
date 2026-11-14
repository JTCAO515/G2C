"""Actual native4 registered producer/Meter/source proof with fixture HTTP only."""
from datetime import datetime,timezone
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import MappingProxyType
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_provider_sources import RegisteredProviderSources,POI2_REGISTRATION
from cj_api.lio_poi2_tool import POI2Input,registration
from cj_api.real_services import RealTools
from cj_memory.runtime import RuntimeDenied
from cj_message.lio_wire import ExplorationOrigin
from cj_message.lio_exploration_schema import RESPONSE
from cj_needs.revision_lease import LeaseUnavailable
from cj_usage.metered_exit import BudgetUnknown
from cj_memory.runtime import RuntimeUnknown
from cj_trip.domain import packed
from cj_place.gaode_v2 import TextSearch
from cj_place import https_transport
import lio_exploration_flow_pg as native


class FixtureWriter:
    def __init__(self,reader,send_check):
        self.reader,self.send_check=reader,send_check
        self.closed=False;self.transport=self;self.writes=[]
    def write(self,data):
        self.send_check();self.writes.append(data)
        body=json.dumps(dict(status='1',infocode='10000',count='1',pois=[dict(
            id='B000SYNTH1',name='合成博物馆',cityname='北京市',adcode='110101',location='116.4,39.9')]),ensure_ascii=False).encode()
        self.reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
        self.reader.feed_eof()
    async def drain(self):pass
    def close(self):self.closed=True
    async def wait_closed(self):pass
    def abort(self):self.closed=True


def main():
    original_registry=RealTools._registrations
    original_model=ExplorationPlanning._model
    captures=[];writers=[]
    def registry(tools):
        return MappingProxyType(dict(original_registry(tools),**{POI2_REGISTRATION:registration(tools.services)}))
    def model(host,worker,binding,view,profile,system,extra):
        if profile==RESPONSE and extra.get('scene')=='plan_now_preview':
            sources=RegisteredProviderSources(worker,binding)
            origin=ExplorationOrigin(host.database,binding,worker.messages.query(binding.message_id))
            packet=POI2Input(TextSearch('合成博物馆','北京',2),'poi2-'+binding.run_id[:16],origin,sources)
            phases=[]
            def send_check():
                worker.memory_run.check()
                assert worker.message_context.active_original(binding).receipt.message_id==binding.message_id
                phases.append('sent-under-original-frame')
            async def dial():
                reader=asyncio.StreamReader()
                writer=FixtureWriter(reader,send_check);writers.append(writer)
                return reader,writer
            read=https_transport._read_response
            async def receive(*args):
                try:worker.memory_run.check()
                except RuntimeDenied:pass
                else:raise AssertionError('Memory lock retained over network response')
                try:worker.message_context.active_original(binding)
                except LeaseUnavailable:pass
                else:raise AssertionError('MESSAGE lock retained over network response')
                phases.append('received-outside-original-frame')
                return await read(*args)
            with patch.object(https_transport,'_connect',dial),patch.object(https_transport,'_read_response',receive):
                raw=''.join(worker._registered_stream(binding,'plan4.poi2.0',POI2_REGISTRATION,packet))
            reply=json.loads(raw)
            assert phases==['sent-under-original-frame','received-outside-original-frame'],phases
            assert reply['version']=='LIO-poi2-result.1'and reply['status']=='ok'
            assert reply['items'][0]['place']['coordinate']['raw']=='116.4,39.9'
            capture=sources.capture(binding)
            assert len(capture.records)==1
            assert capture.records[0]['sha256']==sha256(packed(capture.records[0]['payload'])).hexdigest()
            late=[]
            def prove():
                with worker.message_context.hold_for_effect(binding)as message:
                    with sources.hold(binding,capture,message)as held:held.check();late.append(held)
                    try:
                        with RegisteredProviderSources(worker,binding).hold(binding,capture,message):pass
                    except RuntimeDenied:pass
                    else:raise AssertionError('copied provider descriptor granted source')
            worker._step(binding,prove)
            try:late[0].check()
            except RuntimeDenied:pass
            else:raise AssertionError('provider source outlived its actual frame')
            captures.append(capture)
            print('PASS registered POI2 original/Meter/live receipt/source '+binding.message_id+'; one send then unlocked receive; no Trip write',flush=True)
        return original_model(host,worker,binding,view,profile,system,extra)
    def diagnosed(*args,**kwargs):
        try:return model(*args,**kwargs)
        except (BudgetUnknown,RuntimeUnknown,RuntimeDenied)as error:
            print('PROVIDER_SOURCE_REJECTED '+type(error).__name__+': '+str(error)+' cause='+repr(error.__cause__),flush=True)
            raise
    with patch.object(RealTools,'_registrations',registry),patch.object(ExplorationPlanning,'_model',diagnosed):native.main()
    assert len(captures)==6 and len(writers)==6
    assert all(writer.closed and len(writer.writes)==1 for writer in writers)
    print('PASS ZH3/EN3 actual native4 registered tool/Meter/financial RECEIVED/SELECT-only status proof; HTTP fixture only, no real supplier claim',flush=True)


if __name__=='__main__':main()
