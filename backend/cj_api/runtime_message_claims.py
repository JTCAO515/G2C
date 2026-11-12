"""Canonical runtime admission under the original MESSAGE scope lock and AUTH.

No MESSAGE is sent here. A durable claim precedes native dispatch; an uncertain
claim remains query-only even if its MESSAGE never committed.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from runtime_adapter.contract import Unavailable

from .runtime_claims import CanonicalClaims


class MessageClaims:
    def __init__(self,directory,boundary,token_supplier,authority,pins):
        self.boundary,self.token_supplier,self.authority=boundary,token_supplier,authority
        self.binding,self.pins=authority.binding(),pins
        self._deadline=ContextVar('runtime_message_claim_deadline')
        self._transaction=ContextVar('runtime_message_claim_transaction')
        self.claims=CanonicalClaims(directory,self.binding,pins,guard=self._guard,
            original_exists=self._exists,admission_lock=self._admission)

    def _guard(self,*,read_only):
        self.authority.require(binding=self.binding,pins_sha256=self.pins.key,
            purpose='query' if read_only else 'claim',deadline=self._deadline.get(),read_only=read_only)

    @contextmanager
    def _admission(self):
        # Boundary's repository wrapper repeats the original AUTH decision at
        # transaction entry, commit and return. Its native lock is shared with
        # ordinary MESSAGE admission, rather than a parallel experiment lock.
        service=self.boundary._service(self.token_supplier())
        with service.repository.transaction() as transaction:
            if transaction.scope!=self.binding.scope:
                raise Unavailable('ORIGINAL_MESSAGE_OWNER_CHANGED')
            transaction.lock_scope()
            current=self._transaction.set(transaction)
            try:yield
            finally:self._transaction.reset(current)

    def _exists(self,step):
        return self._transaction.get().find(step) is not None

    @contextmanager
    def _within(self,deadline):
        current=self._deadline.set(deadline)
        try:yield
        finally:self._deadline.reset(current)

    def claim(self,request,*,deadline):
        with self._within(deadline):return self.claims.claim(request)

    def consume(self,request,capability,*,deadline):
        with self._within(deadline):return self.claims.consume(request,capability)

    def read(self,step,*,deadline):
        with self._within(deadline):return self.claims.read(step)
