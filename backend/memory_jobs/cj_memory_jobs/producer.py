"""Bounded incremental intake for the original worker's explicit background host.

Only C's consent/queue/cursor tables and public MESSAGE head/source APIs are used.
The injected submit function owns the B JobRequest/unique Meter composition.
"""
from dataclasses import asdict
from hashlib import sha256
import base64,json

from cj_message.domain import Cursor
from cj_message.source import SourceQuery
from cj_auth.interfaces import AdmissionStatus
from .codec import SourceV2,Unavailable
from .postgres import Transaction,encode,stream_key
from .model_v2 import NoEligibleSource


class IncrementalProducer:
    def __init__(self,collection,submit,*,max_payload_bytes,max_conversations):
        if submit is None or type(max_conversations) is not int or not 1<=max_conversations<=100:
            raise ValueError('explicit bounded producer composition required')
        if type(max_payload_bytes) is not int or not 1<=max_payload_bytes<=262144:
            raise ValueError('explicit bounded model source required')
        self.collection,self.submit=collection,submit
        self.max_payload_bytes,self.max_conversations=max_payload_bytes,max_conversations

    def _plan(self,token):
        c=self.collection
        def read(context):
            repository,_,guard=c._binding(context,token)
            # No MEMORY holder spans a public MESSAGE call.
            with repository.transaction() as memory:
                tx=Transaction(memory)
                tx.cur.execute('SELECT active FROM cj_memory_scope WHERE scope=%s',(tx.scope,))
                scope_state=tx.cur.fetchone()
                tx.cur.execute('SELECT erased FROM cj_memory_history_fence WHERE scope_digest=%s',(tx.scope_digest,))
                fence=tx.cur.fetchone()
                tx.cur.execute('''SELECT conversation_id,generation,message_epoch,source_version,withdrawal_epoch
                    FROM cj_memory_history_consent WHERE scope=%s AND enabled ORDER BY conversation_id LIMIT %s''',
                    (tx.scope,self.max_conversations+1))
                consents=tx.cur.fetchall()
                if not consents and fence is None:
                    if scope_state not in (None,(True,)):raise Unavailable('history scope unavailable')
                    guard('incremental_default_off')
                    return encode([])
                tx.require_live()
                if len(consents)>self.max_conversations:raise Unavailable('enabled source inventory exceeds bound')
            plans=[]
            for chat,generation,epoch,version,withdrawal in consents:
                head=context.send_status(chat).head
                if head is None:raise Unavailable('enabled conversation unavailable')
                if (head.generation,head.epoch)!=(generation,epoch) or head.last_sequence==0:continue
                source=SourceV2(Cursor(context.scope,chat,generation,epoch,head.last_sequence,0),version,withdrawal)
                key=stream_key(source,'incremental')
                with repository.transaction() as memory:
                    tx=Transaction(memory);tx.require_live()
                    tx.cur.execute('SELECT processed FROM cj_memory_history_cursor WHERE scope=%s AND stream_key=%s',(tx.scope,key))
                    row=tx.cur.fetchone();after=0 if row is None else row[0]
                    tx.cur.execute('''SELECT job_id,attempt_id,state FROM cj_memory_history_job WHERE scope=%s AND stream_key=%s
                        AND state IN ('pending','inflight','unknown','cancelled','failed') ORDER BY job_id LIMIT 1''',(tx.scope,key))
                    # Reconciliation belongs to the original action. A failed,
                    # cancelled or uncertain interval cannot mint a replacement.
                    unresolved=tx.cur.fetchone()
                    if unresolved is not None:
                        if unresolved[2]=='pending':
                            row=tx.job(unresolved[0],unresolved[1])
                            plans.append(base64.b64encode(row[1]).decode('ascii'))
                        continue
                    if after>=head.last_sequence:continue
                    query=SourceQuery(chat,generation,epoch,after,min(after+100,head.last_sequence),version,withdrawal)
                    identity=sha256(encode(dict(scope_digest=sha256(context.scope.encode()).hexdigest(),source=asdict(query)))).hexdigest()
                    command=dict(version='MEMORY-JOBS@1',job_id='incremental-v1:'+identity,
                        attempt_id='incremental-attempt-v1:'+identity,source=asdict(query))
                    plans.append(base64.b64encode(encode(command)).decode('ascii'))
                    guard('incremental_plan')
            return encode(plans)
        return json.loads(c.boundary.with_history_context(token,read))

    def poll(self,token):
        results=[];c=self.collection
        from .consent import EnqueueCommand
        for original in self._plan(token):
            raw=base64.b64decode(original,validate=True)
            plan=EnqueueCommand.parse(raw);jid,attempt=plan.job_id,plan.attempt_id
            c.enqueue(token,raw)
            c.transition(token,jid,attempt,'inflight')
            prepared=c.prepare_model_input_v2(token,jid,attempt,max_payload_bytes=self.max_payload_bytes)
            try:
                result=self.submit(token,jid,attempt,plan.query,prepared)
            except NoEligibleSource:
                # A first-submit source denial is not a provider result or proof
                # about any other original unknown attempt's financial state.
                c.transition(token,jid,attempt,'cancelled')
                raise
            results.append(result)
        return tuple(results)


class ProducerHost:
    def __init__(self,producer,tokens_for_run,background):
        self.producer,self.tokens_for_run,self.background=producer,tokens_for_run,background

    def run_once(self,provider):
        for token in self.tokens_for_run():
            # Like B's local host, a definitively retired/revoked roster member
            # cannot prevent another admitted owner's background pass. UNKNOWN
            # still reaches the canonical boundary and is never defaulted off.
            admission=self.producer.collection.boundary.checker.check(token)
            if admission.status is AdmissionStatus.DENIED:continue
            self.producer.poll(token)
        return self.background.run_once(provider)
