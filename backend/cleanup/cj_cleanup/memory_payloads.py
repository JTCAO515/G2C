"""B-MEMORY-PAYLOAD@1: exact copied payload erasure, original chat/fees stay."""
from dataclasses import replace
import json
from .core import Denied,digest
from .store import require_intent,original_result,record_result,receipt_for
from .memory_barrier import require_lease,hold_payloads
from .memory_payload_plan import read_plan
from cj_run.payload_evidence import owner_digest,key_digest
from cj_run.background import BackgroundJobsV2
from cj_run.background_v3 import BackgroundJobsV3
from cj_memory_withdrawal.association_codec import parse_original
from cj_memory_withdrawal.erasure_evidence import parse_original as parse_evidence,compare_prepared
from cj_memory_jobs.consent import EnqueueCommand
from cj_memory_jobs.ending import EndingCommand
from cj_memory_jobs.decision_command import DecisionCommand

TARGETS=('business/message','checkpoints/run','business/usage')


def _proof(cursor,scope,kind,key):
    cursor.execute('SELECT payload_sha256,c_enqueue_sha256,outcome FROM cj_run_payload_erasure WHERE owner_digest=%s AND kind=%s AND object_digest=%s',
                   (owner_digest(scope),kind,key))
    return cursor.fetchone()


