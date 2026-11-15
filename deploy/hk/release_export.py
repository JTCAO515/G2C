"""Read only the leased national messages and original evidence; never dispatch."""
import base64,hashlib,json,os,sqlite3,stat
from dataclasses import asdict
from types import SimpleNamespace
from cj_memory_jobs.lio_batch import job_ids
from cj_agent.draft import trip_scope_for
from cj_message.needs_binding import needs_scope_for
from cj_message.lio_plan_needs import lio_needs_id
from datetime import datetime,timezone
from pathlib import Path
from deploy.hk import checkpoint
from deploy.hk.configuration import load_secret_environment
from cj_api.local_app import ISSUER,scope_for
from cj_usage.codec import decode_stored
from m4_budget_transfer import attempts

def b64(value):return None if value is None else base64.b64encode(bytes(value)).decode('ascii')

def collect(plan,control,evidence,budget):
 subjects={x['locale']:x['subject'] for x in plan['identities']}
 observations=[]; attempt_ids=set()
 with checkpoint.operator() as (db,_),db.transaction():
  db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
  db.execute("SET LOCAL statement_timeout='8s'")
  checkpoint.require_release(db,control)
  pending,active=db.execute("SELECT (SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged),(SELECT count(*) FROM cj_run_record WHERE status IN ('queued','running'))").fetchone()
  background_states=dict(db.execute('SELECT state,count(*) FROM cj_run_background_job GROUP BY state').fetchall())
  memory_states=dict(db.execute('SELECT state,count(*) FROM cj_memory_history_job GROUP BY state').fetchall())
  for case in plan['cases']:
   scope=scope_for(ISSUER,subjects[case['locale']])
   row=db.execute('SELECT conversation_id,generation,sequence,run_id,input_sha256,raw_input,demo_dialogue_input_sha256,demo_question_day,demo_dialogue_locale FROM cj_message_receipt WHERE scope=%s AND message_id=%s',(scope,case['message_id'])).fetchone()
   item=dict(case,scope_sha256=hashlib.sha256(scope.encode()).hexdigest(),message_record=None)
   if row is not None:
    cid,generation,sequence,rid,canonical_sha,raw,wire_sha,question_day,locale=row
    state=db.execute('SELECT status FROM cj_run_record WHERE scope=%s AND run_id=%s',(scope,rid)).fetchone()
    status=None if state is None else state[0]
    events=db.execute('SELECT sequence,kind,value FROM cj_run_event WHERE scope=%s AND run_id=%s ORDER BY sequence',(scope,rid)).fetchall()
    operations=db.execute('SELECT operation_key,registration_id,kind,attempt_id,operation_id,ledger_scope,command_bytes,input_bytes FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key',(scope,rid)).fetchall()
    ledgers={}
    for account in {r[5] for r in operations}:
     version,original=db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
     ledgers[account]=decode_stored(version,original)
    ops=[]
    for key,registration,kind,attempt,operation,account,command,inputs in operations:
     meter=ledgers[account].attempts.get(attempt)
     ops.append(dict(operation_key=key,registration_id=registration,kind=kind,attempt_id=attempt,operation_id=operation,command_utf8=bytes(command).decode(),input_utf8_base64=b64(inputs),input_sha256=None if inputs is None else hashlib.sha256(bytes(inputs)).hexdigest(),meter=None if meter is None else asdict(meter)))
     attempt_ids.add(attempt)
    msg_needs=db.execute('SELECT needs_id,needs_version,content_sha256 FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s AND run_id=%s',(scope,case['message_id'],rid)).fetchall()
    needs=[]
    for needs_id,version,digest in msg_needs:
     content=db.execute('SELECT content FROM cj_needs_revision WHERE scope=%s AND needs_id=%s AND version=%s',(needs_scope_for(scope),needs_id,version)).fetchone()
     # A newer canonical NEEDS row does not replace the immutable captured source.
     needs.append(dict(needs_id=needs_id,version=version,content_sha256=digest,revision_utf8_base64=None if content is None else b64(content[0])))
    current=db.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current WHERE scope=%s AND needs_scope=%s AND needs_id=%s',
        (trip_scope_for(scope),needs_scope_for(scope),lio_needs_id(scope,cid))).fetchone()
    trip=None
    if current is not None:
     tid,version=current
     record=db.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(trip_scope_for(scope),tid)).fetchone()
     assert record is not None and record[0]==version
     revisions=db.execute("SELECT r.committed_version,r.action_id,r.kind,r.original_input,p.content,p.basis_version,b.message_scope,b.run_id,b.source_input,b.source_sha256,b.proposed_input,b.needs_id,b.needs_version FROM cj_trip_receipt r JOIN cj_trip_proposal p ON (p.scope,p.proposal_id)=(r.scope,r.proposal_id) JOIN cj_trip_needs_basis b ON (b.scope,b.proposal_id)=(r.scope,r.proposal_id) WHERE r.scope=%s AND r.trip_id=%s AND r.kind='accept' ORDER BY r.committed_version",(trip_scope_for(scope),tid)).fetchall()
     history=[]
     for v,aid,kind,original,content,basis,origin_scope,origin_run,source,digest,proposed,nid,nversion in revisions:
      assert origin_scope==scope and hashlib.sha256(bytes(source)).hexdigest()==digest
      history.append(dict(version=v,action_id=aid,kind=kind,original_action_utf8_base64=b64(original),
          content_utf8_base64=b64(content),content_sha256=hashlib.sha256(bytes(content)).hexdigest(),basis_version=basis,
          origin_run_id=origin_run,source_utf8_base64=b64(source),source_sha256=digest,proposed_utf8_base64=b64(proposed),needs_id=nid,needs_version=nversion))
     trip=dict(trip_id=tid,current_version=version,current_content_utf8_base64=b64(record[1]),current_content_sha256=hashlib.sha256(bytes(record[1])).hexdigest(),revisions=history)
    record=SimpleNamespace(receipt=SimpleNamespace(conversation_id=cid,generation=generation,message_id=case['message_id'],run_id=rid))
    job,attempt=job_ids(scope,record)
    jobs=db.execute('SELECT job_id,attempt_id,state,original_input,batch,candidate,result_bytes FROM cj_memory_history_job WHERE scope=%s AND job_id=%s AND attempt_id=%s',(scope,job,attempt)).fetchall()
    memory_jobs=[dict(job_id=j,attempt_id=a,state=st,original_utf8_base64=b64(o),batch_utf8_base64=b64(ba),candidate_utf8_base64=b64(c),result_utf8_base64=b64(r)) for j,a,st,o,ba,c,r in jobs]
    item['message_record']=dict(conversation_id=cid,generation=generation,sequence=sequence,run_id=rid,status=status,canonical_input_sha256=canonical_sha,question_day=None if question_day is None else question_day.isoformat(),locale=locale,canonical_input_utf8_base64=b64(raw),lio_wire_input_sha256=wire_sha,events=[dict(sequence=s,kind=k,value=v) for s,k,v in events],operations=ops,needs=needs,trip=trip,memory_jobs=memory_jobs)
   observations.append(item)
 with sqlite3.connect('file:'+str(budget)+'?mode=ro',uri=True) as journal:
  journal.execute('BEGIN')
  count,anchor=attempts(journal)
  shared={}
  for attempt in sorted(attempt_ids):
   row=journal.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',(attempt,)).fetchone()
   shared[attempt]=None if row is None else dict(kind=row[0],actual_wire_input_sha256=row[1],state=row[2],receipt=None if row[3] is None else json.loads(row[3]))
 artifacts=[]
 allowed={x['message_id'] for x in plan['cases']}
 for file in sorted(evidence.glob('*.json')):
  metadata=file.lstat()
  assert stat.S_ISREG(metadata.st_mode) and stat.S_IMODE(metadata.st_mode)==0o600 and metadata.st_uid==10001
  raw=file.read_bytes();assert len(raw)<=1048576
  try:value=json.loads(raw)
  except ValueError:continue # A concurrently open writer is not yet a complete artifact.
  assert value['message_id'] in allowed and value['source_commit']==plan['source_commit']
  parts=[next(scope_for(ISSUER,s) for s in subjects.values() if hashlib.sha256(scope_for(ISSUER,s).encode()).hexdigest()==value['scope_sha256']),value['run_id'],value['operation_key'],value['attempt_id']]
  if value.get('version')=='G2C-model-wire-input.1':
   assert value.get('capture_kind')=='model_wire_input'
   parts.append('model_wire_input')
  else:assert value.get('capture_kind')!='model_wire_input'
  assert file.name==hashlib.sha256(json.dumps(parts,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()+'.json'
  artifacts.append(dict(name=file.name,sha256=hashlib.sha256(raw).hexdigest(),utf8_base64=base64.b64encode(raw).decode()))
 return dict(version='G2C-national-readonly-proof.1',exporter_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),window_id=plan['window_id'],source_commit=plan['source_commit'],observed_at=datetime.now(timezone.utc).isoformat(),global_pending=pending,global_active=active,background_states=background_states,memory_states=memory_states,ledger=dict(count=count,sha256=anchor),observations=observations,shared_outflows=shared,artifacts=artifacts)


def main():
 load_secret_environment('migrate')
 plan=json.loads(Path('/plan.json').read_bytes())
 value=collect(plan,Path('/control'),Path('/evidence'),Path('/budget/m4-outflows.sqlite'))
 print(json.dumps(value,ensure_ascii=False))

if __name__=='__main__':main()
