"""C1 actual signed API, runtime PG and worker; no synthetic Context authority."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'backend/memory/tests'), str(ROOT/'backend/agent/tests'), str(ROOT/'scripts')]
import memory_save_read_checks as helpers
import runtime_host_pg as runtime
from e2e_local import Harness, CONNINFO
from cj_api.local_app import create_local_memory_management_app, LocalDatabase, scope_for, ISSUER
from cj_memory.local import LocalMemoryConfiguration
from cj_memory.postgres import Repository
from cj_memory.domain import CommitUnknown, Unavailable


class EditManagementChecks(Harness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import time
        from cj_api.local_run_context import load_run_context
        import local_run_context as operator
        now=int(time.time())
        cls.run_path=cls.auth/'memory-meter.json'
        cls.run_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@1',current=dict(meter=dict(
            unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,
            max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
            output_limits=dict(answer=1000,draft=1000)),history=[])))
        cls.run_context=load_run_context(cls.run_path)
        for identity in ('alice','bob'):
            operator.provision_budget(CONNINFO,cls.run_context,identity)
        cls.database=LocalDatabase(CONNINFO,run_context=cls.run_context)

    write_policy = helpers.MemorySaveReadChecks.write_policy
    app_from_policy = runtime.MemoryRuntimeChecks.app_from_policy
    raw = helpers.MemorySaveReadChecks.raw
    save = helpers.MemorySaveReadChecks.save
    receipt = helpers.MemorySaveReadChecks.receipt
    service = helpers.MemorySaveReadChecks.service
    configuration = runtime.MemoryRuntimeChecks.configuration
    execute = runtime.MemoryRuntimeChecks.execute

    def setUp(self):
        helpers.MemorySaveReadChecks.setUp(self)
        self.runtime_expiry=self.policy['expires_at']
        self.manager=self.management_app()
        with TestClient(self.memory_app) as api:
            self.assertEqual(api.get('/v1/memories', params={'limit':50},
                                     headers=self.headers('bob')).status_code,200)

    def management_app(self, policy=None):
        return create_local_memory_management_app(conninfo_path=CONNINFO,auth_dir=self.auth,
            memory_configuration=LocalMemoryConfiguration.from_bytes(json.dumps(policy or self.policy).encode()))

    def action(self, raw, operation='edit', version=1, **changes):
        obj=json.loads(raw)
        action=dict(action_id='action-'+uuid.uuid4().hex,operation=operation,item_id=obj['item_id'],
                    expected_version=version,expected_source_version=1)
        if operation=='edit': action.update(version='MEMORY-MANAGEMENT-EDIT@1',text='Corrected 原文')
        action.update(changes)
        return json.dumps(action,ensure_ascii=False,separators=(',',':')).encode()

    def apply(self, client, raw, identity='alice'):
        path='/v1/memory-edit-actions' if json.loads(raw)['operation']=='edit' else '/v1/memory-management-actions'
        return client.post(path,content=raw,headers={**self.headers(identity),'Content-Type':'application/octet-stream'})

    def query(self, client, raw, identity='alice'):
        return client.get('/v1/memory-management-receipts',params={'action_id':json.loads(raw)['action_id']},
                          headers=self.headers(identity))

    def test_three_kinds_history_pause_edit_resume_worker_and_reopen(self):
        with TestClient(self.memory_app) as api, TestClient(self.manager) as manager:
            final=[]
            for kind in ('fact','experience','preference'):
                original=self.raw(kind);self.assertEqual(self.save(api,original).status_code,200)
                old=self.service().detail(json.loads(original)['item_id']);old_source=old.command.source_id
                pause=self.action(original,'pause');self.assertEqual(self.apply(manager,pause).status_code,200)
                edit=self.action(original,version=2,text='新 '+kind+' / New '+kind)
                changed=self.apply(manager,edit);self.assertEqual(changed.status_code,200,changed.text)
                self.assertEqual((changed.json()['receipt']['status'],changed.json()['receipt']['version']),('disabled',3))
                self.assertNotIn(old.command.item_id, [i.command.item_id for i in self.service().effective('self').items])
                resume=self.action(original,'resume',version=3)
                self.assertEqual(self.apply(manager,resume).status_code,200)
                item=self.service().detail(old.command.item_id)
                self.assertEqual((item.version,item.status,item.command.kind,item.command.subject,item.command.slot,
                                  item.command.extent,item.command.context_id,item.command.occurred_at),
                                 (4,'active',kind,old.command.subject,old.command.slot,old.command.extent,
                                  old.command.context_id,old.command.occurred_at))
                with self.database.connect(scope_for(ISSUER,'alice')) as conn:
                    self.assertEqual(bytes(conn.execute('SELECT approved_input FROM cj_memory_source WHERE source_id=%s',(old_source,)).fetchone()[0]),old.command.raw)
                    row=conn.execute('SELECT previous_source_id,new_source_id,disabled_by_version FROM cj_memory_management_action WHERE action_id=%s',(json.loads(edit)['action_id'],)).fetchone()
                    self.assertEqual(row,(old_source,item.command.source_id,2))
                self.assertEqual(self.apply(manager,edit).json()['receipt'],changed.json()['receipt'])
                self.assertEqual(self.query(manager,edit).json()['receipt'],changed.json()['receipt'])
                self.assertEqual(self.query(manager,edit,'bob').json()['receipt'],None)
                self.assertEqual(self.apply(manager,edit+b' ').status_code,409)
                self.assertEqual(self.receipt(api,original).json()['receipt']['version'],1)
                final.append(item.command.text)
            for chat in (self.chat_a,self.chat_b):
                mid,response=self.send(api,'alice','Use latest saved values',conversation=chat)
                self.assertEqual(response.status_code,200,response.text)
                model=runtime.ObservedProvider();self.assertIn('completed',[o.status for o in self.execute(model) if o.message_id==mid])
                items=json.loads(model.inputs[0][0][0]['content'].split('\n',1)[1])['items']
                self.assertEqual({x['text'] for x in items},set(final))
        with TestClient(self.management_app()) as rebuilt:
            self.assertEqual(self.query(rebuilt,edit).json()['receipt'],changed.json()['receipt'])

    def test_active_edit_concurrent_cas_and_conflicting_slot(self):
        with TestClient(self.memory_app) as api, TestClient(self.manager) as manager:
            raw=self.raw();self.assertEqual(self.save(api,raw).status_code,200)
            edits=[self.action(raw,text=text) for text in ('One 一','Two 二')]
            with ThreadPoolExecutor(max_workers=2) as pool:
                codes=list(pool.map(lambda raw:self.apply(manager,raw).status_code,edits))
            self.assertEqual(sorted(codes),[200,409])
            pause=self.action(raw,'pause',version=2);self.assertEqual(self.apply(manager,pause).status_code,200)
            new=self.raw();self.assertEqual(self.save(api,new).status_code,200)
            self.assertEqual(self.apply(manager,self.action(raw,'resume',version=3)).status_code,409)

    def test_rejected_edit_policy_candidate_generic_disabled_and_foreign(self):
        with TestClient(self.memory_app) as api, TestClient(self.manager) as manager:
            raw=self.raw();self.assertEqual(self.save(api,raw).status_code,200)
            edit=self.action(raw)
            self.assertNotEqual(self.apply(manager,edit,'bob').status_code,200)
            denied=deepcopy(self.policy);denied['profiles']['alice']['slots'][self.slots['preference']]['collection_allowed']=False
            with TestClient(self.management_app(denied)) as blocked:
                self.assertNotEqual(self.apply(blocked,edit).status_code,200)
                self.assertIsNone(self.query(blocked,edit).json()['receipt'])
            candidate=self.raw('ambiguous',kind='fact');self.assertEqual(self.save(api,candidate).status_code,200)
            self.assertNotEqual(self.apply(manager,self.action(candidate)).status_code,200)
            # Existing runtime INSERT models a generic preexisting disabled row; it
            # has no management pause causality and cannot be edited or resumed.
            from cj_memory.manual import parse_manual
            c=parse_manual(self.raw('experience'));scope=scope_for(ISSUER,'alice')
            with self.database.connect(scope) as conn:
                from cj_memory.postgres import Transaction
                tx=Transaction(conn.cursor(),scope);tx.lock_scope();tx.create_manual_source(c,True,LocalMemoryConfiguration.from_bytes(json.dumps(self.policy).encode()).profiles['alice'].expires_at);tx.insert(c,'disabled')
            for op in ('edit','resume'):
                self.assertNotEqual(self.apply(manager,self.action(c.raw,op)).status_code,200)
            self.assertEqual(self.service().detail(json.loads(raw)['item_id']).version,1)
            for extra in ({'scope':'bob'},{'expected_version':True},{'text':' '},{'version':'unknown'}):
                self.assertEqual(self.apply(manager,self.action(raw,**extra)).status_code,400)
            invalid=edit[:-1]+b',"text":"duplicate"}'
            self.assertEqual(self.apply(manager,invalid).status_code,400)

    def test_real_rollback_ack_unknown_auth_and_same_action_reconciliation(self):
        original_transaction=Repository.transaction
        with TestClient(self.memory_app) as api, TestClient(self.manager) as manager:
            raw=self.raw();self.assertEqual(self.save(api,raw).status_code,200)
            rollback=self.action(raw)
            @contextmanager
            def rollback_tx(repository):
                with original_transaction(repository) as tx:
                    yield tx
                    raise Unavailable('fixture fail before commit')
            with patch.object(Repository,'transaction',rollback_tx):
                self.assertNotEqual(self.apply(manager,rollback).status_code,200)
            self.assertIsNone(self.query(manager,rollback).json()['receipt'])
            self.assertEqual(self.service().detail(json.loads(raw)['item_id']).version,1)
            edit=self.action(raw)
            @contextmanager
            def lost_ack(repository):
                with original_transaction(repository) as tx: yield tx
                raise CommitUnknown('fixture ACK lost after commit')
            with patch.object(Repository,'transaction',lost_ack):
                result=self.apply(manager,edit)
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['error']['recovery'],'reconcile_original')
            found=self.query(manager,edit);self.assertEqual(found.status_code,200)
            self.assertEqual(found.json()['receipt']['input_sha256'],hashlib.sha256(edit).hexdigest())
            self.assertEqual(self.service().detail(json.loads(raw)['item_id']).version,2)
            (self.auth/'invited.json').write_text('[]')
            try:self.assertNotEqual(self.query(manager,edit).status_code,200)
            finally:(self.auth/'invited.json').write_text(json.dumps(['alice','bob']))

    def test_rls_minimum_acl_and_nonempty_down_refuses_without_loss(self):
        from psycopg import errors
        with TestClient(self.memory_app) as api, TestClient(self.manager) as manager:
            raw=self.raw();self.assertEqual(self.save(api,raw).status_code,200)
            edit=self.action(raw);self.assertEqual(self.apply(manager,edit).status_code,200)
            alice=scope_for(ISSUER,'alice');bob=scope_for(ISSUER,'bob')
            with self.database.connect(bob) as conn:
                # Bob has no MEMORY namespace yet; RLS still denies Alice's rows.
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_management_action').fetchone()[0],0)
                self.assertEqual(conn.execute('UPDATE cj_memory_item SET version=version+1 WHERE scope=%s',(alice,)).rowcount,0)
            for statement in ("DELETE FROM cj_memory_item","TRUNCATE cj_memory_item",
                              "UPDATE cj_memory_source SET active=false","UPDATE cj_memory_item SET subject='other'",
                              "UPDATE cj_memory_management_action SET original_input='x'"):
                with self.assertRaises(errors.InsufficientPrivilege):
                    with self.database.connect(alice) as conn: conn.execute(statement)
            with psycopg.connect(**self.database.conninfo) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_management_action').fetchone()[0],0)
            for finish in ('commit','rollback'):
                conn=self.database.connect(alice)
                try:
                    with conn.cursor() as cursor:
                        cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                        conn.bind_scope(cursor)
                        self.assertGreater(cursor.execute('SELECT count(*) FROM cj_memory_management_action').fetchone()[0],0)
                    if finish=='commit':conn.commit()
                    else:conn.rollback()
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_management_action').fetchone()[0],0)
                finally:conn.close()
            config=json.loads(Path(CONNINFO).read_text())
            with psycopg.connect(**config,autocommit=True) as conn:
                import migrate
                with self.assertRaises(errors.RaiseException):migrate.down(conn,migrate.load(),18)
                self.assertEqual(migrate.applied(conn)[-1],19)
            self.assertEqual(self.query(manager,edit).json()['receipt']['version'],2)
