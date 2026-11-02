"""Bounded incremental intake for the original worker's explicit background host.

Only C's consent/queue/cursor tables and public MESSAGE head/source APIs are used.
The injected submit function owns the B JobRequest/unique Meter composition.
"""
from dataclasses import asdict,replace
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
            repository,guard,consents,originals=self._inventory(context,token)
            pending=self._resume(context,originals,'incremental')
            if pending is not None:
                guard('incremental_original_pending')
                return encode(pending)
            plans=[]
            for chat,generation,epoch,version,withdrawal in consents:
                head=context.send_status(chat).head
                if head is None:continue  # Explicitly missing/inactive, not a lookup failure.
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
                            plans.append((after,chat,base64.b64encode(row[1]).decode('ascii')))
                        continue
                    if after>=head.last_sequence:continue
                    query=SourceQuery(chat,generation,epoch,after,min(after+100,head.last_sequence),version,withdrawal)
                    identity=sha256(encode(dict(scope_digest=sha256(context.scope.encode()).hexdigest(),source=asdict(query)))).hexdigest()
                    command=dict(version='MEMORY-JOBS@1',job_id='incremental-v1:'+identity,
                        attempt_id='incremental-attempt-v1:'+identity,source=asdict(query))
                    plans.append((after,chat,base64.b64encode(encode(command)).decode('ascii')))
                    guard('incremental_plan')
            # Publishing one source may advance the account-wide Memory epoch.
            # The next source must be planned after that original has settled.
            return encode([min(plans)[2]] if plans else [])
        return json.loads(c.boundary.with_history_context(token,read))

    def _inventory(self,context,token):
        repository,_,guard=self.collection._binding(context,token)
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
                guard('collection_default_off')
                return repository,guard,[],()
            tx.require_live()
            if len(consents)>self.max_conversations:raise Unavailable('enabled source inventory exceeds bound')
            originals=tx.current_unresolved()
        return repository,guard,consents,originals

    def _resume(self,context,originals,purpose):
        pending=[]
        for row in originals:
            cursor=row[3].cursor
            head=context.send_status(cursor.conversation_id).head
            if head is None or (head.generation,head.epoch)!=(cursor.generation,cursor.epoch):continue
            if row[0].state in ('inflight','unknown') or row[5]!=purpose:return []
            pending.append(base64.b64encode(row[1]).decode('ascii'))
        return pending[:1] if pending else None

    def poll(self,token):
        return self._dispatch(token,self._plan(token))

    def _parse(self,raw):
        from .consent import EnqueueCommand
        return EnqueueCommand.parse(raw)

    def _enqueue(self,token,raw):return self.collection.enqueue_serialized(token,raw)

    def _reader(self,command):return command.query

    def _dispatch(self,token,originals):
        results=[];c=self.collection
        for original in originals:
            raw=base64.b64decode(original,validate=True)
            plan=self._parse(raw);jid,attempt=plan.job_id,plan.attempt_id
            self._enqueue(token,raw)
            c.transition(token,jid,attempt,'inflight')
            prepared=c.prepare_model_input_v2(token,jid,attempt,max_payload_bytes=self.max_payload_bytes)
            try:
                result=self.submit(token,jid,attempt,self._reader(plan),prepared)
            except NoEligibleSource:
                # A first-submit source denial is not a provider result or proof
                # about any other original unknown attempt's financial state.
                c.transition(token,jid,attempt,'cancelled')
                raise
            results.append(result)
        return tuple(results)


class EndingProducer(IncrementalProducer):
    """Known real ends only; no finish writer or exception-to-open fallback."""
    def _parse(self,raw):
        from .ending import EndingCommand
        return EndingCommand.parse(raw)

    def _enqueue(self,token,raw):return self.collection.enqueue_ending_serialized(token,raw)

    def _reader(self,command):return replace(command.query,mode='incremental')

    def _plan(self,token):
        def read(context):
            repository,guard,consents,originals=self._inventory(context,token)
            pending=self._resume(context,originals,'conversation_end')
            if pending is not None:
                # Old exact-head JOBS1 end tasks remain their separate explicit
                # path; they are not reinterpreted as segmented END-JOBS1.
                if pending and json.loads(base64.b64decode(pending[0]))['version']!='MEMORY-END-JOBS@1':return encode([])
                guard('ending_original_pending');return encode(pending)
            plans=[]
            for chat,generation,epoch,version,withdrawal in consents:
                status=context.source_status_v1(chat)
                head=status.cursor
                if (head.generation,head.epoch)!=(generation,epoch) or head.through==0 or status.end is None:continue
                source=SourceV2(head,version,withdrawal)
                with repository.transaction() as memory:
                    tx=Transaction(memory);tx.require_live()
                    # Incremental facts are timely; end work supplements them
                    # after their original cursor settles at this immutable head.
                    tx.cur.execute('SELECT processed FROM cj_memory_history_cursor WHERE scope=%s AND stream_key=%s',
                                   (tx.scope,stream_key(source,'incremental')))
                    incremental=tx.cur.fetchone()
                    if incremental is None or incremental[0]<head.through:continue
                    key=stream_key(source,'conversation_end')
                    tx.cur.execute('SELECT processed FROM cj_memory_history_cursor WHERE scope=%s AND stream_key=%s',(tx.scope,key))
                    row=tx.cur.fetchone();after=0 if row is None else row[0]
                    tx.cur.execute('''SELECT 1 FROM cj_memory_history_job WHERE scope=%s AND stream_key=%s
                        AND state IN ('pending','inflight','unknown','cancelled','failed') LIMIT 1''',(tx.scope,key))
                    if tx.cur.fetchone() is not None or after>=head.through:continue
                    query=SourceQuery(chat,generation,epoch,after,min(after+100,head.through),version,withdrawal,'conversation_end')
                    end=dict(conversation_id=chat,generation=generation,epoch=epoch,through=status.end.through)
                    identity=sha256(encode(dict(scope_digest=sha256(context.scope.encode()).hexdigest(),source=asdict(query),end=end))).hexdigest()
                    command=dict(version='MEMORY-END-JOBS@1',job_id='ending-v1:'+identity,attempt_id='ending-attempt-v1:'+identity,
                        source=asdict(query),end=end)
                    plans.append((after,chat,base64.b64encode(encode(command)).decode('ascii')))
                    guard('ending_plan')
            return encode([min(plans)[2]] if plans else [])
        return json.loads(self.collection.boundary.with_history_context(token,read))


class ConversationProducer:
    """One original per account basis, fair across eligible incremental/end work."""
    def __init__(self,collection,submit,*,max_payload_bytes,max_conversations):
        self.collection=collection
        args=dict(max_payload_bytes=max_payload_bytes,max_conversations=max_conversations)
        self.incremental=IncrementalProducer(collection,submit,**args)
        self.ending=EndingProducer(collection,submit,**args)

    def poll(self,token):
        incremental=self.incremental._plan(token);ending=self.ending._plan(token)
        if not ending:return self.incremental._dispatch(token,incremental)
        if not incremental:return self.ending._dispatch(token,ending)
        before=lambda value:json.loads(base64.b64decode(value[0]))['source']['after']
        if before(ending)<before(incremental):return self.ending._dispatch(token,ending)
        return self.incremental._dispatch(token,incremental)


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
