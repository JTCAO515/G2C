"""Headers-only read on actual C publisher2 scope, without an edit writer host."""
from pathlib import Path
from uuid import uuid4
import json,sys,unittest
import psycopg
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/manual_edit/tests'),str(ROOT/'backend/memory/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from scoped_result_body_pg import ScopedResultChecks,Model
from edit_support import CONNINFO
from cj_api.local_app import LocalDatabase,scope_for,ISSUER
from cj_api.local_account_admission_v2 import account_checker_for
from cj_message.auth_boundary import Boundary
from cj_message.domain import Unavailable


class ScopedHeadersChecks(ScopedResultChecks):
    def test_actual_readonly_host_preserves_writer_refusal(self):
        f=self.fixture('headers-readonly',legacy=False)
        binding,raw,receipt=self.send(f)
        self.assertEqual(f.run(Model())[0].status,'completed')
        database=LocalDatabase(CONNINFO,run_context=f.context,travel_context=True,trip_context=True)
        token=f.headers['Authorization'][7:];connections=[]
        def resolve(principal):
            scope=scope_for(principal.issuer,principal.subject)
            repo=database.message_repository(scope);connect=repo.connect
            def captured():
                connection=connect();connections.append(connection);return connection
            repo.connect=captured
            return repo
        boundary=Boundary(account_checker_for(f.auth,database),resolve,lambda:str(uuid4()))
        with database.connect(f.scope) as before:
            self.assertEqual(before.execute('SELECT count(*) FROM cj_message_scope').fetchone(),(0,))
        captured=[]
        def project(snapshot):
            self.assertTrue(snapshot.complete);self.assertEqual(snapshot.scope,f.scope)
            refs=[r.to_dict() for r in snapshot.references]
            self.assertIn(dict(conversation_id=binding.conversation_id,generation=binding.generation,sequence=binding.message_sequence,
                               message_id=binding.message_id,input_sha256=receipt['input_sha256']),refs)
            # The temporary reader compatibility marker is already gone before
            # any caller code runs, including on the exact held connection.
            connection=connections[-1]
            self.assertIn(connection.execute("SELECT current_setting('cj.message_edit_result_abi',true)").fetchone()[0],(None,''))
            self.assertEqual(connection.execute('SELECT count(*) FROM cj_message_scope').fetchone(),(0,))
            self.assertEqual(connection.execute("UPDATE cj_message_chat SET active=active WHERE scope=%s",(f.scope,)).rowcount,0)
            captured.append(snapshot);return b'actual-scoped-headers'
        def read(project,max_refs=100):
            return boundary.with_history_context(token,lambda ctx:ctx.with_erasure_headers(project,max_refs=max_refs,max_result_bytes=32768))
        self.assertEqual(read(project),b'actual-scoped-headers')
        with database.connect(f.scope) as after:
            self.assertEqual(after.execute('SELECT count(*) FROM cj_message_scope').fetchone(),(0,))
        with self.assertRaises(Unavailable):captured[0].check()
        with self.assertRaises(Unavailable):read(lambda s:b'not truncated',max_refs=1)
        self.assertEqual(read(lambda s:b'clean after error'),b'clean after error')
        print('PASS real signed MSG4/C publisher2 scope readable as complete metadata by readonly travel host; same-connection ABI restored before callback, old reads/updates still refuse, errors clean and account/owner remain bound')

if __name__=='__main__':unittest.main(defaultTest='ScopedHeadersChecks.test_actual_readonly_host_preserves_writer_refusal')
