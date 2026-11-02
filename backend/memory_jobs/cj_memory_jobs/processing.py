"""C-owned dispatch input fence for B's outer MESSAGE/Travel source callback.

No B SQL, new Boundary, Run, Meter or provider. The actual registered exit remains
B-owned; its callback enters with_input after B produces the live SourceSnapshot.
"""
from contextlib import contextmanager
from hashlib import sha256
from threading import get_ident
from typing import Callable

from cj_message.source import SourceQuery
from .codec import Conflict,Unavailable,SourceV2,encode_v2,job_identity
from .model_input import encoded
from .publication_store import PublicationTransaction
from .source_policy import SourcePolicy


class ProcessingSourcePolicy(SourcePolicy):
    transaction_type=PublicationTransaction

    def __init__(self,repository,principal,guard,job_id,attempt_id,original_input,prepared_input_sha256,
                 extraction,*,max_payload_bytes):
        super().__init__(repository,principal,guard)
        job_identity(job_id);job_identity(attempt_id)
        if type(original_input) is not bytes or not 0<len(original_input)<=524288:
            raise ValueError('bounded original prepared input required')
        if sha256(original_input).hexdigest()!=prepared_input_sha256:
            raise Conflict('original prepared input digest differs')
        self.job_id,self.attempt_id=job_id,attempt_id
        self.original_input=original_input
        self.prepared_input_sha256=prepared_input_sha256
        self.extraction,self.max_payload_bytes=extraction,max_payload_bytes
        self.query=None
        self.thread=None

    def _bound(self,query):
        if self.transaction is None or query is None or self.thread!=get_ident():
            raise Unavailable('processing source lifetime unavailable')
        tx=self.transaction
        row,output=tx.output(self.job_id,self.attempt_id)
        source,mode=row[3],row[5];c=source.cursor
        expected=SourceQuery(c.conversation_id,c.generation,c.epoch,c.after,c.through,
                             source.source_version,source.withdrawal_epoch,mode)
        if query!=expected or row[7]!=tx.epoch:
            raise Conflict('original processing source or Memory basis changed')
        return row,output

    def _original(self,query):
        row,output=self._bound(query)
        if row[0].state!='inflight' or output is not None:
            raise Conflict('original processing phase changed')
        return row

    @contextmanager
    def hold(self,principal,scope,query):
        with super().hold(principal,scope,query) as permit:
            self.thread=get_ident()
            try:
                self._original(query)
                self.query=query
                yield permit
                self._original(query)
            finally:self.query=None;self.thread=None

    def _input(self,snapshot):
        row=self._original(self.query)
        source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
        if encode_v2(source,snapshot.messages,row[5])!=row[2]:
            raise Conflict('original processing messages differ')
        current=self._render(snapshot,row[5])
        if current!=self.original_input:
            raise Conflict('original processing model input differs')
        return row

    def _render(self,snapshot,mode):
        return encoded(snapshot,self.extraction,mode,max_payload_bytes=self.max_payload_bytes)

    def with_input(self,snapshot,operation: Callable[[bytes],bytes]):
        """Enter bounded local claim/intent work; no provider/network wait here.

        The callback cannot write a C checkpoint or grant permission to resend an
        unknown B attempt. B retains its own original Run/Meter/cancellation gate.
        """
        self._input(snapshot)
        self.guard('processing_dispatch')
        result=operation(self.original_input)
        self.guard('processing_return')
        self._original(self.query)
        return result
