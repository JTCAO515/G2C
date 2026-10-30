"""Actual signed NEEDS API/runtime PG and registered synthetic PLACE -> FEAS."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_worker_context import checker_for
from cj_api.local_needs import protected_reader
from cj_api.local_tools import LocalTools,SyntheticToolModel
from cj_needs.contract_v1 import encode_snapshot,encode_revision
from cj_feasibility.current_read import ReadLimits,ReadWithheld
from cj_feasibility.formal_current import FormalReadLimits
from cj_feasibility.local_runtime import current_reader
from cj_feasibility import formal_v1
from cj_feasibility.validator import Candidate
from cj_feasibility.routes import Window
from cj_place import prepare,Observed,FieldState,Quantity
from cj_place.contract_v1 import decode_query,QUERY_VERSION
from registered_host_support import RegisteredHost

LIMITS=FormalReadLimits(ReadLimits(16,1_000_000,524288),2_000_000)
AT=datetime(2026,11,2,1,tzinfo=timezone.utc)


def known(value):return {'state':'known','value':value}
def event(clock,day='2026-11-02',zone='Asia/Shanghai'):
    return dict(date=known(day),time=known(clock),timezone=known(zone),place={'state':'unknown'})
def item(key,start,end,locked=False):
    return dict(item_id=key,kind='appointment',description='用户安排 / explicit appointment',applies_to=['self'],
        locked=known(locked),booking_status=known('booked'),start=event(start),end=event(end))
def seconds(value):return Observed(FieldState.PRESENT,Quantity(value,Decimal(value),'s'))


class RuntimeFeasChecks(Harness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app=create_local_app(conninfo_path=CONNINFO,auth_dir=cls.auth,needs_profile='manual-v1')
        cls.read=current_reader(conninfo_path=CONNINFO,auth_dir=cls.auth,limits=LIMITS)

    def setUp(self):self.tag=uuid.uuid4().hex;self.needs_id='visit-'+self.tag

    def save(self,client,changes,version=0,subject='alice'):
        raw=json.dumps(dict(action_id='act-'+uuid.uuid4().hex,needs_id=self.needs_id,expected_version=version,
            source=dict(kind='manual',text='用户明确核对 / checked source'),changes=changes),ensure_ascii=False,separators=(',',':')).encode()
        result=client.post('/v1/needs-actions',content=raw,headers={**self.headers(subject),'Content-Type':'application/octet-stream'})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()['receipt']

    def test_signed_current_two_fixed_conflict_rebuild_and_source_history(self):
        with TestClient(self.app) as client:
            self.save(client,dict(fixed_items=[item('a','09:00','10:00',True),item('b','09:30','11:00')],
                budget_currency=known('USD'),budget_per_person=known('1000.50'),budget_paid={'state':'unknown'},budget_basis=known('per_person')))
            token=self.headers('alice')['Authorization'][7:]
            result=json.loads(self.read.read(token,self.needs_id))
            self.assertEqual(result['status'],'CONFLICT')
            self.assertEqual(result['evaluator_version'],'FEASIBILITY@1.0')
            self.assertIn('DECLARED_OCCUPANCY_OVERLAP',{c['code'] for c in result['checks']})
            self.assertTrue(all(c['zh'] and c['en'] for c in result['checks']))
            self.save(client,dict(pace={'state':'uncertain','note':'慢一些 / slower'}),1)
            rebuilt=current_reader(conninfo_path=CONNINFO,auth_dir=self.auth,limits=LIMITS)
            value=json.loads(rebuilt.read(token,self.needs_id))
            self.assertEqual(value['revision'],2)
            self.assertEqual([s['revision'] for s in value['sources']],[1,2])
            self.assertEqual(value['overall'],'UNKNOWN')
            with self.assertRaises(ReadWithheld):self.read.read(self.headers('bob')['Authorization'][7:],self.needs_id)
            with self.assertRaises(ReadWithheld):self.read.read(token,'absent-'+self.tag)

    def test_real_registered_place_route_and_explicit_buffer_rest(self):
        # This actually executes B's accepted MESSAGE/model/tool/model/Meter host.
        auth=self.auth/('route-'+self.tag)
        host=RegisteredHost(auth,Path(CONNINFO),{'route':(8,2,16000)})
        tools=LocalTools();tools.place.clock=lambda:AT
        with host.api('route') as client:
            host.send(client,'route','route-'+self.tag,'查询合成路线 / synthetic route')
            model=SyntheticToolModel();outcome=host.worker('route',model,tools).process()[0]
            self.assertEqual(outcome.status,'completed')
            self.assertEqual((model.calls,tools.place.invocations,tools.place.transport_calls),(2,1,1))
            raw=host.display(client,'route','route-'+self.tag)['text']
            result=json.loads(raw.splitlines()[0])['result']
        from cj_usage.core import Meter
        self.assertEqual(Meter.exposure(host.ledger('route')),3)
        query=decode_query(json.dumps(dict(version=QUERY_VERSION,query=result['query'])).encode())
        request=prepare(tools.place.config,query,result['source']['request_ref'],AT)
        place_raw=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
        with TestClient(self.app) as client:
            self.save(client,dict(fixed_items=[item('a','08:00','09:00'),item('b','09:15','10:00')]))
        database=LocalDatabase(CONNINFO,needs_context=True)
        reader=protected_reader(database,checker_for(self.auth))
        def project(operation,context):
            snapshot=operation.detail(self.needs_id)
            revisions=tuple(operation.revision(self.needs_id,v) for v in range(1,snapshot.version+1))
            candidate=Candidate(snapshot.needs_id,snapshot.version,snapshot.content)
            report=formal_v1.check_route(encode_snapshot(snapshot),tuple(encode_revision(r) for r in revisions),
                candidate,Window('a','b',query,seconds('600'),seconds('600')),place_raw,
                route_index=0,request=request,config=tools.place.config,as_of=AT,
                selected_fields=frozenset(),selected_item_ids=frozenset(),max_revisions=16,max_input_bytes=2_000_000)
            self.assertEqual(report.status,'UNKNOWN')
            self.assertEqual(report.report.conditional_relation,'required_exceeds_gap')
            self.assertEqual(report.place_original,place_raw)
            return json.dumps(dict(status=report.status,codes=[c.code for c in report.report.checks])).encode()
        value=json.loads(reader.read(self.headers('alice')['Authorization'][7:],project))
        self.assertIn('ROUTE_EVIDENCE_UNVERIFIED',value['codes'])
        # No Trip or AI draft was created by either input/evaluation path.
        with database.connect(scope_for(ISSUER,'alice')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)

    def test_real_declared_currency_paid_scope_and_time_unknowns(self):
        cases=[
            dict(party_size=known(3),budget_currency=known('USD'),budget_per_person=known('1000.50'),
                 budget_total={'state':'unknown'},budget_paid={'state':'missing'},budget_basis=known('per_person'),
                 budget_includes=known(['excludes international airfare'])),
            dict(fixed_items=[item('a','23:30','00:30')]),
            dict(fixed_items=[dict(item('a','01:30','02:30'),start=event('01:30','2026-11-01','America/New_York'),
                                  end=event('02:30','2026-11-01','America/New_York'))]),
        ]
        with TestClient(self.app) as client:
            for index,fields in enumerate(cases):
                with self.subTest(case=index):
                    self.needs_id='matrix-'+str(index)+'-'+self.tag
                    self.save(client,fields)
                    value=json.loads(self.read.read(self.headers('alice')['Authorization'][7:],self.needs_id))
                    original=json.loads(value['sources'][0]['original_input_utf8'])['changes']
                    self.assertEqual(original,fields)
                    self.assertEqual(value['overall'],'UNKNOWN')
                    if index==0:
                        self.assertEqual(value['status'],'UNKNOWN')
                        self.assertEqual(original['budget_paid'],{'state':'missing'})
                        self.assertEqual(original['budget_total'],{'state':'unknown'})
                        self.assertIn('BUDGET_SCOPE_UNPROVEN',{c['code'] for c in value['checks']})
                    elif index==1:self.assertIn('ITEM_TIME_REVERSED',{c['code'] for c in value['checks']})
                    else:self.assertIn('ITEM_TIME_UNKNOWN',{c['code'] for c in value['checks']})
            duplicate=dict(fixed_items=[item('same','09:00','10:00'),item('same','10:00','11:00')])
            raw=json.dumps(dict(action_id='duplicate-'+self.tag,needs_id='duplicate-'+self.tag,expected_version=0,
                source=dict(kind='manual',text='explicit'),changes=duplicate)).encode()
            response=client.post('/v1/needs-actions',content=raw,headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,400,response.text)

    def test_real_current_source_change_and_revocation_withhold(self):
        with TestClient(self.app) as client:self.save(client,dict(party_size=known(2)))
        token=self.headers('alice')['Authorization'][7:]
        with TestClient(self.app) as client:
            from cj_feasibility import formal_current
            original_check=formal_current.check_constraints
            corrected=[]
            def change_after_evaluation(*args,**kwargs):
                report=original_check(*args,**kwargs)
                if not corrected:
                    self.save(client,dict(party_size=known(3)),1)
                    corrected.append(True)
                return report
            with patch.object(formal_current,'check_constraints',change_after_evaluation):
                with self.assertRaises(ReadWithheld):self.read.read(token,self.needs_id)
            self.assertEqual(corrected,[True])
        original=json.loads((self.auth/'invited.json').read_text())
        try:
            (self.auth/'invited.json').write_text(json.dumps([s for s in original if s!='alice']))
            with self.assertRaises(Exception):self.read.read(token,self.needs_id)
        finally:(self.auth/'invited.json').write_text(json.dumps(original))


if __name__=='__main__':unittest.main(verbosity=2)
