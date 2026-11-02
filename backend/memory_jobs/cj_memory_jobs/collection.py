"""Protected checkpoint/publication and explicit user confirmation, no model exit."""
from contextlib import nullcontext
from hashlib import sha256

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


def _candidate(item):
    command=item.command
    return dict(candidate_id=command.item_id,version=item.version,status=item.status,
        subject=command.subject,slot=command.slot,kind=command.kind,text=command.text,
        extent=command.extent,occurred_at=command.occurred_at,
        context=None if command.extent=='long_term' else dict(kind=command.context_kind,
            id=command.context_id,expected_version=command.context_version))


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
            from .ending import with_original_source
            return with_original_source(context,row,policy,project,
                probe_policy=SourcePolicy(repository,principal,guard))
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
        from .model_input import encoded
        def project(tx,snapshot,principal):
            row,output=tx.output(job_id,attempt_id)
            if row[0].state!='inflight' or row[7]!=tx.epoch or output is not None:
                raise Conflict('original extraction input phase changed')
            extraction,_,_=self.resolve_collection(principal)
            return encoded(snapshot,extraction,row[5],max_payload_bytes=max_payload_bytes)
        return self._with_job(token,job_id,attempt_id,project)

    def prepare_model_input_v2(self,token,job_id,attempt_id,*,max_payload_bytes):
        """Explicit filtered input; Data1 remains the old separate contract."""
        from .model_v2 import encoded
        def project(tx,snapshot,principal):
            row,output=tx.output(job_id,attempt_id)
            if row[0].state!='inflight' or row[7]!=tx.epoch or output is not None:
                raise Conflict('original extraction input phase changed')
            extraction,_,_=self.resolve_collection(principal)
            return encoded(tx,snapshot,extraction,row[5],max_payload_bytes=max_payload_bytes)
        return self._with_job(token,job_id,attempt_id,project)

    def _ending_binding(self,context,token,job_id,attempt_id):
        from .ending import EndingCommand,checked_end
        repository,principal,guard=self._binding(context,token)
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            row=tx.job(job_id,attempt_id)
        command=EndingCommand.parse(row[1])
        actual=checked_end(context,command.segment,SourcePolicy(repository,principal,guard))
        extraction,memory_policy,_=self.resolve_collection(principal)
        return repository,principal,guard,command,actual,extraction,memory_policy

    def discover_candidate_jobs(self,token,conversation_id,after_job_id,*,request_id=None):
        """Actual first-producer refs for a chat; no fixture ID or source renewal."""
        from .codec import pg_identity
        import json
        pg_identity(conversation_id,256)
        if after_job_id:job_identity(after_job_id)
        def query(context):
            repository,_,guard=self._binding(context,token)
            if context.send_status(conversation_id).head is None:
                raise Unavailable('candidate conversation unavailable')
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                tx.cur.execute('''SELECT DISTINCT o.job_id,o.attempt_id FROM cj_memory_history_origin o
                    JOIN cj_memory_item i ON (i.scope,i.source_id,i.item_id)=(o.scope,o.source_id,o.item_id)
                    WHERE o.scope=%s AND i.status='candidate' AND o.job_id>%s
                      AND o.origin_refs @> %s::jsonb ORDER BY o.job_id LIMIT 51''',
                    (tx.scope,after_job_id,json.dumps([dict(conversation_id=conversation_id)])))
                rows=tx.cur.fetchall()
                value=dict(conversation_id=conversation_id,
                    jobs=[dict(job_id=job,attempt_id=attempt) for job,attempt in rows[:50]],
                    next_after_job_id=rows[49][0] if len(rows)>50 else None)
                raw=encode(value)
                if len(raw)>524288:raise Unavailable('candidate discovery exceeds bound')
                guard('candidate_discovery_return')
            return raw
        return self._invoke(token,query,request_id,'MEMORY-CANDIDATE-JOBS@1')

    def ending_processing_policy(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,*,max_payload_bytes):
        from .ending import EndingProcessingPolicy
        repository,principal,guard,command,actual,extraction,_=self._ending_binding(context,token,job_id,attempt_id)
        return EndingProcessingPolicy(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
            extraction,max_payload_bytes=max_payload_bytes,ending_command=command,actual_end=actual)

    def ending_publication_policy(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,
                                  model_output,model_output_sha256,*,max_payload_bytes):
        from .ending import EndingPublicationPolicy
        repository,principal,guard,command,actual,extraction,memory_policy=self._ending_binding(context,token,job_id,attempt_id)
        return EndingPublicationPolicy(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
            extraction,max_payload_bytes=max_payload_bytes,ending_command=command,actual_end=actual,
            model_output=model_output,model_output_sha256=model_output_sha256,memory_policy=memory_policy)

    def ending_publication_policy_v3(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,
                                     model_output,model_output_sha256,*,max_payload_bytes,before_commit):
        from .ending import EndingPublicationPolicyV3
        repository,principal,guard,command,actual,extraction,memory_policy=self._ending_binding(context,token,job_id,attempt_id)
        return EndingPublicationPolicyV3(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
            extraction,max_payload_bytes=max_payload_bytes,ending_command=command,actual_end=actual,
            model_output=model_output,model_output_sha256=model_output_sha256,memory_policy=memory_policy,before_commit=before_commit)

    def processing_policy(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,*,max_payload_bytes):
        """Compose inside B's outer protected context; never opens a Boundary."""
        from .processing import ProcessingSourcePolicy
        repository,principal,guard=self._binding(context,token)
        extraction,_,_=self.resolve_collection(principal)
        return ProcessingSourcePolicy(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
                                      extraction,max_payload_bytes=max_payload_bytes)

    def publication_policy(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,
                           model_output,model_output_sha256,*,max_payload_bytes):
        """Only bounded local publication in B's existing protected callback."""
        from .result_policy import ResultSourcePolicy
        repository,principal,guard=self._binding(context,token)
        extraction,memory,_=self.resolve_collection(principal)
        return ResultSourcePolicy(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
            extraction,max_payload_bytes=max_payload_bytes,model_output=model_output,
            model_output_sha256=model_output_sha256,memory_policy=memory)

    def processing_policy_v2(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,*,max_payload_bytes):
        from .policy_v2 import ProcessingSourcePolicyV2
        repository,principal,guard=self._binding(context,token)
        extraction,_,_=self.resolve_collection(principal)
        return ProcessingSourcePolicyV2(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
                                        extraction,max_payload_bytes=max_payload_bytes)

    def publication_policy_v2(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,
                              model_output,model_output_sha256,*,max_payload_bytes):
        from .policy_v2 import ResultSourcePolicyV2
        repository,principal,guard=self._binding(context,token)
        extraction,memory,_=self.resolve_collection(principal)
        return ResultSourcePolicyV2(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
            extraction,max_payload_bytes=max_payload_bytes,model_output=model_output,
            model_output_sha256=model_output_sha256,memory_policy=memory)

    def transition_original_in_context(self,context,token,job_id,attempt_id,target):
        """Nonproductive original metadata only, before entering any C holder.

        Withdrawal does not prevent stopping/reconciling the original job. No
        source is renewed and no begin/completion or model dispatch is exposed.
        """
        if target not in ('cancelled','failed','unknown'):
            raise ValueError('nonproductive original transition required')
        job_identity(job_id);job_identity(attempt_id)
        repository,_,guard=self._binding(context,token)
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            result=tx.transition(job_id,attempt_id,target).encode()
            guard('original_transition')
        return result

    def publication_policy_v3(self,context,token,job_id,attempt_id,original_input,prepared_input_sha256,
                              model_output,model_output_sha256,*,max_payload_bytes,before_commit):
        """Explicit trusted Meter deadline check at the actual C commit tail."""
        from .policy_v3 import ResultSourcePolicyV3
        repository,principal,guard=self._binding(context,token)
        extraction,memory,_=self.resolve_collection(principal)
        return ResultSourcePolicyV3(repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
            extraction,max_payload_bytes=max_payload_bytes,model_output=model_output,
            model_output_sha256=model_output_sha256,memory_policy=memory,before_commit=before_commit)

    def query_publication_in_context(self,context,token,job_id,attempt_id):
        from .publication_result import VERSION
        return self._publication_receipt(context,token,job_id,attempt_id,VERSION)

    def query_publication_v2_in_context(self,context,token,job_id,attempt_id):
        from .publication_result import VERSION_V2
        return self._publication_receipt(context,token,job_id,attempt_id,VERSION_V2)

    def _publication_receipt(self,context,token,job_id,attempt_id,version):
        from .publication_result import original_result
        job_identity(job_id);job_identity(attempt_id)
        repository,_,guard=self._binding(context,token)
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            result=original_result(tx,job_id,attempt_id,expected_version=version)
            guard('publication_receipt')
            return result if result is not None else b'null'

    def query_publication(self,token,job_id,attempt_id,*,request_id=None):
        return self._invoke(token,lambda context:self.query_publication_in_context(context,token,job_id,attempt_id),
                            request_id,'MEMORY-PUBLICATION-response@1')

    def query_publication_v2(self,token,job_id,attempt_id,*,request_id=None):
        return self._invoke(token,lambda context:self.query_publication_v2_in_context(context,token,job_id,attempt_id),
                            request_id,'MEMORY-PUBLICATION-response@2')

    def publication_items_v2(self,token,job_id,attempt_id,*,request_id=None):
        """Current own items plus their original review producer, not renewed authority."""
        from .publication_result import original_result,VERSION_V2
        import json
        job_identity(job_id);job_identity(attempt_id)
        def query(context):
            repository,_,guard=self._binding(context,token)
            with repository.transaction() as memory:
                tx=PublicationTransaction(memory);tx.require_live()
                raw=original_result(tx,job_id,attempt_id,expected_version=VERSION_V2)
                if raw is None:raise Unavailable('original publication unavailable')
                values=[]
                for receipt in json.loads(raw)['receipts']:
                    item=memory.detail(receipt['item_id'])
                    if item is None:raise Unavailable('current publication item unavailable')
                    value=_candidate(item);value['review']=None
                    if item.status=='candidate':
                        tx.cur.execute('SELECT job_id,attempt_id FROM cj_memory_history_origin '
                            'WHERE scope=%s AND source_id=%s AND item_id=%s',
                            (tx.scope,item.command.source_id,item.command.item_id))
                        origin=tx.cur.fetchone()
                        if origin is not None:value['review']=dict(job_id=origin[0],attempt_id=origin[1])
                    values.append(value)
                result=encode(dict(job_id=job_id,attempt_id=attempt_id,memory_epoch=tx.epoch,items=values))
                if len(result)>524288:raise Unavailable('publication item projection exceeds bound')
                guard('publication_items')
                return result
        return self._invoke(token,query,request_id,'MEMORY-PUBLICATION-items@2')

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
                    values.append(_candidate(item))
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
