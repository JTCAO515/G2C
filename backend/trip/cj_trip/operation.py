"""TRIP synchronous response lifetime; no new AUTH policy or wire contract."""
from contextvars import ContextVar
from dataclasses import dataclass
from .domain import Action, CommitUnknown
from cj_auth.interfaces import TrustedPrincipal
from cj_auth.operation_fence import FencedOperation, new_state, run_fenced

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


_PREPARING = ('prepare_manual', 'prepare_initialization', 'prepare_needs', 'prepare_source_initialization')


def _write_types():
    from .manual import ManualSave, ManualEdit
    from .needs_action import NeedsAction
    from .scoped_actions import ScopedAction
    from .manual_needs import NeedsEdit, NeedsSave
    from .initialization import Initialization, InitializationSave
    from .source_initialization import SourceInitialization, SourceInitializationSave
    from .lio_history import Undo
    from .calendar_history import CalendarUndo
    return {'act': Action, 'undo_calendar': CalendarUndo, 'save_manual': ManualSave, 'prepare_manual': ManualEdit,
            'prepare_initialization': Initialization, 'save_initialization': InitializationSave,
            'act_needs': NeedsAction, 'act_scoped': ScopedAction, 'prepare_needs': NeedsEdit,
            'save_needs': NeedsSave, 'prepare_source_initialization': SourceInitialization,
            'save_source_initialization': SourceInitializationSave, 'undo_lio': Undo}


class OperationContext(FencedOperation):
    active, withheld, commit_unknown = _active, OperationWithheld, CommitUnknown

    def _admit(self, s, name, args):
        expected = _write_types().get(name)
        if expected is None: return False
        if s['action_id'] is not None: raise ValueError('one action per operation')
        if not isinstance(args[0], expected): raise ValueError('validated original action required')
        s['action_id'] = args[0].request_id if name in _PREPARING else args[0].action_id
        return True

    def prepare_source_initialization(self,value):return self._call('prepare_source_initialization',value)
    def save_source_initialization(self,value):return self._call('save_source_initialization',value)
    def source_initialization(self,value):return self._call('source_initialization',value)
    def source_initialization_receipt(self,value):return self._call('source_initialization_receipt',value)
    def prepare_initialization(self, value): return self._call('prepare_initialization', value)
    def save_initialization(self, value): return self._call('save_initialization', value)
    def initialization(self, request_id): return self._call('initialization', request_id)
    def prepare_needs(self,request):return self._call('prepare_needs',request)
    def save_needs(self,request):return self._call('save_needs',request)
    def needs_preparation(self,request_id):return self._call('needs_preparation',request_id)
    def act_scoped(self,request):return self._call('act_scoped',request)
    def scoped_receipt(self,action_id):return self._call('scoped_receipt',action_id)
    def scoped_detail(self,proposal_id):return self._call('scoped_detail',proposal_id)
    def discover_scoped(self,query,encode):return self._call('discover_scoped',query,encode)
    def scoped_result(self,result_id,encode):return self._call('scoped_result',result_id,encode)
    def discover_needs(self,query,encode):return self._call('discover_needs',query,encode)
    def discover_place_needs(self,query,encode):return self._call('discover_place_needs',query,encode)
    def discover_demo_needs(self,query,encode):return self._call('discover_demo_needs',query,encode)
    def act_needs(self,request):return self._call('act_needs',request)
    def act(self, action): return self._call('act', action)
    def prepare_manual(self, edit): return self._call('prepare_manual', edit)
    def save_manual(self, save): return self._call('save_manual', save)
    def manual_preparation(self, request_id): return self._call('manual_preparation', request_id)
    def query_action(self, action_id): return self._call('query_action', action_id)
    def calendar_conversion_receipt(self, request): return self._call('calendar_conversion_receipt', request)
    def calendar_plan_receipt(self, binding): return self._call('calendar_plan_receipt', binding)
    def calendar_edit_receipt(self, binding): return self._call('calendar_edit_receipt', binding)
    def lio_revisions(self, trip_id, *, before=None, limit=10): return self._call('lio_revisions', trip_id, before, limit)
    def lio_current_trip(self, needs_scope, needs_id): return self._call('lio_current_trip', needs_scope, needs_id)
    def lio_plan_receipt(self, binding): return self._call('lio_plan_receipt', binding)
    def lio_edit_receipt(self, binding): return self._call('lio_edit_receipt', binding)
    def undo_lio(self, request): return self._call('undo_lio', request)
    def undo_calendar(self, request): return self._call('undo_calendar', request)
    def lio_undo_receipt(self, request): return self._call('lio_undo_receipt', request)
    def detail(self, trip_id): return self._call('detail', trip_id)
    def read_decision_source(self,query,project,*,max_source_bytes,max_result_bytes):
        return self._call('read_decision_source',query,project,max_source_bytes,max_result_bytes)
    def list_trips(self, after='', limit=20): return self._call('list_trips', after, limit)
    def proposal_detail(self, proposal_id): return self._call('proposal_detail', proposal_id)


def with_operation(boundary, token, operation):
    state = new_state()

    def bind():
        repository, principal, check_binding = boundary._bind(token)

        def guard(stage):
            try:
                if state['blocked']: raise OperationWithheld(state['action_id'], state['commit_possible'])
                check_binding(stage)
            except BaseException:
                state['blocked'] = True
                raise
        repository.guard = guard
        return OperationContext(repository, OperationMetadata(principal, repository.scope), state), guard

    return run_fenced(OperationContext, state, bind, operation)
