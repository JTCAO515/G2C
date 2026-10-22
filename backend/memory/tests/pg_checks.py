"""Run only against an explicitly created task-private empty PostgreSQL cluster."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import unittest
import psycopg
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cj_memory.domain import Service, Command, Conflict, Unavailable, CommitUnknown, InvalidInput
from cj_memory.postgres import Repository

# Ignore ambient DSN/service/pgpass; explicit task-local socket, role and database.
for key in tuple(os.environ):
    if key.startswith('PG'): del os.environ[key]
KW = dict(host='/tmp/cj011-memory-01a16218', port=56111, user='cj011_owner', dbname='cj011_test', passfile=str(Path(__file__).resolve().parents[1]/'.local'/'empty.pgpass'), connect_timeout=3)
def connect(): return psycopg.connect(**KW)
def command(n, **changes):
    obj = dict(operation_id='op-'+n,item_id='item-'+n,subject='self',slot='food-'+n,kind='preference',text='不吃辣 / no spicy food',extent='long_term',context_id=None,source_id='source-'+n,source_version=1,occurred_at='user reported; exact date unknown')
    obj.update(changes)
    return json.dumps(obj,ensure_ascii=False).encode()
def grant(raw, scope='A', **changes):
    c=Command.parse(raw)
    values=dict(authorized=True,confirmed=True,semantic_resolved=True,active=True)
    values.update(changes)
    with connect() as conn:
        conn.execute('INSERT INTO cj_memory_source VALUES (%s,%s,1,%s,%s,%s,%s,%s,clock_timestamp()+interval \'1 hour\')', (scope,c.source_id,raw,values['authorized'],values['confirmed'],values['semantic_resolved'],values['active']))

def setup():
    base=dict(KW,dbname='postgres')
    with psycopg.connect(**base,autocommit=True) as c:
        c.execute("CREATE DATABASE cj011_test ENCODING 'UTF8' TEMPLATE template0")
    with connect() as c:
        c.execute(Path(__file__).resolve().parents[1].joinpath('schema.sql').read_text())
        c.execute("INSERT INTO cj_memory_scope(scope) VALUES ('A'),('B')")

class Checks(unittest.TestCase):
    def setUp(self):
        self.a=Service(Repository(connect,'A')); self.b=Service(Repository(connect,'B'))
    def test_01_durable_and_isolation(self):
        raw=command('durable'); grant(raw)
        r=self.a.save(raw)
        self.assertEqual(r,self.a.query('op-durable'))
        self.assertEqual(self.a.detail(r.item_id).command.raw,raw)
        self.assertIsNone(self.b.detail(r.item_id)); self.assertIsNone(self.b.query(r.operation_id))
        self.assertFalse(self.b.effective('self').items)
        self.assertTrue(self.a.groups())
    def test_02_concurrency_and_exact_bytes(self):
        raw=command('race'); grant(raw)
        with ThreadPoolExecutor(max_workers=8) as pool: receipts=list(pool.map(lambda _: self.a.save(raw),range(16)))
        self.assertEqual(len(set(receipts)),1)
        with self.assertRaises(Conflict): self.a.save(raw+b' ')
    def test_03_candidates_and_authority(self):
        for n,opts in [('infer',{}),('unconfirmed',{'confirmed':False}),('ambiguous',{'semantic_resolved':False})]:
            raw=command(n,kind='inference' if n=='infer' else 'preference');grant(raw,**opts)
            self.assertEqual(self.a.save(raw).status,'candidate')
        for n,opts in [('unauthorized',{'authorized':False}),('revoked',{'active':False})]:
            raw=command(n);grant(raw,**opts)
            with self.assertRaises(Unavailable): self.a.save(raw)
            self.assertIsNone(self.a.query('op-'+n))
        effective={i.command.item_id for i in self.a.effective('self').items}
        self.assertFalse(effective & {'item-infer','item-unconfirmed','item-ambiguous'})
    def test_04_current_and_companion(self):
        for n,kw in [('long',{}),('current',dict(extent='current',context_id='chat-generation-1')),('companion',dict(subject='companion-1'))]:
            raw=command(n,slot='pace',**kw);grant(raw);self.a.save(raw)
        def selected(context=None):return {i.command.slot:i.command.item_id for i in self.a.effective('self',context).items}
        self.assertEqual(selected()['pace'],'item-long')
        self.assertEqual(selected('chat-generation-1')['pace'],'item-current')
        self.assertEqual(selected('other-trip')['pace'],'item-long')
        self.assertEqual(self.a.detail('item-long').version,1)
    def test_05_unknown_ack(self):
        raw=command('unknown');grant(raw)
        class LostAck:
            def __init__(self):self.conn=connect()
            def __getattr__(self,k):return getattr(self.conn,k)
            def commit(self):self.conn.commit();raise OSError('simulated lost commit ACK')
        with self.assertRaises(CommitUnknown):Service(Repository(LostAck,'A')).save(raw)
        self.assertEqual(self.a.query('op-unknown').item_id,'item-unknown')
    def test_06_failed_commit(self):
        raw=command('failed');grant(raw)
        class Failed:
            def __init__(self):self.conn=connect()
            def __getattr__(self,k):return getattr(self.conn,k)
            def commit(self):raise OSError('before commit')
        with self.assertRaises(CommitUnknown):Service(Repository(Failed,'A')).save(raw)
        self.assertIsNone(self.a.query('op-failed'))
    def test_07_source_fence(self):
        raw=command('fence');grant(raw);self.a.save(raw)
        snapshot=self.a.effective('self')
        with connect() as c:
            c.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A' FOR UPDATE")
            c.execute("UPDATE cj_memory_source SET active=false,version=version+1 WHERE scope='A' AND source_id='source-fence'")
            c.execute("UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope='A'")
        self.assertNotIn('item-fence',[i.command.item_id for i in self.a.effective('self').items])
        with self.assertRaises(Conflict):self.a.check_fence(snapshot.epoch)
        self.assertEqual(self.a.query('op-fence').status,'active') # Historical receipt, not current validity.
    def test_08_translation_does_not_duplicate(self):
        raw=command('english',slot='food-durable',text='No spicy food');grant(raw)
        with self.assertRaises(Conflict):self.a.save(raw)
        self.assertIsNone(self.a.query('op-english'))
    def test_09_invalid_and_expired(self):
        with self.assertRaises(InvalidInput):self.a.save(b'{"owner":"A"}')
        raw=command('expired');grant(raw)
        with connect() as c:c.execute("UPDATE cj_memory_source SET expires_at=clock_timestamp()-interval '1 second' WHERE source_id='source-expired'")
        with self.assertRaises(Unavailable):self.a.save(raw)
    def test_10_list_and_disabled(self):
        first=self.a.list_items(limit=2)
        second=self.a.list_items(after=first[-1].command.item_id,limit=2)
        self.assertFalse({i.command.item_id for i in first} & {i.command.item_id for i in second})
        self.assertFalse(self.b.list_items())
        raw=command('disabled');grant(raw);self.a.save(raw)
        with connect() as c:
            c.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A' FOR UPDATE")
            c.execute("UPDATE cj_memory_item SET status='disabled',version=2 WHERE item_id='item-disabled' AND scope='A'")
            c.execute("UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope='A'")
        self.assertNotIn('item-disabled',[i.command.item_id for i in self.a.effective('self').items])
    def test_11_expiry_publication_fence(self):
        raw=command('expiry-fence');grant(raw);self.a.save(raw)
        context=self.a.effective('self')
        with connect() as c:c.execute("UPDATE cj_memory_source SET expires_at=clock_timestamp()-interval '1 second' WHERE source_id='source-expiry-fence'")
        with self.assertRaises(Conflict):
            with self.a.repository.transaction() as tx:tx.require_current(context,'self')
    def test_12_stale_source_and_item_collision(self):
        raw=command('stale');grant(raw)
        with connect() as c:c.execute("UPDATE cj_memory_source SET version=2 WHERE source_id='source-stale'")
        with self.assertRaises(Unavailable):self.a.save(raw)
        raw=command('collision',item_id='item-durable');grant(raw)
        with self.assertRaises(Conflict):self.a.save(raw)

if __name__=='__main__':
    if '--setup' in sys.argv: setup();sys.argv.remove('--setup')
    unittest.main(verbosity=2)
