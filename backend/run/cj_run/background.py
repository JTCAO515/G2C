"""Original background JobRun scheduling over public MESSAGE/C/Meter boundaries."""
from contextlib import ExitStack
from dataclasses import dataclass
import json,time
from cj_usage.core import Meter
from cj_usage.postgres import PostgresRepository
from cj_usage.background_exit import BackgroundExit,ModelInput
from cj_usage.metered_exit import BudgetExceeded,BudgetUnknown
from .background_store import JobStore,JobRequest,ABI,pack,sha
from .core import Denied,Conflict


class JobOutcomeUnknown(Exception):
    def __init__(self,record):
        super().__init__('query original background job; do not redispatch')
        self.job_id,self.attempt_id,self.run_id=record.job_id,record.attempt_id,record.binding.run_id
        self.commit_possible=True
        self.recovery='reconcile_original'


@dataclass(frozen=True)
class JobOutcome:
    job_id:str
    attempt_id:str
    run_id:str
    status:str
    proposal_id:None=None


class _SourceMeter:
    """Same actual Meter; each local mutation holds the current C source lease."""
    def __init__(self,meter,authorized):
        self.base,self.authorized=meter,authorized
        self.repo,self.config=meter.repo,meter.config
    def reserve(self,command):return self.authorized(lambda:self.base.reserve(command))
    def claim(self,attempt):return self.authorized(lambda:self.base.claim(attempt))
    def settle(self,receipt):return self.authorized(lambda:self.base.settle(receipt))
    def cancel(self,run_id):return self.base.cancel(run_id)


