"""#27 actual RUN/FakeProvider content preserved while diagnostic timing expires."""
from dataclasses import asdict
import json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,app_from_environment,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
from cj_cleanup.core import Scope,digest,encode
from cj_cleanup.registry import freeze
from cj_cleanup.store import Store
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.hooks_v1_1 import Selection
from cj_cleanup.diagnostic_retention import DiagnosticHook,SECONDS
from cj_cleanup.account_hooks import DomainHook,UsageHook,MESSAGE,RUN,NEEDS
from cj_run.account_stop import stop_scope
from cj_run.step_usage import ledger_scope_for
from cj_message.needs_binding import needs_scope_for
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker


def main(root,conninfo):
    config=json.loads(conninfo.read_text());auth=root/'auth';subjects=['retention-a','retention-b'];dev_auth.init(auth,subjects)
    now=int(time.time());path=root/'run.json'
    path.write_text(json.dumps({'version':'CJ-LOCAL-RUN@2','current':{'meter':dict(unit='provider_call',budget=20,
        period_start=now-60,period_end=now+3600,max_steps=20,max_tools=10,max_output=10000,max_seconds=600),
        'output_limits':{'model':2000,'tool':2000,'memory':2000}},'history':[]}))
    context=load_run_context(path)
    for subject in subjects:local_run_context.provision_budget(conninfo,context,subject)
    database=LocalDatabase(conninfo,run_context=context);headers={s:{'Authorization':'Bearer '+dev_auth.token(auth,s,30),'Content-Type':'application/octet-stream'} for s in subjects}
    env=dict(CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(path))
    with patch.dict(os.environ,env),TestClient(app_from_environment()) as client:
        for subject in subjects:
            head=client.put('/v1/conversations',params={'conversation_id':'retention'},headers=headers[subject]).json()
            raw=encode(dict(version='MESSAGE-send.1',conversation_id='retention',message_id='retained-message',text='RETAIN_ANSWER_AND_INPUT',
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
            assert client.post('/v1/messages',content=raw,headers=headers[subject]).status_code==200
        model=FakeProvider();run_worker.run_once(database,model,auth);assert model.calls==2
    owner=scope_for(ISSUER,subjects[0]);other=scope_for(ISSUER,subjects[1]);cutoff=now-SECONDS
    with psycopg.connect(**config) as conn:
        original=conn.execute('SELECT scope,run_id,sequence,event_id,kind,value FROM cj_run_event ORDER BY scope,sequence').fetchall()
        usage=conn.execute('SELECT scope_id,revision,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
        for index,row in enumerate([r for r in original if r[0]==owner]):
            stamp=cutoff-1 if index==0 else cutoff if index==1 else cutoff+1
            conn.execute('UPDATE cj_run_event SET diagnostic_at=to_timestamp(%s) WHERE scope=%s AND run_id=%s AND sequence=%s',(stamp,*row[:3]))
        conn.execute('UPDATE cj_run_event SET diagnostic_at=to_timestamp(%s) WHERE scope=%s',(cutoff-100,other))
        other_times=conn.execute('SELECT diagnostic_at FROM cj_run_event WHERE scope=%s ORDER BY sequence',(other,)).fetchall()
    principal=checker_for(auth).check(headers[subjects[0]]['Authorization'].split(' ',1)[1]).principal
    subject=digest(encode(asdict(Scope.from_principal('local',principal))))
    store=Store(lambda:psycopg.connect(**dict(config,user='cj_local_cleanup')),subject,lambda stage:None)
    target='checkpoints/run';raw=encode(dict(version='retention-local-proof',stores=[dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')])]))
    manifest=freeze(raw,(target,),versions=('CLEANUP@1.1',));hook=DiagnosticHook(store,owner,lambda:now)
    host=Coordinator(store,lambda:manifest,{target:hook});selection=Selection('diagnostics',before_unix=cutoff)
    host.create('retention-90d',digest(b'explicit local maintenance'),'diagnostics',{target:{'domain_scope':owner,'selection':selection.to_dict()}})
    request=host.request('retention-90d',target,owner,selection)
    assert host.advance(request)['status']=='complete'
    assert host.advance(request)['status']=='complete'
    with psycopg.connect(**config) as conn:
        rows=conn.execute('SELECT diagnostic_at FROM cj_run_event WHERE scope=%s ORDER BY sequence',(owner,)).fetchall()
        assert rows[0][0] is None and rows[1][0] is not None and rows[2][0] is not None
        assert conn.execute('SELECT diagnostic_at FROM cj_run_event WHERE scope=%s ORDER BY sequence',(other,)).fetchall()==other_times
        assert conn.execute('SELECT scope,run_id,sequence,event_id,kind,value FROM cj_run_event ORDER BY scope,sequence').fetchall()==original
        assert conn.execute('SELECT scope_id,revision,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()==usage
        assert conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0]==2
    print('PASS injected 90-day before/at/after cutoff, same dedicated role/original result, actual original run_once/FakeProvider, other owner/content/usage evidence untouched')
    # Actual periodic host step uses the same dedicated role and injected clock.
    from cj_api.local_cleanup import Runtime,Configuration
    from cleanup_worker import step
    tick=[now//86400*86400]
    diagnostic_registry=root/'diagnostic-registry.json';diagnostic_registry.write_bytes(raw)
    options=Configuration({'maintenance':b'explicit-synthetic-maintenance-00'},'maintenance',3600,(target,),diagnostic_registry,clock=lambda:tick[0])
    runtime=Runtime(database,options,scope_for)
    scheduled_cutoff=tick[0]-SECONDS
    with psycopg.connect(**config) as conn:
        for index,row in enumerate([r for r in original if r[0]==owner]):
            stamp=scheduled_cutoff-1 if index==0 else scheduled_cutoff if index==1 else scheduled_cutoff+1
            conn.execute('UPDATE cj_run_event SET diagnostic_at=to_timestamp(%s) WHERE scope=%s AND run_id=%s AND sequence=%s',(stamp,*row[:3]))
    scheduled=step(runtime,checker_for(auth),principal)
    assert scheduled['status']=='complete'
    assert step(runtime,checker_for(auth),principal)==scheduled
    with psycopg.connect(**config) as conn:
        marks=conn.execute('SELECT diagnostic_at FROM cj_run_event WHERE scope=%s ORDER BY sequence',(owner,)).fetchall()
        assert marks[0][0] is None and marks[1][0] is not None and marks[2][0] is not None
    tick[0]+=86400
    following=step(runtime,checker_for(auth),principal)
    assert following['status']=='complete' and following['operation_id']!=scheduled['operation_id']
    with psycopg.connect(**config) as conn:
        assert all(row[0] is None for row in conn.execute('SELECT diagnostic_at FROM cj_run_event WHERE scope=%s',(owner,)))
        assert conn.execute('SELECT scope,run_id,sequence,event_id,kind,value FROM cj_run_event ORDER BY scope,sequence').fetchall()==original
        assert conn.execute('SELECT scope_id,revision,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()==usage
        assert conn.execute('SELECT diagnostic_at FROM cj_run_event WHERE scope=%s ORDER BY sequence',(other,)).fetchall()==other_times
    print('PASS actual periodic host step/restart/day rollover with injected clock; exact-cutoff and other-owner/content/accounting invariants')
    # Real B domain hooks over the produced data, not no-op owner callbacks.
    # Provision older unreferenced periods; discovery must not depend on retaining
    # current RUN bindings or on a caller-supplied list of ledger IDs.
    old_document=json.loads(path.read_text())
    old_document['current']['meter']['period_start']=now-20000
    old_document['current']['meter']['period_end']=now-10000
    old_path=root/'old-period.json';old_path.write_text(json.dumps(old_document))
    old_context=load_run_context(old_path,require_active=False)
    for user in subjects:local_run_context.provision_budget(conninfo,old_context,user)
    old_owner_ledger=ledger_scope_for(owner,old_context.current.meter)
    old_other_ledger=ledger_scope_for(other,old_context.current.meter)
    names=('checkpoints/run','business/message','business/needs-current-planning','business/usage')
    reg=encode(dict(version='b-domain-proof',stores=[dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='business',objects=[dict(id=x.split('/')[1],cleanup_protocol='CLEANUP@1.1') for x in names[1:]])]))
    manifest2=freeze(reg,names,versions=('CLEANUP@1.1',))
    usage_hook=UsageHook(store,owner,(ledger_scope_for(owner,context.current.meter),))
    hooks={names[0]:DomainHook(store,owner,RUN),names[1]:DomainHook(store,owner,MESSAGE),
           names[2]:DomainHook(store,needs_scope_for(owner),NEEDS),names[3]:usage_hook}
    plan={t:{'domain_scope':needs_scope_for(owner) if t==names[2] else owner,'selection':{'kind':'account'}} for t in names}
    host2=Coordinator(store,lambda:manifest2,hooks)
    # Dialogue cards inherit physical erasure through their original receipt FK.
    for account in (owner,other):
        with database.connect(account) as conn:
            run,=conn.execute('SELECT run_id FROM cj_message_receipt WHERE scope=%s AND message_id=%s',
                              (account,'retained-message')).fetchone()
            conn.execute("INSERT INTO cj_demo_needs_card(scope,origin_message_id,origin_run_id,card_id,version,fields) "
                         "VALUES(%s,%s,%s,%s,1,%s)",(account,'retained-message',run,'needs-'+'a'*32,b'{}'))
            conn.execute("INSERT INTO cj_demo_trip_adoption(scope,action_id,original_message_id,proposal_id,"
                         "candidate_hash,input_sha256) VALUES(%s,%s,%s,%s,%s,%s)",
                         (account,'fixture-trip-adoption','retained-message','p-fixture','a'*64,'b'*64))
    host2.create('real-b-domain-erasure',digest(b'explicit local B domain proof'),'account',plan)
    # The real API creates this prepared operation before confirmation.
    with store.transaction('real-b-domain-erasure') as cur:
        cur.execute("INSERT INTO cj_cleanup_request(subject_digest,operation_id,action_id,input_digest,registry_bytes,inventory,plan_bytes,plan_digest,binding_id,phase) "
                    "VALUES(%s,'real-b-domain-erasure','b-domain-action',%s,%s,%s::jsonb,%s,%s,'fixture-binding','confirmed')",
                    (subject,digest(b'proof'),reg,json.dumps(names),encode(plan),digest(encode(plan))))
        cur.execute('INSERT INTO cj_account_fence(subject_digest,owner_digest,operation_id,namespace_digests) VALUES(%s,%s,%s,%s::jsonb)',
                    (subject,digest(owner.encode()),'real-b-domain-erasure',json.dumps([digest(owner.encode()),digest(needs_scope_for(owner).encode()),digest(ledger_scope_for(owner,context.current.meter).encode())])))
        cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(owner,))
        assert stop_scope(cur,owner)
    usage_hook.require_settled('real-b-domain-erasure')
    for target in names:
        request=host2.request('real-b-domain-erasure',target,plan[target]['domain_scope'],Selection('account'))
        host2.advance(request)
    assert host2.query('real-b-domain-erasure')['status']=='complete'
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_demo_needs_card WHERE scope=%s',(owner,)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM cj_demo_needs_card WHERE scope=%s',(other,)).fetchone()==(1,)
        assert conn.execute('SELECT count(*) FROM cj_demo_trip_adoption WHERE scope=%s',(owner,)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM cj_demo_trip_adoption WHERE scope=%s',(other,)).fetchone()==(1,)
        assert conn.execute('SELECT count(*) FROM cj_run_record WHERE scope=%s',(owner,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_usage_ledger_candidate WHERE scope_id=%s',(ledger_scope_for(owner,context.current.meter),)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_usage_ledger_candidate WHERE scope_id=%s',(old_owner_ledger,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_usage_ledger_candidate WHERE scope_id=%s',(old_other_ledger,)).fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(other,)).fetchone()[0]==1
    # Bare old runtime credentials cannot reconstruct the erased account scope.
    try:
        with database.connect(owner) as conn:conn.execute('INSERT INTO cj_message_scope(scope) VALUES(%s)',(owner,))
    except psycopg.Error:pass
    else:raise AssertionError('runtime recreated a retired account namespace')
    print('PASS real message/run/needs/usage B hooks after actual FakeProvider, original task ownership stop, cross-owner preservation and database non-resurrection fence')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-retention-') as temp:main(Path(temp),Path(os.environ['CJ_E2E_CONNINFO']))
