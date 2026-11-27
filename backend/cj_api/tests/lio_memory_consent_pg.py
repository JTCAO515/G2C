"""#1970: the account's append-only memory consent record on a fresh restricted PG.

scripts/pg_suites.py lio_memory_consent. Runtime SQL runs as cj_m1_runtime through the real
LocalDatabase connection and the HTTP routes; only fixtures and inspection use the cluster owner.
Synthetic data only.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import migrate  # noqa: E402
from cj_api.lio_memory_consent import ConsentStore, Conflict, register_lio_memory_consent_routes  # noqa: E402
from cj_api.local_app import ISSUER, LocalDatabase, scope_for  # noqa: E402

TEXT = 'consent-2026-11'


def expect(sqlstate, fn):
    try:
        fn()
    except psycopg.Error as error:
        assert sqlstate is None or error.sqlstate == sqlstate, (sqlstate, error.sqlstate, str(error)[:200])
        return
    raise AssertionError('statement was allowed')


def main(config, conninfo):
    with psycopg.connect(**config, autocommit=True) as conn:
        assert conn.execute('SELECT max(version) FROM cj.schema_migrations').fetchone()[0] >= 60
    owner = lambda: psycopg.connect(**config)
    runtime = lambda: psycopg.connect(**dict(config, user='cj_m1_runtime'))
    alice, bob = scope_for(ISSUER, 'm4-synthetic-demo-aaaaaaaaaaaa'), scope_for(ISSUER, 'm4-synthetic-demo-bbbbbbbbbbbb')
    with owner() as conn:
        conn.execute('INSERT INTO cj_message_scope(scope) VALUES(%s),(%s)', (alice, bob))
    store = ConsentStore(LocalDatabase(conninfo))

    def rows(scope):
        with owner() as conn:
            return conn.execute('SELECT seq,state,consent_text_version,request_id FROM cj_lio_memory_consent WHERE scope=%s ORDER BY seq',
                                (scope,)).fetchall()

    # --- no record means not consented --------------------------------------------------------------
    none = store.current(alice)
    assert none == dict(recorded=False, state='withdrawn', consent_text_version=None, changed_at=None)
    assert store.granted(alice) is False
    print('PASS no record: reads as withdrawn and not recorded; not granted')

    # --- grant, repeat, withdraw, grant -------------------------------------------------------------------
    first = store.record(alice, 'granted', TEXT, 'r1')
    assert first['recorded'] and first['state'] == 'granted' and first['consent_text_version'] == TEXT
    assert store.granted(alice) is True and store.granted(bob) is False
    same = store.record(alice, 'granted', TEXT, 'r2')                       # already granted: nothing is written
    assert same['state'] == 'granted' and [r[:2] for r in rows(alice)] == [(1, 'granted')]
    replay = store.record(alice, 'granted', TEXT, 'r1')                     # the same request again
    assert replay['state'] == 'granted' and len(rows(alice)) == 1
    withdrawn = store.record(alice, 'withdrawn', TEXT, 'r3')
    assert withdrawn['state'] == 'withdrawn' and store.granted(alice) is False
    assert store.record(alice, 'withdrawn', TEXT, 'r3')['state'] == 'withdrawn'    # replay of the withdrawal
    # the old request id with a different change is refused, and changes nothing
    try:
        store.record(alice, 'granted', TEXT, 'r3')
    except Conflict:
        pass
    else:
        raise AssertionError('a request id was reused for another change')
    try:
        store.record(alice, 'withdrawn', 'other-version', 'r3')
    except Conflict:
        pass
    else:
        raise AssertionError('a request id was reused with another consent text')
    again = store.record(alice, 'granted', 'consent-2026-12', 'r4')          # a new consent text version after re-consent
    assert again['consent_text_version'] == 'consent-2026-12' and store.granted(alice) is True
    assert [r[:3] for r in rows(alice)] == [(1, 'granted', TEXT), (2, 'withdrawn', TEXT), (3, 'granted', 'consent-2026-12')]
    assert rows(bob) == []                                                      # another account is untouched
    print('PASS record: append-only, one row per change, repeat is a no-op, request id is idempotent and not reusable for another change')

    # --- concurrency: simultaneous opposite changes still end in an ordered log ---------------------------------
    def change(n):
        return store.record(bob, 'granted' if n % 2 else 'withdrawn', TEXT, 'c%d' % n)
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(change, range(1, 9)))
    log = rows(bob)
    assert [r[0] for r in log] == list(range(1, len(log) + 1))
    assert all(a[1] != b[1] for a, b in zip(log, log[1:]))                      # states strictly alternate
    assert store.current(bob)['state'] == log[-1][1]
    print('PASS concurrent changes keep one ordered, alternating log')

    # --- the runtime role can only read and append, in order ------------------------------------------------------------
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        for statement in ("UPDATE cj_lio_memory_consent SET state='granted' WHERE scope=%s",
                          "UPDATE cj_lio_memory_consent SET consent_text_version='x' WHERE scope=%s",
                          "DELETE FROM cj_lio_memory_consent WHERE scope=%s"):
            expect('42501', lambda: conn.execute(statement, (alice,)))
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        expect('42501', lambda: conn.execute('TRUNCATE cj_lio_memory_consent'))
        conn.rollback()
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        # out of order: a skipped number, a repeated state, a row for someone else
        for values in ((alice, 9, 'withdrawn', TEXT, 'x1'),        # skips numbers
                       (alice, 4, 'granted', TEXT, 'x2'),          # repeats the last state
                       (alice, 3, 'withdrawn', TEXT, 'x3')):       # reuses a number
            expect(None, lambda: conn.execute('INSERT INTO cj_lio_memory_consent(scope,seq,state,consent_text_version,request_id) '
                                              'VALUES(%s,%s,%s,%s,%s)', values))
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        expect('42501', lambda: conn.execute('INSERT INTO cj_lio_memory_consent(scope,seq,state,consent_text_version,request_id) '
                                             'VALUES(%s,1,%s,%s,%s)', (bob + 'x', 'granted', TEXT, 'y1')))
        conn.rollback()
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        assert conn.execute('SELECT count(*) FROM cj_lio_memory_consent WHERE scope=%s', (bob,)).fetchone()[0] == 0
        for bad in ('bad version!', 'x' * 65, ''):
            expect('23514', lambda: conn.execute('INSERT INTO cj_lio_memory_consent(scope,seq,state,consent_text_version,request_id) '
                                                 'VALUES(%s,4,%s,%s,%s)', (alice, 'withdrawn', bad, 'z')))
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
    assert len(rows(alice)) == 3
    print('PASS runtime role: no update, delete or truncate; inserts only in order and own scope; text version shape enforced')

    # --- HTTP surface over the real store ---------------------------------------------------------------------------------
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # The real boundary (#2080): the token is checked by the account checker and the history context is opened over the
    # real message repository, exactly as the mounted app does. Only the token store is a development fixture.
    import tempfile
    import dev_auth
    from cj_api.local_worker_context import checker_for
    from cj_message.auth_boundary import Boundary
    auth = Path(tempfile.mkdtemp(prefix='cj2080-')) / 'auth'
    dev_auth.init(auth, ['m4-synthetic-demo-aaaaaaaaaaaa'])
    alice_token = dev_auth.token(auth, 'm4-synthetic-demo-aaaaaaaaaaaa', 30)
    database = LocalDatabase(conninfo)
    boundary = Boundary(checker_for(auth), lambda p: database.message_repository(scope_for(p.issuer, p.subject)), lambda: 'unused')

    app = FastAPI()
    register_lio_memory_consent_routes(app, boundary, store)
    http = TestClient(app)
    headers = {'Authorization': 'Bearer ' + alice_token}
    put_headers = dict(headers, **{'Content-Type': 'application/octet-stream'})
    body = lambda **v: json.dumps(dict(version='LIO-memory-consent.1', state='withdrawn', consent_text_version=TEXT,
                                       request_id='h1', **v)).encode()
    got = http.get('/v1/lio/memory/consent', headers=headers)
    assert got.status_code == 200 and got.json()['state'] == 'granted' and got.json()['recorded'] is True
    assert got.json()['consent_text_version'] == 'consent-2026-12'
    put = http.put('/v1/lio/memory/consent', content=body(), headers=put_headers)
    assert put.status_code == 200, (put.status_code, put.text)
    assert put.json()['state'] == 'withdrawn' and put.headers['cache-control'] == 'no-store'
    assert http.put('/v1/lio/memory/consent', content=body(), headers=put_headers).json()['state'] == 'withdrawn'   # retry
    assert http.get('/v1/lio/memory/consent', headers=headers).json()['state'] == 'withdrawn'
    assert store.granted(alice) is False
    conflict = http.put('/v1/lio/memory/consent', content=body().replace(b'withdrawn', b'granted'), headers=put_headers)
    assert conflict.status_code == 409
    for raw in (b'', b'{}', b'[]', b'not json', body(extra=1),
                json.dumps(dict(version='LIO-memory-consent.2', state='granted', consent_text_version=TEXT, request_id='h2')).encode(),
                json.dumps(dict(version='LIO-memory-consent.1', state='maybe', consent_text_version=TEXT, request_id='h2')).encode(),
                json.dumps(dict(version='LIO-memory-consent.1', state='granted', consent_text_version='a b', request_id='h2')).encode(),
                json.dumps(dict(version='LIO-memory-consent.1', state='granted', consent_text_version=TEXT, request_id='')).encode(),
                body().replace(b'"request_id": "h1"', b'"request_id": "h1", "request_id": "h2"')):
        assert http.put('/v1/lio/memory/consent', content=raw, headers=put_headers).status_code == 400, raw
    assert http.put('/v1/lio/memory/consent?x=1', content=body(), headers=put_headers).status_code == 400
    assert http.put('/v1/lio/memory/consent', content=body(), headers=headers).status_code == 415   # not octet-stream, like every Lio send
    assert http.put('/v1/lio/memory/consent', content=body(), headers={'Content-Type': 'application/octet-stream'}).status_code == 401
    assert http.get('/v1/lio/memory/consent').status_code == 401
    assert http.get('/v1/lio/memory/consent', headers={'Authorization': 'Bearer nobody'}).status_code == 403      # the real checker refuses a token it did not issue
    # An admission failure that is not a clean refusal (the history context cannot be opened) stays a 503, never a 200 or a 401.
    broken = FastAPI()
    register_lio_memory_consent_routes(broken, SimpleNamespace(with_history_context=lambda token, operation: (_ for _ in ()).throw(RuntimeError('blocked'))), store)
    assert TestClient(broken).get('/v1/lio/memory/consent', headers=headers).status_code == 503
    assert len(rows(alice)) == 4                                                        # only the one real withdrawal was appended
    print('PASS routes: GET and PUT over the real store, retry idempotent, reused request id 409, strict bodies 400, no token 401')

    # --- erasure and down ----------------------------------------------------------------------------------------------------
    with owner() as conn:
        assert {r[1] for r in conn.execute("SELECT conname,confdeltype FROM pg_constraint WHERE conrelid='cj_lio_memory_consent'::regclass AND contype='f'")} == {'c'}
        conn.execute('DELETE FROM cj_message_scope WHERE scope=%s', (alice,))
        assert conn.execute('SELECT count(*) FROM cj_lio_memory_consent WHERE scope=%s', (alice,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM cj_lio_memory_consent WHERE scope=%s', (bob,)).fetchone()[0] > 0
    print('PASS erasure: records cascade away with the account\'s message scope; other accounts keep theirs')
    with owner() as conn:
        conn.autocommit = True
        migrations = migrate.load()
        try:
            migrate.down(conn, migrations, 59)
        except psycopg.Error as error:
            assert 'retained private data' in str(error)
        else:
            raise AssertionError('down ran with consent records present')
        conn.execute('DELETE FROM cj_message_scope WHERE scope=%s', (bob,))
        migrate.down(conn, migrations, 59)
        assert conn.execute("SELECT to_regclass('public.cj_lio_memory_consent')").fetchone()[0] is None
        migrate.up(conn, migrations, 60)
        assert conn.execute("SELECT to_regclass('public.cj_lio_memory_consent')").fetchone()[0] is not None
    print('PASS down refused while records exist; after they are gone it drops the table and up re-applies')


if __name__ == '__main__':
    path = Path(os.environ['CJ_E2E_CONNINFO'])
    main(json.loads(path.read_text()), path)
