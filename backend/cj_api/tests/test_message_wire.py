"""Wire integration with actual pinned AUTH/MESSAGE, synthetic RSA keys and transaction double.

No live JWKS, provider, database, deployment or concurrent-revocation proof.
"""
import asyncio
import copy
import hashlib
import json
import os
from contextlib import contextmanager
from urllib.parse import quote
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from cj_api.app import create_app
from cj_api.composition import create_composed_app, CompositionUnavailable
from cj_auth.interfaces import Fact
from cj_message.domain import Chat, CommitUnknown, Unavailable, Receipt, Stored
from test_composition import SyntheticFixture, PolicyDouble


class TransactionDouble:
    scope = 'server-owned-synthetic-only'
    def __init__(self):
        self.rows, self.jobs, self.chats = {}, {}, {'c-original':Chat('generation-original',0,0)}
        self.inserts_started = 0
        self.commit_unknown = False
        self.active = True
    @contextmanager
    def transaction(self):
        snapshot = copy.deepcopy((self.rows,self.jobs,self.chats))
        try:
            yield self
        except BaseException:
            self.rows,self.jobs,self.chats = snapshot
            raise
        if self.commit_unknown:
            raise CommitUnknown()  # deliberate committed-but-ACK-unknown fault
    def lock_scope(self):
        pass
    def find(self, mid):
        return self.rows.get(mid)
    def chat(self, cid, generation=None):
        if (not self.active or cid not in self.chats or
                (generation is not None and generation != self.chats[cid].generation)):
            raise Unavailable()
        return self.chats[cid]
    def active_head(self, cid):
        return self.chats.get(cid) if self.active else None
    def insert(self, stored):
        self.inserts_started += 1
        self.rows[stored.receipt.message_id] = stored
        c = self.chats[stored.receipt.conversation_id]
        self.chats[stored.receipt.conversation_id] = Chat(c.generation,c.epoch,stored.receipt.sequence)
    def enqueue(self, receipt):
        self.jobs[receipt.message_id] = receipt.run_id


class RecheckingPolicy(PolicyDouble):
    deny_at = None
    fact_at = Fact.NO
    def evaluate(self, principal):
        result = super().evaluate(principal)
        if self.calls == self.deny_at:
            return type(result)(principal,Fact.YES,Fact.YES,self.fact_at)
        return result


