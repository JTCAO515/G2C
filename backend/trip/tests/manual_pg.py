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
        cls.old_app=cls.app
        cls.signer=ConfirmationSigner(b'synthetic-explicit-manual-host-key-1234567')
        from cj_api.local_run_context import load_run_context
        path=cls.auth/'manual-source-context.json';now=int(time.time())
        path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
            meter=dict(unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,
                max_steps=20,max_tools=10,max_output=10000,max_seconds=600),
            output_limits=dict(model=4000,tool=8000,memory=2000)))))
        cls.run_context=load_run_context(path)
        cls.app=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=cls.auth,
            confirmation_signer=cls.signer,run_context=cls.run_context)

    def setUp(self):
        self.tag=uuid.uuid4().hex
        self.owner=scope_for(ISSUER,'alice');self.scope=trip_scope_for(self.owner)
        self.database.provision(self.owner)
        self.repository=Repository(lambda:self.database.connect(self.owner),self.scope,self.signer,structured=True)
        self.trip_id,self.root_run_id,self.root_message_id,self.original_legacy=self.legacy_trip()
        event={name:{'state':'unknown'} for name in ('date','time','timezone','utc_offset')}
        original=json.loads(self.original_legacy)
        initialize=packed(dict(version='TRIP-initialize.1',request_id='fixture-initialize-'+self.tag,
            trip_id=self.trip_id,expected_version=1,original_hash=sha256(self.original_legacy).hexdigest(),
            items=[dict(id=item['id'],schedule=dict(start=event,end=event),
                        fixed={'state':'known','value':False}) for item in original['items']]))
        with TestClient(self.app) as client:
            prepared=self.write(client,'/v1/trip-structured-initializations',initialize)
            self.assertEqual(prepared.status_code,200,prepared.text)
            candidate=prepared.json()['initialization']
            saved=self.write(client,'/v1/trip-structured-initialization-saves',packed(dict(
                version='TRIP-initialize-save.1',action_id='fixture-save-'+self.tag,
                proposal_id=candidate['proposal_id'],candidate_hash=candidate['candidate_hash'])))
            self.assertEqual(saved.status_code,200,saved.text)
        current=self.repository.detail(self.trip_id);self.assertEqual(current.version,2)
        self.base_version=2;self.content=current.content
        self.item_id=json.loads(self.content)['items'][0]['id']
        self.edit=packed(dict(version='TRIP-manual-edit.1',request_id='prepare-'+self.tag,trip_id=self.trip_id,
            expected_version=self.base_version,original_hash=sha256(self.content).hexdigest(),
            title='保存明确改写 / saved',changes=[],order=None))

    def legacy_trip(self):
        from cj_agent.provider import FakeProvider
        with TestClient(self.old_app) as client:
            mid,response=self.send(client,'alice','Plan Beijing explicitly',conversation='origin-'+uuid.uuid4().hex,intent='consider_trip')
            self.assertEqual(response.status_code,200,response.text)
            run_id=response.json()['receipt']['run_id']
            outcome=next(value for value in self.work('alice',FakeProvider()) if value.message_id==mid)
            self.assertEqual(outcome.status,'completed')
            proposal=client.get('/v1/trip-proposals',params={'proposal_id':outcome.proposal_id},headers=self.headers('alice'))
            self.assertEqual(proposal.status_code,200,proposal.text)
            value=proposal.json()['proposal']
            raw=packed(['origin-accept-'+uuid.uuid4().hex,'accept',value['proposal_id'],value['candidate_hash'],'ui-confirm'])
            accepted=self.write(client,'/v1/trip-actions',raw)
            self.assertEqual(accepted.status_code,200,accepted.text)
            content=self.database.trip_repository(self.owner).detail(value['trip_id']).content
            return value['trip_id'],run_id,mid,content

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
            self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version)
            response=self.write(client,'/v1/trip-manual-saves',raw)
            self.assertEqual(response.status_code,200,response.text)
            receipt=response.json()['receipt'];self.assertEqual(receipt['committed_version'],self.base_version+1)
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',raw).json()['receipt'],receipt)
            self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version+1)
            foreign=self.write(client,'/v1/trip-manual-saves',raw,'bob')
            self.assertNotEqual(foreign.status_code,200)
            rebuilt=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=self.auth,confirmation_signer=self.signer,run_context=self.run_context)
            with TestClient(rebuilt) as reopened:
                result=reopened.get('/v1/trip-manual-receipts',params={'action_id':'save-'+self.tag},headers=self.headers('alice'))
                self.assertEqual(result.json()['receipt'],receipt)
                denied=reopened.get('/v1/trip-manual-receipts',params={'action_id':'save-'+self.tag},headers=self.headers('bob'))
                self.assertEqual(denied.json()['receipt'],None)
            changed=json.loads(raw);changed['candidate_hash']='f'*64
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',packed(changed)).status_code,409)
            current=client.get('/v3/trip-structured',params={'trip_id':self.trip_id},headers=self.headers('alice'))
            self.assertEqual(current.json()['trip']['version'],self.base_version+1)
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
            self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version+1)

    def test_explicit_time_conflict_has_no_proposal_and_fixed_read_protects_next_edit(self):
        def event(clock):
            return dict(date={'state':'known','value':'2026-11-02'},
                time={'state':'known','value':clock},timezone={'state':'known','value':'Asia/Shanghai'},
                utc_offset={'state':'unknown'})
        with TestClient(self.app) as client:
            edit=json.loads(self.edit);edit['title']=None
            edit['changes']=[dict(item_id=self.item_id,field='schedule',value=dict(start=event('09:00:00'),end=event('10:00:00')))]
            response=self.write(client,'/v1/trip-manual-preparations',packed(edit))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',self.save(response.json()['preparation'])).status_code,200)
            current=self.repository.detail(self.trip_id)
            self.assertEqual(current.version,self.base_version+1)
            self.assertEqual(json.loads(current.content)['items'][0]['schedule']['start'],event('09:00:00'))
            edit.update(request_id='bad-time-'+self.tag,expected_version=self.base_version+1,original_hash=sha256(current.content).hexdigest())
            edit['changes'][0]['value']['start']=event('11:00:00')
            bad=self.write(client,'/v1/trip-manual-preparations',packed(edit))
            self.assertEqual(bad.status_code,409,bad.text)
            absent=client.get('/v1/trip-manual-preparations',params={'request_id':edit['request_id']},headers=self.headers('alice'))
            self.assertIsNone(absent.json()['preparation'])
            self.assertEqual(self.repository.detail(self.trip_id),current)
            edit.update(request_id='lock-'+self.tag,changes=[dict(item_id=self.item_id,field='fixed',value={'state':'known','value':True})])
            prepared=self.write(client,'/v1/trip-manual-preparations',packed(edit))
            self.assertEqual(prepared.status_code,200,prepared.text)
            save=json.loads(self.save(prepared.json()['preparation']));save['action_id']='lock-save-'+self.tag
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',packed(save)).status_code,200)
            current=self.repository.detail(self.trip_id)
            self.assertEqual(current.version,self.base_version+2)
            self.assertEqual(json.loads(current.content)['items'][0]['fixed'],{'state':'known','value':True})
            edit.update(request_id='after-lock-'+self.tag,expected_version=self.base_version+2,original_hash=sha256(current.content).hexdigest(),
                changes=[dict(item_id=self.item_id,field='text',value='incidental change')])
            self.assertEqual(self.write(client,'/v1/trip-manual-preparations',packed(edit)).status_code,409)
            self.assertEqual(self.repository.detail(self.trip_id),current)

    def test_legacy_formal_trip_explicit_initialization_then_same_manual_editor(self):
        from cj_api.local_app import create_local_app
        self.trip_id,_,_,legacy=self.legacy_trip()
        item_id=json.loads(legacy)['items'][0]['id']
        # Read the actual existing CJ015 minimal endpoint, not a constructed DTO.
        with TestClient(create_local_app(conninfo_path=CONNINFO,auth_dir=self.auth)) as original_client:
            old=original_client.get('/v1/trip-details',params={'trip_id':self.trip_id},headers=self.headers('alice'))
            self.assertEqual(old.status_code,200,old.text)
        event={name:{'state':'unknown'} for name in ('date','time','timezone','utc_offset')}
        request=packed(dict(version='TRIP-initialize.1',request_id='initialize-'+self.tag,trip_id=self.trip_id,
            expected_version=1,original_hash=sha256(legacy).hexdigest(),items=[dict(id=item['id'],
                schedule=dict(start=event,end=event),fixed={'state':'known','value':False}) for item in json.loads(legacy)['items']]))
        with TestClient(self.app) as client:
            response=self.write(client,'/v1/trip-structured-initializations',request)
            self.assertEqual(response.status_code,200,response.text)
            preparation=response.json()['initialization']
            self.assertEqual(response.json()['version'],'TRIP-initialize-result.1')
            self.assertEqual(self.repository.detail(self.trip_id).content,legacy)
            save=packed(dict(version='TRIP-initialize-save.1',action_id='initialize-save-'+self.tag,
                proposal_id=preparation['proposal_id'],candidate_hash=preparation['candidate_hash']))
            saved=self.write(client,'/v1/trip-structured-initialization-saves',save)
            self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(saved.json()['receipt']['committed_version'],2)
            current=self.repository.detail(self.trip_id);content=json.loads(current.content)
            self.assertEqual(content['title'],json.loads(legacy)['title'])
            self.assertEqual(content['items'][0]['text'],json.loads(legacy)['items'][0]['text'])
            self.assertEqual(content['items'][0]['source_category'],'unknown')
            self.assertEqual(content['items'][0]['schedule']['start']['date'],{'state':'unknown'})
            self.assertEqual(self.write(client,'/v1/trip-structured-initialization-saves',save).json()['receipt'],saved.json()['receipt'])
            self.assertNotEqual(self.write(client,'/v1/trip-structured-initialization-saves',save,'bob').status_code,200)
            wrong=json.loads(save);wrong['version']='TRIP-manual-save.1';wrong['action_id']='wrong-path-'+self.tag
            self.assertNotEqual(self.write(client,'/v1/trip-manual-saves',packed(wrong)).status_code,200)
            self.assertIsNone(self.repository.query_action(wrong['action_id']))
            edit=json.loads(self.edit);edit.update(request_id='after-initialize-'+self.tag,trip_id=self.trip_id,expected_version=2,
                original_hash=sha256(current.content).hexdigest(),title=None,
                changes=[dict(item_id=item_id,field='text',value='明确手动改写 / explicit manual edit')])
            edited=self.write(client,'/v1/trip-manual-preparations',packed(edit))
            self.assertEqual(edited.status_code,200,edited.text)
            committed=self.write(client,'/v1/trip-manual-saves',self.save(edited.json()['preparation']))
            self.assertEqual(committed.status_code,200,committed.text)
            self.assertEqual(committed.json()['receipt']['committed_version'],3)

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
                    self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version)
                else:
                    self.assertEqual(query.json()['receipt']['committed_version'],self.base_version+1)
                    self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version+1)
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
        self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version)
    def test_z_origin_guard_rejects_hidden_needs_markers_and_corrupt_context(self):
        from unittest.mock import patch
        from cj_api.local_app import LocalDatabase
        from cj_message.needs_binding import needs_scope_for
        # A missing source context must not use RLS-filtered absence as evidence.
        closed=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=self.auth,confirmation_signer=self.signer)
        with TestClient(closed) as client:
            result=self.write(client,'/v1/trip-manual-preparations',self.edit)
            self.assertEqual(result.status_code,503,result.text)
        # Source GUC must agree with the actual canonical principal mapping.
        from cj_api.local_app import _ScopedConnection
        original_bind=_ScopedConnection.bind_scope
        def wrong_needs(connection,cursor):
            original_bind(connection,cursor)
            cursor.execute("SELECT set_config('cj.needs_scope','n-wrong',true)")
        with patch.object(_ScopedConnection,'bind_scope',wrong_needs),TestClient(self.app) as client:
            result=self.write(client,'/v1/trip-manual-preparations',self.edit)
            self.assertEqual(result.status_code,503,result.text)
        self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version)
        # A manually labelled root with no persisted origin is not source proof.
        unknown_id='unknown-'+self.tag
        marker=Proposal('marker-'+self.tag,unknown_id,0,'manual-unbound.1',int(time.time())+300,self.content)
        digest=self.repository.publish(marker)
        action=self.signer.issue(self.scope,self.repository.proposal_detail(marker.proposal_id),
            action_id='marker-save-'+self.tag,kind='accept',candidate_hash=digest).action
        self.repository.act(action)
        unknown=json.loads(self.edit);unknown.update(trip_id=unknown_id,expected_version=1,
            request_id='unknown-origin-'+self.tag,original_hash=sha256(self.content).hexdigest())
        with TestClient(self.app) as client:
            self.assertEqual(self.write(client,'/v1/trip-manual-preparations',packed(unknown)).status_code,503)
            prepared=self.prepare(client);save=self.save(prepared)
        # Inject a genuine-domain NEEDS source record through the private test
        # administrator only. This is a rejection probe, never B305 L1 acceptance.
        from cj_needs.domain import Command as NeedsCommand
        from cj_needs.postgres import Repository as NeedsRepository
        config=json.loads(Path(CONNINFO).read_text());needs_scope=needs_scope_for(self.owner)
        needs_id='needs-'+self.tag
        with psycopg.connect(**config,autocommit=True) as admin:
            admin.execute('INSERT INTO cj_needs_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(needs_scope,))
        needs=NeedsRepository(lambda:psycopg.connect(**config),needs_scope,lambda stage:None)
        command=NeedsCommand(packed(dict(action_id='source-'+self.tag,needs_id=needs_id,expected_version=0,
            source=dict(kind='manual',text='synthetic source for a rejection probe'),changes=dict(party_size={'state':'known','value':2}))))
        needs.act(command);snapshot=needs.detail(needs_id)
        with psycopg.connect(**config,autocommit=True) as admin:
            admin.execute('INSERT INTO cj_message_needs_binding(message_scope,message_id,run_id,needs_scope,needs_id,needs_version,content_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (self.owner,self.root_message_id,self.root_run_id,needs_scope,needs_id,1,sha256(snapshot.content).hexdigest()))
        with self.database.connect(self.owner) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_scope=%s',(self.owner,)).fetchone()[0],0)
        configured=LocalDatabase(CONNINFO,run_context=self.run_context)
        with configured.connect(self.owner) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_scope=%s',(self.owner,)).fetchone()[0],1)
        # Trace initialization markers back to the actual newly bound RUN. Both
        # fresh prepare and save of an earlier candidate must now refuse effects.
        changed=json.loads(self.edit);changed['request_id']='after-needs-'+self.tag
        with TestClient(self.app) as client:
            self.assertEqual(self.write(client,'/v1/trip-manual-preparations',packed(changed)).status_code,503)
            self.assertEqual(self.write(client,'/v1/trip-manual-saves',save).status_code,503)
            query=client.get('/v1/trip-manual-receipts',params={'action_id':'save-'+self.tag},headers=self.headers('alice'))
            self.assertIsNone(query.json()['receipt'])
            # Original successful receipt lookup remains possible without a
            # current source configuration; it cannot publish another version.
        with TestClient(closed) as client:
            original=client.get('/v1/trip-structured-initialization-receipts',
                params={'action_id':'fixture-save-'+self.tag},headers=self.headers('alice'))
            self.assertEqual(original.status_code,200,original.text)
            self.assertEqual(original.json()['receipt']['committed_version'],self.base_version)
        self.assertEqual(self.repository.detail(self.trip_id).version,self.base_version)


if __name__=='__main__':unittest.main(verbosity=2)
