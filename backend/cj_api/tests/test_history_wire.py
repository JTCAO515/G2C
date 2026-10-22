"""Actual pinned context/domain + synthetic JWT/facts/codec and transaction double; no listener/DB."""
import base64
from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import urlencode
from unittest.mock import patch
import jwt
from fastapi.testclient import TestClient
from cj_api.composition import create_composed_app
from cj_api.history_config import (CursorPolicy, CursorBinding, CursorResyncRequired, HistoryWireConfiguration)
from cj_auth.interfaces import Fact
from cj_message.domain import Chat, ChatSummary, Draft, Unavailable
from test_composition import SyntheticFixture
from test_message_wire import TransactionDouble


class HistoryRepository(TransactionDouble):
    def __init__(self):
        super().__init__()
        self.drafts={};self.history_epoch=0;self.scope_generation='scope-generation'
        self.chats['c-second']=Chat('generation-second',0,0)
        self.order={'c-original':1,'c-second':2}
    @contextmanager
    def transaction(self):
        drafts=copy.deepcopy(self.drafts)
        try:
            with super().transaction():yield self
        except BaseException:
            # CommitUnknown deliberately preserves successful commit in parent double.
            from cj_message.domain import CommitUnknown
            import sys
            if not isinstance(sys.exception(),CommitUnknown):self.drafts=drafts
            raise
    def list_boundary(self):return self.scope_generation,self.history_epoch,max(self.order.values())
    def conversations(self,after,through,limit):
        return [ChatSummary(cid,self.chats[cid].generation,self.chats[cid].epoch,n)
                for cid,n in sorted(self.order.items(),key=lambda x:x[1]) if after<n<=through][:limit]
    def history(self,cid,generation,after,through,limit):
        return sorted([v for v in self.rows.values() if v.receipt.conversation_id==cid
            and v.receipt.generation==generation and after<v.receipt.sequence<=through],key=lambda x:x.receipt.sequence)[:limit]
    def draft(self,cid,generation):return self.drafts.get((cid,generation))
    def save_draft(self,draft):self.drafts[(draft.conversation_id,draft.generation)]=draft


class SignedCursorFixture:
    """Test-only authenticated opaque server-state token, not a production codec/retention policy."""
    def __init__(self):self.key=secrets.token_bytes(32);self.records={};self.now=100;self.on_encode=None
    def encode(self,cursor,*,binding,ttl_seconds):
        nonce=secrets.token_hex(12)
        self.records[nonce]=(cursor,replace(binding,context=None),self.now+ttl_seconds)
        token=nonce+'.'+hmac.new(self.key,nonce.encode(),hashlib.sha256).hexdigest()
        if self.on_encode:self.on_encode()
        return token
    def decode(self,token,*,binding,ttl_seconds):
        self.last_binding=binding
        try:
            nonce,signature=token.split('.')
            if not hmac.compare_digest(signature,hmac.new(self.key,nonce.encode(),hashlib.sha256).hexdigest()):raise ValueError()
            cursor,expected,expiry=self.records[nonce]
            if expected!=binding or self.now>=expiry:raise ValueError()
            return cursor
        except Exception:raise CursorResyncRequired() from None