class WireTests(SyntheticFixture):
    def setUp(self):
        super().setUp()
        self.repo = TransactionDouble()
        self.policy = RecheckingPolicy()
        self.kwargs.update(access_provider=self.policy)
        # The inherited host resolver closes over self.repo; no caller-supplied scope.
        self.run_count = 0
        def run_id():
            self.run_count += 1
            return 'run-' + str(self.run_count)
        self.kwargs['new_run_id'] = run_id
        self.environment = patch.dict(os.environ, {'CJ_ENV':'local'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_composed_app(**self.kwargs, max_body_bytes=512)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization':'Bearer '+self.token, 'Content-Type':'application/octet-stream'}

    def raw(self, mid='m-original', sequence=0):
        # Whitespace, decomposed Unicode and opaque ID bytes are deliberately retained.
        return json.dumps(dict(version='MESSAGE-send.1',conversation_id='c-original',message_id=mid,
            text='e\u0301 + 中文',trip_id=None,creation_intent='none',
            expected_generation='generation-original',expected_sequence=sequence),ensure_ascii=False,indent=1).encode()

    def post(self, raw=None):
        return self.client.post('/v1/messages',content=self.raw() if raw is None else raw,headers=self.headers)

    def query(self, mid='m-original'):
        return self.client.get('/v1/message-receipts?message_id='+quote(mid,safe=''),headers=self.headers)

    def send_status(self, cid='c-original', mid='m-original'):
        params = {'conversation_id': cid}
        if mid is not None: params['message_id'] = mid
        return self.client.get('/v1/message-send-status', params=params, headers=self.headers)

    def test_send_head_cas_and_closed_original_replay(self):
        initial = self.send_status().json()
        self.assertIsNone(initial['receipt'])
        self.assertEqual(initial['head'], dict(conversation_id='c-original',
                         generation='generation-original', last_sequence=0))
        receipt = self.post().json()['receipt']
        conflict = self.post(self.raw('competing'))
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual({k: conflict.json()['error'][k] for k in ('code','category','outcome','recovery')},
                         dict(code='SEQUENCE_CONFLICT', category='conflict', outcome='failed', recovery='reconcile_original'))
        self.repo.active = False
        self.assertEqual(self.post().json()['receipt'], receipt)
        status = self.send_status().json()
        self.assertEqual(status['receipt'], receipt)
        self.assertIsNone(status['head'])
        self.assertEqual(self.query().status_code, 503)  # ordinary source-read guard stays closed
        self.assertEqual(self.post(self.raw('later', sequence=1)).status_code, 503)

    def test_send_parser_rejects_old_version_missing_and_invalid_head(self):
        original = json.loads(self.raw())
        invalid = []
        old = dict(original, version='MESSAGE-draft.1')
        del old['expected_generation'], old['expected_sequence']
        invalid.append(old)
        for value in (True, 1.0, '0', -1): invalid.append(dict(original, expected_sequence=value))
        for value in ('', ' ', None): invalid.append(dict(original, expected_generation=value))
        for field in ('expected_generation', 'expected_sequence'):
            missing = original.copy(); del missing[field]; invalid.append(missing)
        for obj in invalid:
            with self.subTest(obj=obj):
                response = self.post(json.dumps(obj).encode())
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT')
        self.assertEqual((self.repo.rows, self.repo.jobs), ({}, {}))

    def test_send_status_query_and_storage_errors_never_become_absence(self):
        for query in ('', 'conversation_id=', 'conversation_id=a&conversation_id=b',
                      'conversation_id=a&scope=caller', 'conversation_id=%FF',
                      'conversation_id=%', 'conversation_id=a&message_id=', 'conversation_id=%00'):
            with self.subTest(query=query):
                response = self.client.get('/v1/message-send-status?'+query, headers=self.headers)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/v1/message-send-status?conversation_id=x').status_code, 401)
        self.post()
        absent = self.send_status('other').json()
        self.assertIsNone(absent['receipt']); self.assertIsNone(absent['head'])
        self.assertIsNone(self.send_status(mid=None).json()['receipt'])
        self.repo.commit_unknown = True
        failed = self.send_status()
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn('head', failed.json())
        self.repo.commit_unknown = False
        def unavailable(): raise Unavailable()
        self.repo.lock_scope = unavailable
        failed = self.send_status()
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn('receipt', failed.json())

    def test_preserves_bytes_receipt_and_idempotence_without_raw_projection(self):
        raw = self.raw()
        first, second = self.post(raw), self.post(raw)
        self.assertEqual((first.status_code,second.status_code),(200,200))
        self.assertEqual(first.json()['receipt'],second.json()['receipt'])
        self.assertNotEqual(first.json()['request_id'],second.json()['request_id'])
        self.assertEqual(first.headers['X-Request-ID'],first.json()['request_id'])
        self.assertEqual(self.repo.rows['m-original'].raw,raw)
        self.assertEqual(first.json()['receipt']['input_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual((self.run_count,len(self.repo.jobs)),(1,1))
        found = self.query()
        self.assertEqual(found.json()['receipt'],first.json()['receipt'])
        self.assertEqual(set(found.json()),{'request_id','receipt'})
        self.assertNotIn('text',found.text)
        self.assertNotIn('raw',found.text)
        self.assertEqual(self.post(raw+b' ').status_code,409)

    def test_opaque_query_single_decode_and_duplicate_or_invalid_query_rejection(self):
        for sequence, mid in enumerate((' + / % & é ', '%2F')):
            receipt = self.post(self.raw(mid, sequence)).json()['receipt']
            self.assertEqual(self.query(mid).json()['receipt'],receipt)
        for query in ('message_id=a&message_id=b','message_id=a&extra=b','message_id=','message_id=%FF','message_id=%'):
            response = self.client.get('/v1/message-receipts?'+query,headers=self.headers)
            self.assertEqual(response.status_code,400)
        self.assertIsNone(self.query('never-observed').json()['receipt'])

    def test_duplicate_and_combined_auth_headers_never_resolve(self):
        for headers in ([('Authorization','Bearer '+self.token),('Authorization','Bearer '+self.token)],
                        [('Authorization','Bearer '+self.token+', Bearer '+self.token)]):
            response = self.client.get('/v1/message-receipts?message_id=m',headers=headers)
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.json()['error']['recovery'],'do_not_retry')
        self.assertEqual(self.resolved,[])

    def test_missing_config_explicit_unavailable_and_invalid_body_limit_refuses(self):
        with TestClient(create_app()) as client:
            response = client.post('/v1/messages',content=self.raw(),headers=self.headers)
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['error']['outcome'],'unknown')
        for limit in (None,0,False,-1):
            with self.assertRaises(CompositionUnavailable):
                create_composed_app(**self.kwargs,max_body_bytes=limit)

    def test_unknown_denied_invalid_and_sensitive_error_redaction(self):
        self.policy.invited = Fact.UNKNOWN
        unknown = self.post()
        self.assertEqual(unknown.status_code,503)
        self.assertEqual(unknown.json()['error']['recovery'],'retry_safe_read')
        self.policy.invited = Fact.NO
        self.assertEqual(self.post().status_code,403)
        self.assertEqual(self.client.get('/v1/message-receipts?message_id=m',headers={'Authorization':'Bearer broken'}).status_code,401)
        self.assertEqual(self.resolved,[])
        for private in (self.token,'synthetic-user','not_invited','identity_unknown'):
            self.assertNotIn(private,unknown.text)

    def test_content_type_duplicate_owner_fields_and_exact_bytes_conflict(self):
        response = self.client.post('/v1/messages',content=self.raw(),headers=dict(self.headers,**{'Content-Type':'application/json'}))
        self.assertEqual(response.status_code,415)
        obj = json.loads(self.raw());obj['owner']='caller-owner'
        self.assertEqual(self.post(json.dumps(obj).encode()).status_code,400)
        duplicate = self.raw().replace(b'"version":',b'"version":"MESSAGE-draft.1","version":')
        self.assertEqual(self.post(duplicate).status_code,400)
        self.assertEqual(self.repo.rows,{})

    def test_body_limit_is_enforced_during_stream_not_claimed_length(self):
        chunks_seen = []
        async def content():
            for n in range(3):
                chunks_seen.append(n)
                yield b'x'*300
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://synthetic.invalid') as client:
                return await client.post('/v1/messages',content=content(),headers=dict(self.headers,**{'Content-Length':'1'}))
        response = asyncio.run(exercise())
        self.assertEqual(response.status_code,413)
        self.assertEqual(chunks_seen,[0,1])
        self.assertEqual(self.repo.rows,{})

    def test_commit_unknown_and_after_commit_denial_keep_original_recovery(self):
        self.repo.commit_unknown = True
        response = self.post()
        self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
        self.assertEqual(response.json()['error']['outcome'],'unknown')
        self.repo.commit_unknown = False
        self.assertEqual(self.query().json()['receipt']['run_id'],'run-1')
        self.policy.calls = 0;self.policy.deny_at = 4
        response = self.post(self.raw('m-after-denial', sequence=1))
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
        self.policy.deny_at = None
        self.assertIsNotNone(self.query('m-after-denial').json()['receipt'])

    def test_precommit_denial_and_generation_failure_never_become_null(self):
        self.policy.deny_at = 3
        response = self.post()
        self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
        self.assertEqual(self.repo.rows,{})  # double rollback does not prove real-PG rollback
        self.policy.deny_at = None
        self.assertEqual(self.post().status_code,200)
        self.repo.active = False
        self.assertEqual(self.query().status_code,503)

    def test_invalid_receipt_projection_and_run_factory_never_fill_fake_values(self):
        self.kwargs['new_run_id'] = lambda:''
        with TestClient(create_composed_app(**self.kwargs,max_body_bytes=512)) as client:
            response = client.post('/v1/messages',content=self.raw(),headers=self.headers)
            self.assertEqual(response.status_code,503)
            self.assertNotIn('receipt',response.json())
        self.assertEqual(self.repo.rows,{})
        self.repo.rows['bad'] = Stored(b'private-body',Receipt('bad','c-original','',1,'run-ok','0'*64))
        self.assertEqual(self.query('bad').status_code,503)
        self.assertNotIn('private-body',self.query('bad').text)
        original_insert = self.repo.insert
        def invalid_insert(stored):
            object.__setattr__(stored.receipt, 'generation', '')  # boundary corruption fixture
            original_insert(stored)
        self.repo.insert = invalid_insert
        invalid_projection = self.post(self.raw('m-invalid-projection'))
        self.assertEqual(invalid_projection.status_code,503)
        self.assertEqual(invalid_projection.json()['error']['recovery'],'reconcile_original')
        self.assertEqual(self.repo.rows['m-invalid-projection'].receipt.generation,'')
        self.assertNotIn('receipt',invalid_projection.json())

    def test_four_stage_matrix_write_reach_and_conservative_recovery(self):
        for call, stage in enumerate(('entry','transaction','commit','return'), start=1):
            for fact in (Fact.NO,Fact.UNKNOWN):
                with self.subTest(stage=stage,fact=fact.value):
                    self.repo = TransactionDouble()
                    policy = RecheckingPolicy()
                    policy.deny_at, policy.fact_at = call, fact
                    kwargs = dict(self.kwargs, access_provider=policy)
                    with TestClient(create_composed_app(**kwargs,max_body_bytes=512)) as client:
                        response = client.post('/v1/messages',content=self.raw(),headers=self.headers)
                    error = response.json()['error']
                    expected_status = 503 if call >= 3 or fact is Fact.UNKNOWN else 403
                    expected_recovery = ('reconcile_original' if call >= 3 else
                                         'retry_safe_read' if fact is Fact.UNKNOWN else 'do_not_retry')
                    self.assertEqual(response.status_code,expected_status)
                    self.assertEqual(error['recovery'],expected_recovery)
                    self.assertEqual(self.repo.inserts_started,0 if call <= 2 else 1)
                    self.assertEqual(len(self.repo.rows),1 if call == 4 else 0)
                    self.assertNotIn('receipt',response.json())
                    print(f'MATRIX {stage} fact={fact.value} http={response.status_code} '
                          f'recovery={error["recovery"]} insert_started={self.repo.inserts_started} '
                          f'persisted_in_double={len(self.repo.rows)}')
