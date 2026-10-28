"""Five new root wire cases: fixed NEEDS/FEASIBILITY + strict JWT + new real PG."""
from dataclasses import replace
import hashlib,json,os,time
from pathlib import Path
from unittest.mock import patch
import jwt,psycopg
from fastapi.testclient import TestClient
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import Fact
from cj_auth.jwt_adapter import PyJWTVerifier
from cj_needs import Boundary,Command
from cj_needs.protected_read import ProtectedReader
from cj_api.app import create_app
from cj_api.composition import CompositionUnavailable
from cj_api.feasibility_composition import FeasibilityConfiguration,_candidate_dependencies,create_feasibility_app
from cj_api import feasibility_routes
from test_composition import SyntheticFixture

CONFIG=json.loads(Path(os.environ['CJ005_FEASIBILITY_PG_CONFIG']).read_text())
def connect():return psycopg.connect(**CONFIG)
def known(value):return dict(state='known',value=value)
def event(day):return dict(date=known(day),time=known('09:00'),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
class Cursor:
    def __init__(self,c,owner):self.c,self.owner=c,owner
    def execute(self,sql,args=None):self.owner.sql.append(sql);return self.c.execute(sql,args)
    def fetchone(self):return self.c.fetchone()
class Conn:
    def __init__(self,owner):self.owner=owner;self.c=connect();owner.opened+=1
    @property
    def autocommit(self):return self.c.autocommit
    @property
    def closed(self):return self.c.closed
    @property
    def info(self):return self.c.info
    def cursor(self):return Cursor(self.c.cursor(),self.owner)
    def commit(self):self.c.commit()
    def rollback(self):self.c.rollback()
    def close(self):
        self.c.close();self.owner.closed+=1
        if self.owner.close_hook:self.owner.close_hook()
        if self.owner.close_error:raise OSError('PRIVATE_CLOSE_FAILURE')

class FeasibilityChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();env=patch.dict(os.environ,{'CJ_ENV':'local'});env.start();self.addCleanup(env.stop)
        self.scope='f-'+self._testMethodName;self.other='b-'+self._testMethodName;self.sql=[];self.opened=self.closed=0;self.close_error=False;self.close_hook=None
        self.checker=AdmissionChecker(PyJWTVerifier(self.config,self.keys),self.policy)
        self.read_connect=lambda:Conn(self)
        def resolve(principal,environment):
            if environment!='local':raise ValueError('Unconfigured host environment')
            return self.read_connect,self.scope if principal.subject=='synthetic-user' else self.other
        self.resolve=resolve;self.options=FeasibilityConfiguration(10,1048576,131072,262144)
        self.deps=self.dependencies(self.options)
        self.client=TestClient(create_app(_feasibility_dependencies=self.deps));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token};self.originals=[]
        with connect() as c:c.execute('INSERT INTO cj_needs_scope VALUES (%s),(%s)',(self.scope,self.other))
        self.seed(self.scope,dict(arrival=event('2026-11-03'),departure=event('2026-11-02'),budget_total=known('100.000001')),0)
        self.seed(self.scope,dict(party_size=known(3)),1)
        self.seed(self.other,dict(party_size=dict(state='unknown')),0)
    def dependencies(self,options):return _candidate_dependencies(environment='local',checker=self.checker,resolve=self.resolve,configuration=options,issuer=self.config.issuer,audience=self.config.audience)
    def seed(self,scope,changes,version):
        boundary=Boundary(self.checker,lambda p:(connect,scope))
        raw=json.dumps(dict(action_id='original-'+str(version+1),needs_id='needs-current',expected_version=version,source=dict(kind='manual',text='explicit synthetic source e\u0301/中文'),changes=changes),ensure_ascii=False,indent=2).encode()+b'\n'
        boundary.with_operation(self.token,lambda op:(op.act(Command(raw)),b'fixture-only')[1])
        if scope==self.scope:self.originals.append(raw)
    def get(self,client=None,**params):return (client or self.client).get('/v1/needs-feasibility',params=params or {'needs_id':'needs-current'},headers=self.headers)
    def inventory(self):
        with connect() as c:return [c.execute('SELECT * FROM '+t+' WHERE scope=%s ORDER BY '+order,(self.scope,)).fetchall() for t,order in [('cj_needs_scope','scope'),('cj_needs_record','scope,needs_id'),('cj_needs_revision','scope,needs_id,version')]]
    def test_exact_original_report_envelope_hash_conflict_unknown_and_no_domain_write(self):
        before=self.inventory();project=self.deps.modules['cj_feasibility.current_read'].project_current;captured=[]
        def capture(*a,**kw):
            raw=project(*a,**kw);captured.append(raw);return raw
        with patch.object(self.deps.modules['cj_feasibility.current_read'],'project_current',side_effect=capture):r=self.get()
        self.assertEqual(r.status_code,200,r.text);body=r.json();report=body['evaluation']
        self.assertEqual(r.content,b'{"request_id":'+json.dumps(body['request_id']).encode()+b',"evaluation":'+captured[-1]+b'}')
        self.assertEqual((report['status'],report['overall'],report['revision']),('CONFLICT','UNKNOWN',2))
        self.assertEqual([s['original_input_utf8'].encode() for s in report['sources']],self.originals)
        for source,raw in zip(report['sources'],self.originals):self.assertEqual(source['original_input_sha256'],hashlib.sha256(raw).hexdigest())
        with connect() as c:content=c.execute('SELECT content FROM cj_needs_record WHERE scope=%s',(self.scope,)).fetchone()[0]
        self.assertEqual(report['content_sha256'],hashlib.sha256(bytes(content)).hexdigest())
        self.assertEqual(body['request_id'],r.headers['X-Request-ID']);self.assertEqual(r.headers['Cache-Control'],'no-store')
        self.assertEqual(self.inventory(),before);self.assertTrue(all(sql.startswith(('SELECT ','SET ')) for sql in self.sql));self.assertEqual(self.opened,self.closed)
        now=int(time.time());token=jwt.encode(dict(iss=self.config.issuer,aud=self.config.audience,sub='other',iat=now-1,nbf=now-1,exp=now+120),self.key,algorithm='RS256',headers={'kid':'test-key'})
        r=self.client.get('/v1/needs-feasibility?needs_id=needs-current',headers={'Authorization':'Bearer '+token})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['evaluation']['status'],'UNKNOWN');self.assertEqual(r.json()['evaluation']['revision'],1)
    def test_bounds_missing_data_extra_selectors_and_closed_factory(self):
        for options in [FeasibilityConfiguration(1,1048576,131072,262144),FeasibilityConfiguration(10,1,131072,262144),FeasibilityConfiguration(10,1048576,1,262144),FeasibilityConfiguration(10,1048576,131072,1)]:
            with TestClient(create_app(_feasibility_dependencies=self.dependencies(options))) as c:
                r=self.get(c);self.assertEqual(r.status_code,503);self.assertNotIn('evaluation',r.json())
        self.assertEqual(self.get(needs_id='missing-original').status_code,503)
        before=self.opened
        for key in ['owner','environment','max_revisions','history','candidate']:
            self.assertEqual(self.get(needs_id='needs-current',**{key:'caller'}).status_code,400)
        self.assertEqual(self.opened,before)
        with self.assertRaises(CompositionUnavailable):create_feasibility_app(configuration=self.options,environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve=self.resolve)
        with TestClient(create_app()) as c:self.assertEqual(self.get(c).status_code,503)
    def test_invalid_original_history_is_explicit_safe_error_not_fake_report(self):
        corrupt=json.loads(self.originals[0]);corrupt['action_id']='different-original';corrupt['source']['text']='PRIVATE_HISTORY_SENTINEL'
        with connect() as c:c.execute('UPDATE cj_needs_revision SET original_input=%s WHERE scope=%s AND version=1',(json.dumps(corrupt).encode(),self.scope))
        r=self.get();self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['code'],'FEASIBILITY_INPUT_INVALID');self.assertNotIn('evaluation',r.json());self.assertNotIn('PRIVATE_',r.text)
    def test_strict_first_close_failure_withholds_at_wire(self):
        self.close_error=True;r=self.get();self.assertEqual(r.status_code,503);self.assertEqual(self.opened,1);self.assertEqual(self.closed,1);self.assertNotIn('evaluation',r.json())
    def test_outer_auth_refusal_closed_before_io(self):
        before=self.opened
        for fact,status in [(Fact.NO,403),(Fact.UNKNOWN,503)]:
            self.policy.invited=fact;self.assertEqual(self.get().status_code,status);self.assertEqual(self.opened,before)
