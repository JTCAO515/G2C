"""New tests mixed into the existing typed PG fixture; no new host or cluster."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg

from cj_memory.domain import Unavailable
from cj_memory.postgres import Transaction
from cj_memory.typed_api import MemoryDetailV3Response, create_local_typed_app


class TitleProjectionPG:
    def _title_save(self, text='I prefer quiet entrances.', *, expires=None):
        raw = self.raw(text=text)
        if expires is None:
            receipt = self.save(raw)
        else:
            with patch.object(self.service, 'manual_policy', replace(self.service.manual_policy, expires_at=expires)):
                receipt = self.save(raw)
        return json.loads(raw), receipt

    def _title_get(self, client, item_id, subject='alice', version=3):
        return client.get(f'/v{version}/memory-items', params={'item_id':item_id}, headers=self.headers(subject))

    def test_title_read_versions_source_text_and_foreign_scope(self):
        original, receipt = self._title_save('我喜欢慢节奏旅行。')
        with TestClient(self.typed_app()) as client, patch('cj_api.app.uuid4', return_value=UUID(int=1)):
            old = self._title_get(client, original['item_id'], version=2)
            new = self._title_get(client, original['item_id'])
            self.assertEqual((old.status_code, new.status_code), (200, 200))
            value = new.json();self.assertEqual(value['version'], 'MEMORY-result.3')
            self.assertEqual(value['item']['title'], '慢节奏旅行')
            self.assertEqual(value['item']['command']['text'], original['text'])
            self.assertEqual(value['item']['version'], receipt['version'])
            value['version']='MEMORY-result.2';value['item'].pop('title')
            self.assertEqual(value, old.json())
            self.assertEqual(self._title_get(client, original['item_id'], version=2).content, old.content)
            self.assertIsNone(self._title_get(client, original['item_id'], 'bob').json()['item'])
            listing=client.get('/v3/memories',params={'limit':'100'},headers=self.headers('alice'))
            self.assertEqual(listing.status_code,200,listing.text)
            self.assertEqual(next(i for i in listing.json()['items'] if i['command']['item_id']==original['item_id'])['title'],'慢节奏旅行')
        # Capture through the real accepted MESSAGE reference and public typed
        # consumer, rather than inferring model data from the UI projection.
        from cj_message.domain import Service as MessageService
        from cj_run.core import Binding
        configuration,_=self.runtime_configuration()
        runtime=configuration.bind_readonly(self.database,self.scope,'alice',self.admit,
                                            message_context=self.authority)
        with TestClient(self.app) as messages:
            mid,_=self.send_v2(messages,'title-model-'+self.tag,None)
        stored=MessageService(self.database.message_repository(self.scope),new_run_id=lambda:None).query(mid)
        receipt=stored.receipt
        binding=Binding(self.scope,receipt.conversation_id,receipt.generation,mid,receipt.run_id,receipt.sequence)
        model_data=json.loads(runtime.capture(binding).payload)
        self.assertEqual(model_data['version'],'MEMORY-RUN-CONSUME@2')
        self.assertEqual([i['text'] for i in model_data['items']],[original['text']])
        self.assertTrue(all('title' not in item for item in model_data['items']))

    def test_title_generation_unavailable_never_blocks_save(self):
        original, receipt=self._title_save('I prefer a slow travel pace when I travel.')
        self.assertEqual(receipt['status'],'active')
        with TestClient(self.typed_app()) as client:
            response=self._title_get(client,original['item_id'])
            self.assertEqual(response.status_code,200,response.text)
            self.assertIsNone(response.json()['item']['title'])
            self.assertEqual(response.json()['item']['command']['text'],original['text'])

    def test_title_inactive_or_expired_source_does_not_gain_label(self):
        original,_=self._title_save()
        config=json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text())
        # Negative corrupted/withdrawn-store fixture only. This initializer UPDATE
        # is not a runtime producer, approval, ownership or positive setup claim.
        with psycopg.connect(**config) as db:
            db.execute('UPDATE cj_memory_source SET active=false WHERE scope=%s AND source_id=(SELECT source_id FROM cj_memory_item WHERE scope=%s AND item_id=%s)',
                       (self.scope,self.scope,original['item_id']))
        with TestClient(self.typed_app()) as client:
            read=self._title_get(client,original['item_id'])
            self.assertEqual(read.status_code,200,read.text)
            self.assertEqual(read.json()['item']['status'],'active')
            self.assertIsNone(read.json()['item']['title'])

    def test_title_expiry_during_encoding_withholds_old_label(self):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=4)
        original,_=self._title_save(expires=deadline)
        validate=MemoryDetailV3Response.model_validate_json
        entered=[]
        def expire(raw, **kwargs):
            entered.append(True)
            time.sleep(max(0,(deadline-datetime.now(timezone.utc)).total_seconds())+.08)
            return validate(raw,**kwargs)
        with TestClient(self.typed_app()) as client:
            with patch.object(MemoryDetailV3Response,'model_validate_json',side_effect=expire):
                stale=self._title_get(client,original['item_id'])
            self.assertTrue(entered)
            self.assertEqual(stale.status_code,503,stale.text)
            self.assertNotIn('Quiet entrances',stale.text)
            expired=self._title_get(client,original['item_id'])
            self.assertEqual(expired.status_code,200,expired.text)
            self.assertEqual(expired.json()['item']['status'],'active')
            self.assertIsNone(expired.json()['item']['title'])

    def _title_interleave(self, client, writer, item_id, action, endpoint):
        entered,release=threading.Event(),threading.Event()
        validate=MemoryDetailV3Response.model_validate_json
        result={}
        def encode(raw,**kwargs):
            entered.set()
            if not release.wait(8):raise RuntimeError('test encoder release timed out')
            return validate(raw,**kwargs)
        def read():result['read']=self._title_get(client,item_id)
        def write():result['write']=writer.post(endpoint,content=json.dumps(action).encode(),
            headers={**self.headers('alice'),'Content-Type':'application/octet-stream'})
        config=json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text())
        with patch.object(MemoryDetailV3Response,'model_validate_json',side_effect=encode):
            reader=threading.Thread(target=read);reader.start()
            self.assertTrue(entered.wait(5))
            editing=threading.Thread(target=write);editing.start()
            try:
                waiting=False
                with psycopg.connect(**config,autocommit=True) as db:
                    for _ in range(100):
                        waiting=db.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%%cj_memory_scope%%FOR UPDATE%%')").fetchone()[0]
                        if waiting or 'write' in result:break
                        time.sleep(.01)
                self.assertTrue(waiting,'writer must actually wait on the original MEMORY scope lock')
            finally:
                release.set();reader.join(10);editing.join(10)
        self.assertFalse(reader.is_alive());self.assertFalse(editing.is_alive())
        self.assertEqual(result['read'].status_code,200,result['read'].text)
        self.assertEqual(result['write'].status_code,200,result['write'].text)
        return result['read'].json()['item']

    def test_title_edit_and_withdraw_are_serialized_with_encoding(self):
        original,_=self._title_save();iid=original['item_id']
        with TestClient(self.typed_app()) as client,TestClient(self.typed_app()) as writer:
            edit=dict(version='MEMORY-management.2',action_id=uuid4().hex,operation='edit',item_id=iid,
                expected_version=1,expected_source_version=1,text='I prefer a slow pace.',context=None)
            before=self._title_interleave(client,writer,iid,edit,'/v2/memory-management-actions')
            self.assertEqual((before['version'],before['title']),(1,'Quiet entrances'))
            current=self._title_get(client,iid).json()['item']
            self.assertEqual((current['version'],current['title']),(2,'A slow pace'))
            withdraw=dict(version='MEMORY-STOP-USE@2',action_id=uuid4().hex,operation='withdraw',item_id=iid,
                expected_version=2,source_id=current['command']['source_id'],expected_source_version=current['command']['source_version'])
            before=self._title_interleave(client,writer,iid,withdraw,'/v2/memory-withdrawal-actions')
            self.assertEqual((before['version'],before['title']),(2,'A slow pace'))
            stopped=self._title_get(client,iid).json()['item']
            self.assertEqual(stopped['status'],'withdrawn');self.assertIsNone(stopped['title'])

    def test_title_identity_loss_while_encoding_withholds_response(self):
        original,_=self._title_save();invites=self.auth/'invited.json';before=invites.read_bytes()
        validate=MemoryDetailV3Response.model_validate_json
        def revoke(raw,**kwargs):
            invites.write_text(json.dumps([s for s in json.loads(before) if s!='alice']))
            return validate(raw,**kwargs)
        try:
            with TestClient(self.typed_app()) as client,patch.object(MemoryDetailV3Response,'model_validate_json',side_effect=revoke):
                response=self._title_get(client,original['item_id'])
            self.assertIn(response.status_code,(401,403,503));self.assertNotIn('Quiet entrances',response.text)
        finally:invites.write_bytes(before)

    def test_title_context_reentry_thread_lifetime_and_size_limits(self):
        original,_=self._title_save();iid=original['item_id'];captured=[]
        def capture(context):
            captured.append(context)
            return context.project_titles('detail',iid,lambda value,titles:b'{}')
        self.assertEqual(self.service.with_operation(self.guard,capture),b'{}')
        with self.assertRaises(RuntimeError):captured[0].project_titles('detail',iid,lambda value,titles:b'{}')
        with self.assertRaises(RuntimeError):
            self.service.with_operation(self.guard,lambda c:c.project_titles('detail',iid,lambda value,titles:c.detail(iid)))
        def wrong_thread(context):
            errors=[]
            def call():
                try:context.project_titles('detail',iid,lambda value,titles:b'{}')
                except RuntimeError:errors.append(True)
            thread=threading.Thread(target=call);thread.start();thread.join(3)
            self.assertEqual(errors,[True]);return b'{}'
        self.service.with_operation(self.guard,wrong_thread)
        app=create_local_typed_app(conninfo_path=os.environ['CJ_E2E_CONNINFO'],auth_dir=self.auth,
            configuration=self.typed_configuration(),max_response_bytes=32)
        with TestClient(app) as client:
            response=self._title_get(client,iid)
            self.assertEqual(response.status_code,503);self.assertNotIn('Quiet entrances',response.text)
