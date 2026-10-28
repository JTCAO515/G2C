"""New isolated history/draft PG cluster only; no environment DSN or old DB."""
import concurrent.futures
import threading
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
import psycopg
from cj_message.domain import Service, InputConflict, Unavailable, ResyncRequired, InvalidInput
from cj_message.postgres import Repository

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'.local-pg-02'

def connect():
    assert not any(k.startswith('PG') for k in os.environ)
    c=psycopg.connect(host=str(PRIVATE/'s'),port=55440,user='cj009',dbname='postgres',connect_timeout=5,
                       options='-c statement_timeout=10000 -c lock_timeout=5000')
    row=c.execute("SELECT current_setting('data_directory'), current_setting('listen_addresses')").fetchone()
    assert Path(row[0]).resolve()==(PRIVATE/'data').resolve() and row[1]==''
    c.commit()
    return c

def provision(scope, ids=('a','b','c')):
    with connect() as c:
        c.execute('INSERT INTO cj_message_scope(scope) VALUES (%s)',(scope,))
        for cid in ids:
            c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',(scope,cid,'g-'+cid))

def wire(mid,cid='a',text='合成 original',sequence=0):
    return json.dumps(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text=text,
                           trip_id=None,creation_intent='none',expected_generation='g-'+cid,
                           expected_sequence=sequence),ensure_ascii=False).encode()

