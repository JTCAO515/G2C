"""Two new same-process NEEDS write/FEAS read combinations on real private PG."""
import base64,hashlib,inspect,json,os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_needs import domain,boundary,postgres,protected_read
from cj_api.app import create_app
from cj_api.needs_composition import NeedsWireConfiguration,build_needs_boundary
from cj_api.feasibility_composition import FeasibilityConfiguration,_candidate_dependencies
from cj_api import feasibility_routes
from test_composition import SyntheticFixture

CONFIG=json.loads(Path(os.environ['CJ005_FEASIBILITY_PG_CONFIG']).read_text())
def connect():return psycopg.connect(**CONFIG)
def known(v):return dict(state='known',value=v)
def event(day):return dict(date=known(day),time=known('09:00'),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
class Conn:
    def __init__(self,owner):self.owner=owner;self.c=connect();owner.opened+=1
    @property
    def autocommit(self):return self.c.autocommit
    @property
    def closed(self):return self.c.closed
    @property
    def info(self):return self.c.info
    def cursor(self):return self.c.cursor()
    def commit(self):
        self.c.commit()
        if self.owner.unknown:raise OSError('PRIVATE_ACK_LOSS_AFTER_COMMIT')
    def rollback(self):self.c.rollback()
    def close(self):
        self.c.close();self.owner.closed+=1
        if self.owner.close_error:raise OSError('PRIVATE_ORDINARY_CLOSE_FAILURE')

class NeedsCohostChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();env=patch.dict(os.environ,{'CJ_ENV':'local'});env.start();self.addCleanup(env.stop)
        self.scope='nco-'+self._testMethodName;self.other='other-'+self._testMethodName
        self.unknown=False;self.close_error=False;self.opened=self.closed=0;self.repositories=[];self.last_strict=None
        self.read_connect=lambda:Conn(self)
        self.legacy_resolve=lambda p:(self.read_connect,self.scope)
        def resolve(p,environment):
            if environment!='local':raise ValueError('Unconfigured host environment')
            return self.legacy_resolve(p)
        self.current_resolve=resolve
        self.old,self.modules=build_needs_boundary(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve=self.legacy_resolve)
        self.current=_candidate_dependencies(environment='local',checker=self.old.checker,resolve=self.current_resolve,configuration=FeasibilityConfiguration(10,1048576,131072,262144),issuer=self.config.issuer,audience=self.config.audience)
        self.needs_options=NeedsWireConfiguration(131072,524288)
        self.assertIs(inspect.signature(postgres.Repository).parameters['strict_close'].default,False)
        original=postgres.Repository.__init__
        def initialize(repo,*args,**kwargs):
            original(repo,*args,**kwargs);self.repositories.append(repo)
            if repo.strict_close:self.last_strict=repo
        observer=patch.object(postgres.Repository,'__init__',new=initialize);observer.start();self.addCleanup(observer.stop)
        self.client=TestClient(create_app(_needs_boundary=self.old,_needs_configuration=self.needs_options,_needs_modules=self.modules,_feasibility_dependencies=self.current));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/octet-stream'}
        with connect() as c:c.execute('INSERT INTO cj_needs_scope VALUES (%s),(%s)',(self.scope,self.other))
    def raw(self,aid,changes,version=0):
        return json.dumps(dict(action_id=aid,needs_id='cohost-needs',expected_version=version,source=dict(kind='manual',text='synthetic e\u0301 / 中文'),changes=changes),ensure_ascii=False,indent=2).encode()+b'\n'
    def post(self,raw):return self.client.post('/v1/needs-actions',content=raw,headers=self.headers)
    def get(self,path,**q):return self.client.get(path,params=q,headers=self.headers)
    def evaluate(self):return self.get('/v1/needs-feasibility',needs_id='cohost-needs')
    def inventory(self):
        with connect() as c:return [c.execute('SELECT * FROM '+table+' WHERE scope=%s ORDER BY '+order,(self.scope,)).fetchall() for table,order in [('cj_needs_scope','scope'),('cj_needs_record','scope,needs_id'),('cj_needs_revision','scope,needs_id,version')]]
    def test_single_package_write_read_then_versioned_feasibility_history(self):
        self.assertIs(self.modules['cj_needs.domain'],self.current.modules['cj_needs.domain'])
        self.assertIs(self.modules['cj_needs.postgres'].Repository,postgres.Repository)
        self.assertIs(boundary.Repository,protected_read.Repository);self.assertIs(self.old.checker,self.current.checker)
        self.assertIs(domain.Snapshot,self.current.modules['cj_needs.domain'].Snapshot)
        first=self.raw('original-1',dict(arrival=event('2026-11-03'),departure=event('2026-11-02'),budget_total=known('100.000001')))
        r=self.post(first);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['receipt']['version'],1)
        self.assertIs(self.repositories[-1].strict_close,False)
        before=self.inventory();r=self.evaluate();self.assertEqual(r.status_code,200,r.text);report=r.json()['evaluation']
        self.assertEqual((report['revision'],report['status'],report['overall']),(1,'CONFLICT','UNKNOWN'));self.assertEqual(report['sources'][0]['original_input_utf8'].encode(),first)
        self.assertEqual(self.inventory(),before);self.assertIs(self.repositories[-1].strict_close,True)
        second=self.raw('original-2',dict(arrival=event('2026-11-01')),1)
        r=self.post(second);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['receipt']['version'],2)
        old=self.get('/v1/needs',needs_id='cohost-needs').json()['needs']
        historical=self.get('/v1/needs-revisions',needs_id='cohost-needs',version=1).json()['revision'];self.assertEqual(base64.b64decode(historical['original_input_utf8_base64']),first)
        before=self.inventory();r=self.evaluate();self.assertEqual(r.status_code,200,r.text);report=r.json()['evaluation']
        self.assertEqual((report['revision'],report['status'],report['overall']),(2,'UNKNOWN','UNKNOWN'))
        self.assertEqual(report['content_sha256'],hashlib.sha256(base64.b64decode(old['content_utf8_base64'])).hexdigest())
        self.assertEqual([s['original_input_utf8'].encode() for s in report['sources']],[first,second]);self.assertEqual(self.inventory(),before)
        for source,raw in zip(report['sources'],[first,second]):self.assertEqual(source['original_input_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertTrue(all(type(repo) is postgres.Repository and repo.connect is self.read_connect and repo.scope==self.scope for repo in self.repositories))
        self.assertEqual(len({id(repo) for repo in self.repositories}),len(self.repositories));self.assertEqual(self.opened,self.closed)
        with TestClient(create_app(_needs_boundary=self.old,_needs_configuration=self.needs_options,_needs_modules=self.modules)) as old_only:
            self.assertEqual(old_only.get('/v1/needs-feasibility?needs_id=cohost-needs',headers=self.headers).status_code,503)
    def test_unknown_recovery_legacy_close_and_strict_final_scope(self):
        raw=self.raw('original-unknown',dict(party_size=known(2)));self.unknown=True
        r=self.post(raw);self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['recovery'],'reconcile_original');self.assertNotIn('receipt',r.json())
        self.unknown=False;before=self.inventory();receipt=self.get('/v1/needs-action-receipts',action_id='original-unknown').json()['receipt'];self.assertEqual(receipt['version'],1)
        r=self.evaluate();self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['evaluation']['sources'][0]['original_input_utf8'].encode(),raw);self.assertEqual(self.inventory(),before)
        # Preserve legacy ordinary-close behavior; strict current reader must reject.
        self.close_error=True
        legacy=self.get('/v1/needs',needs_id='cohost-needs');self.assertEqual(legacy.status_code,200,legacy.text);self.assertIs(self.repositories[-1].strict_close,False)
        self.opened=self.closed=0;r=self.evaluate();self.assertEqual(r.status_code,503);self.assertNotIn('evaluation',r.json());self.assertEqual((self.opened,self.closed),(1,1));self.assertIs(self.repositories[-1].strict_close,True)
        self.close_error=False;target=[None];encode=feasibility_routes.encode_response;policy=self.policy.evaluate
        def encoded(*args,**kwargs):
            result=encode(*args,**kwargs);target[0]=self.policy.calls+3;return result
        def evaluate(principal):
            facts=policy(principal)
            if self.policy.calls==target[0]:self.last_strict.scope=self.other
            return facts
        with patch.object(feasibility_routes,'encode_response',side_effect=encoded),patch.object(self.policy,'evaluate',side_effect=evaluate):r=self.evaluate()
        self.assertEqual(self.policy.calls,target[0]);self.assertEqual(r.status_code,503);self.assertNotIn('evaluation',r.json())
        # Retired strict repo mutation never rebinds a new legacy operation.
        restored=self.get('/v1/needs',needs_id='cohost-needs');self.assertEqual(restored.status_code,200,restored.text);self.assertEqual(restored.json()['needs']['version'],1)
        self.assertEqual(self.inventory(),before)
