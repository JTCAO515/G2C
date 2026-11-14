"""Real native short source holders; Fake planning, no provider or HK activation."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import local_history_pg as harness
import runtime_native_dialogue_pg as native
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import psycopg
from psycopg_pool import ConnectionPool

from cj_api.runtime_fixture_boundary import FixtureSourceBoundary
from cj_api.runtime_release_witness import NativeReleaseWitness
from cj_api.runtime_disclosure_scan import NativeExactDisclosureScan,SENTINEL_VERSION
from cj_api.runtime_surface_inventory import VERSION as SURFACE_VERSION
from cj_api.local_app import load_confirmation_signer,scope_for
from cj_api.local_account_admission_v2 import account_checker_for,retired_in_transaction
from cj_api.local_worker_context import checker_factory_for
from cj_api.lio_trip_routes import LioTripBoundary
from cj_api.supabase_test_database import _RuntimeLease
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import Boundary
from cj_memory_jobs.service import Service as HistoryService
from cj_usage.authorization_budget import canonical
from deploy.hk import checkpoint,configuration
from runtime_adapter import Binding,Unavailable
from runtime_adapter.contract import decode,encode


def exercise(auth,conninfo):
    f=native.exercise(auth.parent/'composite-native',conninfo)
    owner=f.scope;token=f.token
    checker=account_checker_for(f.auth,f.database)
    builder=checker_factory_for(f.auth)
    f.messages=Boundary(checker,lambda p:f.database.message_repository(scope_for(p.issuer,p.subject)),
        lambda:'unused-composite-generation',
        checker_in_transaction=lambda tx,scope:builder(retired_in_transaction(tx.cur,scope)))
    f.trips=LioTripBoundary(f.database,checker,load_confirmation_signer(f.auth))
    f.checker=checker
    binding=Binding(owner,sha256(token.encode()).hexdigest(),'local-fixture-ledger','local-fixture-producer')
    pins=SimpleNamespace(key='a'*64,raw=b'local-native-composite-pins')
    state=dict(pins=pins.raw,qualified=True)
    class Authority:
        def require(self,**kwargs):
            assert kwargs['binding']==binding and kwargs['pins_sha256']==pins.key and kwargs['read_only']is True
            assert time.monotonic()<kwargs['deadline']
            if f.checker.check(token).status is not AdmissionStatus.ALLOWED:raise Unavailable('LOCAL_AUTH_WITHHELD')
        def pins(self):return state['pins']
    authority=Authority()
    def qualify(deadline):
        assert time.monotonic()<deadline
        if not state['qualified']:raise Unavailable('LOCAL_CONSUMER_WITHHELD')
        if f.checker.check(f.foreign_token).status is not AdmissionStatus.ALLOWED:
            raise Unavailable('LOCAL_CONSUMER_AUTH_WITHHELD')
    def guard():authority.require(binding=binding,pins_sha256=pins.key,purpose='query',deadline=time.monotonic()+30,read_only=True)
    control=auth.parent/'composite-control';control.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    environment=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',
        CJ_DEPLOY_CONTROL=str(control),CJ_TRIAL_VALID_UNTIL='2026-11-15T00:00:00+00:00',
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,14,tzinfo=timezone.utc)
    config=json.loads(conninfo.read_bytes())
    with patch.dict(os.environ,environment),patch('deploy.hk.configuration.datetime',Clock),\
            psycopg.connect(**config,autocommit=True)as admin:
        instance,lineage=checkpoint.identity(admin)
        checkpoint.atomic(control/'release.json',dict(version='g2c-beta-release.1',instance=instance,
            lineage=lineage,checkpoint='local-composite-fixture'),public=True)
        f.database._before_scope=configuration.runtime_transaction
        release=NativeReleaseWitness(f.database,owner,control,guard=guard,release=checkpoint)
        source=FixtureSourceBoundary(authority,binding,pins,f.messages,f.trips,lambda:token,
            'native-undo-plan',release,qualification_guard=qualify)
        calls=f.model.calls
        try:source.capture(deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('missing Memory/history scope became an empty qualified source')
        assert admin.execute('SELECT count(*) FROM cj_memory_scope WHERE scope=%s',(owner,)).fetchone()[0]==0

        # Native explicit local consent action initializes the canonical scope;
        # the production reader itself never initializes or enables anything.
        original=f.messages.with_history_context(token,lambda ctx:ctx.query_lio_message('native-undo-plan'))
        head=f.messages.with_history_context(token,lambda ctx:ctx.send_status(original.receipt.conversation_id).head)
        history=HistoryService(f.messages,lambda principal,scope:source.memories)
        def consent(operation,version,aid):
            return history.apply_consent(token,encode(dict(version='MEMORY-HISTORY@1',action_id=aid,
                operation=operation,conversation_id=original.receipt.conversation_id,
                expected_generation=head.generation,expected_epoch=head.epoch,expected_source_version=version)))
        consent('disable',0,'fixture-initialize-disabled')
        before=source.capture(deadline=time.monotonic()+30);frame=decode(before)
        assert frame['trip']['version']==3 and frame['memory']['consent'][2]is False
        assert source.capture(deadline=time.monotonic()+30)==before
        assert source.with_current(before,lambda current,private:encode({'trip_version':current['trip']['version']}),
            deadline=time.monotonic()+30)==encode({'trip_version':3})
        assert f.model.calls==calls
        # Native C custody is real here; E bytes are explicit controlled scan
        # fixtures, separate from the native surface-capture group's evidence.
        private=source.with_current(before,lambda state,content:content,deadline=time.monotonic()+30)
        marker=json.loads(private)['title']
        sentinel=encode(dict(version=SENTINEL_VERSION,source_state_sha256=sha256(before).hexdigest(),values=[marker]))
        scan_state=dict(data=b'ordinary E reply',missing=[])
        def controlled_surfaces(mid):
            data=scan_state['data']
            return encode(dict(version=SURFACE_VERSION,message_id=mid,run_id='controlled-e-run',
                surfaces=[dict(source_kind='visible_text',source_id='controlled-e-run',
                    sha256=sha256(data).hexdigest(),bytes_base64=base64.b64encode(data).decode())],
                evidence_status='UNKNOWN'if scan_state['missing']else'COMPLETE',
                missing=scan_state['missing'],coverage_scope='controlled-E-bytes'))
        scanner=NativeExactDisclosureScan(SimpleNamespace(collect=controlled_surfaces),source,before,
            sentinel,sha256(sentinel).hexdigest())
        assert decode(scanner.scan('controlled-e-message',deadline=time.monotonic()+30))['exact_status']=='PASS'
        scan_state.update(data=marker.encode(),missing=[{'field':'uncaptured-output'}])
        report=decode(scanner.scan('controlled-e-message',deadline=time.monotonic()+30))
        assert report['exact_status']=='FAIL'and report['semantic_disclosure_review']=='UNRUN'
        assert marker not in str(report)and f.model.calls==calls

        with ThreadPoolExecutor(max_workers=3)as pool:
            entered=[Event()for _ in range(3)];pending=[]
            def writer(index):
                entered[index].set()
                if index==0:
                    with f.messages._service(token).repository.transaction()as tx:tx.lock_scope()
                elif index==1:
                    with f.trips._bind(token)[0].transaction():pass
                else:
                    with source.memories.transaction()as tx:tx.lock_scope()
                return index
            def check_holders(current,private):
                pending.extend(pool.submit(writer,i)for i in range(3))
                assert all(event.wait(5)for event in entered)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    waits=admin.execute("SELECT query FROM pg_stat_activity WHERE wait_event_type='Lock'").fetchall()
                    if all(any(table in q for(q,)in waits)for table in ('cj_message_scope','cj_trip_scope','cj_memory_scope')):break
                    time.sleep(.01)
                else:raise AssertionError('actual M/Trip/Memory writers were not all fenced')
                assert not any(item.done()for item in pending)
                return b'encoded-local-projection'
            assert source.with_current(before,check_holders,deadline=time.monotonic()+30)==b'encoded-local-projection'
            assert sorted(item.result(timeout=10)for item in pending)==[0,1,2]

        # The actual current HK worker value is six. Exercise a real bounded
        # psycopg pool/native lease, including the outer consumer M admission;
        # the preceding three-writer test remains independent/unpooled.
        checkout=f.database._open_runtime_connection
        occupancy=dict(active=0,peak=0)
        with ConnectionPool(kwargs=dict(f.database.conninfo,autocommit=True,prepare_threshold=None,
                options='-c statement_timeout=10000 -c lock_timeout=5000'),min_size=0,max_size=6,
                max_waiting=32,timeout=2)as pool:
            class Lease(_RuntimeLease):
                def close(self):
                    if not self._returned:occupancy['active']-=1
                    return super().close()
            def pooled():
                connection=pool.getconn()
                connection.autocommit=True
                occupancy['active']+=1;occupancy['peak']=max(occupancy.values())
                return Lease(pool,connection)
            f.database._open_runtime_connection=pooled
            try:
                with f.messages._service(f.foreign_token).repository.transaction()as outer:
                    outer.lock_scope()
                    assert source.with_current(before,lambda state,private:b'pooled-six-projection',
                        deadline=time.monotonic()+30)==b'pooled-six-projection'
                assert occupancy['active']==0 and occupancy['peak']==6
            finally:f.database._open_runtime_connection=checkout

        state['pins']=b'changed-current-source'
        try:source.with_current(before,lambda *args:b'not-reached',deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('changed source reused a composite witness')
        state['pins']=pins.raw
        def withdraw(current,private):state['qualified']=False;return b'earlier-private-result'
        try:source.with_current(before,withdraw,deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('withdrawn consumer received earlier projection')
        state['qualified']=True

        consent('enable',1,'fixture-enable-source')
        consent('disable',2,'fixture-disable-source-again')
        after=decode(source.capture(deadline=time.monotonic()+30))
        assert after['trip']==frame['trip']and after['memory']['consent'][2]is False
        assert after['memory']['consent'][3]>frame['memory']['consent'][3]
        try:source.with_current(before,lambda *args:b'stale-boolean-state',deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('consent disable/enable/disable ABA was hidden by same Trip hash')
        assert f.model.calls==calls
        current=source.capture(deadline=time.monotonic()+30)
        # An authoritative account-fence fixture, not a claim of running the
        # complete physical cleanup. It can commit independently of Trip locks.
        def retire_during_projection(frame,private):
            subject=sha256(b'local-composite-account-fence').hexdigest()
            owner_digest=sha256(owner.encode()).hexdigest()
            admin.execute("INSERT INTO cj_cleanup_request(subject_digest,operation_id,action_id,input_digest,"
                "registry_bytes,inventory,plan_digest,binding_id,phase) VALUES(%s,'fixture-retire',"
                "'fixture-retire-action',%s,%s,'[]'::jsonb,%s,'local-fence','confirmed')",
                (subject,sha256(b'local-fence').hexdigest(),b'local-fence-control',sha256(b'local-fence').hexdigest()))
            admin.execute('INSERT INTO cj_account_fence(subject_digest,owner_digest,operation_id,namespace_digests) '
                "VALUES(%s,%s,'fixture-retire',%s::jsonb)",(subject,owner_digest,json.dumps([owner_digest])))
            return b'earlier-private-result-must-not-escape'
        try:source.with_current(current,retire_during_projection,deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('retirement committed during projection returned private bytes')
        try:source.capture(deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('retired owner reused cached native fixture state')
        assert f.model.calls==calls
    print('PASS native release+M+Trip+Memory short composite, actual three writer fences, '
        'no implicit Memory init, source/qualification withdrawal, consent ABA and actual retirement fence withheld; publication/E-F UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
