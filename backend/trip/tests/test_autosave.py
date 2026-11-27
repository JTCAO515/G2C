"""#1994 T-1 pure rules: writer classification, item origin, tombstones and the Lio write comparison."""
import pytest

from cj_trip.autosave import (LIO, UNDO, USER, MAX_NEW_DAYS, MAX_NEW_ITEMS, AutosaveConflict,
                              check_lio_write, item_origins, tombstones, writer)
from cj_trip.domain import Conflict


def item(item_id, text=None, amap=None):
    value = dict(id=item_id, text=text or item_id)
    if amap is not None:
        value['place'] = dict(state='matched', amap_id=amap)
    return value


def refused(code, *args, **kwargs):
    with pytest.raises(AutosaveConflict) as error:
        check_lio_write(*args, **kwargs)
    assert error.value.code == code and str(error.value) == code and isinstance(error.value, Conflict)


@pytest.mark.parametrize('basis,expected', [
    ('lio-plan.1', LIO), ('lio-edit.1', LIO), ('lio-calendar-plan.1', LIO), ('lio-calendar-edit.1', LIO),
    ('lio-rich-plan.1', LIO), ('lio-undo.1', UNDO), ('lio-calendar-undo.1', UNDO), ('lio-rich-undo.1', UNDO),
    ('lio-date-convert.1', USER), ('needs-manual.1', USER), ('needs-manual.2', USER), ('manual-unbound.1', USER),
    ('manual-initialization.1', USER), ('source-initialization.1', USER), ('scoped-edit.1', USER),
    ('run-abc', USER), ('needs-run-abc', USER), ('lio-plan.2', USER), ('basis1', USER)])
def test_writer_is_decided_by_basis_version_only_and_defaults_to_user(basis, expected):
    assert writer(basis) == expected


def test_lio_write_marks_new_and_own_items_lio_and_keeps_user_items_user():
    previous = [item('a'), item('b'), item('c')]
    origins = {'a': USER, 'b': LIO}                         # c has no record: before 0061, so user
    new = [item('a'), item('b', 'changed by Lio'), item('c'), item('d')]
    assert item_origins(LIO, previous, origins, new) == dict(a=USER, b=LIO, c=USER, d=LIO)
    assert item_origins(LIO, [], {}, [item('x'), item('y')]) == dict(x=LIO, y=LIO)   # new Trip by Lio


def test_user_write_marks_new_or_changed_items_user_and_keeps_unchanged_origins():
    previous = [item('a'), item('b'), item('c')]
    origins = {'a': LIO, 'b': LIO, 'c': USER}
    new = [item('b'), item('a', 'renamed'), item('c'), item('e')]
    assert item_origins(USER, previous, origins, new) == dict(b=LIO, a=USER, c=USER, e=USER)
    # A move only (same bytes) keeps the origin; the comparison is by packed item bytes.
    assert item_origins(USER, previous, origins, [item('c'), item('b'), item('a')]) == dict(c=USER, b=LIO, a=LIO)


def test_undo_restores_previous_origins_but_never_turns_user_back_to_lio():
    undone = [item('a'), item('b', 'touched'), item('n')]
    undone_origins = {'a': LIO, 'b': USER, 'n': LIO}
    restored = [item('a'), item('b'), item('old')]
    restored_origins = {'a': LIO, 'b': LIO, 'old': LIO}
    assert item_origins(UNDO, undone, undone_origins, restored, restored_origins) == dict(a=LIO, b=USER, old=LIO)
    # Restored version without records (before 0061): user.
    assert item_origins(UNDO, undone, undone_origins, restored, {}) == dict(a=USER, b=USER, old=USER)


def test_an_undo_that_kept_fixed_points_is_still_an_undo_not_a_person_write():
    # #2041 P2 (defensive; every undo entry appends version-1 exactly today): an undo-basis commit that
    # differs from version-1, e.g. one keeping a point of the undone version, is still an undo.
    undone = [item('a', 'Lio moved'), item('f', 'fixed by Lio'), item('n')]
    undone_origins = {'a': LIO, 'f': LIO, 'n': LIO}
    restored_version = [item('a'), item('f', 'before')]
    restored_origins = {'a': LIO, 'f': LIO}
    appended = [item('a'), item('f', 'fixed by Lio')]          # f kept from the undone version
    assert item_origins(UNDO, undone, undone_origins, appended, restored_origins,
                        restored_version) == dict(a=LIO, f=LIO)
    # The point the undo dropped (n) is Lio's: no tombstone, so a later autosave may add it again.
    assert tombstones(UNDO, undone, appended) == []
    check_lio_write(appended, dict(a=LIO, f=LIO), [], appended + [item('n')])
    # A user point stays user; a point matching neither version is user.
    assert item_origins(UNDO, undone, dict(undone_origins, f=USER), appended + [item('x')], restored_origins,
                        restored_version) == dict(a=LIO, f=USER, x=USER)


