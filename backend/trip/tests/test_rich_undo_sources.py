"""Current-profile version controls; these doubles are not actual API authority."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from cj_api.lio_exploration_profile import CONTEXT, snapshot
from cj_memory.runtime import RuntimeDenied
from cj_trip.domain import Denied, packed
from cj_trip.rich_undo_sources import ApiRichUndoSources


def fixture():
    state = dict(memory=False, message=True, calls=0, row=('current-message', 'current-run', 3, 4,
        CONTEXT+packed(snapshot({}, memory_epoch=7)).decode()))
    def message_check():
        if not state['message']: raise Denied('actual M frame withdrawn')
    message = SimpleNamespace(scope='owner', check=message_check)
    class Database:
        @contextmanager
        def connect(self, scope):
            assert scope == message.scope and state['memory']
            state['calls'] += 1
            yield SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: state['row']))
    class Memory:
        @contextmanager
        def hold(self, current_message):
            assert current_message is message
            state['memory'] = True
            def check():
                if not state['memory']: raise RuntimeDenied('actual Memory frame ended')
                message_check()
            try: yield SimpleNamespace(epoch=7, check=check)
            finally: state['memory'] = False
    source = ApiRichUndoSources(Database(), Memory())
    origin = dict(message_scope='owner', source=packed(dict(calendar_basis=dict(fixed_bindings=dict(
        reference=dict(conversation_id='actual-chat', generation='actual-generation'))))))
    args = dict(current=object(), previous=object(), active_origin=origin, previous_origin=origin, message_context=message)
    return source, args, state


def test_current_profile_is_read_inside_memory_hold_and_check_expires_with_it():
    source, args, state = fixture()
    with source.hold(object(), **args) as check:
        check()
        assert state['memory'] and state['calls'] >= 2
    with pytest.raises(RuntimeDenied): check()


def test_missing_or_changed_current_profile_cannot_be_substituted_with_history():
    source, args, state = fixture()
    state['row'] = None
    with pytest.raises(Denied, match='unavailable'):
        with source.hold(object(), **args): pass
    source, args, state = fixture()
    with pytest.raises(Denied, match='profile changed'):
        with source.hold(object(), **args) as check:
            state['row'] = ('later-message', *state['row'][1:])
            check()


def test_actual_owner_and_both_current_frames_are_required():
    source, args, state = fixture()
    args['active_origin'] = dict(args['active_origin'], message_scope='foreign')
    with pytest.raises(Denied, match='owner'):
        with source.hold(object(), **args): pass
    assert state['calls'] == 0
    source, args, state = fixture()
    with pytest.raises(Denied, match='M frame'):
        with source.hold(object(), **args) as check:
            state['message'] = False
            check()


def test_rebound_source_or_malformed_persisted_profile_is_withheld():
    source, args, state = fixture()
    with pytest.raises(Denied, match='binding changed'):
        with source.hold(object(), **args) as check:
            source.memory_holder = object()
            check()
    source, args, state = fixture()
    state['row'] = (*state['row'][:-1], CONTEXT+'{}')
    with pytest.raises(ValueError):
        with source.hold(object(), **args): pass
    with pytest.raises(Denied): ApiRichUndoSources(object(), None)