def service(scope): return Service(Repository(connect,scope),lambda:uuid.uuid4().hex)

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.scope='history-'+uuid.uuid4().hex; provision(self.scope)
        self.other='other-'+uuid.uuid4().hex; provision(self.other,('private',))
        self.s=service(self.scope)

    def test_list_snapshot_append_and_scope_fence(self):
        first,cursor=self.s.conversations(limit=1)
        self.assertEqual([r.conversation_id for r in first],['a'])
        with connect() as c:
            c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',(self.scope,'later','g-later'))
        tail,nxt=service(self.scope).conversations(cursor)
        self.assertEqual([r.conversation_id for r in tail],['b','c']); self.assertIsNone(nxt)
        with self.assertRaises(ResyncRequired): service(self.other).conversations(cursor)
        self.assertEqual([r.conversation_id for r in service(self.other).conversations()[0]],['private'])

    def test_deleted_recreated_list_cursor_rejects_other_scope_unaffected(self):
        _,cursor=self.s.conversations(limit=1)
        with connect() as c:
            c.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(self.scope,))
            c.execute('DELETE FROM cj_message_chat WHERE scope=%s AND conversation_id=%s',(self.scope,'b'))
            c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',(self.scope,'b','new-b'))
        with self.assertRaises(ResyncRequired): self.s.conversations(cursor)
        self.assertEqual([r.conversation_id for r in self.s.conversations()[0]],['a','c','b'])
        self.assertEqual([r.conversation_id for r in service(self.other).conversations()[0]],['private'])

    def test_body_history_exact_bytes_highwater_and_epoch(self):
        self.s.receive(wire('m1')); self.s.receive(wire('m2',text='第二条',sequence=1))
        first,cursor=self.s.message_history('a',limit=1)
        self.assertEqual(first[0].original_utf8,wire('m1')); self.assertEqual(first[0].text,'合成 original')
        self.s.receive(wire('m3',sequence=2))
        tail,nxt=service(self.scope).message_history('a',cursor)
        self.assertEqual([r.receipt.message_id for r in tail],['m2']); self.assertIsNone(nxt)
        with self.assertRaises(Unavailable): service(self.other).message_history('a',cursor)
        with connect() as c:
            c.execute('UPDATE cj_message_chat SET epoch=epoch+1 WHERE scope=%s AND conversation_id=%s',(self.scope,'a'))
        with self.assertRaises(ResyncRequired): self.s.message_history('a',cursor)

    def test_draft_reopen_revision_conflict_and_no_message_side_effect(self):
        self.assertIsNone(self.s.read_draft('a','g-a'))
        raw='未发草稿 \n'.encode()
        d=self.s.save_draft('a','g-a',raw,0)
        self.assertEqual(service(self.scope).read_draft('a','g-a'),d)
        with self.assertRaises(InputConflict): self.s.save_draft('a','g-a',b'old editor',0)
        self.assertEqual(self.s.read_draft('a','g-a').original_utf8,raw)
        updated=self.s.save_draft('a','g-a',b'',1)
        self.assertEqual(updated.revision,2)
        self.assertEqual(self.s.page('a'),([],None)); self.assertEqual(self.s.pending(),[])
        with self.assertRaises(Unavailable): service(self.other).read_draft('a','g-a')
        with self.assertRaises(Unavailable): self.s.save_draft('a','wrong-generation',b'bad',2)
        # Durable value for independent process after actual restart.
        self.s.save_draft('a','g-a',raw,2)
        self.s.receive(wire('restart-body',text='restart original body'))
        (PRIVATE/'restart-history.json').write_text(json.dumps({'scope':self.scope,'raw_hex':raw.hex()}))

    def test_message_and_draft_old_generation_rejected(self):
        self.s.receive(wire('m1')); self.s.receive(wire('m2',sequence=1))
        _,cursor=self.s.message_history('a',limit=1)
        self.s.save_draft('a','g-a',b'old draft',0)
        with connect() as c:
            c.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(self.scope,))
            for table in ('cj_message_draft','cj_message_delivery','cj_message_receipt','cj_message_chat'):
                c.execute('DELETE FROM '+table+' WHERE scope=%s AND '+('conversation_id=%s' if table!='cj_message_delivery' else 'true'), (self.scope,'a') if table!='cj_message_delivery' else (self.scope,))
            c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',(self.scope,'a','new-a'))
        with self.assertRaises(ResyncRequired): self.s.message_history('a',cursor)
        with self.assertRaises(Unavailable): self.s.read_draft('a','g-a')
        self.assertIsNone(self.s.read_draft('a','new-a'))

    def test_concurrent_draft_revision_and_missing_generation(self):
        barrier=threading.Barrier(2)
        def save(raw):
            barrier.wait(timeout=5)
            try: return service(self.scope).save_draft('a','g-a',raw,0)
            except InputConflict: return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(save,[b'first',b'second']))
        accepted=[d for d in results if d is not None]
        self.assertEqual(len(accepted),1)
        self.assertEqual(self.s.read_draft('a','g-a'),accepted[0])
        for generation in (None, ''):
            with self.assertRaises(InvalidInput): self.s.read_draft('a',generation)
            with self.assertRaises(InvalidInput): self.s.save_draft('a',generation,b'invalid',1)

    def test_empty_history_and_inactive_private_rejection(self):
        self.assertEqual(self.s.message_history('a'),([],None))
        with connect() as c:
            c.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s',(self.scope,))
        self.assertEqual(self.s.conversations(),([],None))
        for cid in ('a','nonexistent'):
            with self.assertRaises(Unavailable): self.s.read_draft(cid,'g-a')

if __name__=='__main__':
    if sys.argv[1:]==['setup']:
        sql=(ROOT/'sql/candidate.sql').read_bytes()
        with connect() as c:
            assert c.execute("SELECT to_regclass('cj_message_scope')").fetchone()[0] is None
            c.execute(sql.decode())
            version=c.execute('SELECT version()').fetchone()[0]
        print(json.dumps({'version':version,'driver':psycopg.__version__,'sql_sha256':hashlib.sha256(sql).hexdigest(),'data_directory':str(PRIVATE/'data'),'listen_addresses':''},indent=2))
    elif sys.argv[1:]==['restart-check']:
        saved=json.loads((PRIVATE/'restart-history.json').read_text()); s=service(saved['scope'])
        assert s.read_draft('a','g-a').original_utf8==bytes.fromhex(saved['raw_hex'])
        assert s.read_draft('a','g-a').revision==3
        assert len(s.conversations()[0])==3
        assert s.message_history('a')[0][0].original_utf8==wire('restart-body',text='restart original body')
        print('PASS new process after PG restart: list, exact message body and draft bytes/revision restored')
    else: unittest.main(verbosity=2)