def test_only_a_user_write_leaves_tombstones_with_the_gaode_id_when_known():
    previous = [item('a', amap='poi-a'), item('b'), item('c')]
    new = [item('c')]
    assert tombstones(USER, previous, new) == [('a', 'poi-a'), ('b', None)]
    assert tombstones(LIO, previous, new) == [] and tombstones(UNDO, previous, new) == []
    unconfirmed = dict(id='u', text='u', place=dict(state='unconfirmed', amap_id=None))
    assert tombstones(USER, [unconfirmed], []) == [('u', None)]


def test_lio_may_add_points_and_change_or_remove_its_own_points():
    previous = [item('u1'), item('l1'), item('u2'), item('l2')]
    origins = {'u1': USER, 'l1': LIO, 'u2': USER, 'l2': LIO}
    new = [item('new'), item('u1'), item('l1', 'Lio rewrote its own'), item('u2')]   # l2 removed
    check_lio_write(previous, origins, [], new)
    check_lio_write([], {}, [], [item(f'i{n}') for n in range(MAX_NEW_ITEMS)])


def test_lio_cannot_change_move_or_remove_a_user_point():
    previous = [item('u1'), item('l1'), item('u2'), item('old')]   # old: no record, counts as user
    origins = {'u1': USER, 'l1': LIO, 'u2': USER}
    refused('user_item_changed', previous, origins, [], [item('u1', 'edited'), item('l1'), item('u2'), item('old')])
    refused('user_item_changed', previous, origins, [], [item('u1'), item('l1'), item('u2')])
    refused('user_item_changed', previous, origins, [], [item('u1'), item('l1'), item('u2'), item('old', 'x')])
    refused('user_order_changed', previous, origins, [], [item('u2'), item('l1'), item('u1'), item('old')])
    # Moving a Lio point between user points does not change the user order.
    check_lio_write(previous, origins, [], [item('l1'), item('u1'), item('u2'), item('old')])


def test_lio_cannot_add_back_a_point_the_person_removed():
    previous = [item('a')]
    origins = {'a': LIO}
    marks = [('gone', None), ('gone-place', 'poi-9')]
    refused('tombstone_readded', previous, origins, marks, [item('a'), item('gone')])
    refused('tombstone_readded', previous, origins, marks, [item('a'), item('fresh-id', amap='poi-9')])
    # Without a Gaode id only the item id is blocked, never a name match.
    check_lio_write(previous, origins, marks, [item('a'), item('fresh-id', 'gone'), item('other', amap='poi-1')])
    # Re-pointing an existing Lio point at a removed Gaode place brings that place back too (#2041 P1).
    refused('tombstone_readded', previous, origins, marks, [item('a', amap='poi-9')])
    # A Lio point that already sat at that place before the removal keeps it.
    kept = [item('a', amap='poi-9')]
    check_lio_write(kept, origins, marks, [item('a', amap='poi-9'), item('new')])
    # #2041 P3: a new point that only reuses the item id of a removed *matched* point (model ids such as
    # item-3) is not that place; its place decides.
    check_lio_write(previous, origins, marks, [item('a'), item('gone-place', amap='poi-1')])
    check_lio_write(previous, origins, marks, [item('a'), item('gone-place')])
    refused('tombstone_readded', previous, origins, marks, [item('a'), item('gone-place', amap='poi-9')])


def test_one_lio_write_is_bounded_in_new_points_and_new_days():
    refused('too_large', [], {}, [], [item(f'i{n}') for n in range(MAX_NEW_ITEMS + 1)])
    days = [dict(day_index=n) for n in range(1, MAX_NEW_DAYS + 2)]
    refused('too_large', [], {}, [], [item('a')], previous_days=[], new_days=days)
    check_lio_write([], {}, [], [item('a')], previous_days=days[:1], new_days=days)   # 7 new days


def test_unknown_refusal_code_is_not_constructed():
    with pytest.raises(ValueError):
        AutosaveConflict('partial')


class _NoAuditTables:
    """A cursor on a frozen chain without 0061 (Supabase target at 48, older local fixtures)."""
    def execute(self, sql, params=None):
        assert 'to_regclass' in sql, 'nothing but the schema probe may run without 0061'

    def fetchone(self):
        return (False,)


def test_without_0061_the_switch_off_keeps_today_and_the_switch_on_refuses():
    from types import SimpleNamespace
    from cj_trip.autosave import record_commit, require_undo_window
    from cj_trip.domain import Denied
    proposal = SimpleNamespace(basis_version='lio-plan.1', expected_version=1, trip_id='t', content=b'{}')
    assert record_commit(SimpleNamespace(autosave=None, scope='s'), _NoAuditTables(), proposal, b'{}') is None
    require_undo_window(SimpleNamespace(scope='s'), _NoAuditTables(), SimpleNamespace(trip_id='t', version=2))
    with pytest.raises(Denied):
        record_commit(SimpleNamespace(autosave=True, scope='s'), _NoAuditTables(), proposal, b'{}')
