"""TRIP synchronous response lifetime; no new AUTH policy or wire contract."""
from contextvars import ContextVar
from dataclasses import dataclass
import inspect
import threading
from .domain import Action, CommitUnknown
from cj_auth.interfaces import TrustedPrincipal

_active = ContextVar('trip_operation', default=None)


@dataclass(frozen=True, repr=False)
class OperationMetadata:
    principal: TrustedPrincipal  # Existing AUTH type; never a wire owner.
    scope: str        # Actual captured Repository.scope, not request input.


class OperationWithheld(Exception):
    """No private bytes; caller retains original Action for reconciliation."""
    def __init__(self, action_id, commit_possible):
        super().__init__('trip operation unavailable')
        self.action_id = action_id
        self.commit_possible = commit_possible
        # Even a precommit denial cannot disprove a previous original-ID attempt.
        self.recovery = 'reconcile_original' if action_id is not None else 'withhold'


class OperationContext:
    def __init__(self, repository, metadata, state):
        self.__repository, self.__metadata, self.__state = repository, metadata, state

    def __check(self):
        s = self.__state
        if (not s['active'] or s['blocked'] or _active.get() is not self
                or threading.get_ident() != s['thread']):
            s['blocked'] = True
            raise OperationWithheld(s['action_id'], s['commit_possible'])

    @property
    def metadata(self):
        self.__check()
        return self.__metadata

    def __call(self, name, *args):
        self.__check()
        s = self.__state
        try:
            if name in ('act', 'save_manual', 'prepare_manual', 'prepare_initialization', 'save_initialization','act_needs','prepare_needs','save_needs','act_scoped'):
                from .manual import ManualSave, ManualEdit
                from .needs_action import NeedsAction
                from .scoped_actions import ScopedAction
                from .manual_needs import NeedsEdit,NeedsSave
                from .initialization import Initialization, InitializationSave
                if s['action_id'] is not None: raise ValueError('one action per operation')
                expected = {'act':Action,'save_manual':ManualSave,'prepare_manual':ManualEdit,
                            'prepare_initialization':Initialization,'save_initialization':InitializationSave,'act_needs':NeedsAction,'act_scoped':ScopedAction,'prepare_needs':NeedsEdit,'save_needs':NeedsSave}[name]
                if not isinstance(args[0], expected): raise ValueError('validated original action required')
                s['action_id'] = args[0].request_id if name in ('prepare_manual','prepare_initialization','prepare_needs') else args[0].action_id
            result = getattr(self.__repository, name)(*args)
            if name in ('act', 'save_manual', 'prepare_manual', 'prepare_initialization', 'save_initialization','act_needs','prepare_needs','save_needs','act_scoped'): s['commit_possible'] = True
            return result
        except BaseException as exc:
            s['blocked'] = True
            s['commit_possible'] |= bool(getattr(exc, 'commit_possible', False)) or isinstance(exc, CommitUnknown)
            if s['commit_possible'] or not isinstance(exc, Exception):
                raise OperationWithheld(s['action_id'], s['commit_possible']) from None
            raise

    def prepare_initialization(self, value): return self.__call('prepare_initialization', value)
    def save_initialization(self, value): return self.__call('save_initialization', value)
    def initialization(self, request_id): return self.__call('initialization', request_id)
    def prepare_needs(self,request):return self.__call('prepare_needs',request)
    def save_needs(self,request):return self.__call('save_needs',request)
    def needs_preparation(self,request_id):return self.__call('needs_preparation',request_id)
    def act_scoped(self,request):return self.__call('act_scoped',request)
    def scoped_receipt(self,action_id):return self.__call('scoped_receipt',action_id)
    def scoped_detail(self,proposal_id):return self.__call('scoped_detail',proposal_id)
    def act_needs(self,request):return self.__call('act_needs',request)
    def act(self, action): return self.__call('act', action)
    def prepare_manual(self, edit): return self.__call('prepare_manual', edit)
    def save_manual(self, save): return self.__call('save_manual', save)
    def manual_preparation(self, request_id): return self.__call('manual_preparation', request_id)
    def query_action(self, action_id): return self.__call('query_action', action_id)
    def detail(self, trip_id): return self.__call('detail', trip_id)
    def list_trips(self, after='', limit=20): return self.__call('list_trips', after, limit)
    def proposal_detail(self, proposal_id): return self.__call('proposal_detail', proposal_id)


def with_operation(boundary, token, operation):
    state = dict(active=True, blocked=False, action_id=None, commit_possible=False,
                 thread=threading.get_ident())
    context_token = None
    try:
        repository, principal, check_binding = boundary._bind(token)
        def guard(stage):
            try:
                if state['blocked']: raise OperationWithheld(state['action_id'], state['commit_possible'])
                check_binding(stage)
            except BaseException:
                state['blocked'] = True
                raise
        repository.guard = guard
        context = OperationContext(repository, OperationMetadata(principal, repository.scope), state)
        context_token = _active.set(context)
        guard('entry')  # Also covers no-DB callbacks and resolver side effects.
        result = operation(context)
        if type(result) is not bytes:
            if inspect.iscoroutine(result): result.close()
            raise TypeError('operation must synchronously return fully encoded bytes')
        guard('serialized_return')  # After projection, size checks and encoding.
        return result
    except BaseException as exc:
        state['blocked'] = True
        state['commit_possible'] |= bool(getattr(exc, 'commit_possible', False)) or isinstance(exc, CommitUnknown)
        if isinstance(exc, OperationWithheld):
            raise OperationWithheld(state['action_id'], state['commit_possible']) from None
        if state['commit_possible'] or not isinstance(exc, Exception):
            raise OperationWithheld(state['action_id'], state['commit_possible']) from None
        raise
    finally:
        state['active'] = False
        if context_token is not None: _active.reset(context_token)
