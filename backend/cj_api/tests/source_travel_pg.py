"""Real C consent/MEMORY plus B MESSAGE/TRAVEL locks, no producer/model claim."""
import json,os,sys,tempfile,uuid
from pathlib import Path
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for
from cj_api.local_account_admission_v2 import account_checker_for
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import Boundary,AccessBlocked,IdentityChanged
from cj_message.domain import Unavailable as MessageUnavailable
from cj_message.source import SourceQuery
from cj_message.travel import Selection
from cj_message.travel_reference import CurrentTravelLease
from cj_memory.postgres import Repository as MemoryRepository
from cj_memory.domain import Unavailable as MemoryDomainUnavailable
from cj_memory_jobs.service import Service as HistoryService
from cj_memory_jobs.source_policy import SourcePolicy
from cj_memory_jobs.codec import Unavailable as MemoryUnavailable
from cj_needs.revision_lease import LeaseUnavailable
from cj_run.core import Denied
from cj_cleanup.core import encode
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth


def exercise(root,conninfo):
    auth=root/'auth';dev_auth.init(auth,['source-alice','source-bob'])
    tokens={s:dev_auth.token(auth,s,30) for s in ('source-alice','source-bob')}
    database=LocalDatabase(conninfo);checker=account_checker_for(auth,database)
    boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:uuid.uuid4().hex)
    def resolve(principal,scope):
        return MemoryRepository(lambda:database.connect(scope),scope,transaction_binder=lambda conn,cur:conn.bind_scope(cur))
    history=HistoryService(boundary,resolve)
    app=create_local_app(conninfo_path=conninfo,auth_dir=auth)
    with TestClient(app) as client:
        def post(path,value,who='source-alice'):
            response=client.post(path,content=encode(value),headers={'Authorization':'Bearer '+tokens[who],'Content-Type':'application/octet-stream'})
            assert response.status_code==200,('source/travel HTTP status',response.status_code)
            return response.json()
        heads={}
        for who in tokens:
            response=client.put('/v1/conversations',params={'conversation_id':'history'},headers={'Authorization':'Bearer '+tokens[who]})
            assert response.status_code==200;heads[who]=response.json()
            for index in range(2):
                post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='history',message_id='m'+str(index),text='synthetic source '+who,
                    trip_id=None,creation_intent='none',expected_generation=heads[who]['generation'],expected_sequence=index),who)
        travel=post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='travel-create',operation='create',travel_context=None))['receipt']['travel_context']
        foreign=post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='travel-create',operation='create',travel_context=None),'source-bob')['receipt']['travel_context']
        token=tokens['source-alice'];principal=checker.check(token).principal;owner=scope_for(ISSUER,'source-alice')
        def guard(stage):
            decision=checker.check(token)
            if decision.status is not AdmissionStatus.ALLOWED:raise AccessBlocked(decision,stage)
            if decision.principal!=principal:raise IdentityChanged(stage)
        def run(query,selection,project):
            policy=SourcePolicy(resolve(principal,owner),principal,guard)
            return boundary.with_history_context(token,lambda context:context.with_enabled_source_and_travel(query,policy,selection,project))
        query=SourceQuery('history',heads['source-alice']['generation'],0,0,2,1,1)
        selected=Selection(travel['id'],travel['version'])
        try:run(query,selected,lambda source,lease:b'forbidden')
        except (MemoryUnavailable,MemoryDomainUnavailable,MessageUnavailable):pass
        else:raise AssertionError('default-off history gained authority from travel selection')
        action=dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='history',
                    expected_generation=heads['source-alice']['generation'],expected_epoch=0,expected_source_version=0)
        enabled=json.loads(history.apply_consent(token,encode(action)))
        query=SourceQuery('history',heads['source-alice']['generation'],0,0,2,enabled['source_version'],enabled['withdrawal_epoch'])
        captured=[]
        def inspect(source,lease):
            assert type(lease) is CurrentTravelLease and lease.context==selected and lease.check() is True
            assert source.scope==owner and len(source.messages)==2 and source.source_version==enabled['source_version']
            assert all('source-alice' in item.text for item in source.messages)
            captured.append(lease)
            for sql,args in (('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE NOWAIT',(owner,)),
                             ('SELECT context_id FROM cj_travel_context WHERE scope=%s AND context_id=%s FOR UPDATE NOWAIT',(owner,travel['id'])),
                             ('SELECT scope FROM cj_memory_scope WHERE scope=%s FOR UPDATE NOWAIT',(owner,))):
                try:
                    with database.connect(owner) as other:other.execute(sql,args)
                except psycopg.errors.LockNotAvailable:pass
                else:raise AssertionError('canonical MSG/TRAVEL/MEMORY lease released before materialization')
            return b'actual-joint-source'
        assert run(query,selected,inspect)==b'actual-joint-source'
        try:captured[0].check()
        except LeaseUnavailable:pass
        else:raise AssertionError('travel lease escaped its source callback lifetime')
        try:run(query,Selection(foreign['id'],foreign['version']),lambda source,lease:b'forbidden')
        except (MessageUnavailable,Denied):pass
        else:raise AssertionError('foreign travel selection became current source authority')
        advanced=post('/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='travel-next',operation='advance',
            travel_context=dict(id=travel['id'],expected_version=travel['version'])))['receipt']['travel_context']
        try:run(query,selected,lambda source,lease:b'forbidden')
        except Denied:pass
        else:raise AssertionError('stale travel version accepted')
        selected=Selection(advanced['id'],advanced['version'])
        assert run(query,selected,lambda source,lease:b'current')==b'current'
        disabled=json.loads(history.apply_consent(token,encode(action|dict(action_id='disable',operation='disable',expected_source_version=enabled['source_version']))))
        try:run(query,selected,lambda source,lease:b'forbidden')
        except (MemoryUnavailable,MemoryDomainUnavailable,MessageUnavailable):pass
        else:raise AssertionError('withdrawn source retained collection authority')
        renewed=json.loads(history.apply_consent(token,encode(action|dict(action_id='re-enable',expected_source_version=disabled['source_version']))))
        renewed_query=SourceQuery('history',heads['source-alice']['generation'],0,0,2,renewed['source_version'],renewed['withdrawal_epoch'])
        invited=auth/'invited.json';saved=invited.read_bytes()
        def revoked(source,lease):
            invited.write_text(json.dumps(['source-bob']))
            return b'PRIVATE_WITHHELD_SOURCE'
        try:
            try:run(renewed_query,selected,revoked)
            except AccessBlocked:pass
            else:raise AssertionError('late admission loss published joint source bytes')
        finally:invited.write_bytes(saved)
        print('PASS actual signed MESSAGE/TRAVEL/C consent: MSG→T→MEMORY locks coexist without second MSG connection; default-off/foreign/stale/withdrawal/lifetime/late admission negatives; no model/job/Meter claim')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-source-travel-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
