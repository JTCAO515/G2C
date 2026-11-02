"""#402 dedicated-role PG checks. Synthetic feedback deletion probe, not real hook."""
import json
import os
from pathlib import Path
import sys
import psycopg
from cj_cleanup.core import Conflict, Denied, digest, encode
from cj_cleanup.hooks import Selection, make_receipt
from cj_cleanup import hooks as v1, hooks_v1_1 as v11
from cj_cleanup.registry import freeze
from cj_cleanup.store import Store, original_result, record_result, require_intent
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.metadata_hook import MetadataHook

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import migrate


def main():
    config=json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text())
    subject=digest(b'synthetic original principal')
    def connect():return psycopg.connect(**dict(config,user='cj_local_cleanup'))
    store=Store(connect,subject,lambda stage:None)
    raw=encode(dict(version='fixture1',stores=[dict(id='business',objects=[dict(id='feedback',cleanup_protocol='CLEANUP@1.0',objects=['cj_feedback_action'])])]))
    inventory=('business/feedback',)
    current=[freeze(raw,inventory)]
    target=inventory[0]
    plan={target:{'domain_scope':'alice','selection':{'kind':'account'}}}
    calls=[]
    class Probe:
        def execute(self,request):
            with store.transaction(request.operation_id) as cur:
                cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(request.domain_scope,))
                old=original_result(cur,request)
                if old is not None:return old
                require_intent(cur,request)
                calls.append(request.digest)
                cur.execute('DELETE FROM cj_feedback_action WHERE scope=%s',(request.domain_scope,))
                assert cur.execute('SELECT count(*) FROM cj_feedback_action').fetchone()[0]==0
                value=record_result(cur,request,'confirmed')
            return value
        def reconcile(self,request):
            with store.transaction(request.operation_id,writing=False) as cur:
                result=original_result(cur,request)
            return result if result is not None else make_receipt(request,'unknown')
    host=Coordinator(store,lambda:current[0],{target:Probe()})
    with psycopg.connect(**config) as conn:
        for scope in ('alice','bob'):
            conn.execute("INSERT INTO cj_feedback_action(scope,operation,action_id,original_input,input_sha256) VALUES(%s,'submit','a',%s,%s)",(scope,b'fixture',digest(b'fixture')))
    assert host.create('op1',digest(b'confirm'),'account',plan)['status']=='in_progress'
    request=host.request('op1',target,'alice',Selection('account'))
    # Wrong domain selection cannot expand the confirmed plan, even in same account.
    try:host.advance(host.request('op1',target,'bob',Selection('account')))
    except Conflict:pass
    else:raise AssertionError('confirmed selection changed')
    assert host.advance(request)['status']=='complete'
    assert host.advance(request)['status']=='complete' and len(calls)==1
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT scope FROM cj_feedback_action').fetchall()==[('bob',)]
        role=conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='cj_local_cleanup'").fetchone()
        assert role==(False,)*6
        assert not conn.execute("SELECT pg_has_role('cj_m1_runtime','cj_local_cleanup','MEMBER')").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM information_schema.role_table_grants WHERE grantee='cj_m1_runtime' AND privilege_type IN ('DELETE','TRUNCATE')").fetchone()[0]==0
    print('PASS dedicated role/least DELETE, actual row erasure, other-owner preserved, immutable confirmed selection, no repeated execute')

    # Read and delete queries with another owner predicate see nothing under RLS.
    with store.transaction('op1') as cur:
        cur.execute("SELECT set_config('cj.cleanup_scope','alice',true),set_config('cj.cleanup_purpose','account',true)")
        assert cur.execute("SELECT scope FROM cj_feedback_action WHERE scope='bob'").fetchall()==[]
        assert cur.execute("DELETE FROM cj_feedback_action WHERE scope='bob' RETURNING scope").fetchall()==[]
    with psycopg.connect(**dict(config,user='cj_m1_runtime')) as conn:
        for sql in ('DELETE FROM cj_message_receipt','TRUNCATE cj_message_receipt','SET ROLE cj_local_cleanup'):
            try:conn.execute(sql)
            except psycopg.Error:conn.rollback()
            else:raise AssertionError('runtime acquired destructive privilege')
    for foreign_id in ('op1','absent'):
        try:Store(connect,digest(b'other principal'),lambda stage:None).query(foreign_id)
        except Denied as error:assert str(error)=='operation unavailable'
        else:raise AssertionError('foreign progress visible')
    print('PASS forced RLS owner negatives, runtime DELETE/TRUNCATE/SET ROLE rejected, foreign and absent progress indistinguishable')

    # Registry bytes changing in either direction latch blocked; no actual hook call.
    changed=json.loads(raw);changed['stores'][0]['objects'].append(dict(id='new',cleanup_hook='UNIMPLEMENTED'))
    current[0]=freeze(encode(changed),inventory)
    assert host.query('op1')['status']=='blocked'
    current[0]=freeze(raw,inventory)
    assert host.query('op1')['status']=='blocked'
    bad=freeze(encode(changed),('business/feedback','business/new'))
    store.create('gap',digest(b'gap'),bad,'account',(target,),plan)
    assert store.query('gap')['status']=='blocked'
    try:host.advance(request)
    except Denied:pass
    else:raise AssertionError('blocked operation dispatched')
    print('PASS real PG registry added/missing-hook and changed-byte gaps latch blocked without widening/omitting original targets')

    # Restart after durable intent never claims completion. Original actual result recovers.
    host.create('interrupted',digest(b'confirm2'),'account',plan)
    second=host.request('interrupted',target,'alice',Selection('account'))
    assert store.intent(second)
    reopened=Store(connect,subject,lambda stage:None)
    reopened.recover('interrupted')
    assert reopened.query('interrupted')['status']=='unknown'
    assert not store.intent(second) and len(calls)==1
    try:Probe().execute(second)
    except Denied:pass
    else:raise AssertionError('lost writer was redispatched after UNKNOWN')
    assert reopened.query('interrupted')['status']=='unknown'
    assert len(calls)==1
    # A different original call commits its owner result before import is lost.
    host.create('result-import-lost',digest(b'confirmed-original-result'),'account',plan)
    committed=host.request('result-import-lost',target,'alice',Selection('account'))
    assert store.intent(committed)
    Probe().execute(committed)
    assert reopened.query('result-import-lost')['status']=='in_progress'
    reopened.recover('result-import-lost')
    assert reopened.query('result-import-lost')['status']=='complete'
    assert len(calls)==2
    # The newly provided metadata store ships its own erasure in this same slice.
    legacy=b'synthetic original principal'
    metadata='business/cleanup-metadata'
    raw2=encode(dict(version='fixture2',stores=[dict(id='business',objects=[
        dict(id='feedback',cleanup_protocol='CLEANUP@1.0'),
        dict(id='cleanup-metadata',cleanup_protocol='CLEANUP@1.0')])]))
    current[0]=freeze(raw2,(target,metadata))
    meta=MetadataHook(store,legacy)
    host2=Coordinator(store,lambda:current[0],{target:Probe(),metadata:meta})
    plan2={**plan,metadata:{'domain_scope':subject,'selection':{'kind':'account'}}}
    host2.create('metadata-erasure',digest(b'confirm3'),'account',plan2)
    other_subject=digest(b'other principal')
    other_store=Store(connect,other_subject,lambda stage:None)
    other_plan={target:{'domain_scope':'bob','selection':{'kind':'account'}},metadata:{'domain_scope':other_subject,'selection':{'kind':'account'}}}
    other_store.create('other-op',digest(b'other-confirm'),current[0],'account',(target,metadata),other_plan)
    with psycopg.connect(**config) as conn:
        conn.execute('INSERT INTO cj_cleanup_journal_candidate VALUES(%s,%s,0,%s,%s)',(legacy,'old-op',b'private old journal',b'private old state'))
    host2.advance(host2.request('metadata-erasure',target,'alice',Selection('account')))
    meta_request=host2.request('metadata-erasure',metadata,subject,Selection('account'))
    store.intent(meta_request)
    meta.execute(meta_request)  # original hook finishes; coordinator import is interrupted
    reopened.recover('metadata-erasure')
    assert reopened.query('metadata-erasure')['status']=='complete'
    assert host2.advance(meta_request)['status']=='complete'
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT count(*) FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s',(legacy,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_cleanup_operation WHERE subject_digest=%s AND plan_bytes IS NOT NULL',(subject,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_cleanup_step WHERE subject_digest=%s AND request_bytes IS NOT NULL',(subject,)).fetchone()[0]==0
        assert conn.execute('SELECT plan_bytes IS NOT NULL FROM cj_cleanup_operation WHERE subject_digest=%s',(other_subject,)).fetchone()==(True,)
    print('PASS own metadata hook physically erases legacy private journal, clears selection/request bytes, retains bounded original progress/result; interruption recovers actual receipt')
    # Mixed target protocols are explicit; C's legal long ID survives PG intent/recovery.
    unicode_target='business/memory'
    unicode_registry=encode(dict(version='fixture3',stores=[dict(id='business',objects=[
        dict(id='memory',cleanup_protocol=v11.VERSION),dict(id='unrelated',cleanup_hook='UNIMPLEMENTED')])]))
    unicode_manifest=freeze(unicode_registry,(unicode_target,'business/unrelated'),versions=('CLEANUP@1.0',v11.VERSION))
    item='北京🙂'*1000
    selection=v11.Selection('memory',item,2,3)
    unicode_plan={unicode_target:{'domain_scope':'alice','selection':selection.to_dict()}}
    store.create('unicode-memory',digest(b'confirm-unicode'),unicode_manifest,'memory',(unicode_target,),unicode_plan)
    assert store.query('unicode-memory')['status']=='in_progress'
    assert [s['target'] for s in store.query('unicode-memory')['steps']]==[unicode_target]
    store.create('account-needs-all',digest(b'account-confirm'),unicode_manifest,'account',(unicode_target,),unicode_plan)
    assert store.query('account-needs-all')['status']=='blocked'
    unicode_host=Coordinator(store,lambda:unicode_manifest,{unicode_target:object()})
    unicode_request=unicode_host.request('unicode-memory',unicode_target,'alice',selection)
    assert unicode_request.protocol==v11.VERSION and unicode_request.selection.item_id==item
    assert store.intent(unicode_request)
    try:store.receipt(unicode_request,make_receipt(unicode_request,'confirmed'))
    except Exception as error:
        from cj_cleanup.core import Invalid
        assert isinstance(error,Invalid)
    else:raise AssertionError('downgraded receipt accepted')
    reopened.recover('unicode-memory')
    assert reopened.query('unicode-memory')['status']=='unknown'
    assert not store.intent(unicode_request)
    print('PASS explicit 1.1 codec, exact Unicode MEMORY selection persisted/recovered, 1.0 receipt downgrade refused; no C hook executed')
    # Public read-only seam: C can authorize a new hook body without private loaders.
    seam_manifest=freeze(raw,inventory)
    seam_host=Coordinator(store,lambda:seam_manifest,{target:Probe()})
    seam_host.create('intent-seam',digest(b'intent-seam'),'account',plan)
    seam_request=seam_host.request('intent-seam',target,'alice',Selection('account'))
    def check(request):
        with store.transaction('intent-seam',writing=False) as cur:
            require_intent(cur,request)
    try:check(seam_request)
    except Denied:pass
    else:raise AssertionError('require_intent created a missing intent')
    assert store.intent(seam_request)
    before=store.query('intent-seam')
    check(seam_request)
    assert store.query('intent-seam')==before
    wrong=seam_host.request('intent-seam',target,'bob',Selection('account'))
    try:check(wrong)
    except Denied:pass
    else:raise AssertionError('different selection authorized')
    for field,value in (('invocation_id','other-call'),('target','business/missing'),('registry_digest','4'*64),('entry_digest','5'*64)):
        wire=json.loads(seam_request.original_utf8);wire[field]=value
        try:check(v1.HookRequest.from_bytes(encode(wire)))
        except Denied:pass
        else:raise AssertionError('different original binding authorized: '+field)
    wire=json.loads(seam_request.original_utf8);wire['protocol']=v11.VERSION
    try:check(v11.HookRequest.from_bytes(encode(wire)))
    except Denied:pass
    else:raise AssertionError('different protocol authorized')
    try:check(v1.HookRequest.from_bytes(seam_request.original_utf8+b' '))
    except Denied:pass
    else:raise AssertionError('different original bytes authorized')
    reopened.recover('intent-seam')
    try:check(seam_request)
    except Denied:pass
    else:raise AssertionError('UNKNOWN granted new execution')
    seam_host.create('intent-blocked',digest(b'intent-blocked'),'account',plan)
    blocked_request=seam_host.request('intent-blocked',target,'alice',Selection('account'))
    store.intent(blocked_request)
    store.audit('intent-blocked',bad)
    try:
        with store.transaction('intent-blocked',writing=False) as cur:require_intent(cur,blocked_request)
    except Denied:pass
    else:raise AssertionError('blocked frozen plan authorized')
    print('PASS public require_intent is read-only: persisted exact bytes/invocation/selection/version required, no implicit intent, wrong scope/UNKNOWN/blocked denied')
    try:
        with psycopg.connect(**config,autocommit=True) as conn:migrate.down(conn,migrate.load(),31)
    except psycopg.Error:pass
    else:raise AssertionError('down dropped retained operation')
    print('PASS lost-writer original-operation recovery, no silent completion/retry, actual atomic result recovered, populated down refused')


if __name__=='__main__':main()
