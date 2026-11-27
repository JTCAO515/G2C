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
    # item-2 was a matched point: its place is what is blocked, under its old id or any other (#2041 P3).
    refused('tombstone_readded', lambda: commit(LIO_PLAN, base_user(
        lambda items: items.append(dict(deepcopy(BASE['items'][1]), text='back')))))
    refused('tombstone_readded', lambda: commit(LIO_PLAN, base_user(add('item-4', text='back again'))))
    refused('tombstone_readded', lambda: commit(LIO_PLAN, base_user(
        lambda items: items.append(dict(deepcopy(BASE['items'][1]), id='fresh-same-place')))))
    refused('too_large', lambda: commit(LIO_PLAN, base_user(*(add(f'bulk-{n}') for n in range(31)))))
    assert state() == before
    print('PASS Lio refused: change/remove/reorder user points, placeless tombstone id or Gaode id, >30 new points; no partial write')

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
    assert origins(10)['item-8'] == 'user'   # a point matching neither version counts as a person's write
    # #2041 P2: an undo that keeps a fixed point of the undone version (protect_fixed) is still an undo:
    # the dropped Lio point leaves no tombstone and the kept point keeps its Lio origin.
    kept = chain(retext('item-8', 'x'), add('lio-fixed', text='fixed by Lio'))
    lio = commit(LIO_PLAN, document(chain(kept, add('lio-extra', text='Lio extra'))))
    assert lio.committed_version == 11 and origins(11)['lio-fixed'] == origins(11)['lio-extra'] == 'lio'
    marks = rows('cj_trip_item_tombstone')
    keep_fixed = Proposal('undo-r', 'trip-auto', 11, LIO_UNDO, int(time.time()) + 3600, packed(document(kept)))
    assert act(keep_fixed, repo.publish(keep_fixed), 'undo-keep-fixed').committed_version == 12
    assert origins(12) == origins(10) | {'lio-fixed': 'lio'} and rows('cj_trip_item_tombstone') == marks
    commit(LIO_PLAN, document(chain(kept, add('lio-extra', text='Lio extra'))))   # may add it back
    print('PASS undo window: 23 h allowed, 25 h refused, non-autosave unlimited, newer version refused; undo restores origins')

    # --- points from before 0061 count as user ----------------------------------------------------
    pre = commit(LIO_PLAN, document(add('item-11')), trip='trip-old')
    assert pre.committed_version == 2 and origins(2, 'trip-old') == dict.fromkeys(ids, 'user') | {'item-11': 'lio'}
    refused('user_item_changed', lambda: commit(LIO_PLAN, document(retext('item-1', 'x')), trip='trip-old'))
    print('PASS Trip points without an origin record (before 0061) are user; Lio can only add')

    # --- withdrawn Trip (ADR-0012 revision 1): read-only at the sole commit point, not listed --------
    from cj_trip.autosave import WITHDRAW_BASIS, WithdrawnConflict
    repo.autosave = True
    made = commit(LIO_PLAN, document(), trip='trip-wd')
    wd1 = repo.detail('trip-wd')
    mark = Proposal('wd-p', 'trip-wd', 1, WITHDRAW_BASIS, int(time.time()) + 3600, wd1.content)
    marked = act(mark, repo.publish(mark), 'wd-1')
    assert (marked.committed_version, committed('wd-1'), origins(2, 'trip-wd')) == (2, (False,), origins(1, 'trip-wd'))
    with owner_db() as conn:
        expect('42501', lambda: conn.execute('INSERT INTO cj_trip_withdrawal(scope,trip_id,withdrawn_version,undo_action_id) '
                                             "VALUES(%s,'trip-wd',2,%s)", (scope, made.action_id)))
        conn.rollback()
        expect('42501', lambda: conn.execute('INSERT INTO cj_trip_withdrawal(scope,trip_id,withdrawn_version,undo_action_id) '
                                             "VALUES(%s,'trip-auto',2,'wd-1')", (scope,)))
        conn.rollback()
        conn.execute('INSERT INTO cj_trip_withdrawal(scope,trip_id,withdrawn_version,undo_action_id,created_at) '
                     "VALUES(%s,'trip-wd',2,'wd-1','2000-01-01')", (scope,))
        assert conn.execute("SELECT created_at>clock_timestamp()-interval '1 minute' FROM cj_trip_withdrawal WHERE scope=%s",
                            (scope,)).fetchone() == (True,)   # DB clock, never the caller's value
    before = (repo.detail('trip-wd'), rows('cj_trip_receipt'), rows('cj_trip_item_origin'), rows('cj_trip_commit_time'))
    for basis, content in ((USER_EDIT, document(retext('item-1', 'mine'))), (LIO_PLAN, document(add('item-w'))),
                           (LIO_UNDO, document()), (WITHDRAW_BASIS, document())):
        try:
            commit(basis, content, trip='trip-wd')
        except WithdrawnConflict as error:
            assert isinstance(error, Conflict) and str(error) == 'withdrawn Trip is read-only'
        else:
            raise AssertionError('withdrawn Trip accepted a write: ' + basis)
    stale = publish(USER_EDIT, document(retext('item-2', 'x')), trip='trip-wd')
    try:
        repo.act(Action('wd-reject', 'reject', stale[0].proposal_id, stale[1], 'ref'))
    except WithdrawnConflict:
        pass
    else:
        raise AssertionError('withdrawn Trip took an action')
    assert act(mark, repo.publish(mark), 'wd-1') == marked   # replay: the original receipt
    assert (repo.detail('trip-wd'), rows('cj_trip_receipt'), rows('cj_trip_item_origin'), rows('cj_trip_commit_time')) == before
    assert 'trip-wd' not in [trip.trip_id for trip in repo.list_trips(limit=100)]
    assert 'trip-auto' in [trip.trip_id for trip in repo.list_trips(limit=100)]
    assert repo.detail('trip-wd').version == 2 and len(repo.lio_revisions('trip-wd', None, 10)) == 2
    with owner_db() as conn:
        expect('42501', lambda: conn.execute('UPDATE cj_trip_withdrawal SET scope=scope'))
        conn.rollback()
        expect('42501', lambda: conn.execute('TRUNCATE cj_trip_withdrawal CASCADE'))
        conn.rollback()
    with psycopg.connect(**runtime) as conn:
        for statement in ('DELETE FROM cj_trip_withdrawal', 'UPDATE cj_trip_withdrawal SET scope=scope', 'TRUNCATE cj_trip_withdrawal'):
            expect('42501', lambda: conn.execute(statement))
            conn.rollback()
    print('PASS withdrawn Trip: withdrawal version keeps origins, mark bound to its receipt and DB clock; every write '
          'and action refused (WithdrawnConflict), replay returns the original; not listed, detail and history kept')

    # --- trip_receipt projection (LIO-answer-rich.1, part 2): table truth, undo state at read -----------
    from cj_api.lio_trip_receipt import project, read, undo_action_id
    from cj_api.lio_trip_routes import _rich_target
    from cj_message.lio_trip_receipt import effect
    from cj_trip.lio_history import edit_action_id, plan_action_id
    sys.path.insert(0, str(ROOT / 'contracts/message'))
    import check_lio_answer_rich as rich_check

    from cj_message.lio_rich_receipt import wire as rich_wire
    examples = {e['name']: e['rich']['trip_receipt'] for e in json.loads(
        (ROOT / 'contracts/message/lio-answer-rich-examples.1.json').read_bytes())['valid'] if 'trip_receipt' in e['rich']}

    def shape(value):
        return {k: shape(v) if type(v) is dict else type(v).__name__ for k, v in value.items() if k != 'summary'}

    def receipt_of(run, *effects, undo_route=True):
        with repo.transaction() as cur:
            result = project(repo, cur, run, list(effects), undo_route=undo_route)
        if result is not None:
            rich_check.check({'version': 'LIO-answer-rich.1', 'trip_receipt': result.wire})
            assert rich_wire(result) == result.wire, (rich_wire(result), result.wire)   # the timeline's last look
        return result

    def saved(run, kind=plan_action_id):
        return effect(kind(run), 'unknown'), effect(kind(run), 'saved')

    repo.autosave = True
    created = act(*publish(LIO_PLAN, document(), trip='trip-rcpt'), plan_action_id('r1'))
    v1 = repo.detail('trip-rcpt')
    fresh = receipt_of('r1', *saved('r1'))
    assert created.committed_version == 1 and fresh.first is False and 'first_autosave' not in fresh.wire
    assert fresh.wire['undo'] == dict(state='available', kind='withdraw_created', action_id=undo_action_id(plan_action_id('r1')),
        until=fresh.wire['undo']['until'], target=dict(trip_id='trip-rcpt', expected_version=1,
        original_hash=sha256(v1.content).hexdigest(), content_version='structured.4')), fresh.wire
    contract_first = dict(examples['first save of a new trip: undo withdraws it, first automatic save'])
    assert shape(dict(fresh.wire, first_autosave=True)) == shape(contract_first), (shape(fresh.wire), shape(contract_first))
    assert receipt_of('r1', *saved('r1'), undo_route=False).wire['undo'] == {'state': 'unavailable'}   # no .5 route here
    second = act(*publish(LIO_PLAN, document(add('item-r2')), trip='trip-rcpt'), plan_action_id('r2'))
    v2 = repo.detail('trip-rcpt')
    got = receipt_of('r2', *saved('r2'))
    assert got.first is False and got.wire['status'] == 'saved' and got.wire['committed_version'] == 2
    undo = got.wire['undo']
    assert (undo['state'], undo['action_id']) == ('available', undo_action_id(plan_action_id('r2')))
    assert undo['target'] == _rich_target(v2, v1), undo   # the same seven fields the v4 undo route checks
    assert undo['until'].endswith('+00:00') and len(undo['until']) == 29
    assert receipt_of('r2', effect(plan_action_id('r2'), 'unknown')).wire == got.wire       # intent + row = saved
    assert read(database, owner, 'r2', list(saved('r2')), undo_route=True).wire == got.wire  # host read path
    assert receipt_of('r2', *saved('r2'), undo_route=False).wire['undo'] == {'state': 'unavailable'}
    assert receipt_of('r9', *saved('r9')).wire == {'status': 'unknown', 'action_id': plan_action_id('r9')}  # no row
    assert receipt_of('r9', effect(plan_action_id('r9'), 'unknown')).wire['status'] == 'unknown'
    assert receipt_of('r3', *saved('r2')) is None             # an effect naming another RUN's write is dropped
    declined = receipt_of('r4', effect(edit_action_id('r4'), 'unknown'),
                         effect(edit_action_id('r4'), 'not_saved', 'protected'))
    assert declined.wire == {'status': 'not_saved', 'action_id': edit_action_id('r4'), 'reason': 'protected'}
    backdate(plan_action_id('r2'), 25)
    late = receipt_of('r2', *saved('r2')).wire['undo']
    assert late == {'state': 'expired', 'until': late['until']} and late['until'] < undo['until']
    backdate(plan_action_id('r2'), 1)
    assert receipt_of('r1', *saved('r1')).wire['undo'] == {'state': 'superseded', 'until': fresh.wire['undo']['until']}
    act(*publish(USER_EDIT, document(chain(add('item-r2'), retext('item-1', 'mine'))), trip='trip-rcpt'), 'user-r')
    assert receipt_of('r2', *saved('r2')).wire['undo']['state'] == 'superseded'
    act(*publish(LIO_PLAN, document(chain(add('item-r2'), retext('item-1', 'mine'), add('item-r5'))),
                 trip='trip-rcpt'), plan_action_id('r5'))
    v4 = repo.detail('trip-rcpt')
    assert receipt_of('r5', *saved('r5')).wire['undo']['state'] == 'available'
    with owner_db() as conn:
        restore_bytes = bytes(conn.execute('SELECT p.content FROM cj_trip_receipt r JOIN cj_trip_proposal p '
                                           'USING(scope,proposal_id) WHERE r.scope=%s AND r.action_id=%s',
                                           (scope, 'user-r')).fetchone()[0])
    restore = Proposal('undo-r5', 'trip-rcpt', v4.version, LIO_UNDO, int(time.time()) + 3600, restore_bytes)
    act(restore, repo.publish(restore), undo_action_id(plan_action_id('r5')))
    assert receipt_of('r5', *saved('r5')).wire['undo']['state'] == 'undone'
    with owner_db() as conn:
        conn.execute("SET session_replication_role=replica")   # test-only: the Trip is gone
        conn.execute('DELETE FROM cj_trip_record WHERE scope=%s AND trip_id=%s', (scope, 'trip-rcpt'))
    assert receipt_of('r5', *saved('r5')).wire['undo'] == {'state': 'unavailable'}
    # the account's first automatic save carries first_autosave on the wire (a fresh account)
    fresh_owner = scope_for(ISSUER, 'm4-synthetic-demo-cccccccccccc')
    database.provision(fresh_owner)
    other = Repository(lambda: database.connect(fresh_owner), trip_scope_for(fresh_owner), confirm=local_confirmation,
                       structured=True, calendar=True, rich=True)
    other.autosave = True
    proposal = Proposal('first-p', 'trip-first', 0, LIO_PLAN, int(time.time()) + 3600, packed(document()))
    other.act(Action(plan_action_id('f1'), 'accept', 'first-p', other.publish(proposal), 'ref'))
    with other.transaction() as cur:
        first_one = project(other, cur, 'f1', list(saved('f1')), undo_route=True)
    rich_check.check({'version': 'LIO-answer-rich.1', 'trip_receipt': first_one.wire})
    assert first_one.first is True and first_one.wire['first_autosave'] is True and rich_wire(first_one) == first_one.wire
    assert shape(first_one.wire) == shape(contract_first)
    print('PASS trip_receipt: saved only from the receipt table, undo available/expired/superseded/undone/unavailable '
          'at read with the v4 route target; first save of a new Trip reads withdraw_created (available, superseded, '
          'unavailable without the route); first_autosave on the wire; contract checker, read-side wire and example shapes agree')

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