class HistoryWireTests(SyntheticFixture):
    def setUp(self):
        super().setUp();self.repo=HistoryRepository();self.codec=SignedCursorFixture()
        self.options=HistoryWireConfiguration(2,512,8192,CursorPolicy(self.codec,30,256))
        self.environment=patch.dict(os.environ,{'CJ_ENV':'local'});self.environment.start();self.addCleanup(self.environment.stop)
        self.client=TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,history_configuration=self.options))
        self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def raw(self,mid):return json.dumps(dict(version='MESSAGE-draft.1',conversation_id='c-original',message_id=mid,
        text='private e\u0301 + 中文',trip_id=None,creation_intent='none'),ensure_ascii=False,indent=1).encode()
    def receive(self,mid):return self.client.post('/v1/messages',content=self.raw(mid),headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
    def get(self,path,**params):return self.client.get(path,params=params,headers=self.headers)
    def save(self,raw,revision=0,**query):
        q=dict(conversation_id='c-original',generation='generation-original',expected_revision=revision,**query)
        return self.client.put('/v1/message-drafts',params=q,content=raw,headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))

    def test_list_cursor_authenticated_bound_and_required_null(self):
        first=self.get('/v1/conversations',limit=1)
        self.assertEqual(first.status_code,200)
        token=first.json()['next_cursor'];self.assertIsInstance(token,str)
        second=self.get('/v1/conversations',limit=1,cursor=token)
        self.assertEqual([x['conversation_id'] for x in second.json()['conversations']],['c-second'])
        self.assertIn('next_cursor',second.json());self.assertIsNone(second.json()['next_cursor'])
        for bad in (token+'x','{"scope":"caller"}'):
            r=self.get('/v1/conversations',limit=1,cursor=bad)
            self.assertEqual(r.status_code,409);self.assertNotIn('conversations',r.json())
        self.codec.now=131
        self.assertEqual(self.get('/v1/conversations',limit=1,cursor=token).status_code,409)

    def test_codec_binding_cross_identity_query_epoch_and_refresh(self):
        token=self.get('/v1/conversations',limit=1).json()['next_cursor']
        claims=jwt.decode(self.token,options={'verify_signature':False});claims['iat']-=2;claims['nbf']-=2
        refreshed=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})
        r=self.client.get('/v1/conversations',params={'limit':1,'cursor':token},headers={'Authorization':'Bearer '+refreshed})
        self.assertEqual(r.status_code,200)  # times are not cursor identity or storage partition
        claims['sub']='another-synthetic-user'
        other=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})
        self.assertEqual(self.client.get('/v1/conversations',params={'limit':1,'cursor':token},headers={'Authorization':'Bearer '+other}).status_code,409)
        self.assertEqual(self.get('/v1/message-history',conversation_id='c-original',limit=1,cursor=token).status_code,409)
        other_repo=HistoryRepository();other_repo.scope='synthetic-scope-b'
        def mapped(principal):return self.repo if principal.subject=='synthetic-user' else other_repo
        with TestClient(create_composed_app(**dict(self.kwargs,resolve_repository=mapped),max_body_bytes=4096,history_configuration=self.options)) as c:
            cross=c.get('/v1/conversations',params={'limit':1,'cursor':token},headers={'Authorization':'Bearer '+other})
        self.assertEqual(cross.status_code,409)
        self.assertEqual(self.codec.last_binding.scope,'synthetic-scope-b')
        self.assertNotIn('conversations',cross.json())  # decoded scope never selects repository
        self.repo.history_epoch+=1
        self.assertEqual(self.get('/v1/conversations',limit=1,cursor=token).status_code,409)

    def test_actual_history_private_bytes_hash_text_and_snapshot(self):
        self.assertEqual(self.receive('m1').status_code,200);self.assertEqual(self.receive('m2').status_code,200)
        first=self.get('/v1/message-history',conversation_id='c-original',limit=1)
        self.assertEqual(first.status_code,200)
        row=first.json()['messages'][0]
        self.assertEqual(base64.b64decode(row['original_utf8_base64'],validate=True),self.raw('m1'))
        self.assertEqual(row['receipt']['input_sha256'],hashlib.sha256(self.raw('m1')).hexdigest())
        self.assertEqual(row['text'],'private e\u0301 + 中文')
        next_page=self.get('/v1/message-history',conversation_id='c-original',limit=1,cursor=first.json()['next_cursor'])
        self.assertEqual(next_page.json()['messages'][0]['receipt']['message_id'],'m2')
        self.assertIsNone(next_page.json()['next_cursor'])
        self.repo.chats['c-original']=Chat('replacement-generation',0,2)
        stale=self.get('/v1/message-history',conversation_id='c-original',limit=1,cursor=first.json()['next_cursor'])
        self.assertEqual(stale.status_code,409);self.assertNotIn('messages',stale.json())

    def test_draft_exact_empty_revision_and_no_message_or_run(self):
        empty=self.get('/v1/message-drafts',conversation_id='c-original',generation='generation-original')
        self.assertIn('draft',empty.json());self.assertIsNone(empty.json()['draft'])
        first=self.save(b'');self.assertEqual(first.status_code,200)
        self.assertEqual((first.json()['draft']['revision'],first.json()['draft']['original_utf8_base64']),(1,''))
        raw='e\u0301 + 中文\n'.encode();saved=self.save(raw,1)
        self.assertEqual(saved.json()['draft']['revision'],2)
        read=self.get('/v1/message-drafts',conversation_id='c-original',generation='generation-original')
        self.assertEqual(base64.b64decode(read.json()['draft']['original_utf8_base64'],validate=True),raw)
        self.assertEqual(self.save(raw,1).status_code,409)
        self.assertEqual((self.repo.rows,self.repo.jobs),({},{}))
        self.assertEqual(self.get('/v1/message-drafts',conversation_id='c-original',generation='old').status_code,503)

    def test_draft_commit_unknown_and_postcommit_projection_failure(self):
        self.repo.commit_unknown=True
        r=self.save(b'same text');self.assertEqual(r.status_code,503)
        self.assertEqual(r.json()['error']['recovery'],'reconcile_original')
        self.repo.commit_unknown=False
        current=self.get('/v1/message-drafts',conversation_id='c-original',generation='generation-original')
        self.assertEqual(current.json()['draft']['revision'],1)
        self.assertNotIn('action_id',current.json()['draft'])
        self.assertEqual(self.save(b'same text',0).status_code,409)
        tiny=replace(self.options,max_private_response_bytes=1)
        with TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,history_configuration=tiny)) as c:
            r=c.put('/v1/message-drafts',params={'conversation_id':'c-original','generation':'generation-original','expected_revision':1},content=b'committed private',headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
        self.assertEqual(r.status_code,503);self.assertEqual(r.json()['error']['recovery'],'reconcile_original')
        self.assertEqual(self.repo.drafts[('c-original','generation-original')].revision,2)
        self.assertNotIn('committed private',r.text)

    def test_same_context_gate_after_codec_and_scope_change_withholds_content(self):
        self.codec.on_encode=lambda:setattr(self.policy,'invited',Fact.NO)
        r=self.get('/v1/conversations',limit=1)
        self.assertEqual(r.status_code,503);self.assertNotIn('conversations',r.json())
        self.assertEqual(r.json()['error']['recovery'],'reconcile_original')
        self.policy.invited=Fact.YES
        self.codec.on_encode=lambda:setattr(self.repo,'scope','changed-server-scope')
        r=self.get('/v1/conversations',limit=1)
        self.assertEqual(r.status_code,503);self.assertNotIn('conversations',r.json())

    def test_missing_codec_limits_duplicate_params_int64_and_utf8(self):
        missing=replace(self.options,cursor_policy=None)
        with TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,history_configuration=missing)) as c:
            self.assertEqual(c.get('/v1/conversations',params={'limit':1},headers=self.headers).status_code,503)
        for bad in ('limit=1&limit=2','limit=1&scope=caller','limit=3','limit=-1','limit=01'):
            self.assertEqual(self.client.get('/v1/conversations?'+bad,headers=self.headers).status_code,400)
        self.assertEqual(self.save(b'x',((1<<63)-1)).status_code,400)
        self.assertEqual(self.save(b'\xff').status_code,400)
        self.assertEqual(self.save(b'x'*513).status_code,413)
        self.assertEqual(self.repo.drafts,{})
        self.repo.order['c-original']=(1<<63)
        r=self.get('/v1/conversations',limit=2);self.assertEqual(r.status_code,503)
        self.assertNotIn('conversations',r.json())

    def test_invalid_stored_utf8_and_output_size_never_leak_private_fields(self):
        self.repo.drafts[('c-original','generation-original')]=Draft('c-original','generation-original',1,b'\xff')
        r=self.get('/v1/message-drafts',conversation_id='c-original',generation='generation-original')
        self.assertEqual(r.status_code,503);self.assertNotIn('draft',r.json())
        tiny=replace(self.options,max_private_response_bytes=1)
        with TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,history_configuration=tiny)) as c:
            r=c.get('/v1/conversations',params={'limit':1},headers=self.headers)
        self.assertEqual(r.status_code,413);self.assertNotIn('c-original',r.text)

    def test_draft_stream_bound_ignores_false_content_length(self):
        import asyncio,httpx
        seen=[]
        async def chunks():
            for n in range(3):
                seen.append(n)
                yield b'x'*300
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.client.app),base_url='http://synthetic.invalid') as client:
                return await client.put('/v1/message-drafts?conversation_id=c-original&generation=generation-original&expected_revision=0',
                    content=chunks(),headers=dict(self.headers,**{'Content-Type':'application/octet-stream','Content-Length':'1'}))
        response=asyncio.run(exercise())
        self.assertEqual(response.status_code,413)
        self.assertEqual(seen,[0,1])
        self.assertEqual(self.repo.drafts,{})

    def test_codec_none_is_invalid_not_an_implicit_first_page(self):
        token=self.get('/v1/conversations',limit=1).json()['next_cursor']
        self.codec.decode=lambda token,**kwargs:None
        r=self.get('/v1/conversations',limit=1,cursor=token)
        self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['error']['code'],'HISTORY_RESYNC_REQUIRED')
        self.assertNotIn('conversations',r.json())
