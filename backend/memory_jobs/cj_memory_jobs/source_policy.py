"""The C-owned durable consent policy consumed by MESSAGE-SOURCE@1."""
from contextlib import contextmanager

from cj_message.domain import Cursor
from .codec import Unavailable
from .postgres import Transaction


class SourcePolicy:
    """One trusted request binding; never construct from a client authority flag.

    repository is C's canonical MEMORY repository bound by the captured MESSAGE
    HistoryReadContext principal/scope. MESSAGE holds its lock before entering.
    Collection consumers use this transaction only during the protected callback.
    """
    transaction_type=Transaction

    def __init__(self, repository, principal, guard):
        self.repository, self.principal = repository, principal
        self.guard = guard
        self.transaction = None
        self.commit_attempted = False

    @contextmanager
    def hold(self, principal, scope, query):
        from cj_message.source import SourcePermit
        if principal != self.principal or scope != self.repository.scope:
            raise Unavailable('history source unavailable')
        self.guard('source_entry')
        with self.repository.transaction() as memory:
            tx = self.transaction_type(memory)
            tx.require_live()
            tx.require_source(query)
            self.transaction = tx
            try:
                yield SourcePermit(Cursor(scope,query.conversation_id,query.generation,
                    query.epoch,query.through,query.after),query.source_version,query.withdrawal_epoch)
                tx.require_source(query)
                self.guard('source_precommit')
                self._before_commit()
                self.commit_attempted = True
            finally:
                self.transaction = None

    def _before_commit(self):
        """Internal extension point after all source/auth checks, before COMMIT."""