def _record(cursor,scope,kind,key,payload_sha=None,c_sha=None,outcome='erased'):
    cursor.execute('INSERT INTO cj_run_payload_erasure(owner_digest,kind,object_digest,payload_sha256,c_enqueue_sha256,outcome) '
        'VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(owner_digest(scope),kind,key,payload_sha,c_sha,outcome))
    if _proof(cursor,scope,kind,key)!=(payload_sha,c_sha,outcome):raise Denied('original payload proof conflict')


class PayloadHook:
    def __init__(self,store,scope,reader,target):self.store,self.scope,self.reader,self.target=store,scope,reader,target

    def _bound(self,request):
        if (request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.scope or request.target!=self.target
            or request.protocol!='CLEANUP@1.1' or request.selection.kind!='memory'):
            raise Denied('original memory payload binding unavailable')

    def execute(self,request):
        self._bound(request)
        with self.store.transaction(request.operation_id) as cursor:
            old=original_result(cursor,request)
            if old is not None:return old
            require_intent(cursor,request)
            raw=self.reader.read_original(request)
            association=parse_original(raw,request,self.scope)
            lease=require_lease(request,self.scope,raw)
            cursor.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','memory',true),"
                "set_config('cj.cleanup_target',%s,true),set_config('cj.cleanup_invocation',%s,true)",
                (self.scope,self.target,request.invocation_id))
            if lease.plan is None:lease.plan=read_plan(cursor,self.scope,association)
            plan=lease.plan
            if self.target=='business/message':self._message(cursor,plan)
            elif self.target=='checkpoints/run':self._run(cursor,request,raw,association,plan)
            else:self._usage(cursor,request)
            result=record_result(cursor,request,'confirmed')
        return result

    def reconcile(self,request):
        self._bound(request)
        with self.store.transaction(request.operation_id,writing=False) as cursor:result=original_result(cursor,request)
        return result if result is not None else receipt_for(request,'unknown')

    def _stopped(self,cursor,plan):
        by_run={message.run_id:message for message in plan.messages.values()}
        for rid in plan.related:
            _record(cursor,self.scope,'run',key_digest('run',rid),by_run[rid].input_sha256,outcome='stopped')

    def _message(self,cursor,plan):
        self._stopped(cursor,plan)
        for reference in plan.references:
            message=reference.message
            key=key_digest('reference',reference.table,message.message_id,message.run_id,message.input_sha256)
            if reference.payload is None:
                if message.command.trip_context is not None:
                    proof=_proof(cursor,self.scope,'reference',key)
                    if proof is None or proof[2]!='erased':raise Denied('prior copied source erasure unproven')
                continue
            _record(cursor,self.scope,'reference',key,reference.payload_sha256)
            cursor.execute(f'UPDATE {reference.table} SET source_content=NULL,content_sha256=NULL WHERE scope=%s AND message_id=%s AND input_sha256=%s',
                           (self.scope,message.message_id,message.input_sha256))
            cursor.execute(f'SELECT source_content,content_sha256 FROM {reference.table} WHERE scope=%s AND message_id=%s',(self.scope,message.message_id))
            if cursor.fetchone()!=(None,None):raise Denied('copied source payload erasure unconfirmed')
        for message in plan.messages.values():
            if message.run_id in plan.related:
                cursor.execute('UPDATE cj_message_delivery SET acknowledged=true WHERE scope=%s AND message_id=%s AND run_id=%s',
                               (self.scope,message.message_id,message.run_id))

    def _run(self,cursor,request,association_raw,association,plan):
        self._stopped(cursor,plan)
        for entry in plan.inputs:
            key=key_digest('input',entry.table,entry.run_id,entry.key)
            if entry.erased:
                if _proof(cursor,self.scope,'input',key)!=(entry.input_sha256,None,'erased'):
                    raise Denied('prior original input erasure unproven')
                continue
            _record(cursor,self.scope,'input',key,entry.input_sha256)
            key_col='step_key' if entry.table=='cj_run_step_usage' else 'operation_key'
            input_col='input_bytes';command_col='command_bytes'
            if entry.table=='cj_run_record':
                where='';values=(self.scope,entry.run_id,entry.command_bytes)
                input_col='usage_input_bytes';command_col='usage_command_bytes'
            else:where=f' AND {key_col}=%s';values=(self.scope,entry.run_id,entry.command_bytes,entry.key)
            cursor.execute(f'UPDATE {entry.table} SET {input_col}=NULL WHERE scope=%s AND run_id=%s AND {command_col}=%s'+where,values)
            cursor.execute(f'SELECT {input_col} FROM {entry.table} WHERE scope=%s AND run_id=%s AND {command_col}=%s'+where,values)
            if cursor.fetchone()!=(None,):raise Denied('original input payload erasure unconfirmed')
        evidence=parse_evidence(self.reader.read_evidence(request),association,digest(association_raw))
        for job in evidence['jobs']:self._job(cursor,job,plan.background.get((job['job_id'],job['attempt_id'])))

    def _job(self,cursor,job,record):
        jid,attempt,c_sha=job['job_id'],job['attempt_id'],job['original_input_sha256']
        key=key_digest('job',jid,attempt);old=_proof(cursor,self.scope,'job',key)
        if job['state']=='erased':
            if old is None or old[1]!=c_sha or old[2] not in ('erased','empty'):
                raise Denied('earlier shared job lacks original B erasure proof')
            if record is not None and record.input_bytes is not None:raise Denied('erased shared job payload reappeared')
            return
        if record is None:
            _record(cursor,self.scope,'job',key,c_sha=c_sha,outcome='empty');return
        if record.request is None:
            if old!=(record.command.input_digest,c_sha,'erased'):raise Denied('original erased job header differs')
            return
        original=job['original_utf8'].encode('utf-8');version=json.loads(original)['version']
        if version=='MEMORY-DECISION-JOBS@1':
            command=DecisionCommand.parse(original);query=command.reader_query
        elif version=='MEMORY-END-JOBS@1':
            command=EndingCommand.parse(original);query=replace(command.query,mode='incremental')
        elif version=='MEMORY-JOBS@1':command=EnqueueCommand.parse(original);query=command.query
        else:raise Denied('explicit original C enqueue version required')
        if (command.job_id,command.attempt_id,query)!=(record.job_id,record.attempt_id,record.request.query):
            raise Denied('original C job/source differs from B original')
        if compare_prepared(job,record.request.prepared_input)!=record.prepared_input_sha256:
            raise Denied('observed original B prepared hash differs')
        decision=job['source_comparison']['decision']
        if (None if decision is None else decision['source_sha256'])!=record.decision_source_sha256:
            raise Denied('original accepted decision digest differs')
        publication=job['publication_utf8']
        if publication is not None:
            raw=publication.encode('utf-8')
            result=(BackgroundJobsV3._publication(None,raw,record) if decision is not None else BackgroundJobsV2._publication(None,raw,record))
            value=json.loads(raw)
            if (value['enqueue_input_sha256']!=c_sha or result!=job['publication_sha256'] or
                record.receipt_sha256 is not None and result!=record.receipt_sha256):
                raise Denied('original publication proof differs')
        elif record.receipt_sha256 is not None:raise Denied('original publication proof absent')
        _record(cursor,self.scope,'job',key,record.command.input_digest,c_sha)
        cursor.execute('UPDATE cj_run_background_job SET input_bytes=NULL WHERE scope=%s AND job_id=%s AND attempt_id=%s',
                       (self.scope,jid,attempt))
        if cursor.execute('SELECT input_bytes FROM cj_run_background_job WHERE scope=%s AND job_id=%s AND attempt_id=%s',
                          (self.scope,jid,attempt)).fetchone()!=(None,):raise Denied('original job copy erasure unconfirmed')

    def _usage(self,cursor,request):
        # Ledger data contains original command hashes/cost/UNKNOWN, not model
        # bytes. No accounting write, release, settlement or zero-cost inference.
        cursor.execute("SELECT s.request_digest,r.receipt_bytes FROM cj_cleanup_step s JOIN cj_cleanup_domain_result r ON "
            "(r.subject_digest,r.operation_id,r.invocation_id)=(s.subject_digest,s.operation_id,s.invocation_id) "
            "WHERE s.subject_digest=%s AND s.operation_id=%s AND s.target='checkpoints/run' AND s.state='confirmed'",
            (request.subject_digest,request.operation_id))
        row=cursor.fetchone()
        if row is None:raise Denied('original B payload result unconfirmed')
        from .hooks_v1_1 import HookReceipt
        if HookReceipt.from_digest(bytes(row[1]),row[0]).outcome!='confirmed':raise Denied('original B payload result unavailable')


def hooks(store,scope,reader):
    return {target:PayloadHook(store,scope,reader,target) for target in TARGETS}