class BackgroundJobs:
    def __init__(self,*,database,boundary,collection,max_payload_bytes,clock=time.time):
        if database.run_context is None or database.run_context.version!='CJ-LOCAL-RUN@2' or collection is None:
            raise ValueError('explicit registered local budget and C processing adapter required')
        if type(max_payload_bytes) is not int or not 1<=max_payload_bytes<=1048576:raise ValueError('explicit job payload bound required')
        self.database,self.boundary,self.collection=database,boundary,collection
        self.max_payload_bytes,self.clock=max_payload_bytes,clock

    def _owned(self,token,operation):
        return self.boundary.with_history_context(token,operation)

    def _load(self,token,jid,attempt):
        holder={}
        def read(context):
            store=JobStore(self.database.run_repository(context.scope))
            record=store.read(jid,attempt)
            if record is None:raise Denied('original background job unavailable')
            holder.update(store=store,record=record)
            return b'original-read'
        self._owned(token,read)
        return holder['store'],holder['record']

    def _phase(self,token,store,request,work,*,output=None):
        holder={}
        def enter(context):
            if context.scope!=store.scope:raise Denied('background job owner changed')
            args=(context,token,request.job_id,request.attempt_id,request.prepared_input,request.prepared_sha256)
            policy=(self.collection.processing_policy(*args,max_payload_bytes=self.max_payload_bytes) if output is None else
                self.collection.publication_policy(*args,output,sha(output),max_payload_bytes=self.max_payload_bytes))
            def project(source,lease=None):
                def local(actual):
                    if actual!=request.prepared_input:raise Conflict('original prepared model bytes required')
                    holder['value']=work(policy,source,lease)
                    return b'local-job-stage'
                if output is None:return policy.with_input(source,local)
                holder['value']=work(policy,source,lease)
                return b'local-publication-stage'
            if request.travel is None:return context.with_enabled_source(request.query,policy,project)
            return context.with_enabled_source_and_travel(request.query,policy,request.travel,project)
        self._owned(token,enter)
        return holder['value']

    def prepare(self,token,request:JobRequest):
        ModelInput.parse(request.prepared_input)
        profile=self.database.run_context.current
        holder={}
        def bind(context):
            store=JobStore(self.database.run_repository(context.scope))
            old=store.read(request.job_id,request.attempt_id)
            if old is not None:store.require_original(old,request,profile.meter,profile.output_limits['memory'])
            holder.update(store=store,old=old)
            return b'job-owner'
        self._owned(token,bind)
        if holder['old'] is not None:return holder['old'].summary()
        store=holder['store']
        self.database.require_budget_account(store.scope,profile=profile)
        record=self._phase(token,store,request,lambda policy,source,lease:store.prepare(request,profile.meter,profile.output_limits['memory']))
        return record.summary()

    def query_original(self,token,jid,attempt):
        store,record=self._load(token,jid,attempt)
        return record.summary()

    def _require_stage(self,store,record,states):
        current=store.read(record.job_id,record.attempt_id)
        if (current is None or current.binding!=record.binding or current.request is None or current.state not in states):
            raise Denied('original job stage or payload unavailable')
        return current

    def _meter(self,record):
        matches=[p for p in self.database.run_context.profiles if p.meter==record.config]
        if len(matches)!=1:raise BudgetUnknown('original background quota profile unavailable')
        profile=matches[0]
        self.database.require_budget_account(record.binding.scope,profile=profile)
        repo=PostgresRepository(lambda:self.database.connect(record.binding.scope,usage_profile=profile),record.ledger_scope)
        return Meter(repo,record.config,clock=self.clock)

    def _publication(self,raw,record):
        value=json.loads(raw)
        if (type(value) is not dict or value.get('version')!='MEMORY-PUBLICATION-result@1'
                or (value.get('job_id'),value.get('attempt_id'),value.get('prepared_input_sha256'),value.get('model_output_sha256'))
                !=(record.job_id,record.attempt_id,record.prepared_input_sha256,record.output_sha256)):
            raise Conflict('actual original typed C publication receipt required')
        return sha(raw)

    def reconcile(self,token,jid,attempt):
        store,record=self._load(token,jid,attempt)
        if record.output_sha256 is None or record.state in ('completed','budget_exhausted'):return record.summary()
        def read(context):return self.collection.query_publication_in_context(context,token,jid,attempt)
        raw=self._owned(token,read)
        if raw==b'null':return record.summary()  # Absence is never authority to resend.
        receipt=self._publication(raw,record)
        def commit(context):
            if context.scope!=store.scope:raise Denied('original job owner changed')
            return pack(store.transition(record,('publishing','unknown'),'completed',receipt=receipt).summary())
        return json.loads(self._owned(token,commit))

    def _metadata(self,token,record,target):
        return self._owned(token,lambda context:self.collection.transition_original_in_context(
            context,token,record.job_id,record.attempt_id,target))

    def cancel(self,token,jid,attempt):
        store,record=self._load(token,jid,attempt)
        observed=self.reconcile(token,jid,attempt)
        if observed['state']=='completed':return observed
        self._metadata(token,record,'cancelled')
        record=store.transition(record,('queued','running','publishing','unknown','cancelled'),'cancelled')
        meter=self._meter(record)
        with meter.repo.transaction() as ledger:exists=record.binding.run_id in ledger.runs
        if exists:meter.cancel(record.binding.run_id)  # Claimed UNKNOWN stays UNKNOWN.
        return record.summary()

    def process_one(self,token,jid,attempt,provider):
        store,record=self._load(token,jid,attempt)
        if record.state!='queued' or record.request is None:return record.summary()
        with store.repository.worker_lease(record.binding) as ownership:
            if ownership is None:return record.summary()
            try:
                record=self._phase(token,store,record.request,lambda policy,source,lease:
                    store.transition(record,('queued',),'running'))
                def authorized(effect):
                    def stage(policy,source,lease):
                        ownership();self._require_stage(store,record,('running',))
                        return effect()
                    return self._phase(token,store,record.request,stage)
                def guard():
                    authorized(lambda:None)
                    return True
                meter=_SourceMeter(self._meter(record),authorized)
                core=BackgroundExit(record.config,lambda binding,account:meter,clock=self.clock,environment='local')
                stream=core.stream(core.prepare(record,provider,guard));chunks=[]
                try:
                    # The first actual outflow is fenced by the original job row;
                    # short source/MEMORY guards finish before provider waits.
                    with store.hold(record):
                        self._require_stage(store,record,('running',))
                        try:chunks.append(next(stream))
                        except StopIteration:pass
                    while True:
                        guard()
                        try:chunks.append(next(stream))
                        except StopIteration:break
                finally:stream.close()
                output=''.join(chunks).encode('utf-8')
                record=store.transition(record,('running',),'publishing',output=sha(output))
                check_budget=core.prepare_publication(record.binding)
                with ExitStack() as stack:
                    held={}
                    def publish(policy,source,lease):
                        tx,current=stack.enter_context(store.hold(record));held.update(tx=tx,current=current)
                        self._require_stage(store,record,('publishing',));ownership();check_budget()
                        return policy.apply_original_result(source,lease)
                    raw=self._phase(token,store,record.request,publish,output=output)
                    # C and outer MESSAGE commits are known before B writes this.
                    receipt=self._publication(raw,record)
                    store.write_state(held['tx'],held['current'],'completed',receipt=receipt)
                return store.read(jid,attempt).summary()
            except BudgetExceeded:
                self._metadata(token,record,'failed')
                result=store.transition(record,('queued','running'),'budget_exhausted')
                meter=self._meter(record)
                with meter.repo.transaction() as ledger:exists=record.binding.run_id in ledger.runs
                if exists:meter.cancel(record.binding.run_id)
                return result.summary()
            except Exception as error:
                try:
                    current=store.read(jid,attempt)
                    if current is not None and current.state in ('running','publishing'):
                        store.transition(current,('running','publishing'),'unknown')
                except Exception as state_error:error.add_note('original background state unavailable: '+type(state_error).__name__)
                raise JobOutcomeUnknown(record) from error

    def run_once(self,token,provider):
        holder={}
        def pending(context):
            store=JobStore(self.database.run_repository(context.scope));holder['jobs']=store.pending()
            return b'own-pending-jobs'
        self._owned(token,pending)
        results=[]
        for jid,attempt in holder['jobs']:
            try:
                value=self.process_one(token,jid,attempt,provider)
                results.append(JobOutcome(jid,attempt,value['run_id'],value['state']))
            except JobOutcomeUnknown as error:results.append(JobOutcome(jid,attempt,error.run_id,'unknown'))
        return results
