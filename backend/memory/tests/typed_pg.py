"""Typed storage with real signed B identity APIs/current leases and runtime PG."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from cj_api.local_app import LocalDatabase,scope_for,ISSUER
from cj_api.local_worker_context import checker_for
from cj_auth.interfaces import AdmissionStatus
from cj_memory.domain import Service,Command,Unavailable,Conflict
from cj_memory.postgres import Repository
from cj_memory.manual import ManualPolicy
from cj_memory.typed import ContextRef
from cj_message.travel_reference import MessageContextAuthority
from cj_message.travel import Selection


class TypedStorageChecks(Harness):
    def setUp(self):
        self.tag=uuid.uuid4().hex
        self.scope=scope_for(ISSUER,'alice')
        self.checker=checker_for(self.auth)
        self.token=self.headers('alice')['Authorization'].removeprefix('Bearer ')
        def admit():
            value=self.checker.check(self.token)
            if value.status is not AdmissionStatus.ALLOWED:raise Unavailable('fresh actual admission required')
            return value.principal
        self.admit=admit
        self.authority=MessageContextAuthority(self.database.message_repository(self.scope),admit)
        with TestClient(self.app) as client:
            self.travel=[]
            for label in ('A','B'):
                raw=json.dumps(dict(version='TRAVEL-context-action.1',action_id=label+'-'+self.tag,
                                    operation='create',travel_context=None)).encode()
                response=client.post('/v1/travel-context-actions',content=raw,
                    headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
                self.assertEqual(response.status_code,200,response.text)
                self.travel.append(response.json()['receipt']['travel_context'])
        with self.database.connect(self.scope) as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(self.scope,))
        policy=ManualPolicy(frozenset({'self'}),frozenset({'pace-'+self.tag}),
            frozenset({'long_term','current'}),frozenset(x['id'] for x in self.travel),
            datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
        self.service=Service(Repository(lambda:self.database.connect(self.scope),self.scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur),typed_context=True),manual_policy=policy)

    def raw(self,context=None,*,text='长期 / long term'):
        return json.dumps(dict(version='MEMORY-manual.2',operation_id='op-'+uuid.uuid4().hex,
            item_id='item-'+uuid.uuid4().hex,subject='self',slot='pace-'+self.tag,kind='preference',text=text,
            extent='long_term' if context is None else 'current',
            context=None if context is None else dict(kind='travel',id=context['id'],expected_version=context['version']),
            occurred_at='date unknown'),ensure_ascii=False,separators=(',',':')).encode()

    def guard(self,stage):return self.admit(),self.scope
    def save(self,raw,authority=None):
        return json.loads(self.service.with_operation(self.guard,lambda operation:json.dumps(
            operation.save_manual_typed(raw,self.authority if authority is None else authority).__dict__).encode()))
    def selected(self,context):
        with self.authority.hold_current(Selection(context['id'],context['version'])) as lease:
            return self.service.effective('self',ContextRef('travel',lease.context.id))

    def test_actual_owned_lease_type_isolation_longterm_and_original_bytes(self):
        long=self.raw();saved=self.save(long)
        first=self.raw(self.travel[0],text='仅A / A only');a=self.save(first)
        second=self.raw(self.travel[1],text='仅B / B only');b=self.save(second)
        slot='pace-'+self.tag
        self.assertEqual([i.command.text for i in self.selected(self.travel[0]).items if i.command.slot==slot],['仅A / A only'])
        self.assertEqual([i.command.text for i in self.selected(self.travel[1]).items if i.command.slot==slot],['仅B / B only'])
        self.assertEqual(self.save(first),a)
        with self.assertRaises(Conflict):self.save(first+b' ')
        self.assertEqual(saved['input_sha256'],hashlib.sha256(long).hexdigest())
        self.assertEqual(self.service.detail(saved['item_id']).command.text,'长期 / long term')
        # Same opaque string may also be a legacy conversation. It is not travel.
        original=dict(operation_id='legacy-'+self.tag,item_id='legacy-item-'+self.tag,subject='self',slot=slot,
            kind='preference',text='Legacy only',extent='current',context_id=self.travel[0]['id'],
            source_id='legacy-source-'+self.tag,source_version=1,occurred_at='date unknown')
        command=Command.parse(json.dumps(original,separators=(',',':')).encode())
        with self.service.repository.transaction() as tx:
            tx.lock_scope();tx.create_manual_source(command,True,self.service.manual_policy.expires_at);tx.insert(command,'active')
        legacy=self.service.effective('self',ContextRef('legacy',self.travel[0]['id']))
        self.assertEqual([i.command.text for i in legacy.items if i.command.slot==slot],['Legacy only'])
        self.assertEqual([i.command.text for i in self.selected(self.travel[0]).items if i.command.slot==slot],['仅A / A only'])
        # An explicit legacy-only decoder fails closed on new stored bytes.
        old=Service(Repository(lambda:self.database.connect(self.scope),self.scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur)))
        from cj_memory.domain import InvalidInput
        with self.assertRaises(InvalidInput):old.detail(a['item_id'])

    def test_wrong_owner_current_version_and_lease_scope_rejected(self):
        self.save(self.raw())
        from cj_run.core import Denied
        from cj_memory.operation import OperationWithheld
        wrong=dict(self.travel[0],version=2)
        with self.assertRaises((Denied,OperationWithheld)):self.save(self.raw(wrong))
        bob=scope_for(ISSUER,'bob');token=self.headers('bob')['Authorization'].removeprefix('Bearer ')
        other=MessageContextAuthority(self.database.message_repository(bob),lambda:self.checker.check(token).principal)
        with self.assertRaises((Unavailable,OperationWithheld)):self.save(self.raw(self.travel[0]),other)
        with self.database.connect(bob) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(self.scope,)).fetchone()[0],0)


if __name__=='__main__':unittest.main(verbosity=2)
