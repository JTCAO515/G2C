"""Actual AUTH + public MEMORY Service with isolated transaction double. No DB/listener."""
import copy
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_api.memory_boundary import (create_memory_composed_app, MemoryBinding,
    MemoryWireConfiguration)
from cj_api.composition import CompositionUnavailable
from cj_memory.domain import Service, Receipt, Item, Conflict, Unavailable, CommitUnknown
from cj_memory.manual import ManualPolicy
from test_composition import SyntheticFixture


class MemoryRepositoryDouble:
    def __init__(self, scope='fixture-scope'):
        self.scope=scope
        self.ops={};self.items={};self.approved={};self.allowed_raw={};self.lost=False;self.after_save=None
    @contextmanager
    def transaction(self):
        old=(copy.deepcopy(self.ops),copy.deepcopy(self.items),copy.deepcopy(self.approved))
        try:
            yield self
            if self.after_save:self.after_save()
            if self.lost:
                self.lost=False
                raise CommitUnknown()
        except CommitUnknown:raise
        except BaseException:
            self.ops,self.items,self.approved=old
            raise
    def lock_scope(self):return 1
    def operation(self,oid):return self.ops.get(oid)
    def source(self,c):
        if c.raw not in self.approved:raise Unavailable()
        return self.approved[c.raw]
    def create_manual_source(self,c,resolved,expires_at):
        if c.raw in self.approved:raise Conflict()
        self.approved[c.raw]=resolved and c.kind!='inference'
    def insert(self,c,status,*,operation_raw=None):
        if c.item_id in self.items:raise Conflict()
        receipt=Receipt(c.operation_id,c.item_id,1,status,hashlib.sha256(c.raw if operation_raw is None else operation_raw).hexdigest())
        self.ops[c.operation_id]=(c.raw if operation_raw is None else operation_raw,receipt)
        self.items[c.item_id]=Item(c,1,status,datetime.now(timezone.utc))
        return receipt
    def detail(self,iid):return self.items.get(iid)
    def list_items(self,after,limit):
        return [v for k,v in sorted(self.items.items()) if after is None or k>after][:limit]
    def groups(self):
        groups={}
        for item in self.items.values():
            key=(item.command.subject,item.status);groups[key]=groups.get(key,0)+1
        return [(s,t,n) for (s,t),n in sorted(groups.items())]


