"""#1994 T-1 (ADR-0012): item origin, tombstones, Lio write comparison, commit time and undo window.

scripts/pg_suites.py trip_autosave. Fresh restricted PG with the whole migration chain. Trip SQL runs as
cj_m1_runtime through the real LocalDatabase connection and the sole commit point (publish/act);
only fixtures, clock forgery and inspection use the cluster owner. Synthetic data only.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import migrate  # noqa: E402
from cj_agent.draft import trip_scope_for  # noqa: E402
from cj_api.local_app import ISSUER, LocalDatabase, local_confirmation, scope_for  # noqa: E402
from cj_trip.autosave import AutosaveConflict, require_undo_window  # noqa: E402
from cj_trip.domain import Action, Conflict, Denied, Proposal, packed  # noqa: E402
from cj_trip.lio_history import _current_for_undo  # noqa: E402
from cj_trip.postgres import Repository  # noqa: E402
from cj_trip.structured_v4 import adjacent_pairs  # noqa: E402

BASE = json.loads((ROOT / 'contracts/trip/structured-examples.4.json').read_bytes())['cases']['matched']['content']
LIO_PLAN, LIO_UNDO, USER_EDIT = 'lio-rich-plan.1', 'lio-rich-undo.1', 'needs-manual.2'


def expect(sqlstate, fn):
    try:
        fn()
    except psycopg.Error as error:
        assert sqlstate is None or error.sqlstate == sqlstate, (sqlstate, error.sqlstate, str(error)[:200])
        return
    raise AssertionError('statement was allowed')


def refused(code, fn):
    try:
        fn()
    except AutosaveConflict as error:
        assert error.code == code, (code, error.code)
        return
    raise AssertionError('Lio write was not refused: ' + code)


def document(change=None):
    doc = deepcopy(BASE)
    if change is not None:
        change(doc['items'])
    old = {(leg['from_item_id'], leg['to_item_id']): leg for leg in doc['legs']}
    doc['legs'] = [old.get((a, b)) or dict(day_index=d, from_item_id=a, to_item_id=b, state='unconfirmed', mode=None,
                   duration_seconds=None, distance_m=None, source=None,
                   time_semantics='provider_estimate_at_query_time', future_guaranteed=False)
                   for d, a, b in adjacent_pairs(doc)]
    return doc


def by_id(items, item_id):
    return next(item for item in items if item['id'] == item_id)


def retext(item_id, text):
    return lambda items: by_id(items, item_id).update(text=text)


def drop(*ids):
    def change(items):
        items[:] = [item for item in items if item['id'] not in ids]
    return change


def add(item_id, like='item-8', **fields):
    def change(items):
        value = deepcopy(by_id(items, like))
        value.update(id=item_id, **fields)
        items.append(value)
    return change


def chain(*changes):
    def change(items):
        for one in changes:
            one(items)
    return change


def main(config, conninfo):
    owner_db = lambda: psycopg.connect(**config)
    database = LocalDatabase(conninfo)
    subject = 'm4-synthetic-demo-aaaaaaaaaaaa'
    owner = scope_for(ISSUER, subject)
    database.provision(owner)
    scope = trip_scope_for(owner)
    repo = Repository(lambda: database.connect(owner), scope, confirm=local_confirmation,
                      structured=True, calendar=True, rich=True)
    assert repo.autosave is None
    counter = [0]

    def publish(basis, content, *, trip='trip-auto', expected=None):
        counter[0] += 1
        current = repo.detail(trip)
        version = (current.version if current else 0) if expected is None else expected
        proposal = Proposal(f'p{counter[0]}', trip, version, basis, int(time.time()) + 3600, packed(content))
        return proposal, repo.publish(proposal)

    def act(proposal, digest, action_id=None):
        return repo.act(Action(action_id or 'a-' + proposal.proposal_id, 'accept', proposal.proposal_id, digest, 'ref'))

    def commit(basis, content, **kwargs):
        return act(*publish(basis, content, **kwargs))

    def origins(version, trip='trip-auto'):
        with owner_db() as conn:
            return dict(conn.execute('SELECT item_id,origin FROM cj_trip_item_origin WHERE scope=%s AND trip_id=%s '
                                     'AND trip_version=%s', (scope, trip, version)).fetchall())

    def rows(table):
        with owner_db() as conn:
            return conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s', (scope,)).fetchone()[0]

    def state():
        return (repo.detail('trip-auto'), rows('cj_trip_item_origin'), rows('cj_trip_item_tombstone'),
                rows('cj_trip_commit_time'), rows('cj_trip_receipt'))

    def committed(action_id):
        with owner_db() as conn:
            return conn.execute('SELECT autosave FROM cj_trip_commit_time WHERE scope=%s AND action_id=%s',
                                (scope, action_id)).fetchone()

    ids = [item['id'] for item in BASE['items']]

    # --- Lio adds points, changes its own points (switch on) ----------------------------------------
    repo.autosave = True
    first = commit(LIO_PLAN, document())
    assert first.committed_version == 1 and origins(1) == dict.fromkeys(ids, 'lio')
    assert committed(first.action_id) == (True,)
    one = repo.autosave_receipt(first.action_id)
    assert (one.first, one.committed_version, one.restore_version, one.restore_hash) == (True, 1, None, None)
    assert one.content_version == 'structured.4' and one.content_sha256 == sha256(repo.detail('trip-auto').content).hexdigest()
    v1 = repo.detail('trip-auto')
    added = commit(LIO_PLAN, document(add('item-9', text='Lio new stop')))
    assert added.committed_version == 2 and origins(2) == dict.fromkeys(ids + ['item-9'], 'lio')
    two = repo.autosave_receipt(added.action_id)
    assert (two.first, two.restore_version, two.restore_hash, two.restore_content_version) == (
        False, 1, sha256(v1.content).hexdigest(), 'structured.4')
    assert (two.undo_until - one.undo_until).total_seconds() >= 0
    with owner_db() as conn:
        at = conn.execute('SELECT committed_at FROM cj_trip_commit_time WHERE scope=%s AND action_id=%s',
                          (scope, added.action_id)).fetchone()[0]
    assert (two.undo_until - at).total_seconds() == 24 * 3600
    lio_own = commit(LIO_PLAN, document(chain(add('item-9', text='Lio new stop'), retext('item-3', 'Lio rewrote 3'))))
    assert lio_own.committed_version == 3 and set(origins(3).values()) == {'lio'}
    print('PASS Lio adds points and rewrites its own points; all lio; receipt restore = previous version, first once')

    # --- a person's edit: changed points become user, removed points leave tombstones ---------------
    def user_change(items):
        retext('item-1', 'I changed 1')(items)
        retext('item-5', 'I changed 5')(items)
        retext('item-3', 'Lio rewrote 3')(items)
        drop('item-2', 'item-4')(items)
    user_doc = document(chain(add('item-9', text='Lio new stop'), user_change))
    edit = commit(USER_EDIT, user_doc)
    assert edit.committed_version == 4 and committed(edit.action_id) == (False,)
    assert repo.autosave_receipt(edit.action_id) is None
    after_user = origins(4)
    assert after_user == {'item-1': 'user', 'item-5': 'user', 'item-3': 'lio', 'item-6': 'lio', 'item-7': 'lio',
                          'item-8': 'lio', 'item-9': 'lio'}, after_user
    with owner_db() as conn:
        marks = conn.execute('SELECT item_id,amap_id,trip_version FROM cj_trip_item_tombstone WHERE scope=%s ORDER BY item_id',
                             (scope,)).fetchall()
    assert marks == [('item-2', 'synthetic-poi-2', 4), ('item-4', None, 4)], marks
    print('PASS person edit: changed points become user, unchanged keep lio; removed points tombstoned with Gaode id')

    # --- Lio cannot touch user points or add back removed ones; nothing partial is written -----------
    def base_user(*changes):
        return document(chain(add('item-9', text='Lio new stop'), user_change, *changes))
    before = state()
    refused('user_item_changed', lambda: commit(LIO_PLAN, base_user(retext('item-1', 'Lio overwrote'))))
    refused('user_item_changed', lambda: commit(LIO_PLAN, base_user(drop('item-5'))))
    def swap(items):
        a, b = items.index(by_id(items, 'item-1')), items.index(by_id(items, 'item-5'))
        items[a], items[b] = items[b], items[a]
    refused('user_order_changed', lambda: commit(LIO_PLAN, base_user(swap)))
    refused('tombstone_readded', lambda: commit(LIO_PLAN, base_user(add('item-2', like='item-1', text='back'))))
    refused('tombstone_readded', lambda: commit(LIO_PLAN, base_user(add('item-4', text='back again'))))
    refused('tombstone_readded', lambda: commit(LIO_PLAN, base_user(
        lambda items: items.append(dict(deepcopy(BASE['items'][1]), id='fresh-same-place')))))
    refused('too_large', lambda: commit(LIO_PLAN, base_user(*(add(f'bulk-{n}') for n in range(31)))))
    assert state() == before
    print('PASS Lio refused: change/remove/reorder user points, tombstone id or Gaode id, >30 new points; no partial write')

    allowed = commit(LIO_PLAN, base_user(retext('item-6', 'Lio changed its 6'), drop('item-7'), add('item-10')))
    assert allowed.committed_version == 5 and committed(allowed.action_id) == (True,)
    assert origins(5) == {'item-1': 'user', 'item-5': 'user', 'item-3': 'lio', 'item-6': 'lio', 'item-8': 'lio',
                          'item-9': 'lio', 'item-10': 'lio'}
    assert rows('cj_trip_item_tombstone') == 2   # Lio's removal of its own point leaves no tombstone
    print('PASS Lio may still add, rewrite and remove its own points between user points')

    # --- trigger: user never returns to lio; append-only; only the current version ----------------
    with owner_db() as conn:
        conn.execute('UPDATE cj_trip_record SET version=6 WHERE scope=%s AND trip_id=%s', (scope, 'trip-auto'))
        expect('42501', lambda: conn.execute("INSERT INTO cj_trip_item_origin VALUES(%s,'trip-auto',6,'item-1','lio')", (scope,)))
        conn.rollback()
    with owner_db() as conn:
        conn.execute('UPDATE cj_trip_record SET version=6 WHERE scope=%s AND trip_id=%s', (scope, 'trip-auto'))
        conn.execute("INSERT INTO cj_trip_item_origin VALUES(%s,'trip-auto',6,'item-1','user')", (scope,))
        conn.execute("INSERT INTO cj_trip_item_origin VALUES(%s,'trip-auto',6,'item-6','user')", (scope,))   # lio -> user
        conn.rollback()
    with owner_db() as conn:
        expect('42501', lambda: conn.execute("INSERT INTO cj_trip_item_origin VALUES(%s,'trip-auto',3,'item-x','lio')", (scope,)))
        conn.rollback()
        for table in ('cj_trip_item_origin', 'cj_trip_item_tombstone', 'cj_trip_commit_time'):
            expect('42501', lambda: conn.execute(f'UPDATE {table} SET scope=scope'))
            conn.rollback()
            expect('42501', lambda: conn.execute(f'TRUNCATE {table} CASCADE'))
            conn.rollback()
    runtime = dict(database.conninfo)
    with psycopg.connect(**runtime) as conn:
        for table in ('cj_trip_item_origin', 'cj_trip_item_tombstone', 'cj_trip_commit_time'):
            for statement in (f'DELETE FROM {table}', f'UPDATE {table} SET scope=scope', f'TRUNCATE {table}'):
                expect('42501', lambda: conn.execute(statement))
                conn.rollback()
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone() == (0,)   # RLS: no scope bound
            conn.rollback()
    print('PASS trigger keeps user from returning to lio; UPDATE/TRUNCATE refused; runtime cannot delete; RLS by scope')

    # --- switch off: today's behaviour, origin still recorded -------------------------------------
    repo.autosave = None
    off = commit(LIO_PLAN, base_user(retext('item-6', 'Lio changed its 6'), drop('item-7'), add('item-10'),
                                     retext('item-1', 'Lio overwrote while off'), add('item-2', like='item-1', text='back')))
    assert off.committed_version == 6 and committed(off.action_id) == (False,)
    assert repo.autosave_receipt(off.action_id) is None
    assert origins(6)['item-1'] == 'user' and origins(6)['item-2'] == 'lio'
    print('PASS switch off: Lio write is not compared (as today); origin and commit time still recorded, no receipt')

    # --- concurrent writes: the version CAS refuses the second; replay returns the original ----------
    repo.autosave = True
    v6 = repo.detail('trip-auto')
    lio_a = publish(LIO_PLAN, json.loads(v6.content) | dict(title='Lio A'))
    user_b = publish(USER_EDIT, json.loads(v6.content) | dict(title='Person B'))
    won = act(*user_b, 'user-b')
    assert won.committed_version == 7
    before = state()
    try:
        act(*lio_a, 'lio-a')
    except Conflict as error:
        assert str(error) == 'trip version conflict' and not isinstance(error, AutosaveConflict)
    else:
        raise AssertionError('stale Lio write committed')
    assert state() == before
    replay_source = publish(LIO_PLAN, json.loads(repo.detail('trip-auto').content) | dict(title='Lio C'))
    original = act(*replay_source, 'lio-c')
    receipt = repo.autosave_receipt('lio-c')
    assert act(*replay_source, 'lio-c') == original and repo.autosave_receipt('lio-c') == receipt
    try:
        repo.act(Action('lio-c', 'accept', replay_source[0].proposal_id, replay_source[1], 'other-ref'))
    except Conflict as error:
        assert str(error) == 'action ID input conflict'
    else:
        raise AssertionError('reused action id with other input')
    assert rows('cj_trip_commit_time') == rows('cj_trip_receipt')
    print('PASS concurrent edit wins by version CAS, stale Lio write refused whole; replay returns the original receipt')

    # --- undo window (DB clock) and origin of an undo ---------------------------------------------
    current = repo.detail('trip-auto')
    assert current.version == 8

    def window(version):
        with repo.transaction() as cur:
            require_undo_window(repo, cur, SimpleNamespace(trip_id='trip-auto', version=version))

    def backdate(action_id, hours):
        with owner_db() as conn:
            conn.execute("SET session_replication_role=replica")   # test-only forgery of the DB time
            conn.execute("UPDATE cj_trip_commit_time SET committed_at=clock_timestamp()-make_interval(hours=>%s) "
                         'WHERE scope=%s AND action_id=%s', (hours, scope, action_id))
    window(8)
    backdate('lio-c', 23)
    window(8)
    backdate('lio-c', 25)
    try:
        window(8)
    except Denied as error:
        assert str(error) == 'autosave undo window expired'
    else:
        raise AssertionError('expired autosave undo allowed')
    backdate(edit.action_id, 30)
    window(4)                                # not an autosave version: no time limit (as today)
    with owner_db() as conn:
        conn.execute('INSERT INTO cj_trip_record VALUES(%s,%s,1,%s)', (scope, 'trip-old', packed(document())))
    old_request = SimpleNamespace(trip_id='trip-auto', expected_version=7,
                                  original_hash=sha256(repo.detail('trip-auto').content).hexdigest())
    with repo.transaction() as cur:
        try:
            _current_for_undo(repo, cur, old_request)
        except Conflict as error:
            assert str(error) == 'original Trip changed'
        else:
            raise AssertionError('undo of a version with a newer version allowed')
    backdate('lio-c', 1)
    restore = Proposal('undo-p', 'trip-auto', 8, LIO_UNDO, int(time.time()) + 3600, user_b[0].content)
    undone = act(restore, repo.publish(restore), 'undo-lio-c')
    assert undone.committed_version == 9 and committed('undo-lio-c') == (False,) and origins(9) == origins(7)
    not_restore = Proposal('undo-q', 'trip-auto', 9, LIO_UNDO, int(time.time()) + 3600, packed(document(retext('item-8', 'x'))))
    act(not_restore, repo.publish(not_restore), 'undo-other')
    assert origins(10)['item-8'] == 'user'   # an "undo" that is not the previous bytes counts as a person's write
    print('PASS undo window: 23 h allowed, 25 h refused, non-autosave unlimited, newer version refused; undo restores origins')

    # --- points from before 0061 count as user ----------------------------------------------------
    pre = commit(LIO_PLAN, document(add('item-11')), trip='trip-old')
    assert pre.committed_version == 2 and origins(2, 'trip-old') == dict.fromkeys(ids, 'user') | {'item-11': 'lio'}
    refused('user_item_changed', lambda: commit(LIO_PLAN, document(retext('item-1', 'x')), trip='trip-old'))
    print('PASS Trip points without an origin record (before 0061) are user; Lio can only add')

    # --- down refused while rows exist ---------------------------------------------------------------
    with owner_db() as conn:
        conn.autocommit = True
        try:
            migrate.down(conn, migrate.load(), 60)
        except psycopg.Error as error:
            assert 'retained private data' in str(error)
        else:
            raise AssertionError('down ran with autosave records present')
        assert conn.execute("SELECT to_regclass('public.cj_trip_item_origin')").fetchone()[0] is not None
    print('PASS 0061 down refused while records exist')


if __name__ == '__main__':
    path = Path(os.environ['CJ_E2E_CONNINFO'])
    main(json.loads(path.read_text()), path)
