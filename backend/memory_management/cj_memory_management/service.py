"""Trusted domain-only lifecycle entry. HTTP/AUTH composition is not wired here."""
from cj_memory.domain import CommitUnknown, Conflict, InvalidInput
from .domain import Action


class ActionUnknown(CommitUnknown):
    """Preserve the original action; absence on query is not retry authorization."""
    def __init__(self, action_id):
        super().__init__('query original memory management action')
        self.action_id = action_id
        self.commit_possible = True
        self.recovery = 'reconcile_original'


class Service:
    def __init__(self, repository):
        self.repository = repository

    def apply(self, original_utf8):
        action = Action.parse(original_utf8)
        try:
            with self.repository.transaction() as tx:
                tx.lock_scope()
                stored = tx.action(action.action_id)
                if stored is not None:
                    if stored[0] != original_utf8:
                        raise Conflict('action bytes differ')
                    result = stored[1]
                else:
                    result = tx.change_status(action)
        except CommitUnknown:
            raise ActionUnknown(action.action_id) from None
        return result

    def query(self, action_id):
        if type(action_id) is not str or not action_id.strip() or len(action_id) > 4096:
            raise InvalidInput('invalid action ID')
        with self.repository.transaction() as tx:
            tx.lock_scope()
            stored = tx.action(action_id)
        return stored[1] if stored is not None else None