class MemoryWireTests(SyntheticFixture):
    def setUp(self):
        super().setUp()
        self.memory=MemoryRepositoryDouble();self.other=MemoryRepositoryDouble('scope-b');self.source_allowed=True
        self.environment=patch.dict(os.environ,{'CJ_ENV':'local'});self.environment.start();self.addCleanup(self.environment.stop)
        self.manual_policy=ManualPolicy(frozenset({'self'}),frozenset({'diet.spicy'}),
            frozenset({'long_term','current'}),frozenset({'approved-context'}),
            datetime.now(timezone.utc)+timedelta(hours=1),
            lambda c,raw:raw in self.memory.allowed_raw,
            lambda c,raw:self.memory.allowed_raw.get(raw) is True)
        self.memory_args=dict(environment='local',jwt_configuration=self.config,
            verification_keys=self.keys,access_provider=self.policy,
            resolve_binding=lambda principal:MemoryBinding('fixture-scope',Service(self.memory,manual_policy=self.manual_policy)),
            source_policy=lambda *args:self.source_allowed)
        self.options=MemoryWireConfiguration(32768,2,65536)
        self.client=TestClient(create_memory_composed_app(configuration=self.options,**self.memory_args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def raw(self,oid='op1',iid='item1',**fields):
        value=dict(operation_id=oid,item_id=iid,subject='self',slot='diet.spicy',text='e\u0301 不吃辣',
            kind='preference',extent='long_term',context_id=None,occurred_at='date not specified')
        value.update(fields)
        return json.dumps(value,ensure_ascii=False,indent=1).encode()
    def save(self,raw):
        return self.client.post('/v1/memories',content=raw,headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
    def get(self,path,**query):return self.client.get(path,params=query,headers=self.headers)
    def approve(self,raw,confirmed=True):self.memory.allowed_raw[raw]=confirmed

    def test_save_replay_original_query_and_private_detail(self):
        raw=self.raw();self.approve(raw)
        first=self.save(raw);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['receipt']['status'],'active')
        self.assertEqual(first.json()['receipt']['input_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(hashlib.sha256(self.memory.items['item1'].command.raw).hexdigest(),first.json()['receipt']['input_sha256'])
        self.assertEqual(len(self.memory.approved),1)
        self.assertEqual(self.memory.ops['op1'][0],raw)
        self.assertEqual(self.save(raw).json()['receipt'],first.json()['receipt'])
        q=self.get('/v1/memory-receipts',operation_id='op1')
        self.assertEqual(q.json()['receipt'],first.json()['receipt'])
        detail=self.get('/v1/memory-items',item_id='item1')
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['item']['command']['text'],'e\u0301 不吃辣')
        self.assertEqual(first.headers['X-Request-ID'],first.json()['request_id'])
        self.assertEqual(first.headers['Cache-Control'],'no-store')
        self.assertNotEqual(q.json()['request_id'],first.json()['request_id'])
        self.assertEqual(self.save(self.raw(text='different')).status_code,409)

    def test_required_null_list_groups_and_candidate(self):
        self.assertIsNone(self.get('/v1/memory-receipts',operation_id='absent').json()['receipt'])
        self.assertIsNone(self.get('/v1/memory-items',item_id='absent').json()['item'])
        for n in range(3):
            raw=self.raw('op'+str(n),'item'+str(n),kind='inference' if n==2 else 'fact')
            self.approve(raw,confirmed=n!=1)
            self.assertEqual(self.save(raw).status_code,200)
        a=self.get('/v1/memories',limit=2).json();self.assertEqual(len(a['items']),2)
        b=self.get('/v1/memories',limit=2,after=a['next_after']).json()
        self.assertEqual([x['command']['item_id'] for x in b['items']],['item2'])
        empty=self.get('/v1/memories',limit=2,after=b['next_after']).json()
        self.assertEqual(empty,dict(request_id=empty['request_id'],items=[],next_after=None))
        self.assertEqual(sorted(x['status'] for x in self.get('/v1/memory-groups').json()['groups']),['active','candidate'])
        self.assertEqual(b['items'][0]['status'],'candidate')

    def test_unapproved_source_and_source_policy_never_create_approval(self):
        raw=self.raw()
        self.assertEqual(self.save(raw).status_code,503)
        self.assertEqual(self.memory.ops,{})
        self.source_allowed=False;self.approve(raw)
        denied=self.save(raw);self.assertEqual(denied.status_code,403)
        self.assertEqual(self.memory.ops,{})

    def test_unknown_commit_original_query_and_withheld_private_response(self):
        raw=self.raw();self.approve(raw);self.memory.lost=True
        unknown=self.save(raw)
        self.assertEqual(unknown.status_code,503)
        self.assertEqual(unknown.json()['error']['recovery'],'reconcile_original')
        self.assertEqual(self.get('/v1/memory-receipts',operation_id='op1').json()['receipt']['item_id'],'item1')
        self.memory.after_save=lambda:setattr(self.policy,'invited',Fact.NO)
        denied=self.get('/v1/memory-items',item_id='item1')
        self.assertEqual(denied.status_code,403);self.assertNotIn('item',denied.json())

    def test_invalid_raw_fields_bounds_media_queries_and_access(self):
        for raw in [self.raw(owner='caller'),self.raw(approved=True),self.raw(source_id='caller'),self.raw(confirmed=True),self.raw(source_version=True),
                    self.raw(context_id='client-context'),self.raw(kind='invented'),
                    self.raw()+b' ',b'\xff',self.raw().replace(b'"op1"',b'"op1", "operation_id":"dupe"')]:
            # trailing whitespace is valid JSON, retained unchanged; domain approval still rejects it.
            expected=503 if raw==self.raw()+b' ' else 400
            self.assertEqual(self.save(raw).status_code,expected)
        self.assertEqual(self.save(b'x'*32769).status_code,413)
        self.assertEqual(self.client.post('/v1/memories',content=self.raw(),headers=self.headers).status_code,415)
        for query in ['operation_id=x&operation_id=x','operation_id=x&owner=y','operation_id=%ff']:
            self.assertEqual(self.client.get('/v1/memory-receipts?'+query,headers=self.headers).status_code,400)
        self.assertEqual(self.get('/v1/memories',limit=3).status_code,400)
        self.policy.invited=Fact.UNKNOWN
        denied=self.get('/v1/memories',limit=1);self.assertEqual(denied.status_code,503);self.assertNotIn('items',denied.json())
        self.assertEqual(self.client.get('/v1/memory-groups').status_code,401)

    def test_two_identity_partition_and_refresh_not_a_new_scope(self):
        import jwt
        raw=self.raw();self.approve(raw);self.assertEqual(self.save(raw).status_code,200)
        claims=jwt.decode(self.token,options={'verify_signature':False})
        claims['sub']='synthetic-other'
        other_token=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})
        def resolve(principal):
            return MemoryBinding('fixture-scope' if principal.subject=='synthetic-user' else 'scope-b',
                Service(self.memory if principal.subject=='synthetic-user' else self.other,manual_policy=self.manual_policy))
        with TestClient(create_memory_composed_app(configuration=self.options,
                **dict(self.memory_args,resolve_binding=resolve))) as client:
            headers={'Authorization':'Bearer '+other_token}
            self.assertIsNone(client.get('/v1/memory-items',params={'item_id':'item1'},headers=headers).json()['item'])
            self.assertIsNone(client.get('/v1/memory-receipts',params={'operation_id':'op1'},headers=headers).json()['receipt'])
            self.assertEqual(client.get('/v1/memories',params={'limit':1},headers=headers).json()['items'],[])
            claims['sub']='synthetic-user';claims['iat']-=1;claims['nbf']-=1
            refresh=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})
            self.assertEqual(client.get('/v1/memory-receipts',params={'operation_id':'op1'},
                headers={'Authorization':'Bearer '+refresh}).json()['receipt']['item_id'],'item1')

    def test_generated_python_required_null_enum_and_integer(self):
        from cj_api.generated import MemoryReceiptQueryResponse,MemoryDetailResponse,MemoryListResponse,MemoryManualSaveCommand
        from pydantic import ValidationError
        rid='00000000-0000-4000-8000-000000000001'
        for model,field in [(MemoryReceiptQueryResponse,'receipt'),(MemoryDetailResponse,'item')]:
            self.assertIsNone(model.model_validate_json(json.dumps({'request_id':rid,field:None})).model_dump(mode='json')[field])
            with self.assertRaises(ValidationError):model.model_validate({'request_id':rid})
            with self.assertRaises(ValidationError):model.model_validate({'request_id':rid,field:'invalid fallback'})
        with self.assertRaises(ValidationError):MemoryListResponse.model_validate({'request_id':rid,'items':[]})
        for raw in [self.raw(kind='invented'),self.raw(source_version=2**63),self.raw(source_version=True)]:
            with self.assertRaises(ValidationError):MemoryManualSaveCommand.model_validate_json(raw,strict=True)

    def test_guard_precommit_rollback_and_postcommit_original_recovery(self):
        raw=self.raw();self.approve(raw)
        def at_precommit(principal,scope,kind,command,argument,stage):
            if stage=='precommit':self.policy.invited=Fact.NO
            return True
        with TestClient(create_memory_composed_app(configuration=self.options,
                **dict(self.memory_args,source_policy=at_precommit))) as client:
            denied=client.post('/v1/memories',content=raw,
                headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
            self.assertEqual(denied.status_code,503)
            self.assertEqual(denied.json()['error']['recovery'],'reconcile_original')
            self.assertNotIn('receipt',denied.json());self.assertEqual(self.memory.ops,{})
        self.policy.invited=Fact.YES
        stages=[]
        def after_projection(principal,scope,kind,command,argument,stage):
            stages.append(stage)
            if stage=='return':self.policy.invited=Fact.NO
            return True
        with TestClient(create_memory_composed_app(configuration=self.options,
                **dict(self.memory_args,source_policy=after_projection))) as client:
            denied=client.post('/v1/memories',content=raw,
                headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
            self.assertEqual(denied.status_code,503)
            self.assertEqual(denied.json()['error']['recovery'],'reconcile_original')
            self.assertNotIn('receipt',denied.json())
        self.assertEqual(stages,['entry','transaction','transaction_ready','precommit','private_return','return'])
        self.policy.invited=Fact.YES
        self.assertEqual(self.get('/v1/memory-receipts',operation_id='op1').json()['receipt']['item_id'],'item1')

    def test_wrong_service_binding_never_opens_transaction(self):
        raw=self.raw();self.approve(raw)
        with TestClient(create_memory_composed_app(configuration=self.options,
                **dict(self.memory_args,resolve_binding=lambda p:MemoryBinding('wrong-scope',Service(self.memory,manual_policy=self.manual_policy))))) as client:
            denied=client.get('/v1/memory-groups',headers=self.headers)
            self.assertEqual(denied.status_code,503)
            self.assertNotIn('groups',denied.json())
        self.assertEqual(self.memory.ops,{})

    def test_response_cap_after_commit_does_not_report_false_failure(self):
        raw=self.raw();self.approve(raw)
        with TestClient(create_memory_composed_app(configuration=MemoryWireConfiguration(32768,2,64),
                **self.memory_args)) as client:
            result=client.post('/v1/memories',content=raw,
                headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['error']['recovery'],'reconcile_original')
            self.assertEqual(client.get('/v1/memory-items',params={'item_id':'item1'},headers=self.headers).status_code,413)
        self.assertEqual(self.get('/v1/memory-receipts',operation_id='op1').status_code,200)

    def test_existing_combined_app_can_inject_memory_without_parallel_auth_policy(self):
        from cj_api.composition import create_composed_app
        with TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,
                memory_configuration=self.options,resolve_memory_binding=self.memory_args['resolve_binding'],
                memory_source_policy=self.memory_args['source_policy'])) as client:
            self.assertEqual(client.get('/v1/memory-groups',headers=self.headers).json()['groups'],[])
            result=client.get('/v1/message-receipts',params={'message_id':'original'},headers=self.headers)
            self.assertEqual(result.status_code,200)
        with self.assertRaises(CompositionUnavailable):
            create_composed_app(**self.kwargs,max_body_bytes=4096,memory_configuration=self.options)

    def test_manual_missing_or_unknown_collection_policy_rejects_without_source(self):
        from dataclasses import replace
        raw=self.raw();self.approve(raw)
        for policy in [None,replace(self.manual_policy,content_allowed=lambda c,b:None)]:
            with TestClient(create_memory_composed_app(configuration=self.options,
                    **dict(self.memory_args,resolve_binding=lambda p:MemoryBinding('fixture-scope',
                        Service(self.memory,manual_policy=policy))))) as client:
                result=client.post('/v1/memories',content=raw,
                    headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
                self.assertEqual(result.status_code,503)
                self.assertEqual(self.memory.ops,{})
                self.assertEqual(self.memory.approved,{})

    def test_cancelled_precommit_and_final_guard_preserve_original_recovery(self):
        import asyncio
        for stage,exists in [('precommit',False),('return',True)]:
            raw=self.raw(stage,stage);self.approve(raw)
            def interrupted(principal,scope,kind,command,argument,current):
                if current==stage:raise asyncio.CancelledError()
                return True
            with TestClient(create_memory_composed_app(configuration=self.options,
                    **dict(self.memory_args,source_policy=interrupted))) as client:
                result=client.post('/v1/memories',content=raw,
                    headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
                self.assertEqual(result.status_code,503)
                self.assertEqual(result.json()['error']['recovery'],'reconcile_original')
                self.assertNotIn('receipt',result.json())
            receipt=self.get('/v1/memory-receipts',operation_id=stage).json()['receipt']
            self.assertEqual(receipt is not None,exists)
            if receipt is not None:self.assertEqual(receipt['input_sha256'],hashlib.sha256(raw).hexdigest())

    def test_missing_configuration_and_wrong_environment_fail_closed(self):
        for field in ['resolve_binding','source_policy','verification_keys','access_provider']:
            with self.assertRaises(CompositionUnavailable):
                create_memory_composed_app(configuration=self.options,**dict(self.memory_args,**{field:None}))
        with self.assertRaises(CompositionUnavailable):
            create_memory_composed_app(configuration=self.options,**dict(self.memory_args,environment='production'))
