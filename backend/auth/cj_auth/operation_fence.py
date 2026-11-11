"""Synchronous response-lifetime fence shared by the NEEDS and TRIP operation boundaries.

No AUTH policy lives here. Each domain keeps its own ContextVar, exception types,
metadata, binding guard and per-method admission rule; this module only keeps the
one-thread, one-lifetime, withhold-after-possible-commit mechanics identical.
"""
import inspect
import threading


def new_state(**extra):
    return dict(active=True, blocked=False, action_id=None, commit_possible=False,
                thread=threading.get_ident(), **extra)


def _fail(state, exc, commit_unknown):
    state['blocked'] = True
    state['commit_possible'] |= bool(getattr(exc, 'commit_possible', False)) or isinstance(exc, commit_unknown)


class FencedOperation:
    """Issued only inside run_fenced; the repository is reachable through named calls only.

    Subclasses set active (their ContextVar), withheld(action_id, commit_possible)
    and commit_unknown, expose the allowed repository methods through _call, and
    override _admit for their one-write and original-identity rules.
    """
    active = withheld = commit_unknown = None

    def __init__(self, repository, metadata, state):
        self.__repository, self.__metadata, self.__state = repository, metadata, state

    def __check(self):
        s = self.__state
        if (not s['active'] or s['blocked'] or self.active.get() is not self
                or threading.get_ident() != s['thread']):
            s['blocked'] = True
            raise self.withheld(s['action_id'], s['commit_possible'])

    @property
    def metadata(self):
        self.__check()
        return self.__metadata

    def _admit(self, state, name, args):
        """Validate one call before it reaches the repository; True marks a write."""
        return False

    def _call(self, name, *args):
        self.__check()
        s = self.__state
        try:
            writing = self._admit(s, name, args)
            result = getattr(self.__repository, name)(*args)
            if writing: s['commit_possible'] = True
            return result
        except BaseException as exc:
            _fail(s, exc, self.commit_unknown)
            if s['commit_possible'] or not isinstance(exc, Exception):
                raise self.withheld(s['action_id'], s['commit_possible']) from None
            raise


def run_fenced(operation_type, state, bind, callback):
    """bind() -> (operation, guard). Returns the callback's fully encoded bytes.

    guard('entry') also covers no-DB callbacks and resolver side effects;
    guard('serialized_return') runs after projection, size checks and encoding.
    """
    context_token = None
    try:
        operation, guard = bind()
        context_token = operation_type.active.set(operation)
        guard('entry')
        result = callback(operation)
        if type(result) is not bytes:
            if inspect.iscoroutine(result): result.close()
            raise TypeError('operation must synchronously return fully encoded bytes')
        guard('serialized_return')
        return result
    except BaseException as exc:
        _fail(state, exc, operation_type.commit_unknown)
        if (isinstance(exc, operation_type.withheld) or state['commit_possible']
                or not isinstance(exc, Exception)):
            raise operation_type.withheld(state['action_id'], state['commit_possible']) from None
        raise
    finally:
        state['active'] = False
        if context_token is not None: operation_type.active.reset(context_token)
