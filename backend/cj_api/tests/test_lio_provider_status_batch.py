"""Every original receipt stays checked; one atomic ledger read per check."""
from datetime import datetime,timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from cj_api.local_lio_provider_sources import RegisteredProviderSources,POI2_REGISTRATION
from cj_memory.runtime import RuntimeDenied,RuntimeUnknown
from cj_place.gaode import Config,Response
from cj_place.gaode_v2 import TextSearch,prepare
from cj_usage.read_status import ReadUnavailable


class ProviderStatusBatch(unittest.TestCase):
    def case(self,count=3):
        binding=SimpleNamespace(scope='fixture-scope',run_id='fixture-run')
        config=SimpleNamespace(unit='provider_call',period_start=10,period_end=20)
        rows={};operations={};single=[];batch=[];memory=[];messages=[]
        def one(attempt,*,guard,**kwargs):
            if kwargs['expected_period']!=(10,20):raise ReadUnavailable('original period differs')
            single.append(attempt);guard();value=json.dumps(rows[attempt]).encode();guard();return value
        def many(attempts,*,guard,**kwargs):
            if kwargs['expected_period']!=(10,20):raise ReadUnavailable('original period differs')
            batch.append((attempts,kwargs));guard()
            value=json.dumps([rows[attempt]for attempt in attempts]).encode();guard();return value
        repo=SimpleNamespace(read_status=Mock(side_effect=one),read_status_many=Mock(side_effect=many))
        exit=SimpleNamespace(config=config,resolve_meter=Mock(return_value=SimpleNamespace(repo=repo)))
        worker=SimpleNamespace(budget_exit=exit,runs=SimpleNamespace(valid=lambda _:True),
            memory_run=SimpleNamespace(check=lambda:memory.append(True)))
        source=RegisteredProviderSources(worker,binding)
        for n in range(count):
            operation=SimpleNamespace(binding=binding,registration_id=POI2_REGISTRATION,
                operation_key='key-'+str(n),period=(10,20),command=SimpleNamespace(kind='tool',
                    operation_id='operation-'+str(n),attempt_id='attempt-'+str(n),input_digest='0'*64),
                original=SimpleNamespace(input_bytes=json.dumps(dict(targets=['stop-'+str(n)],
                    query_type='TextSearch',query=dict(keyword='合成场馆'))).encode()))
            source.begin(operation);operations[operation.operation_key]=operation
            query=prepare(Config('https://restapi.amap.com',8192,65536,20,60),
                TextSearch('合成场馆','北京',2),'query-'+str(n),datetime.now(timezone.utc))
            response=Response(query.binding_digest,query.origin,query.path,200,
                json.dumps(dict(status='1',infocode='10000',count='0',pois=[])).encode(),datetime.now(timezone.utc))
            reply,_=source.observe_poi2(operation,Config('https://restapi.amap.com',8192,65536,20,60),query,response)
            rows[operation.command.attempt_id]=dict(attempt_id=operation.command.attempt_id,
                operation_id=operation.command.operation_id,run_id=binding.run_id,status='settled',
                unit='provider_call',confirmed_units=1,confirmed_output=len(reply.decode()),
                receipt_id=source.receipt(operation.command.attempt_id,'provider_call',len(reply.decode())).receipt_id,
                cancelled=False,exceeded=False)
        source.store=SimpleNamespace(read_original=Mock(side_effect=lambda bind,key:operations[key]))
        message=SimpleNamespace(check=lambda bind:messages.append(bind))
        return source,binding,rows,operations,repo,single,batch,memory,messages,message

    def test_capture_and_each_live_hold_check_read_all_receipts_once_without_caching_allow(self):
        source,binding,rows,operations,repo,single,batch,_,_,message=self.case()
        capture=source.capture(binding)
        self.assertEqual(source.store.read_original.call_count,3)
        self.assertEqual(single,[]);self.assertEqual(len(batch),1)
        self.assertEqual(batch[0][0],tuple(rows));self.assertEqual(batch[0][1]['expected_period'],(10,20))
        self.assertEqual(len(capture.outcomes),3)
        with self.assertRaises(RuntimeUnknown):
            with source.hold(binding,capture,message)as held:
                before=len(batch);held.check();self.assertEqual(len(batch),before+1)
                rows['attempt-1']['cancelled']=True
                held.check()

    def test_each_original_status_field_remains_binding(self):
        for key,value in (('attempt_id','foreign'),('operation_id','foreign'),('run_id','foreign'),
                ('status','unknown'),('unit','other'),('confirmed_units',2),('confirmed_output',0),
                ('receipt_id','foreign'),('cancelled',True),('exceeded',True)):
            with self.subTest(field=key):
                source,binding,rows,*_=self.case()
                rows['attempt-1'][key]=value
                with self.assertRaises(RuntimeUnknown):source.capture(binding)
                self.assertIsNone(source._issued)

    def test_mixed_original_periods_are_refused_before_any_batch_read(self):
        source,binding,_,operations,repo,*_=self.case()
        operations['key-1'].period=(20,30)
        with self.assertRaises(RuntimeUnknown):source.capture(binding)
        repo.read_status_many.assert_not_called();self.assertIsNone(source._issued)

    def test_original_input_mismatch_stops_before_status_materialization(self):
        source,binding,_,_,repo,*_=self.case()
        source.store.read_original=Mock(return_value=None)
        with self.assertRaises(RuntimeDenied):source.capture(binding)
        repo.read_status_many.assert_not_called();self.assertIsNone(source._issued)

    def test_empty_observation_set_preserves_empty_capture_without_an_invalid_batch_call(self):
        source,binding,_,_,repo,*_=self.case(count=0)
        capture=source.capture(binding)
        self.assertEqual(capture.records,[]);self.assertEqual(capture.outcomes,[])
        repo.read_status_many.assert_not_called();repo.read_status.assert_not_called()

    def test_batch_read_failure_or_revoked_memory_never_issues_eligible_data(self):
        source,binding,_,_,repo,_,_,_,_,message=self.case()
        repo.read_status_many.side_effect=ReadUnavailable('withheld')
        with self.assertRaises(RuntimeUnknown):source.capture(binding)
        self.assertIsNone(source._issued)
        source,binding,*rest=self.case()
        capture=source.capture(binding)
        source.worker.memory_run.check=Mock(side_effect=RuntimeDenied('withdrawn'))
        with self.assertRaises(RuntimeDenied):
            with source.hold(binding,capture,message):pass


if __name__=='__main__':unittest.main()
