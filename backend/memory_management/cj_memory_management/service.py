"""Trusted domain-only lifecycle entry. HTTP/AUTH composition is not wired here."""
from cj_memory.domain import CommitUnknown, Conflict, InvalidInput
from .domain import Action
from .edit import Edit, parse_action
from .postgres import Transaction


def apply_in_transaction(transaction, action, policy=None):
    """Consume the provided public transaction; never connect or commit here."""
    tx = Transaction(transaction.cur, transaction.scope)
    tx.lock_scope()
    stored = tx.action(action.action_id)
    if stored is not None:
        if stored[0] != action.raw:
            raise Conflict('action bytes differ')
        return stored[1]
    return tx.edit(action, policy) if isinstance(action, Edit) else tx.change_status(action)


def query_in_transaction(transaction, action_id):
    if type(action_id) is not str or not action_id.strip() or len(action_id) > 4096:
        raise InvalidInput('invalid action ID')
    tx = Transaction(transaction.cur, transaction.scope)
    tx.lock_scope()
    stored = tx.action(action_id)
    return stored[1] if stored is not None else None


class ActionUnknown(CommitUnknown):
    """Preserve the original action; absence on query is not retry authorization."""
    def __init__(self, action_id):
        super().__init__('query original memory management action')
        self.action_id = action_id
        self.commit_possible = True
        self.recovery = 'reconcile_original'


class Service:
    def __init__(self, repository, *, manual_policy=None):
        self.repository = repository
        self.manual_policy = manual_policy

    def apply(self, original_utf8):
        action = parse_action(original_utf8)
        try:
            with self.repository.transaction() as tx:
                result = apply_in_transaction(tx, action, self.manual_policy)
        except CommitUnknown:
            raise ActionUnknown(action.action_id) from None
        return result

    def query(self, action_id):
        if type(action_id) is not str or not action_id.strip() or len(action_id) > 4096:
            raise InvalidInput('invalid action ID')
        with self.repository.transaction() as tx:
            result = query_in_transaction(tx, action_id)
        return result
