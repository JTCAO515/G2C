"""Explicit RUN-BACKGROUND@2 collection adapter, by original C job version."""
from cj_memory.domain import strict_object,InvalidInput as MemoryInvalidInput
from .codec import Unavailable
from .model_v2 import NoEligibleSource
from .publication_store import PublicationTransaction
from .ending import VERSION


class MemoryCollectionAdapterV2:
    no_eligible_error=NoEligibleSource

    def __init__(self,collection):self.collection=collection

    def _ending(self,context,token,job_id,attempt_id):
        c=self.collection
        repository,_,guard=c._binding(context,token)
        with repository.transaction() as memory:
            tx=PublicationTransaction(memory);tx.require_live()
            row=tx.job(job_id,attempt_id)
            try:value=strict_object(row[1])
            except (MemoryInvalidInput,RecursionError):
                raise Unavailable('stored original worker job unavailable') from None
            if type(value) is not dict or value.get('version') not in ('MEMORY-JOBS@1',VERSION):
                raise Unavailable('explicit original worker job version required')
            guard('worker_adapter_original')
        return value['version']==VERSION

    def processing_policy(self,context,token,job_id,attempt_id,*args,**kwargs):
        c=self.collection
        factory=c.ending_processing_policy if self._ending(context,token,job_id,attempt_id) else c.processing_policy_v2
        return factory(context,token,job_id,attempt_id,*args,**kwargs)

    def publication_policy(self,context,token,job_id,attempt_id,*args,before_commit,**kwargs):
        c=self.collection
        factory=c.ending_publication_policy_v3 if self._ending(context,token,job_id,attempt_id) else c.publication_policy_v3
        return factory(context,token,job_id,attempt_id,*args,before_commit=before_commit,**kwargs)

    def query_publication_in_context(self,*args,**kwargs):
        return self.collection.query_publication_v2_in_context(*args,**kwargs)

    def transition_original_in_context(self,*args,**kwargs):
        return self.collection.transition_original_in_context(*args,**kwargs)
