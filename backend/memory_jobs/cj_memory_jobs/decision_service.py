"""Explicit accepted-decision jobs on the same consent/queue/canonical Memory."""
from hashlib import sha256
import json

from cj_trip.domain import CommitUnknown as TripCommitUnknown
from cj_message.domain import CommitUnknown as MessageCommitUnknown
from cj_memory.domain import CommitUnknown as MemoryCommitUnknown
from .collection import CollectionService
from .service import OperationWithheld
from .source_policy import SourcePolicy
from .codec import SourceV2,Conflict,Unavailable,job_identity
from .postgres import encode
from .decision_command import DecisionCommand,VERSION as JOB_VERSION
from .decision_batch import encoded as batch_encoded
from .decision_input import prepared
from .decision_publication import DecisionTransaction
from .decision_policy import DecisionSourcePolicy,DecisionProcessingPolicy,DecisionResultPolicy
from . import decision_result


class DecisionCollectionService(CollectionService):
    def __init__(self,*args,resolve_decision_authority):
        super().__init__(*args)
        self.resolve_decision_authority=resolve_decision_authority

    def _parts(self,context,token,command):
        repository,principal,guard=self._binding(context,token)
        actual=None
        if command.end is not None:
            from .ending import checked_end
            from .ending_source import EndingSegment
            actual=checked_end(context,EndingSegment(command.query,command.end),SourcePolicy(repository,principal,guard))
        return repository,principal,guard,self.resolve_decision_authority(token),actual

    def _source(self,context,command,policy,project):
        return context.with_enabled_source(command.reader_query,policy,lambda snapshot:project(policy.snapshot(snapshot)))

    def _invoke_decision(self,token,jid,attempt,operation):
        policy=None
        def apply(context):
            nonlocal policy
            repository,_,_=self._binding(context,token)
            with repository.transaction() as memory:
                tx=DecisionTransaction(memory);tx.require_live();row=tx.job(jid,attempt)
            command=DecisionCommand.parse(row[1])
            repository,principal,guard,authority,actual=self._parts(context,token,command)
            policy=DecisionSourcePolicy(repository,principal,guard,decision_command=command,
                                        decision_authority=authority,actual_end=actual)
            def project(snapshot):
                source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
                if batch_encoded(source,snapshot.messages,row[5],policy.decision_lease.decision)!=row[2]:
                    raise Conflict('original accepted decision source changed')
                return operation(policy.transaction,snapshot,principal,policy)
            return self._source(context,command,policy,project)
        try:return self.boundary.with_history_context(token,apply)
        except (TripCommitUnknown,MessageCommitUnknown,MemoryCommitUnknown) as error:
            raise OperationWithheld(jid,attempt) from error
        except Exception as error:
            if policy is not None and policy.commit_attempted:raise OperationWithheld(jid,attempt) from error
            raise

    def enqueue_decision(self,token,original):
        return self._enqueue_decision(token,original,serialized=False)

    def _invalid_originals(self,context,token,principal,repository):
        with repository.transaction() as memory:
            tx=DecisionTransaction(memory);tx.require_live();originals=tx.current_unresolved()
        invalid=set()
        for row in originals:
            cursor=row[3].cursor;head=context.send_status(cursor.conversation_id).head
            if head is None or (head.generation,head.epoch)!=(cursor.generation,cursor.epoch):
                invalid.add(row[0].job_id);continue
            if json.loads(row[1])['version']!=JOB_VERSION:continue
            command=DecisionCommand.parse(row[1]);authority=self.resolve_decision_authority(token)
            def compare(current):
                if current.metadata.principal!=principal:raise Unavailable('decision inspection identity changed')
                trip=current.detail(command.decision.trip_id)
                if trip is None:raise Unavailable('original decision current metadata unavailable')
                return encode(dict(version=trip.version,digest=sha256(trip.content).hexdigest()))
            observed=json.loads(authority.boundary.with_operation(token,compare))
            if observed['version']>command.decision.expected_version:invalid.add(row[0].job_id)
            elif (observed['version'],observed['digest'])!=(command.decision.expected_version,command.decision.content_sha256):
                raise Unavailable('decision metadata cannot prove permanent invalidation')
        return invalid

    def enqueue_decision_serialized(self,token,original):
        return self._enqueue_decision(token,original,serialized=True)

    def _enqueue_decision(self,token,original,*,serialized):
        command=DecisionCommand.parse(original);policy=None
        def apply(context):
            nonlocal policy
            repository,principal,guard,authority,actual=self._parts(context,token,command)
            invalid=self._invalid_originals(context,token,principal,repository) if serialized else set()
            policy=DecisionSourcePolicy(repository,principal,guard,decision_command=command,
                                        decision_authority=authority,actual_end=actual)
            def persist(snapshot):
                if serialized and any(row[0].job_id!=command.job_id and row[0].job_id not in invalid
                       for row in policy.transaction.current_unresolved()):
                    raise Conflict('another original owns the current account basis')
                extraction,_,_=self.resolve_collection(principal)
                prepared(policy.transaction,snapshot,policy.decision_lease,extraction,command.query.mode,max_payload_bytes=262144)
                source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
                return policy.transaction.enqueue_decision(source,snapshot.messages,command.query.mode,
                    command.job_id,command.attempt_id,original,policy.decision_lease.decision).encode()
            return self._source(context,command,policy,persist)
        try:return self.boundary.with_history_context(token,apply)
        except (TripCommitUnknown,MessageCommitUnknown,MemoryCommitUnknown) as error:
            raise OperationWithheld(command.job_id,command.attempt_id) from error
        except Exception as error:
            if policy is not None and policy.commit_attempted:raise OperationWithheld(command.job_id,command.attempt_id) from error
            raise

    def begin_decision(self,token,jid,attempt):
        return self._invoke_decision(token,jid,attempt,
            lambda tx,snapshot,principal,policy:tx.transition(jid,attempt,'inflight').encode())

    def prepare_decision_input(self,token,jid,attempt,*,max_payload_bytes):
        def project(tx,snapshot,principal,policy):
            row,output=tx.output(jid,attempt)
            if row[0].state!='inflight' or row[7]!=tx.epoch or output is not None:
                raise Conflict('original decision input phase changed')
            extraction,_,_=self.resolve_collection(principal)
            return prepared(tx,snapshot,policy.decision_lease,extraction,row[5],max_payload_bytes=max_payload_bytes)[0]
        return self._invoke_decision(token,jid,attempt,project)

    def _policy_parts(self,context,token,jid,attempt):
        repository,_,_=self._binding(context,token)
        with repository.transaction() as memory:
            tx=DecisionTransaction(memory);tx.require_live();row=tx.job(jid,attempt)
        command=DecisionCommand.parse(row[1])
        return (*self._parts(context,token,command),command)

    def decision_processing_policy(self,context,token,jid,attempt,original,prepared_sha,*,max_payload_bytes):
        repository,principal,guard,authority,actual,command=self._policy_parts(context,token,jid,attempt)
        extraction,_,_=self.resolve_collection(principal)
        return DecisionProcessingPolicy(repository,principal,guard,jid,attempt,original,prepared_sha,extraction,
            max_payload_bytes=max_payload_bytes,decision_command=command,decision_authority=authority,actual_end=actual)

    def decision_publication_policy(self,context,token,jid,attempt,original,prepared_sha,output,output_sha,*,max_payload_bytes,before_commit):
        repository,principal,guard,authority,actual,command=self._policy_parts(context,token,jid,attempt)
        extraction,memory,_=self.resolve_collection(principal)
        return DecisionResultPolicy(repository,principal,guard,jid,attempt,original,prepared_sha,extraction,
            max_payload_bytes=max_payload_bytes,decision_command=command,decision_authority=authority,actual_end=actual,
            model_output=output,model_output_sha256=output_sha,memory_policy=memory,before_commit=before_commit)

    def query_decision_publication_in_context(self,context,token,jid,attempt):
        job_identity(jid);job_identity(attempt)
        repository,_,guard=self._binding(context,token)
        with repository.transaction() as memory:
            tx=DecisionTransaction(memory);tx.require_live()
            result=decision_result.original_result(tx,jid,attempt)
            guard('original_decision_publication')
            return b'null' if result is None else result

    def query_decision_publication(self,token,jid,attempt):
        return self.boundary.with_history_context(token,
            lambda context:self.query_decision_publication_in_context(context,token,jid,attempt))


class DecisionCollectionAdapter:
    from .model_v2 import NoEligibleSource as no_eligible_error
    publication_version=decision_result.VERSION
    consumer_version='RUN-BACKGROUND@3'

    def __init__(self,collection):self.collection=collection
    def processing_policy(self,*args,consumer_version,**kwargs):
        if consumer_version!=self.consumer_version:raise Unavailable('explicit decision worker version required')
        return self.collection.decision_processing_policy(*args,**kwargs)
    def publication_policy(self,*args,consumer_version,**kwargs):
        if consumer_version!=self.consumer_version:raise Unavailable('explicit decision worker version required')
        return self.collection.decision_publication_policy(*args,**kwargs)
    def query_publication_in_context(self,*args,**kwargs):return self.collection.query_decision_publication_in_context(*args,**kwargs)
    def transition_original_in_context(self,*args,**kwargs):return self.collection.transition_original_in_context(*args,**kwargs)
