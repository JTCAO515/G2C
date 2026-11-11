"""Read original runtime facts for one logical adapter attempt; no dispatcher."""
import base64
from dataclasses import asdict
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from cj_agent.draft import trip_scope_for
from cj_message.lio_plan_needs import lio_needs_id
from cj_message.needs_binding import needs_scope_for
from cj_usage.authorization_budget import canonical,authorization_usage,journal_state
from cj_usage.codec import decode


def collect(window,attempt_id,journal_path):
 entries=window.entries(attempt_id)
 messages=[];identities=set();scope_cids={};dispatch_ids=set();roles={}
 for entry in entries:
  from .local_app import ISSUER,scope_for
  scope=scope_for(ISSUER,entry['subject']);identities.add(entry['subject'])
  with window.database.connect(scope) as db:
   db.execute('SET TRANSACTION READ ONLY')
   roles[entry['subject']]=db.execute("SELECT current_user,session_user,current_setting('transaction_read_only'),current_setting('cj.message_scope',true)").fetchone()
   row=db.execute('SELECT conversation_id,generation,sequence,run_id,input_sha256,demo_dialogue_input_sha256 FROM cj_message_receipt WHERE scope=%s AND message_id=%s',(scope,entry['message_id'])).fetchone()
   item=dict(message_id=entry['message_id'],entry=entry,status=None,run_id=None,operations=[])
   if row is not None:
    cid,generation,sequence,rid,input_sha,wire_sha=row
    if wire_sha!=entry['input_sha256']:raise ValueError('original adapter MESSAGE digest differs')
    scope_cids.setdefault(scope,set()).add(cid)
    status,=db.execute('SELECT status FROM cj_run_record WHERE scope=%s AND run_id=%s',(scope,rid)).fetchone()
    events=db.execute('SELECT sequence,kind,value FROM cj_run_event WHERE scope=%s AND run_id=%s ORDER BY sequence',(scope,rid)).fetchall()
    item.update(conversation_id=cid,generation=generation,sequence=sequence,run_id=rid,status=status,
                text=''.join(v for _,kind,v in events if kind=='text_delta'),
                events=[dict(sequence=s,kind=k,value=v) for s,k,v in events],
                canonical_input_sha256=input_sha,wire_input_sha256=wire_sha)
    operations=db.execute('SELECT operation_key,registration_id,kind,attempt_id,operation_id,ledger_scope,command_bytes,input_bytes FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key',(scope,rid)).fetchall()
    ledgers={}
    for account in {o[5] for o in operations}:
     raw,=db.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
     ledgers[account]=decode(raw)
    for key,registration,kind,identity,operation,account,command,raw in operations:
     meter=ledgers[account].attempts.get(identity);dispatch_ids.add(identity)
     item['operations'].append(dict(operation_key=key,registration_id=registration,kind=kind,
      attempt_id=identity,operation_id=operation,command_utf8=bytes(command).decode(),
      input_utf8_base64=None if raw is None else base64.b64encode(bytes(raw)).decode(),
      meter=None if meter is None else asdict(meter)))
   messages.append(item)
 states=[]
 for scope,cids in scope_cids.items():
  with window.database.connect(scope) as db:
   db.execute('SET TRANSACTION READ ONLY')
   needs=[lio_needs_id(scope,cid) for cid in sorted(cids)]
   trips=db.execute('SELECT c.needs_id,t.trip_id,t.version,t.content FROM cj_trip_needs_current c '
     'JOIN cj_trip_record t ON (t.scope,t.trip_id)=(c.scope,c.trip_id) '
     'WHERE c.scope=%s AND c.needs_scope=%s AND c.needs_id=ANY(%s)',
     (trip_scope_for(scope),needs_scope_for(scope),needs)).fetchall()
   trip_ids=[t[1] for t in trips]
   revisions=db.execute("SELECT r.trip_id,r.committed_version,r.action_id,r.proposal_id,r.original_input,p.content "
     "FROM cj_trip_receipt r JOIN cj_trip_proposal p ON (p.scope,p.proposal_id)=(r.scope,r.proposal_id) "
     "WHERE r.scope=%s AND r.kind='accept' AND r.trip_id=ANY(%s) ORDER BY r.trip_id,r.committed_version",
     (trip_scope_for(scope),trip_ids)).fetchall()
   memory=db.execute('SELECT i.item_id,i.version,i.status,i.slot,i.source_id,i.source_version,s.active,encode(sha256(i.original_input),\'hex\') FROM cj_memory_item i JOIN cj_memory_source s USING(scope,source_id) WHERE i.scope=%s ORDER BY i.item_id',(scope,)).fetchall()
   states.append(dict(scope_sha256=sha256(scope.encode()).hexdigest(),
     current_trips=[dict(needs_id=n,trip_id=t,version=v,content_utf8_base64=base64.b64encode(bytes(c)).decode()) for n,t,v,c in trips],
     trip_revisions=[dict(trip_id=t,version=v,action_id=a,proposal_id=p,original_action_utf8_base64=base64.b64encode(bytes(raw)).decode(),content_utf8_base64=base64.b64encode(bytes(c)).decode()) for t,v,a,p,raw,c in revisions],
     memory_items=[dict(item_id=i,version=v,status=s,slot=slot,source_id=src,source_version=sv,source_active=active,original_sha256=h) for i,v,s,slot,src,sv,active,h in memory]))
 with sqlite3.connect(Path(journal_path).resolve().as_uri()+'?mode=ro',uri=True) as db:
  db.execute('BEGIN');count,anchor=journal_state(db)
  outflows={}
  for identity in sorted(dispatch_ids):
   row=db.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',(identity,)).fetchone()
   outflows[identity]=None if row is None else dict(kind=row[0],input_sha256=row[1],state=row[2],receipt=None if row[3] is None else json.loads(row[3]))
  counts,estimates,holds=authorization_usage(db,attempt_ids=dispatch_ids,include_M1=False)
 tool_artifacts=[]
 for path in sorted(window.tools_directory.glob('*.json')):
  value=json.loads(path.read_bytes())
  if value['attempt_id'] in dispatch_ids:
   tool_artifacts.append(dict(sha256=sha256(path.read_bytes()).hexdigest(),original=value))
 metadata=[]
 for identity in sorted(dispatch_ids):
  path=window.metadata/(sha256(identity.encode()).hexdigest()+'.json')
  if path.exists():metadata.append(json.loads(path.read_bytes()))
 messages.sort(key=lambda m:m['message_id'])
 return dict(version='G2C-runtime-observation.1',attempt_id=attempt_id,source_commit=window.value['source_commit'],
             observed_at=datetime.now(timezone.utc).isoformat(),runtime_roles=roles,messages=messages,
             states=states,tool_originals=tool_artifacts,dispatch_metadata=metadata,authorization_attempts=outflows,
             shared_ledger=dict(count=count,sha256=anchor),purpose_usage=dict(counts=counts,estimates_scaled_1e7_cny=estimates,holds_scaled_1e7_cny=holds))
