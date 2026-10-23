"""Two new cohost scenarios; one canonical package/checker/repository, real PG."""
import hashlib,json,os,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_auth.interfaces import AdmissionStatus,Fact
from cj_memory import domain,postgres
from cj_memory.manual import ManualPolicy
from cj_memory_management import guarded
from cj_api.app import create_app
from cj_api.memory_boundary import MemoryBinding,MemoryWireConfiguration,build_memory_boundary
from cj_api.memory_management_boundary import MemoryManagementConfiguration,_candidate_boundary_from_checker
from test_composition import SyntheticFixture

CONFIG=json.loads(Path(os.environ['CJ005_MANAGEMENT_PG_CONFIG']).read_text())
def connect():return psycopg.connect(**CONFIG)
class Conn:
    def __init__(self,owner):self.owner=owner;self.c=connect()
    @property
    def autocommit(self):return self.c.autocommit
    def cursor(self):return self.c.cursor()
    def commit(self):
        self.c.commit()
        if self.owner.unknown:raise OSError('PRIVATE_ACK_LOSS')
    def rollback(self):self.c.rollback()
    def close(self):self.c.close()

class CohostChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();env=patch.dict(os.environ,{'CJ_ENV':'local'});env.start();self.addCleanup(env.stop)
        self.scope='cohost-'+self._testMethodName;self.unknown=False;self.connections=0;self.allowed=set()
        with connect() as c:c.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s)',(self.scope,))
        def factory():self.connections+=1;return Conn(self)
        self.repository=postgres.Repository(factory,self.scope)
        policy=ManualPolicy(frozenset({'self'}),frozenset({'diet'}),frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda c,raw:raw in self.allowed,lambda c,raw:True)
        self.old_service=domain.Service(self.repository,manual_policy=policy)
        self.management_service=guarded.GuardedService(self.repository)
        self.old=build_memory_boundary(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve_binding=lambda p:MemoryBinding(self.scope,self.old_service),source_policy=lambda *_:True)
        self.new=_candidate_boundary_from_checker(environment='local',checker=self.old.checker,resolve_binding=lambda p:MemoryBinding(self.scope,self.management_service))
        self.options=MemoryWireConfiguration(32768,20,65536)
        self.client=TestClient(create_app(_memory_boundary=self.old,_memory_configuration=self.options,_memory_management_boundary=self.new,_memory_management_configuration=MemoryManagementConfiguration(32768,65536)));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/octet-stream'}
    def save_raw(self,oid):
        return json.dumps(dict(operation_id=oid,item_id='shared-item',subject='self',slot='diet',kind='preference',text='e\u0301 原事实 / original',extent='long_term',context_id=None,occurred_at='date unknown'),ensure_ascii=False,indent=1).encode()+b'\n'
    def action(self,aid,operation='pause',version=1):
        return json.dumps(dict(action_id=aid,operation=operation,item_id='shared-item',expected_version=version,expected_source_version=1),ensure_ascii=False,indent=2).encode()+b'\n'
    def post(self,path,raw):return self.client.post(path,content=raw,headers=self.headers)
    def get(self,path,**query):return self.client.get(path,params=query,headers=self.headers)
    def consume(self):
        # Existing public held-lock producer seam; no new root route or wrapper.
        # The test guard reuses the same canonical root checker/current host scope.
        def guard(stage):
            d=self.old.checker.check(self.token)
            if d.status is not AdmissionStatus.ALLOWED:raise RuntimeError('withhold')
            return d.principal,self.scope
        def encode(current):
            self.assertTrue(all(type(i) is domain.Item for i in current.items))
            return json.dumps(dict(items=[dict(text=i.command.text,version=i.version) for i in current.items],epoch=current.epoch),ensure_ascii=False).encode()
        return json.loads(self.old_service.with_operation(guard,lambda ctx:ctx.consume_current('self',None,encode,max_result_bytes=4096)))
    def inventory(self):
        with connect() as c:
            return [c.execute('SELECT * FROM '+table+' WHERE scope=%s ORDER BY 1,2',(self.scope,)).fetchall() for table in ['cj_memory_scope','cj_memory_source','cj_memory_item','cj_memory_operation','cj_memory_management_action']]
    def test_single_identity_save_pause_read_consume_resume(self):
        self.assertIs(self.old.modules['cj_memory.domain'],self.new.modules['cj_memory.domain'])
        self.assertIs(self.old.modules['cj_memory.postgres'],self.new.modules['cj_memory.postgres'])
        self.assertIs(sys.modules['cj_memory.domain'].Receipt,domain.Receipt)
        self.assertIs(guarded.GuardedService.__mro__[1],domain.Service)
        self.assertIs(self.old.checker,self.new.checker);self.assertIs(self.old_service.repository,self.management_service.repository)
        raw=self.save_raw('save-original');self.allowed.add(raw);before=self.connections
        r=self.post('/v1/memories',raw);self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.connections,before+1)
        save=r.json()['receipt'];self.assertEqual(save['input_sha256'],hashlib.sha256(raw).hexdigest())
        current=self.consume();self.assertEqual(current['items'],[dict(text=json.loads(raw)['text'],version=1)])
        before=self.connections;r=self.post('/v1/memory-management-actions',self.action('pause-original'));self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.connections,before+1)
        self.assertEqual(r.json()['receipt']['status'],'disabled')
        detail=self.get('/v1/memory-items',item_id='shared-item').json()['item'];self.assertEqual((detail['version'],detail['status']),(2,'disabled'))
        self.assertEqual(self.get('/v1/memories',limit='10').json()['items'][0]['status'],'disabled')
        self.assertEqual(self.get('/v1/memory-groups').json()['groups'][0]['status'],'disabled')
        paused=self.consume();self.assertEqual(paused['items'],[]);self.assertGreater(paused['epoch'],current['epoch'])
        self.assertEqual(self.get('/v1/memory-receipts',operation_id='save-original').json()['receipt'],save)
        r=self.post('/v1/memory-management-actions',self.action('resume-original','resume',2));self.assertEqual(r.status_code,200,r.text)
        resumed=self.consume();self.assertEqual(resumed['items'],[dict(text=json.loads(raw)['text'],version=3)]);self.assertGreater(resumed['epoch'],paused['epoch'])
        self.assertEqual(self.get('/v1/memory-management-receipts',action_id='pause-original').json()['receipt']['status'],'disabled')
        self.assertEqual(self.get('/v1/memory-management-receipts',action_id='resume-original').json()['receipt']['status'],'active')
        self.assertEqual(self.get('/v1/memory-items',item_id='shared-item').json()['item']['command']['text'],json.loads(raw)['text'])
        with TestClient(create_app(_memory_boundary=self.old,_memory_configuration=self.options)) as old_only:
            self.assertEqual(old_only.get('/v1/memory-management-receipts?action_id=pause-original',headers=self.headers).status_code,503)
    def test_both_unknowns_same_original_id_distinct_ledgers_and_shared_guard(self):
        oid='same +e\u0301/中文';raw=self.save_raw(oid);self.allowed.add(raw);self.unknown=True
        r=self.post('/v1/memories',raw);self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['recovery'],'reconcile_original')
        self.unknown=False;saved=self.get('/v1/memory-receipts',operation_id=oid).json()['receipt'];self.assertEqual(saved['version'],1)
        action=self.action(oid);self.unknown=True;r=self.post('/v1/memory-management-actions',action)
        self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['recovery'],'reconcile_original');self.assertNotIn('PRIVATE_',r.text)
        self.unknown=False;before=self.inventory()
        lifecycle=self.get('/v1/memory-management-receipts',action_id=oid).json()['receipt'];save=self.get('/v1/memory-receipts',operation_id=oid).json()['receipt']
        self.assertEqual((lifecycle['status'],lifecycle['version']),('disabled',2));self.assertEqual((save['status'],save['version']),('active',1))
        self.assertEqual(save['input_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(lifecycle['input_sha256'],hashlib.sha256(action).hexdigest());self.assertNotEqual(save['input_sha256'],lifecycle['input_sha256'])
        self.assertEqual(self.inventory(),before)
        connections=self.connections;self.policy.invited=Fact.NO
        for path,key in [('/v1/memory-receipts','operation_id'),('/v1/memory-management-receipts','action_id')]:
            r=self.get(path,**{key:oid});self.assertEqual(r.status_code,403,r.text);self.assertNotIn('receipt',r.json())
        self.assertEqual(self.connections,connections)
