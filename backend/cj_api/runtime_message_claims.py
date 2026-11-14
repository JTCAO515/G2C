"""Canonical runtime admission under the original MESSAGE scope lock and AUTH.

No MESSAGE is sent here. A durable claim precedes native dispatch; an uncertain
claim remains query-only even if its MESSAGE never committed.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import sqlite3

from runtime_adapter.contract import Unavailable
from cj_usage.metered_exit import BudgetUnknown

from .runtime_claims import CanonicalClaims


class MessageClaims:
    def __init__(self,directory,boundary,token_supplier,authority,pins,*,history_profile='message.1'):
        self.boundary,self.token_supplier,self.authority=boundary,token_supplier,authority
        self.binding,self.pins=authority.binding(),pins
        if history_profile not in ('message.1','lio.2'):raise ValueError('explicit original message history profile required')
        self.history_profile=history_profile
        self._deadline=ContextVar('runtime_message_claim_deadline')
        self._transaction=ContextVar('runtime_message_claim_transaction')
        self.claims=CanonicalClaims(directory,self.binding,pins,guard=self._guard,
            original_exists=self._exists,admission_lock=self._admission)

    def query(self,context,message_id):
        # Keep the legacy MESSAGE.1 reader explicit for historical M4/local
        # consumers. Production Demo composition selects Lio's source-bound
        # reader; a rejected source never falls back to the legacy reader.
        return (context.query_lio_message(message_id) if self.history_profile=='lio.2' else
                context.query_message(message_id))

    def _guard(self,*,read_only,purpose='query'):
        try:
            self.authority.require(binding=self.binding,pins_sha256=self.pins.key,
                purpose='query' if read_only else purpose,deadline=self._deadline.get(),read_only=read_only)
        except (BudgetUnknown,sqlite3.Error):
            raise Unavailable('ORIGINAL_FINANCIAL_AUTHORITY_UNAVAILABLE') from None

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
