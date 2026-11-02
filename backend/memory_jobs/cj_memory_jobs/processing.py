"""C-owned dispatch input fence for B's outer MESSAGE/Travel source callback.

No B SQL, new Boundary, Run, Meter or provider. The actual registered exit remains
B-owned; its callback enters with_input after B produces the live SourceSnapshot.
"""
from contextlib import contextmanager
from hashlib import sha256
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
        self.extraction,self.max_payload_bytes=extraction,max_payload_bytes
        self.query=None

    def _original(self,query):
        if self.transaction is None or query is None:
            raise Unavailable('processing source lifetime unavailable')
        tx=self.transaction
        row,output=tx.output(self.job_id,self.attempt_id)
        source,mode=row[3],row[5];c=source.cursor
        expected=SourceQuery(c.conversation_id,c.generation,c.epoch,c.after,c.through,
                             source.source_version,source.withdrawal_epoch,mode)
        if (query!=expected or row[0].state!='inflight' or output is not None or row[7]!=tx.epoch):
            raise Conflict('original processing phase or source changed')
        return row

    @contextmanager
    def hold(self,principal,scope,query):
        with super().hold(principal,scope,query) as permit:
            self._original(query)
            self.query=query
            try:
                yield permit
                self._original(query)
            finally:self.query=None

    def with_input(self,snapshot,operation: Callable[[bytes],bytes]):
        """Verify inside the held C tx before entering the actual B exit callback.

        The callback performs bounded local admission/claim/dispatch-intent work,
        without a provider/network wait. It receives the exact original prepared
        bytes, not a model or client-selected replacement. It cannot write
        a C result/checkpoint or grant permission to resend an unknown B attempt.
        """
        row=self._original(self.query)
        source=SourceV2(snapshot.cursor,snapshot.source_version,snapshot.withdrawal_epoch)
        if encode_v2(source,snapshot.messages,row[5])!=row[2]:
            raise Conflict('original processing messages differ')
        current=encoded(snapshot,self.extraction,row[5],max_payload_bytes=self.max_payload_bytes)
        if current!=self.original_input:
            raise Conflict('original processing model input differs')
        self.guard('processing_dispatch')
        result=operation(self.original_input)
        self.guard('processing_return')
        self._original(self.query)
        return result
