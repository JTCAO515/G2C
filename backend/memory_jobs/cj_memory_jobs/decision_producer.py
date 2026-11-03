"""Explicit automatic accepted-decision intake over existing C/B source seams."""
from dataclasses import asdict,dataclass,replace
from hashlib import sha256
import base64,json

from cj_message.domain import Command
from cj_message.source import SourceQuery
from cj_trip.decision_source import DecisionQuery
from .codec import Unavailable
from .consent import EnqueueCommand
from .ending import EndingCommand
from .decision_command import DecisionCommand,VERSION as DECISION_VERSION
from .producer import IncrementalProducer,EndingProducer
from .source_policy import SourcePolicy
from .postgres import Transaction,encode


@dataclass(frozen=True)
class ProducerPass:
    submitted:tuple
    unavailable:tuple


class _DecisionPlanning:
    """Same one-original account gate; never translate an existing command."""
    def _inventory(self,context,token):
        repo,guard,consents,originals=super()._inventory(context,token)
        if not originals:return repo,guard,consents,originals
        invalid=self.collection._invalid_originals(context,token,context.principal,repo)
        blocked={row[3].cursor.conversation_id for row in originals if row[0].job_id in invalid}
        self.unavailable=tuple(sorted(blocked))
        return repo,guard,[c for c in consents if c[0] not in blocked],tuple(r for r in originals if r[0].job_id not in invalid)

    def _decision_resume(self,token,purpose):
        def read(context):
            _,guard,_,originals=self._inventory(context,token)
            if not any(json.loads(row[1])['version']==DECISION_VERSION for row in originals):return b'null'
            pending=self._resume(context,originals,purpose)
            guard('automatic_original_decision')
            return encode(pending)
        return json.loads(self.collection.boundary.with_history_context(token,read))

    def _promote(self,token,plans):
        if not plans:return plans
        raw=base64.b64decode(plans[0],validate=True);value=json.loads(raw)
        if value['version']==DECISION_VERSION:return plans
        plan=EnqueueCommand.parse(raw) if value['version']=='MEMORY-JOBS@1' else EndingCommand.parse(raw)
        query=plan.query;reader=query if query.mode=='incremental' else replace(query,mode='incremental')
        c=self.collection
        def inspect(context):
            repo,principal,guard=c._binding(context,token)
            with repo.transaction() as memory:
                tx=Transaction(memory);tx.require_live()
                tx.cur.execute('SELECT 1 FROM cj_memory_history_job WHERE scope=%s AND job_id=%s',(tx.scope,plan.job_id))
                if tx.cur.fetchone() is not None:return raw
            def references(snapshot):
                # Only metadata leaves this source callback; no new history
                # copies, Trip reads or second MESSAGE connection under MEMORY.
                result=[]
                for message in snapshot.messages:
                    original=json.loads(message.original_utf8)
                    full=False
                    if original['version']=='MESSAGE-send.3':
                        command=Command.parse_original(message.original_utf8)
                        selected=command.trip_context
                        full=selected is not None and selected.day is None and selected.item_id is None
                    result.append(dict(decision=full,receipt=asdict(message.receipt)))
                return encode(result)
            metadata=json.loads(context.with_enabled_source(reader,SourcePolicy(repo,principal,guard),references))
            if not metadata:raise Unavailable('original automatic source interval unavailable')
            first=None;through=query.after
            for message in metadata:
                selected=None
                if message['decision']:
                    original=context.query_trip_message(message['receipt']['message_id'])
                    if original is None or asdict(original.stored.receipt)!=message['receipt']:
                        raise Unavailable('original discussion receipt differs')
                    reference=original.reference
                    selected=DecisionQuery(reference.trip_selection.id,reference.trip_selection.expected_version,reference.content_sha256)
                if through==query.after:first=selected
                elif selected!=first:break
                through=message['receipt']['sequence']
            query_segment=replace(query,through=through)
            end=None if value['version']=='MEMORY-JOBS@1' else value['end']
            if first is not None:
                authority=c.resolve_decision_authority(token)
                with authority.hold(principal,first,max_source_bytes=4_000_000) as lease:lease.check()
                identity=sha256(encode(dict(scope_digest=sha256(repo.scope.encode()).hexdigest(),
                    source=asdict(query_segment),decision=asdict(first),end=end))).hexdigest()
                result=dict(version=DECISION_VERSION,job_id='automatic-decision-v1:'+identity,
                    attempt_id='automatic-decision-attempt-v1:'+identity,source=asdict(query_segment),decision=asdict(first),end=end)
            elif through==query.through:
                return raw
            else:
                identity=sha256(encode(dict(scope_digest=sha256(repo.scope.encode()).hexdigest(),source=asdict(query_segment),end=end))).hexdigest()
                result=dict(version=value['version'],job_id='automatic-history-v2:'+identity,
                    attempt_id='automatic-history-attempt-v2:'+identity,source=asdict(query_segment))
                if end is not None:result['end']=end
            guard('automatic_source_plan');return encode(result)
        promoted=c.boundary.with_history_context(token,inspect)
        return [base64.b64encode(promoted).decode('ascii')]

    def _plan(self,token):
        self.unavailable=()
        resumed=self._decision_resume(token,self.purpose)
        if resumed is not None:return resumed
        return self._promote(token,super()._plan(token))


class _Incremental(_DecisionPlanning,IncrementalProducer):
    purpose='incremental'


class _Ending(_DecisionPlanning,EndingProducer):
    purpose='conversation_end'


class DecisionConversationProducer:
    """Legacy BG2 and explicit BG3 submitters; no parse fallback or new Meter."""
    def __init__(self,collection,submit,submit_decision,*,max_payload_bytes,max_conversations):
        if submit_decision is None:raise ValueError('explicit actual BG3 submitter required')
        self.collection,self.submit_decision=collection,submit_decision
        self.max_payload_bytes=max_payload_bytes
        args=dict(max_payload_bytes=max_payload_bytes,max_conversations=max_conversations)
        self.incremental=_Incremental(collection,submit,**args)
        self.ending=_Ending(collection,submit,**args)

    def poll(self,token):
        inc=self.incremental._plan(token);end=self.ending._plan(token)
        before=lambda values:json.loads(base64.b64decode(values[0]))['source']['after']
        owner,plans=(self.ending,end) if end and (not inc or before(end)<before(inc)) else (self.incremental,inc)
        unavailable=tuple(sorted(set(self.incremental.unavailable)|set(self.ending.unavailable)))
        if not plans:return ProducerPass((),unavailable)
        raw=base64.b64decode(plans[0],validate=True);version=json.loads(raw)['version']
        if version!=DECISION_VERSION:return ProducerPass(owner._dispatch(token,plans),unavailable)
        command=DecisionCommand.parse(raw);c=self.collection
        c.enqueue_decision_serialized(token,raw);c.begin_decision(token,command.job_id,command.attempt_id)
        prepared=c.prepare_decision_input(token,command.job_id,command.attempt_id,max_payload_bytes=self.max_payload_bytes)
        payload=json.loads(json.loads(prepared)['messages'][0]['content'])
        result=self.submit_decision(token,command.job_id,command.attempt_id,command.reader_query,
                                    payload['decision_source_sha256'],prepared)
        return ProducerPass((result,),unavailable)
