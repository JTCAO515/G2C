"""Genuine Trip before canonical Memory, never a provider wait in either holder."""
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256

from .codec import SourceV2,Conflict
from .source_policy import SourcePolicy
from .decision_publication import DecisionTransaction
from .decision_batch import encoded as batch_encoded
from .decision_input import prepared,source_digest
from .decision_output import parse_output
from .policy_v2 import ProcessingSourcePolicyV2
from .policy_v3 import ResultSourcePolicyV3
from . import model_v2,decision_result


class _DecisionLease:
    transaction_type=DecisionTransaction

    def __init__(self,*args,decision_command,decision_authority,actual_end=None,**kwargs):
        super().__init__(*args,**kwargs)
        if decision_command.end is not None and actual_end is None:raise ValueError('actual full ending head required')
        self.command,self.authority,self.actual_end=decision_command,decision_authority,actual_end

    @contextmanager
    def hold(self,principal,scope,query):
        if query!=self.command.reader_query:raise Conflict('original decision reader range differs')
        with self.authority.hold(principal,self.command.decision,max_source_bytes=4_000_000) as lease:
            self.decision_lease=lease
            try:
                with super().hold(principal,scope,query) as permit:
                    yield permit
                    lease.check()
            finally:self.decision_lease=None

    def snapshot(self,value):return value if self.command.end is None else replace(value,end=self.actual_end)


class DecisionSourcePolicy(_DecisionLease,SourcePolicy):
    pass


class _DecisionProcessing(_DecisionLease):
    def _bound(self,query):
        if query!=self.command.reader_query:raise Conflict('original decision phase query differs')
        return super()._bound(self.command.query)

    def _input(self,snapshot):
        snapshot=self.snapshot(snapshot);row=self._original(self.query)
        source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
        if batch_encoded(source,snapshot.messages,row[5],self.decision_lease.decision)!=row[2]:
            raise Conflict('current original decision source differs')
        if self._render(snapshot,row[5])!=self.original_input:raise Conflict('original decision model data differs')
        self._snapshot,self._mode=snapshot,row[5]
        return row

    def _render(self,snapshot,mode):
        raw,self.eligible_count=prepared(self.transaction,self.snapshot(snapshot),self.decision_lease,self.extraction,mode,
                                        max_payload_bytes=self.max_payload_bytes)
        return raw

    def _entries(self,raw,messages,policy):
        return parse_output(raw,model_v2.visible(self.transaction,messages),self.decision_lease.decision,policy,self.repository.scope)


class DecisionProcessingPolicy(_DecisionProcessing,ProcessingSourcePolicyV2):
    pass


class DecisionResultPolicy(_DecisionProcessing,ResultSourcePolicyV3):
    result_version=decision_result.VERSION

    def original_result(self):return decision_result.original_result(self.transaction,self.job_id,self.attempt_id)

    def encode_result(self,status,receipts):
        return decision_result.encoded(status,self.prepared_input_sha256,self.model_output_sha256,receipts,
            source_digest(self.repository.scope,self.decision_lease.decision))
