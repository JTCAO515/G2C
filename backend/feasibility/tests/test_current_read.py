"""Fresh private Unix-only PostgreSQL + actual fixed NEEDS/AUTH public boundaries.

Root token entry is NOT enabled: known upstream close/environment seams are
separate negative probes, run explicitly with CJ035_RUN_SEAM_PROBES=1.
"""
from dataclasses import replace
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

import psycopg
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import (CJAccessFacts, Fact, TrustedPrincipal, VerificationResult, VerificationStatus)
from cj_auth.read_context import ProtectedReadBoundary
from cj_needs import Boundary, Command
from cj_feasibility.current_read import ReadLimits, ReadWithheld, project_current

ROOT=Path(__file__).resolve().parents[3]
BIN=Path(os.environ.get('CJ_PG17_BINDIR','/opt/homebrew/opt/postgresql@17/bin'))
LIMITS=ReadLimits(10,1024*1024,128*1024)


def known(value):return {'state':'known','value':value}
def event(wall):
    return {'date':known('2026-10-22'),'time':known(wall),'timezone':known('Asia/Shanghai'),'place':{'state':'unknown'}}
def item(key):
    return dict(item_id=key,kind='appointment',description='synthetic current read / 合成读取',applies_to=['self'],
                locked=known(True),booking_status=known('booked'),start=event('09:00'),end=event('10:00'))


class Identity:
    def __init__(self):
        self.subject='synthetic-a';self.fact=Fact.YES;self.now=100;self.expires=1000
    def verify(self,token):
        return VerificationResult(VerificationStatus.VALID,
             TrustedPrincipal('synthetic-cj035',self.subject,'cj-read-test',1,1,self.expires))
    def evaluate(self,principal):return CJAccessFacts(principal,self.fact,Fact.YES,Fact.YES)


class Connection:
    """Test-only close fault/identity hooks; not a consumer runtime wrapper."""
    def __init__(self,base,owner):self.base,self.owner=base,owner
    def __getattr__(self,name):return getattr(self.base,name)
    def close(self):
        self.base.close()
        self.owner.closed+=1
        hook=self.owner.close_hook
        if hook is not None:hook(self.owner.closed)
        if self.owner.close_error:raise RuntimeError('synthetic close failure')


class PrivateReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for key in list(os.environ):
            if key.startswith('PG'):del os.environ[key]
        local=ROOT/'backend/feasibility/.local';local.mkdir(exist_ok=True)
        cls.cluster=Path(tempfile.mkdtemp(prefix='read-',dir=local))
        cls.data=cls.cluster/'data'
        cls.socket=Path(tempfile.mkdtemp(prefix='cj035-rs-',dir='/tmp'));cls.socket.chmod(0o700)
        cls.passfile=cls.cluster/'empty.pass';cls.passfile.touch(mode=0o600)
        cls.role='cj035_synthetic';cls.port=56435
        cls.env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C'}
        cls.started=False
        try:
            cls.run_pg('initdb','-D',str(cls.data),'-U',cls.role,'--auth-local=trust','--auth-host=reject','--encoding=UTF8','--no-locale')
            cls.run_pg('pg_ctl','-D',str(cls.data),'-l',str(cls.cluster/'postgres.log'),'-o',
                       f"-k {cls.socket} -p {cls.port} -c listen_addresses='' -c unix_socket_permissions=0700",'-w','start')
            cls.started=True
            with cls.raw_connect() as conn:
                assert conn.execute('SHOW listen_addresses').fetchone()[0]==''
                conn.execute((Path(__import__('cj_needs').__file__).resolve().parents[1]/'sql/candidate.sql').read_text())
            print('NEW_PRIVATE_PG='+str(cls.cluster)+'; TCP=disabled; synthetic_only=true',flush=True)
            cls.addClassCleanup(cls.stop_cluster)
        except BaseException:
            cls.stop_cluster();raise
    @classmethod
    def run_pg(cls,*args):
        return subprocess.run([str(BIN/args[0]),*args[1:]],env=cls.env,capture_output=True,text=True,check=True).stdout
    @classmethod
    def raw_connect(cls):
        return psycopg.connect(host=str(cls.socket),port=cls.port,user=cls.role,dbname='postgres',password='',
                               passfile=str(cls.passfile),sslmode='disable',connect_timeout=3,options='')
    @classmethod
    def stop_cluster(cls):
        if cls.started:
            cls.run_pg('pg_ctl','-D',str(cls.data),'-m','fast','-w','stop');cls.started=False
            assert not (cls.data/'postmaster.pid').exists()
            (cls.cluster/'STOPPED').write_text('Stopped; new private cluster preserved; no TCP\n')
            print('PG_STOPPED_PRESERVED='+str(cls.cluster),flush=True)
    def setUp(self):
        self.identity=Identity();self.close_hook=None;self.close_error=False;self.closed=0;self.opened=0
        self.scope_a='s-'+uuid.uuid4().hex;self.scope_b='s-'+uuid.uuid4().hex;self.environment='a'
        with self.raw_connect() as conn:
            conn.execute('INSERT INTO cj_needs_scope VALUES (%s),(%s)',(self.scope_a,self.scope_b))
        self.checker=AdmissionChecker(self.identity,self.identity,clock=lambda:self.identity.now)
        def connect():
            self.opened+=1
            return Connection(self.raw_connect(),self)
        self.connect=connect
        def resolve(principal):
            return self.connect,self.scope_a if principal.subject=='synthetic-a' and self.environment=='a' else self.scope_b
        self.boundary=Boundary(self.checker,resolve)
        self.auth=ProtectedReadBoundary(self.checker,max_response_bytes=LIMITS.max_output_bytes)
        self.seed({'fixed_items':[item('a'),item('b')]})
        self.seed({'party_size':known(3)},version=1)
        self.closed=self.opened=0
    def seed(self,changes,version=0):
        raw=json.dumps(dict(action_id='synthetic-'+str(version+1),needs_id='synthetic-needs',expected_version=version,
                            source={'kind':'manual','text':'synthetic original / 合成来源'},changes=changes),ensure_ascii=False).encode()
        self.boundary.with_operation('synthetic-only',lambda op:(op.act(Command(raw)),b'fixture-seeded')[1])
    def read(self,needs_id='synthetic-needs',limits=LIMITS,observer=None):
        def outer(context):
            def inner(operation):
                if observer is not None:observer(operation,context)
                return project_current(operation,context,needs_id,limits=limits)
            return self.boundary.with_operation('synthetic-only',inner)
        return self.auth.with_read_context('synthetic-only',outer)
    def test_actual_current_projection_conflict_and_original_source(self):
        raw=self.read();self.assertIs(type(raw),bytes)
        body=json.loads(raw)
        self.assertEqual((body['status'],body['overall'],body['revision']),('CONFLICT','UNKNOWN',2))
        fields={c['evidence'][0]['path']:c for c in body['checks'] if c['code']=='FIELD_DECLARED'}
        self.assertEqual(fields['fixed_items']['evidence'][0]['revision'],1)
        self.assertEqual(fields['party_size']['evidence'][0]['revision'],2)
        self.assertTrue(fields['fixed_items']['evidence'][0]['original_input_sha256'])
        from hashlib import sha256
        self.assertEqual(len(body['sources']),2)
        for source in body['sources']:
            self.assertEqual(sha256(source['original_input_utf8'].encode('utf-8')).hexdigest(),source['original_input_sha256'])
        self.assertNotIn('scope',body);self.assertNotIn('principal',body)
        self.assertEqual(self.opened,4)  # first + two revisions + final current read
    def test_authorized_missing_and_other_owner_both_withheld(self):
        with self.assertRaises(ReadWithheld) as absent:self.read('missing')
        self.identity.subject='synthetic-b'
        with self.assertRaises(ReadWithheld) as other:self.read()
        self.assertEqual(absent.exception.code,other.exception.code)
    def test_expired_unknown_and_missing_configuration_do_not_read(self):
        self.identity.now=1001
        with self.assertRaises(Exception):self.read()
        self.assertEqual(self.opened,0)
        self.identity.now=100;self.identity.fact=Fact.UNKNOWN
        with self.assertRaises(Exception):self.read()
        self.assertEqual(self.opened,0)
        self.identity.fact=Fact.YES;self.boundary.resolve=None
        with self.assertRaises(Exception):self.read()
        self.assertEqual(self.opened,0)
    def test_history_missing_rejected_not_zero_or_latest(self):
        with self.raw_connect() as conn:
            conn.execute('DELETE FROM cj_needs_revision WHERE scope=%s AND version=1',(self.scope_a,))
        with self.assertRaises(ReadWithheld) as failure:self.read()
        self.assertEqual(failure.exception.code,'REVISION_CHAIN_UNAVAILABLE')
    def test_original_revision_tampering_reuses_evaluator_rejection(self):
        with self.raw_connect() as conn:
            conn.execute('UPDATE cj_needs_revision SET original_input=%s WHERE scope=%s AND version=1',(b'{}',self.scope_a))
        with self.assertRaises(ReadWithheld) as failure:self.read()
        self.assertEqual(failure.exception.code,'EVALUATION_INPUT_INVALID')
    def test_bounds_revision_input_output_explicit(self):
        for limits,code in [(ReadLimits(1,1000000,100000),'REVISION_BOUND_EXCEEDED'),
                            (ReadLimits(10,1,100000),'INPUT_BOUND_EXCEEDED'),
                            (ReadLimits(10,1000000,1),'OUTPUT_BOUND_EXCEEDED')]:
            with self.subTest(code=code):
                with self.assertRaises(ReadWithheld) as failure:self.read(limits=limits)
                self.assertEqual(failure.exception.code,code)
    def test_current_changed_after_history_withheld(self):
        def change(count):
            if count==3:
                self.close_hook=None
                self.seed({'party_size':known(4)},version=2)
        self.close_hook=change
        with self.assertRaises(ReadWithheld) as failure:self.read()
        self.assertEqual(failure.exception.code,'CURRENT_RECORD_OR_BINDING_CHANGED')
    def test_close_revocation_withheld_after_actual_sql(self):
        self.close_hook=lambda count:setattr(self.identity,'fact',Fact.NO)
        with self.assertRaises(Exception):self.read()
        self.assertGreater(self.closed,0)
    def test_close_identity_change_withheld(self):
        self.close_hook=lambda count:setattr(self.identity,'subject','synthetic-b')
        with self.assertRaises(Exception):self.read()
    def test_final_encoded_projection_revocation_withheld(self):
        from cj_feasibility import current_read
        original=current_read.json.JSONEncoder.iterencode
        identity=self.identity
        def revoke(encoder,*args,**kwargs):
            yield from original(encoder,*args,**kwargs)
            identity.fact=Fact.NO
        with patch.object(current_read.json.JSONEncoder,'iterencode',revoke):
            with self.assertRaises(Exception):self.read()
    def test_handle_outside_lifetime_rejected(self):
        captured=[]
        self.read(observer=lambda op,ctx:captured.append((op,ctx)))
        with self.assertRaises(Exception):project_current(*captured[0],'synthetic-needs',limits=LIMITS)
    def test_no_business_writes_during_evaluation(self):
        with self.raw_connect() as conn:
            before=conn.execute('SELECT count(*),sum(version) FROM cj_needs_record').fetchone(),conn.execute('SELECT count(*) FROM cj_needs_revision').fetchone()
        self.read()
        with self.raw_connect() as conn:
            after=conn.execute('SELECT count(*),sum(version) FROM cj_needs_record').fetchone(),conn.execute('SELECT count(*) FROM cj_needs_revision').fetchone()
        self.assertEqual(before,after)


@unittest.skipUnless(os.environ.get('CJ035_RUN_SEAM_PROBES')=='1','explicit known upstream seam probes only')
class UpstreamSeamProbes(PrivateReadTests):
    # Do not repeat inherited positive tests in the explicit negative probe run.
    def test_close_failure_must_not_release_bytes(self):
        self.close_error=True
        with self.assertRaises(Exception):self.read()
    def test_environment_rebind_on_close_must_not_release_bytes(self):
        self.close_hook=lambda count:setattr(self,'environment','b')
        with self.assertRaises(Exception):self.read()


if __name__=='__main__':unittest.main()
