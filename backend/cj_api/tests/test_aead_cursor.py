"""Optional real AEAD, per-test memory keys/clock and actual owner callback; no listener/DB."""
import base64
from dataclasses import replace
import json
import os
import secrets
from types import SimpleNamespace
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
from cj_api.aead_cursor import AeadCursorCodec
from cj_api.history_config import CursorBinding, CursorPolicy, CursorResyncRequired, CursorUnavailable, HistoryWireConfiguration
from cj_api.composition import build_message_boundary, create_composed_app
from cj_message.domain import ChatListCursor, Cursor
from cj_auth.interfaces import Fact
from cj_message.auth_boundary import AccessBlocked
from test_composition import SyntheticFixture, LedgerDouble
from test_history_wire import HistoryRepository


class AeadCursorTests(SyntheticFixture):
    def setUp(self):
        super().setUp();self.aes_key=secrets.token_bytes(32);self.now=100
        self.options=dict(keys={'key1':self.aes_key},active_key_id='key1',version='v1',clock=lambda:self.now,
                          max_ttl_seconds=300,max_token_bytes=2048,max_plaintext_bytes=512,max_binding_bytes=2048)
        self.codec=AeadCursorCodec(**self.options)
        self.boundary=build_message_boundary(**self.kwargs)
    def binding(self,context,*,purpose='conversations',cid=None,environment='local'):
        p=context.principal
        return CursorBinding(environment,p.issuer,p.subject,p.audience,context.scope,purpose,cid,context=context)
    def cursor(self,binding):
        if binding.purpose=='conversations':return ChatListCursor(binding.scope,'private-generation',0,2,1)
        return Cursor(binding.scope,binding.conversation_id,'private-generation',0,2,1)
    def within(self,operation,*,boundary=None,token=None):
        return (boundary or self.boundary).with_history_context(token or self.token,operation)
    def minted(self,**binding):
        return self.within(lambda c:self.codec.encode(self.cursor(self.binding(c,**binding)),binding=self.binding(c,**binding),ttl_seconds=30))
    def read(self,token,**binding):
        return self.within(lambda c:self.codec.decode(token,binding=self.binding(c,**binding),ttl_seconds=30))
    def forged(self,binding,raw):
        # White-box producer fault: authenticate malformed plaintext with test-only
        # known key so parser tests cannot pass merely due to failed AEAD tag.
        nonce=secrets.token_bytes(12)
        blob=nonce+AESGCM(self.aes_key).encrypt(nonce,raw,self.codec._aad(binding,'key1'))
        return 'v1.key1.'+base64.urlsafe_b64encode(blob).rstrip(b'=').decode()

    def test_roundtrip_both_types_nonce_privacy_and_no_default_secret(self):
        for purpose,cid in (('conversations',None),('message_history','opaque +/%&é')):
            token=self.minted(purpose=purpose,cid=cid)
            decoded=self.read(token,purpose=purpose,cid=cid)
            self.assertIs(type(decoded),ChatListCursor if cid is None else Cursor)
            self.assertTrue((decoded.scope,decoded.after,decoded.through)==(self.repo.scope,1,2),'decoded cursor state mismatch')
            again=self.minted(purpose=purpose,cid=cid);self.assertTrue(token!=again,'fresh nonce token equality failure')
            cipher=base64.urlsafe_b64decode(token.split('.')[2]+'='*(-len(token.split('.')[2])%4))
            for value in (self.repo.scope,'synthetic-user','private-generation'):
                self.assertTrue(value not in token and value.encode() not in cipher,'internal plaintext serialized into envelope')
        self.assertTrue(self.aes_key.hex() not in repr(self.codec),'codec repr contains material')
        for field in ('keys','active_key_id','version','clock'):
            with self.assertRaises((TypeError,CursorUnavailable)):
                AeadCursorCodec(**dict(self.options,**{field:None}))
        with self.assertRaises(CursorUnavailable):
            AeadCursorCodec(**dict(self.options,keys={'key1':b'short'}))

    def test_expiry_unknown_key_version_tamper_and_canonical_base64(self):
        token=self.minted();v,k,b=token.split('.')
        variants=[token+'=',token+'\n',token+' ',v+'.unknown.'+b,'unknown.'+k+'.'+b,
                  v+'.'+k+'.!'+b,token[:-3]+('AAA' if token[-3:]!='AAA' else 'BBB'),'v1.key1.A']
        for bad in variants:
            with self.subTest(shape=variants.index(bad)),self.assertRaises(CursorResyncRequired):self.read(bad)
        self.now=130
        with self.assertRaises(CursorResyncRequired):self.read(token)
        self.now=99
        with self.assertRaises(CursorResyncRequired):self.read(token)

    def test_binding_environment_query_kind_id_and_real_identity_scope(self):
        listed=self.minted()
        for arguments in (dict(environment='different-env'),dict(purpose='message_history',cid='c')):
            with self.assertRaises(CursorResyncRequired):self.read(listed,**arguments)
        body=self.minted(purpose='message_history',cid='c-original')
        with self.assertRaises(CursorResyncRequired):self.read(body,purpose='message_history',cid='c-other')
        claims=jwt.decode(self.token,options={'verify_signature':False})
        other_repo=LedgerDouble();other_repo.scope='different-server-scope'
        other_boundary=build_message_boundary(**dict(self.kwargs,resolve_repository=lambda p:other_repo))
        with self.assertRaises(CursorResyncRequired):
            self.within(lambda c:self.codec.decode(listed,binding=self.binding(c),ttl_seconds=30),boundary=other_boundary)
        for field,new_value in (('sub','different-user'),('iss','https://other.synthetic.invalid'),('aud','other-audience')):
            payload=dict(claims,**{field:new_value})
            config=self.config
            if field=='iss':config=replace(config,issuer=new_value)
            if field=='aud':config=replace(config,audience=new_value)
            boundary=build_message_boundary(**dict(self.kwargs,jwt_configuration=config))
            token=jwt.encode(payload,self.key,algorithm='RS256',headers={'kid':'test-key'})
            with self.assertRaises(CursorResyncRequired):
                self.within(lambda c:self.codec.decode(listed,binding=self.binding(c),ttl_seconds=30),boundary=boundary,token=token)
        claims['iat']-=2;claims['nbf']-=2
        refreshed=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})
        self.within(lambda c:self.codec.decode(listed,binding=self.binding(c),ttl_seconds=30),token=refreshed)

    def test_explicit_old_key_rotation_and_policy_reduction(self):
        old=self.minted()
        rotated=AeadCursorCodec(**dict(self.options,keys={'key1':self.aes_key,'key2':secrets.token_bytes(32)},active_key_id='key2'))
        self.within(lambda c:rotated.decode(old,binding=self.binding(c),ttl_seconds=30))
        new=self.within(lambda c:rotated.encode(self.cursor(self.binding(c)),binding=self.binding(c),ttl_seconds=30))
        self.assertTrue(new.startswith('v1.key2.'))
        retired=AeadCursorCodec(**dict(self.options,keys={'key2':secrets.token_bytes(32)},active_key_id='key2'))
        with self.assertRaises(CursorResyncRequired):self.within(lambda c:retired.decode(old,binding=self.binding(c),ttl_seconds=30))
        with self.assertRaises(CursorResyncRequired):self.within(lambda c:self.codec.decode(old,binding=self.binding(c),ttl_seconds=10))

    def test_missing_forged_expired_context_no_metadata_only_fallback(self):
        saved=[]
        def operation(c):
            b=self.binding(c);saved.append(b)
            return self.codec.encode(self.cursor(b),binding=b,ttl_seconds=30)
        token=self.within(operation);binding=saved[0]
        self.assertTrue('context=' not in repr(binding),'binding repr includes live context')
        for bad in (binding,replace(binding,context=None),replace(binding,context=SimpleNamespace())):
            with self.assertRaises(CursorUnavailable):self.codec.decode(token,binding=bad,ttl_seconds=30)
            with self.assertRaises(CursorUnavailable):self.codec.encode(self.cursor(bad),binding=bad,ttl_seconds=30)
        retained=[]
        def fail(c):retained.append(self.binding(c));raise ValueError('test callback failure')
        with self.assertRaises(ValueError):self.within(fail)
        with self.assertRaises(CursorUnavailable):self.codec.decode(token,binding=retained[0],ttl_seconds=30)
        # New callback metadata comes from its own context, never relabel old actor metadata.
        claims=jwt.decode(self.token,options={'verify_signature':False});claims['sub']='new-user'
        new_token=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})
        with self.assertRaises(CursorUnavailable):
            self.within(lambda c:self.codec.decode(token,binding=replace(binding,context=c),ttl_seconds=30),token=new_token)

    def test_authenticated_bad_payload_fields_bounds_and_ttl(self):
        normal=dict(generation='g',epoch=0,through=2,after=1,issued_at=100,expires_at=130)
        def operation(c):
            binding=self.binding(c)
            invalid=[dict(normal,extra=True),dict(normal,after=True),dict(normal,epoch=-1),
                     dict(normal,through=1<<63),dict(normal,after=3),dict(normal,generation=''),
                     dict(normal,issued_at=101),dict(normal,expires_at=400)]
            raws=[json.dumps(v).encode() for v in invalid]
            raws.extend([b'{"generation":"g","generation":"g"}',b'{}',b'\xff',b'{"epoch":NaN}'])
            for raw in raws:
                with self.assertRaises(CursorResyncRequired):self.codec.decode(self.forged(binding,raw),binding=binding,ttl_seconds=30)
            with self.assertRaises(CursorUnavailable):self.codec.encode(self.cursor(binding),binding=binding,ttl_seconds=None)
            tiny=AeadCursorCodec(**dict(self.options,max_plaintext_bytes=1))
            with self.assertRaises(CursorUnavailable):tiny.encode(self.cursor(binding),binding=binding,ttl_seconds=30)
            with self.assertRaises(CursorResyncRequired):tiny.decode(self.forged(binding,json.dumps(normal).encode()),binding=binding,ttl_seconds=30)
        self.within(operation)

    def test_real_context_api_opt_in_and_final_authority_guard(self):
        self.repo=HistoryRepository()
        options=HistoryWireConfiguration(2,512,8192,CursorPolicy(self.codec,30,2048))
        with patch.dict(os.environ,{'CJ_ENV':'local'}),TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,history_configuration=options)) as client:
            headers={'Authorization':'Bearer '+self.token}
            first=client.get('/v1/conversations',params={'limit':1},headers=headers)
            self.assertEqual(first.status_code,200)
            token=first.json()['next_cursor']
            self.assertEqual(client.get('/v1/conversations',params={'limit':1,'cursor':token},headers=headers).status_code,200)
            self.now=130
            self.assertEqual(client.get('/v1/conversations',params={'limit':1,'cursor':token},headers=headers).status_code,409)
        self.now=100
        def withdraw_clock():self.policy.invited=Fact.NO;return 100
        withdrawing=AeadCursorCodec(**dict(self.options,clock=withdraw_clock))
        with self.assertRaises(AccessBlocked):
            self.within(lambda c:withdrawing.encode(self.cursor(self.binding(c)),binding=self.binding(c),ttl_seconds=30))

    def test_same_context_identity_and_metadata_checked_after_crypto_clock(self):
        def outer(first):
            binding=self.binding(first)
            token=self.codec.encode(self.cursor(binding),binding=binding,ttl_seconds=30)
            def inner(second):
                self.assertIsNot(first,second)
                # Explicit trusted-host fault; dataclass equality is insufficient.
                def swap():object.__setattr__(binding,'context',second);return 100
                swapping=AeadCursorCodec(**dict(self.options,clock=swap))
                with self.assertRaises(CursorUnavailable):swapping.encode(self.cursor(binding),binding=binding,ttl_seconds=30)
                object.__setattr__(binding,'context',first)
                with self.assertRaises(CursorUnavailable):swapping.decode(token,binding=binding,ttl_seconds=30)
                object.__setattr__(binding,'context',first)
                def change_metadata():object.__setattr__(binding,'environment','changed-env');return 100
                changing=AeadCursorCodec(**dict(self.options,clock=change_metadata))
                with self.assertRaises(CursorUnavailable):changing.encode(self.cursor(binding),binding=binding,ttl_seconds=30)
            self.within(inner)
        self.within(outer)
