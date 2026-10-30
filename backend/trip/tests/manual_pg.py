"""Actual canonical AUTH/limited PG/sole Trip transaction; no real services."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import unittest
import uuid

from fastapi.testclient import TestClient
import psycopg

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from cj_agent.draft import trip_scope_for
from cj_api.local_app import ISSUER,scope_for
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Proposal,packed
from cj_trip.local_manual_app import create_local_manual_app
from cj_trip.postgres import Repository


def unknown():return {'state':'unknown'}
def event():return {name:unknown() for name in ('date','time','timezone','utc_offset')}


class ManualChecks(Harness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.signer=ConfirmationSigner(b'synthetic-explicit-manual-host-key-1234567')
        cls.app=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=cls.auth,confirmation_signer=cls.signer)

    def setUp(self):
        self.tag=uuid.uuid4().hex
        self.owner=scope_for(ISSUER,'alice');self.scope=trip_scope_for(self.owner)
        self.database.provision(self.owner)
        self.repository=Repository(lambda:self.database.connect(self.owner),self.scope,self.signer,structured=True)
        self.trip_id='trip-'+self.tag
        self.content=packed(dict(content_version='structured.1',title='实际正式行程 / original',sources=[],items=[dict(
            id='item-1',text='明确原文',verification='pending',evidence=[],source_category='user_provided',source_refs=[],
            schedule=dict(start=event(),end=event()),fixed={'state':'known','value':False})]))
        p=Proposal('seed-'+self.tag,self.trip_id,0,'manual-unbound.1',int(time.time())+300,self.content)
        digest=self.repository.publish(p)
        detail=self.repository.proposal_detail(p.proposal_id)
        action=self.signer.issue(self.scope,detail,action_id='seed-save-'+self.tag,kind='accept',candidate_hash=digest).action
        self.repository.act(action)
        self.edit=packed(dict(version='TRIP-manual-edit.1',request_id='prepare-'+self.tag,trip_id=self.trip_id,
            expected_version=1,original_hash=sha256(self.content).hexdigest(),title='保存明确改写 / saved',
            changes=[],order=None))

    def write(self,client,path,raw,identity='alice'):
        return client.post(path,content=raw,headers={**self.headers(identity),'Content-Type':'application/octet-stream'})

    def prepare(self,client):
        response=self.write(client,'/v1/trip-manual-preparations',self.edit)
        self.assertEqual(response.status_code,200,response.text)
        preparation=response.json()['preparation']
        self.assertEqual(preparation['feasibility']['status'],'UNKNOWN')
        return preparation

    def save(self,preparation):
        return packed(dict(version='TRIP-manual-save.1',action_id='save-'+self.tag,
            proposal_id=preparation['proposal_id'],candidate_hash=preparation['candidate_hash']))

    def test_signed_manual_single_save_original_receipt_reopen_and_foreign(self):
        with TestClient(self.app) as client:
            preparation=self.prepare(client);raw=self.save(preparation)
            self.assertEqual(self.repository.detail(self.trip_id).version,1)
            response=self.write(client,'/v1/trip-manual-saves',raw)
            self.assertEqual(response.status_code,200,response.text)
            receipt=response.json()['receipt'];self.assertEqual(receipt['committed_version'],2)
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',raw).json()['receipt'],receipt)
            self.assertEqual(self.repository.detail(self.trip_id).version,2)
            foreign=self.write(client,'/v1/trip-manual-saves',raw,'bob')
            self.assertNotEqual(foreign.status_code,200)
            rebuilt=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=self.auth,confirmation_signer=self.signer)
            with TestClient(rebuilt) as reopened:
                result=reopened.get('/v1/trip-manual-receipts',params={'action_id':'save-'+self.tag},headers=self.headers('alice'))
                self.assertEqual(result.json()['receipt'],receipt)
                denied=reopened.get('/v1/trip-manual-receipts',params={'action_id':'save-'+self.tag},headers=self.headers('bob'))
                self.assertEqual(denied.json()['receipt'],None)
            changed=json.loads(raw);changed['candidate_hash']='f'*64
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',packed(changed)).status_code,409)
            current=client.get('/v3/trip-structured',params={'trip_id':self.trip_id},headers=self.headers('alice'))
            self.assertEqual(current.json()['trip']['version'],2)
            self.assertEqual(current.json()['trip']['content']['items'],json.loads(self.content)['items'])
            self.assertEqual(self.prepare(client)['candidate_hash'],preparation['candidate_hash'])

    def test_two_prepared_saves_have_original_cas_and_rollback(self):
        with TestClient(self.app) as client:
            first=self.prepare(client)
            edit=json.loads(self.edit);edit['request_id']='second-'+self.tag;edit['title']='第二个明确候选'
            second=self.write(client,'/v1/trip-manual-preparations',packed(edit))
            self.assertEqual(second.status_code,200,second.text)
            raw=self.save(first)
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',raw).status_code,200)
            body=json.loads(self.save(second.json()['preparation']));body['action_id']='second-save-'+self.tag
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',packed(body)).status_code,409)
            self.assertIsNone(self.repository.query_action(body['action_id']))
            with self.database.connect(self.owner) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_manual_intent WHERE scope=%s AND action_id=%s',
                    (self.scope,body['action_id'])).fetchone()[0],0)
            self.assertEqual(self.repository.detail(self.trip_id).version,2)

    def test_ack_unknown_reconciles_original_and_rollback_retains_trip(self):
        from unittest.mock import patch
        from cj_api.local_app import LocalDatabase
        for mode in ('rollback','lost_ack'):
            # Separate fixture IDs isolate the two original actions; no resend of
            # an UNKNOWN action is used to manufacture a second scenario.
            if mode=='lost_ack':self.setUp()
            with TestClient(self.app) as client:
                preparation=self.prepare(client);raw=self.save(preparation)
                original=LocalDatabase.connect
                fired=[]
                class Cursor:
                    def __init__(self,base,owner):self.base,self.owner=base,owner
                    def __getattr__(self,name):return getattr(self.base,name)
                    def execute(self,sql,*args,**kwargs):
                        if sql.startswith('INSERT INTO cj_trip_manual_intent'):
                            self.owner.saved=True
                            if mode=='rollback':raise psycopg.OperationalError('synthetic rollback')
                        self.base.execute(sql,*args,**kwargs)
                        return self
                class Connection:
                    def __init__(self,base):self.base,self.saved=base,False
                    def __getattr__(self,name):return getattr(self.base,name)
                    def __enter__(self):return self.base.__enter__()
                    def __exit__(self,*args):return self.base.__exit__(*args)
                    def cursor(self,*args,**kwargs):return Cursor(self.base.cursor(*args,**kwargs),self)
                    def commit(self):
                        self.base.commit()
                        if self.saved and mode=='lost_ack' and not fired:
                            fired.append(True)
                            raise psycopg.OperationalError('synthetic lost acknowledgement')
                def connect(database,scope,*args,**kwargs):return Connection(original(database,scope,*args,**kwargs))
                with patch.object(LocalDatabase,'connect',connect):
                    response=self.write(client,'/v1/trip-manual-saves',raw)
                self.assertEqual(response.status_code,503,response.text)
                self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
                query=client.get('/v1/trip-manual-receipts',params={'action_id':'save-'+self.tag},headers=self.headers('alice'))
                self.assertEqual(query.status_code,200,query.text)
                if mode=='rollback':
                    self.assertIsNone(query.json()['receipt'])
                    self.assertEqual(self.repository.detail(self.trip_id).version,1)
                else:
                    self.assertEqual(query.json()['receipt']['committed_version'],2)
                    self.assertEqual(self.repository.detail(self.trip_id).version,2)
                    self.assertEqual(fired,[True])

    def test_minimum_acl_foreign_rls_and_nonempty_down_refuses(self):
        with TestClient(self.app) as client:self.prepare(client)
        other=scope_for(ISSUER,'bob')
        self.database.provision(other)
        with self.database.connect(other) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_manual_basis WHERE scope=%s',(self.scope,)).fetchone()[0],0)
        with self.database.connect(self.owner) as conn:
            basis=conn.execute('SELECT request_id,proposal_id,original_input,original_content,diff FROM cj_trip_manual_basis WHERE scope=%s AND request_id=%s',
                (self.scope,'prepare-'+self.tag)).fetchone()
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.database.connect(other) as conn:
                conn.execute('INSERT INTO cj_trip_manual_basis(scope,request_id,proposal_id,original_input,original_content,diff) VALUES(%s,%s,%s,%s,%s,%s)',
                    (self.scope,*basis))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.database.connect(other) as conn:
                conn.execute('INSERT INTO cj_trip_manual_intent(scope,action_id,proposal_id,original_input,original_action) VALUES(%s,%s,%s,%s,%s)',
                    (self.scope,'foreign-'+self.tag,basis[1],b'{}',b'{}'))
        for table in ('cj_trip_manual_basis','cj_trip_manual_intent'):
            for operation in ('DELETE','TRUNCATE','UPDATE'):
                with self.database.connect(self.owner) as conn:
                    self.assertFalse(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',(table,operation)).fetchone()[0])
        config=json.loads(Path(CONNINFO).read_text())
        with psycopg.connect(**config) as admin:
            with self.assertRaises(psycopg.Error):admin.execute((ROOT/'backend/migrations/down/0022_trip_manual.down.sql').read_text())
        self.assertEqual(self.repository.detail(self.trip_id).version,1)


if __name__=='__main__':unittest.main(verbosity=2)
