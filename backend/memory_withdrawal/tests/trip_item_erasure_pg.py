"""Actual accepted Trip, scoped result/draft and C memory-purpose erasure."""
import json,os,sys,unittest
import subprocess
from pathlib import Path
from hashlib import sha256

import psycopg
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/memory/tests'),str(ROOT/'backend/manual_edit/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from scoped_result_body_pg import ScopedResultChecks,Model
from edit_support import Harness,CONNINFO
from cj_memory_jobs.collection_app import create_decision_collection_app
from cj_memory_withdrawal.erasure_command import ErasureCommand,VERSION
from cj_memory_withdrawal.erasure_store import freeze
from cj_memory_withdrawal.item_cleanup import erasure_hooks
from cj_cleanup.core import encode,digest
from cj_cleanup.registry import freeze as registry_freeze
from cj_cleanup.store import Store
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.hooks_v1_1 import Selection
from cj_api.local_account_admission_v2 import subject_digest
from cj_agent.draft import trip_scope_for


class TripItemErasureChecks(Harness):
    fixture=ScopedResultChecks.fixture;send_result=ScopedResultChecks.send
    expand_model=ScopedResultChecks.expand_model;pointer=ScopedResultChecks.pointer
    body_app=ScopedResultChecks.body_app;get=ScopedResultChecks.get

    def test_signed_scoped_delete_stops_inflight_and_clears_actual_payloads(self):
        from scoped_erasure_context_pg import exercise
        exercise(self)

    def test_signed_source2_delete_stops_inflight_and_filters_new_models(self):
        from source2_erasure_context_pg import exercise
        exercise(self)

    def test_actual_derived_result_and_pending_draft_erased_formal_trip_kept(self):
        f=self.fixture('item-erasure-real',legacy=False)
        binding,_,_=self.send_result(f,key='derived-clarification',clarify=True)
        model=Model();f.run(model)
        self.assertEqual(model.calls,0)
        pointer=self.pointer(f,binding);self.assertEqual(pointer['kind'],'clarification_required')
        self.assertEqual(self.get(f,pointer['result_id']).status_code,200)
        binding2,_,_=self.send_result(f,key='pending-scoped')
        draft_model=Model();f.run(draft_model);self.assertEqual(draft_model.calls,1)
        ts=trip_scope_for(f.scope)
        with f.database.connect(f.scope) as conn:
            self.assertGreater(conn.execute("SELECT count(*) FROM cj_trip_proposal WHERE scope=%s AND status<>'accepted'",(ts,)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_result WHERE scope=%s',(ts,)).fetchone(),(1,))
            before=conn.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s ORDER BY trip_id',(ts,)).fetchall()
            accepted=conn.execute("SELECT proposal_id,content FROM cj_trip_proposal WHERE scope=%s AND status='accepted' ORDER BY proposal_id",(ts,)).fetchall()
            self.assertTrue(accepted)
            self.assertIsNotNone(conn.execute('SELECT trip_id FROM cj_trip_needs_current WHERE scope=%s',(ts,)).fetchone())
        c=create_decision_collection_app(conninfo_path=CONNINFO,auth_dir=f.auth,resolve_collection=lambda principal:None,
                                run_context=f.context).state.memory_history.service
        for hash_seed in ('1','2'):
            probe=subprocess.run([sys.executable,'-B',str(ROOT/'backend/memory_withdrawal/tests/manual_erasure_read_probe.py'),
                str(CONNINFO),str(f.auth),f.subject,'mem-long'],env=dict(os.environ,PYTHONHASHSEED=hash_seed),capture_output=True,text=True)
            self.assertEqual(probe.returncode,0,probe.stdout+probe.stderr)
        token=f.headers['Authorization'][7:]
        original=encode(dict(version=VERSION,action_id='delete-long',item_id='mem-long',expected_version=1,derived_range='owned_trip_derived_scope'))
        def stop(context):
            repo,principal,guard=c._binding(context,token)
            from cj_trip.decision_source import DecisionQuery
            from cj_trip.domain import Denied as TripDenied,Conflict as TripConflict
            from cj_memory_jobs.decision_fence import read_original_digest,digest_under_lease
            authority=c.resolve_decision_authority(token)
            query=DecisionQuery(f.trip.trip_id,f.trip.version,sha256(f.trip.content).hexdigest())
            digest_bytes=read_original_digest(authority.boundary,token,principal,repo.scope,query)
            with authority.hold(principal,query,max_source_bytes=4_000_000) as lease:
                self.assertEqual(digest_under_lease(repo.scope,lease).encode('ascii'),digest_bytes)
            with self.assertRaises(TripDenied):digest_under_lease(repo.scope,lease)
            with self.assertRaises(TripConflict):read_original_digest(authority.boundary,token,principal,repo.scope,
                DecisionQuery(f.trip.trip_id,f.trip.version+1,query.content_sha256))
            def capture(headers):
                with repo.transaction() as tx:
                    raw=freeze(tx,ErasureCommand.parse(original),subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000,headers=headers)
                    guard('trip_item_erasure_freeze');return raw
            return context.with_erasure_headers(capture,max_refs=10000,max_result_bytes=1_000_000)
        association=json.loads(c.boundary.with_history_context(token,stop));selection=Selection.from_dict(association['selection'])
        targets=('memory-derived','business/memory-management-actions','business/trip-authoritative','business/memory-authoritative')
        registry=registry_freeze(encode(dict(version='trip-item-component',stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
            dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in targets[1:]])])),targets,versions=('CLEANUP@1.1',))
        store=Store(lambda:psycopg.connect(**dict(json.loads(Path(CONNINFO).read_text()),user='cj_local_cleanup')),
                    association['subject_digest'],lambda stage:None)
        hooks=erasure_hooks(store,f.scope);coordinator=Coordinator(store,lambda:registry,{t:hooks[t] for t in targets})
        operation=association['operation_id'];plan={t:dict(domain_scope=ts if t=='business/trip-authoritative' else f.scope,
            selection=selection.to_dict()) for t in targets}
        coordinator.create(operation,digest(original),'memory',plan)
        for target in targets:coordinator.advance(coordinator.request(operation,target,plan[target]['domain_scope'],selection))
        self.assertEqual(coordinator.query(operation)['status'],'complete')
        with f.database.connect(f.scope) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_result WHERE scope=%s',(ts,)).fetchone(),(0,))
            self.assertEqual(conn.execute("SELECT count(*) FROM cj_trip_proposal WHERE scope=%s AND status<>'accepted'",(ts,)).fetchone(),(0,))
            self.assertEqual(conn.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s ORDER BY trip_id',(ts,)).fetchall(),before)
            self.assertEqual(conn.execute("SELECT proposal_id,content FROM cj_trip_proposal WHERE scope=%s AND status='accepted' ORDER BY proposal_id",(ts,)).fetchall(),accepted)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(f.scope,)).fetchone(),(2,))
            self.assertIsNotNone(conn.execute('SELECT trip_id FROM cj_trip_needs_current WHERE scope=%s',(ts,)).fetchone())
        self.assertNotEqual(self.get(f,pointer['result_id']).status_code,200)
        print('PASS signed genuine NEEDS accepted Trip + original run_once/Meter/Fake scoped result/pending proposal; real C purpose-memory cleanup removes derived scope and draft, preserves exact formal Trip/accepted proposal/current NEEDS/unrelated Memory')


if __name__=='__main__':unittest.main(defaultTest='TripItemErasureChecks')
