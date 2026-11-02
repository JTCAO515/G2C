"""Protected checkpoint/publication and explicit user confirmation, no model exit."""
from contextlib import nullcontext
from hashlib import sha256
import json

from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_message.domain import CommitUnknown as MessageCommitUnknown
from cj_message.source import SourceQuery
from cj_message.travel_reference import MessageContextAuthority,LeaseUnavailable
from cj_memory.domain import CommitUnknown as MemoryCommitUnknown
from .candidate import CandidateAction
from .codec import Conflict,SourceV2,Unavailable,encode_v2,job_identity
from .postgres import encode
from .publication_store import PublicationTransaction
from .service import Service,OperationWithheld
from .source_policy import SourcePolicy


class PublicationSourcePolicy(SourcePolicy):
    transaction_type=PublicationTransaction


class CollectionService(Service):
    def __init__(self,boundary,resolve_repository,resolve_collection):
        super().__init__(boundary,resolve_repository)
        # Explicit server-owned resolver: extraction policy, Memory collection
        # policy and current-context resolver. No permissive policy defaults.
        self.resolve_collection=resolve_collection

    def _with_job(self,token,job_id,attempt_id,operation):
        job_identity(job_id);job_identity(attempt_id)
        policy=None
        def apply(context):
            nonlocal policy
            repository,principal,guard=self._binding(context,token)
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                row=tx.job(job_id,attempt_id)
            source,mode=row[3],row[5];c=source.cursor
            query=SourceQuery(c.conversation_id,c.generation,c.epoch,c.after,c.through,
                              source.source_version,source.withdrawal_epoch,mode)
            policy=PublicationSourcePolicy(repository,principal,guard)
            def project(snapshot):
                current=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
                if encode_v2(current,snapshot.messages,mode)!=row[2]:
                    raise Conflict('original collection source differs')
                return operation(policy.transaction,snapshot,principal)
            return context.with_enabled_source(query,policy,project)
        try:return self.boundary.with_history_context(token,apply)
        except (MemoryCommitUnknown,MessageCommitUnknown) as error:
            raise OperationWithheld(job_id,attempt_id) from error
        except (AccessBlocked,IdentityChanged) as error:
            if policy is not None and policy.commit_attempted:
                raise OperationWithheld(job_id,attempt_id) from error
            raise

    def record_output(self,token,job_id,attempt_id,raw):
        """Trusted worker checkpoint after its unique registered model operation.

        No HTTP endpoint accepts model output or bypasses Meter through this method.
        A stored output is immutable and supplies no future publication permit.
        """
        return self._with_job(token,job_id,attempt_id,
            lambda tx,snapshot,principal:encode(dict(job_id=job_id,attempt_id=attempt_id,
                output_sha256=sha256(tx.checkpoint_output(job_id,attempt_id,raw)).hexdigest())))

    def prepare_model_input(self,token,job_id,attempt_id,*,max_payload_bytes):
        """Protected data preparation only; not a Meter/dispatch capability."""
        from .model_input import prepare
        def project(tx,snapshot,principal):
            row,output=tx.output(job_id,attempt_id)
            if row[0].state!='inflight' or row[7]!=tx.epoch or output is not None:
                raise Conflict('original extraction input phase changed')
            extraction,_,_=self.resolve_collection(principal)
            system,messages=prepare(snapshot,extraction,row[5],max_payload_bytes=max_payload_bytes)
            return json.dumps(dict(system=system,messages=messages),ensure_ascii=False,
                              sort_keys=True,separators=(',',':')).encode('utf-8')
        return self._with_job(token,job_id,attempt_id,project)

    def publish_output(self,token,job_id,attempt_id):
        def publish(tx,snapshot,principal):
            extraction,memory,context_for=self.resolve_collection(principal)
            receipts=tx.publish_output(job_id,attempt_id,snapshot.messages,extraction,memory,context_for)
            return encode(dict(version='MEMORY-COLLECTION-result@1',job_id=job_id,attempt_id=attempt_id,
                               receipts=receipts))
        return self._with_job(token,job_id,attempt_id,publish)

    def candidates(self,token,job_id,attempt_id,*,request_id=None):
        job_identity(job_id);job_identity(attempt_id)
        def query(context):
            repository,principal,guard=self._binding(context,token)
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                row,raw=tx.output(job_id,attempt_id)
                if row[0].state!='completed' or raw is None:
                    raise Unavailable('collection result unavailable')
                tx.cur.execute('SELECT DISTINCT item_id FROM cj_memory_history_origin '
                    'WHERE scope=%s AND job_id=%s AND attempt_id=%s ORDER BY item_id',
                    (tx.scope,job_id,attempt_id))
                values=[]
                for (item_id,) in tx.cur.fetchall():
                    item=memory.detail(item_id)
                    if item is None:raise Unavailable('collection item unavailable')
                    command=item.command
                    values.append(dict(candidate_id=item_id,version=item.version,status=item.status,
                        subject=command.subject,slot=command.slot,kind=command.kind,text=command.text,
                        extent=command.extent,occurred_at=command.occurred_at,
                        context=None if command.extent=='long_term' else dict(kind=command.context_kind,
                            id=command.context_id,expected_version=command.context_version)))
                guard('candidate_projection')
                return encode(dict(job_id=job_id,attempt_id=attempt_id,memory_epoch=tx.epoch,candidates=values))
        return self._invoke(token,query,request_id,'MEMORY-CANDIDATE-list@1')

    def apply_candidate(self,token,original,*,request_id=None):
        action=CandidateAction.parse(original);possible=False
        def apply(context):
            nonlocal possible
            repository,principal,guard=self._binding(context,token)
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                old=tx.decision(action.action_id)
                if old is not None:
                    if old[0]!=original:raise Conflict('original candidate action differs')
                    possible=True;guard('candidate_replay')
                    return old[1]
            _,memory_policy,_=self.resolve_collection(principal)
            if action.operation=='confirm' and action.extent=='current':
                def admit():
                    guard('candidate_travel')
                    return principal
                authority=MessageContextAuthority(self.boundary.resolve_repository(principal),admit)
                if authority.repository.scope!=repository.scope:
                    raise Unavailable('candidate travel binding unavailable')
                held=authority.hold_current(action.context)
            else:held=nullcontext(None)
            with held as lease:
                with repository.transaction() as memory:
                    tx=PublicationTransaction(memory);tx.require_live()
                    result=tx.apply_decision(action,memory_policy,context_lease=lease)
                    guard('candidate_precommit');possible=True
                return result
        try:return self._invoke(token,apply,request_id,'MEMORY-CANDIDATE-response@1')
        except (MemoryCommitUnknown,MessageCommitUnknown) as error:
            raise OperationWithheld(action.action_id) from error
        except LeaseUnavailable as error:
            if possible:raise OperationWithheld(action.action_id) from error
            raise
        except (AccessBlocked,IdentityChanged) as error:
            if possible:raise OperationWithheld(action.action_id) from error
            raise

    def query_candidate_action(self,token,action_id,*,request_id=None):
        job_identity(action_id)
        def query(context):
            repository,principal,guard=self._binding(context,token)
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                old=tx.decision(action_id)
                guard('candidate_receipt')
                return old[1] if old is not None else b'null'
        return self._invoke(token,query,request_id,'MEMORY-CANDIDATE-response@1')
