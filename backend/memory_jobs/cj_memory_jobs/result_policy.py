"""C-owned original-result publication inside B's existing source callback."""
from contextlib import contextmanager
from hashlib import sha256
from threading import get_ident

from cj_message.domain import Command
from .codec import Conflict,Unavailable
from .processing import ProcessingSourcePolicy
from .publication_result import encode_result,original_result
from .publication_result import VERSION
from .source_policy import SourcePolicy
from .extraction import parse_output


class ResultSourcePolicy(ProcessingSourcePolicy):
    result_version=VERSION
    def __init__(self,*args,model_output,model_output_sha256,memory_policy,**kwargs):
        super().__init__(*args,**kwargs)
        if type(model_output) is not bytes or not 0<len(model_output)<=16384:
            raise ValueError('bounded original model output required')
        if sha256(model_output).hexdigest()!=model_output_sha256:
            raise Conflict('original model output digest differs')
        self.model_output,self.model_output_sha256=model_output,model_output_sha256
        self.memory_policy=memory_policy
        self.result=None
        self.failed=False

    def _original(self,query):
        row,output=self._bound(query)
        if row[0].state not in ('inflight','unknown') or (output is not None and output!=self.model_output):
            raise Conflict('original result phase or checkpoint differs')
        return row

    @contextmanager
    def hold(self,principal,scope,query):
        with SourcePolicy.hold(self,principal,scope,query) as permit:
            self.thread=get_ident()
            try:
                self._original(query)
                self.query=query
                yield permit
                if self.failed:raise Unavailable('original publication aborted')
                if self.result is None:self._original(query)
                elif self.original_result()!=self.result:
                    raise Unavailable('original publication result changed')
            finally:self.query=None;self.thread=None

    def apply_original_result(self,snapshot,travel_lease=None):
        """Local C writes only; B records its publication after source exit.

        A caught publication error still poisons this C transaction, preserving
        atomicity when the outer worker converts that error into its own status.
        """
        if self.failed or self.query is None or self.transaction is None or self.thread!=get_ident():
            raise Unavailable('original publication lifetime unavailable')
        if self.result is not None:
            self.guard('result_replay')
            return self.result
        try:
            row=self._input(snapshot)
            self.guard('result_prewrite')
            tx=self.transaction
            tx.checkpoint_output(self.job_id,self.attempt_id,self.model_output)
            by_id={m.receipt.message_id:m for m in snapshot.messages}
            def context_for(entry):
                if entry.extent=='long_term':return None,None
                if travel_lease is None:raise Unavailable('actual original Travel lease required')
                selected={Command.parse_original(by_id[e.message_id].original_utf8).travel_context for e in entry.evidence}
                if len(selected)!=1 or None in selected:
                    raise Unavailable('unambiguous committed Travel source required')
                selection=selected.pop()
                travel_lease.check()
                if travel_lease.context!=selection:
                    raise Unavailable('original Travel source and current lease differ')
                return selection,travel_lease
            def completed(receipts):
                return self.encode_result(row[0],receipts)
            tx.publish_output(self.job_id,self.attempt_id,snapshot.messages,self.extraction,self.memory_policy,
                              context_for,completion=completed,decoder=self._entries)
            self.result=self.original_result()
            self.guard('result_precommit')
            return self.result
        except BaseException:
            self.failed=True
            raise

    def _entries(self,raw,messages,policy):
        return parse_output(raw,messages,policy)

    def original_result(self):
        return original_result(self.transaction,self.job_id,self.attempt_id,expected_version=self.result_version)

    def encode_result(self,status,receipts):
        return encode_result(status,self.prepared_input_sha256,self.model_output_sha256,receipts,version=self.result_version)
