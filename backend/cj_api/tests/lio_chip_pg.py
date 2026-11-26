"""#1727 part 2: one-time chip tickets and the question-quota exemption on a fresh restricted PG.

scripts/pg_suites.py lio_chip. Runtime SQL runs as cj_m1_runtime through the real LIO-message.2
admission (`receive_lio`); only fixtures and inspection use the cluster owner. Synthetic data only.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import dev_auth  # noqa: E402
import local_run_context  # noqa: E402
import migrate  # noqa: E402
from cj_api.local_app import ISSUER, LocalDatabase, scope_for  # noqa: E402
from cj_api.local_run_context import load_run_context  # noqa: E402
from cj_message.demo_dialogue import LIO_VERSION_V2, receive_lio  # noqa: E402
from cj_message.domain import Service  # noqa: E402
from cj_message.lio_followups import label_sha256  # noqa: E402
from cj_message.travel import ABI  # noqa: E402
from runtime_adapter.contract import encode  # noqa: E402

LABELS = ['付不了怎么办', '哪些地方不能用', '怎么开通地铁乘车码']
DIGEST = '0' * 64


def erase(conn, scope):
    """Delete one account's MESSAGE and RUN rows in the order the account cleanup hooks do."""
    from cj_cleanup.account_hooks import MESSAGE, RUN
    with conn.transaction():   # the references between these tables are deferred to commit
        for table, column in (*RUN, *MESSAGE):
            assert 'cj_lio_chip' != table
            conn.execute(f'DELETE FROM {table} WHERE {column}=%s', (scope,))


def main(config, conninfo):
    with psycopg.connect(**config, autocommit=True) as conn:
        assert conn.execute('SELECT max(version) FROM cj.schema_migrations').fetchone()[0] >= 59
    runtime = lambda: psycopg.connect(**dict(config, user='cj_m1_runtime'))
    owner = lambda: psycopg.connect(**config)
    subjects = ['m4-synthetic-demo-' + suffix * 12 for suffix in 'abc']
    root = Path(tempfile.mkdtemp(prefix='cj1727-chip-'))
    dev_auth.init(root / 'auth', frozenset(subjects))
    now = int(time.time())
    meter_file = root / 'meter.json'
    meter_file.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2', current=dict(meter=dict(
        unit='provider_call', budget=80, period_start=now - 60, period_end=now + 3600,
        max_steps=12, max_tools=4, max_output=60000, max_seconds=600),
        output_limits=dict(model=12000, tool=4000, memory=12000)), history=[])))
    meter = load_run_context(meter_file)
    for person in subjects:
        local_run_context.provision_budget(conninfo, meter, person)
        dev_auth.activate_travel(conninfo, person, meter, ABI)
    alice, bob, carol = (scope_for(ISSUER, person) for person in subjects)
    with owner() as conn:
        for scope in (alice, bob, carol):
            assert conn.execute("UPDATE cj_message_scope SET demo_invite_digest=%s,"
                                "demo_invite_expires_at=clock_timestamp()+interval '1 hour',demo_session_floor=0 WHERE scope=%s",
                                (DIGEST, scope)).rowcount == 1
    database = LocalDatabase(conninfo, run_context=meter, travel_context=True, needs_context=True, trip_context=True)
    service = lambda scope: Service(database.message_repository(scope), lambda: 'r-' + uuid.uuid4().hex)

    def send(scope, text, ticket=None, mid=None):
        mid = mid or 'm-' + uuid.uuid4().hex
        body = dict(version=LIO_VERSION_V2, message_id=mid, text=text, locale='zh')
        if ticket is not None:
            body['chip_ticket'] = ticket
        receive_lio(service(scope), json.dumps(body, ensure_ascii=False).encode(), prepare_scope=database._provision_scope,
                    version=LIO_VERSION_V2)
        return mid

    def day(mid, scope):
        with owner() as conn:
            row = conn.execute('SELECT demo_question_day FROM cj_message_receipt WHERE scope=%s AND message_id=%s',
                               (scope, mid)).fetchone()
        return row[0]

    def free(mid, scope):
        # Every demo receipt keeps its question day (readers use it); a free one is flagged instead.
        with owner() as conn:
            row = conn.execute('SELECT demo_question_day,demo_chip_free FROM cj_message_receipt WHERE scope=%s AND message_id=%s',
                               (scope, mid)).fetchone()
        assert row[0] is not None
        return row[1] is True

    def chips(scope, answer):
        with owner() as conn:
            return conn.execute('SELECT chip_index,ticket,depth,redeemed_message_id FROM cj_lio_chip '
                                'WHERE scope=%s AND answer_message_id=%s ORDER BY chip_index', (scope, answer)).fetchall()

    def expect(sqlstate, fn):
        try:
            fn()
        except psycopg.Error as error:
            assert sqlstate is None or error.sqlstate == sqlstate, (sqlstate, error.sqlstate, str(error)[:200])
            return
        raise AssertionError('statement was allowed')

    # --- issue ---------------------------------------------------------------------------------
    first = send(alice, '外国游客怎么用支付宝？')
    assert not free(first, alice)            # an ordinary demo question counts
    tickets = service(alice).issue_lio_chips(first, LABELS)
    assert tickets is not None and len(set(tickets)) == 3 and all(len(t) == 43 for t in tickets)
    rows = chips(alice, first)
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [(0, tickets[0], 1, None), (1, tickets[1], 1, None), (2, tickets[2], 1, None)]
    with owner() as conn:
        stored = conn.execute('SELECT label_sha256,issued_at,expires_at,redeemed_xid FROM cj_lio_chip WHERE scope=%s AND answer_message_id=%s '
                              'ORDER BY chip_index', (alice, first)).fetchall()
    assert [r[0] for r in stored] == [label_sha256(label) for label in LABELS]      # only hashes of the questions are kept
    assert all(r[2] - r[1] == timedelta(hours=24) and r[3] is None for r in stored)
    assert service(alice).issue_lio_chips(first, LABELS) is None                    # an answer gets chips once
    assert service(alice).issue_lio_chips('no-such-message', LABELS) is None
    assert service(alice).issue_lio_chips(first, LABELS + ['第四个']) is None       # at most three
    assert service(alice).issue_lio_chips(first, []) is None
    assert service(bob).issue_lio_chips(first, LABELS) is None                      # another account has no such answer
    print('PASS issue: three one-time tickets (43 characters) with label hashes and 24 h expiry; once per answer, own answers only')

    # --- redeem and the daily count --------------------------------------------------------------
    spent = send(alice, LABELS[0], tickets[0])
    assert free(spent, alice)                                                  # not counted
    assert [r[3] for r in chips(alice, first)] == [spent, None, None]
    sibling = send(alice, LABELS[1], tickets[1])
    assert not free(sibling, alice)                                           # one free chip per answer
    assert chips(alice, first)[1][3] is None                                  # not redeemed free, but used: it sets the next level
    with owner() as conn:
        assert conn.execute('SELECT used_message_id FROM cj_lio_chip WHERE scope=%s AND answer_message_id=%s AND chip_index=1',
                            (alice, first)).fetchone()[0] == sibling
    reuse = send(alice, LABELS[0], tickets[0])
    assert not free(reuse, alice)                                             # a spent ticket is an ordinary question
    wrong = send(alice, LABELS[2] + ' ', tickets[2])
    assert not free(wrong, alice) and chips(alice, first)[2][3] is None       # text must be byte-identical
    wrong = send(alice, LABELS[2].replace('开通', '开 通'), tickets[2])
    assert not free(wrong, alice)
    stranger = send(bob, LABELS[2], tickets[2])
    assert not free(stranger, bob) and chips(alice, first)[2][3] is None      # another account's ticket does nothing
    nothing = send(alice, LABELS[2], 'x' * 43)
    assert not free(nothing, alice)
    print('PASS redeem: exact text spends the ticket without counting; sibling, reuse, wrong text, other account, unknown ticket count as ordinary questions')

    # --- an idempotent retry does not spend or count twice -----------------------------------------
    again = send(alice, LABELS[0], tickets[0], mid=spent)
    assert again == spent and free(spent, alice)
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s AND message_id=%s', (alice, spent)).fetchone()[0] == 1
    print('PASS replay of the free question changes nothing')

    # --- expiry --------------------------------------------------------------------------------
    third = send(alice, '怎么打车去机场')
    expiring = service(alice).issue_lio_chips(third, LABELS)
    with owner() as conn:
        conn.execute('ALTER TABLE cj_lio_chip DISABLE TRIGGER cj_lio_chip_redeem_guard')
        conn.execute("UPDATE cj_lio_chip SET issued_at=now()-interval '30 hours',expires_at=now()-interval '6 hours' "
                     'WHERE scope=%s AND answer_message_id=%s', (alice, third))
        conn.execute('ALTER TABLE cj_lio_chip ENABLE TRIGGER cj_lio_chip_redeem_guard')
    late = send(alice, LABELS[0], expiring[0])
    assert not free(late, alice) and chips(alice, third)[0][3] is None
    print('PASS an expired ticket is an ordinary question')

    # --- chain depth: three free levels, then every level counts and stays at level 4 -------------------------
    chain_root = send(alice, '外国游客怎么用微信支付？')
    level = chain_root
    seen = []
    depths = []
    for _ in range(6):
        offered = service(alice).issue_lio_chips(level, LABELS)
        assert offered is not None
        depths.append({r[2] for r in chips(alice, level)})
        question = send(alice, LABELS[0], offered[0])
        seen.append(free(question, alice))
        level = question
    assert depths == [{1}, {2}, {3}, {4}, {4}, {4}], depths
    assert seen == [True, True, True, False, False, False], seen                    # the fourth level and beyond count
    print('PASS chain: three consecutive levels are free; the fourth and every later one counts and stays at level 4')

    # --- twenty free questions per Beijing day --------------------------------------------------------
    with owner() as conn:
        used = conn.execute('SELECT count(*) FROM cj_lio_chip WHERE scope=%s AND redeemed_at IS NOT NULL', (alice,)).fetchone()[0]
    free_days = []
    for _ in range(25):
        root = send(alice, '外国游客怎么用支付宝？')
        offered = service(alice).issue_lio_chips(root, LABELS)
        free_days.append(free(send(alice, LABELS[0], offered[0]), alice))
    assert free_days.count(True) == 20 - used and not any(free_days[20 - used:]), (used, free_days)
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_lio_chip WHERE scope=%s AND redeemed_at IS NOT NULL', (alice,)).fetchone()[0] == 20
    print('PASS daily cap: 20 free chip questions per Beijing day, then ordinary questions')

    # --- the exemption works at the daily limit, and ordinary questions are still refused ---------------
    seed = send(carol, '外国游客怎么用支付宝？')
    offered = service(carol).issue_lio_chips(seed, LABELS)
    count = 1
    try:
        while True:
            send(carol, '问题 %d' % count)
            count += 1
    except psycopg.Error as error:
        assert error.sqlstate == 'P5D01'
    assert count >= 400
    expect('P5D01', lambda: send(carol, '再问一个'))
    free_at_limit = send(carol, LABELS[0], offered[0])
    assert free(free_at_limit, carol)
    expect('P5D01', lambda: send(carol, LABELS[1], offered[1]))                         # the sibling is not free
    print('PASS at the daily question limit a spent ticket still goes through; ordinary and sibling questions are refused (P5D01)')

    # --- concurrency: one free chip per answer, one use per ticket ------------------------------------------
    race = send(bob, '怎么打车去机场')
    offered = service(bob).issue_lio_chips(race, LABELS)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda args: free(send(bob, *args), bob),
                                [(LABELS[0], offered[0]), (LABELS[1], offered[1]), (LABELS[2], offered[2]), (LABELS[0], offered[0])]))
    assert results.count(True) == 1, results
    redeemed = [r for r in chips(bob, race) if r[3] is not None]
    assert len(redeemed) == 1
    print('PASS concurrent chip sends: exactly one free question per answer')

    spare = send(alice, '问个新问题')
    assert service(alice).issue_lio_chips(spare, LABELS) is not None

    # --- the runtime role cannot rewrite tickets, delete them or spend them outside the rules -----------------------
    with runtime() as conn:
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        for statement, args in (
                ("UPDATE cj_lio_chip SET label_sha256=%s WHERE scope=%s", (DIGEST, alice)),
                ("UPDATE cj_lio_chip SET depth=1 WHERE scope=%s", (alice,)),
                ("UPDATE cj_lio_chip SET expires_at=expires_at+interval '1 hour' WHERE scope=%s", (alice,)),
                ("DELETE FROM cj_lio_chip WHERE scope=%s", (alice,)),
                ("TRUNCATE cj_lio_chip", ())):
            expect('42501', lambda: conn.execute(statement, args))
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        # a ticket cannot be inserted already used or already free
        for columns, values in (("used_message_id,used_at", "'m-x',now()"),
                                ("used_message_id,used_at,redeemed_message_id,redeemed_at,redeemed_xid",
                                 "'m-y',now(),'m-y',now(),pg_current_xact_id()")):
            expect('42501', lambda: conn.execute(
                f'INSERT INTO cj_lio_chip(scope,conversation_id,generation,answer_message_id,chip_index,ticket,label_sha256,depth,'
                f"expires_at,{columns}) VALUES(%s,'c','g','m',2,%s,%s,1,now()+interval '1 hour',{values})", (alice, 'y' * 43, DIGEST)))
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        # the free flag and the question day of a receipt cannot be rewritten from the runtime role either
        for column, value in (('demo_chip_free', 'true'), ('demo_chip_free', 'NULL'), ('demo_question_day', 'NULL')):
            try:
                changed = conn.execute(f'UPDATE cj_message_receipt SET {column}={value} WHERE scope=%s', (alice,)).rowcount
            except psycopg.Error as error:
                assert error.sqlstate == '42501', error.sqlstate
            else:
                assert changed == 0, (column, changed)      # the row policy leaves no row to rewrite
            conn.rollback()
            conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        # a spent ticket cannot be spent again, a second chip of the same answer cannot be spent, the spend
        # must be in this very transaction, and the account is already at its 20 free questions today
        expect('42501', lambda: conn.execute("UPDATE cj_lio_chip SET redeemed_message_id='m-x',redeemed_at=now(),"
                                             'redeemed_xid=pg_current_xact_id() WHERE scope=%s AND answer_message_id=%s AND chip_index=0',
                                             (alice, first)))
        conn.rollback()
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        expect('42501', lambda: conn.execute("UPDATE cj_lio_chip SET redeemed_message_id='m-x',redeemed_at=now(),"
                                             'redeemed_xid=pg_current_xact_id() WHERE scope=%s AND answer_message_id=%s AND chip_index=1',
                                             (alice, first)))
        conn.rollback()
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        expect('42501', lambda: conn.execute("UPDATE cj_lio_chip SET redeemed_message_id='m-x',redeemed_at=now(),"
                                             "redeemed_xid=(pg_current_xact_id()::text::bigint+1)::text::xid8 "
                                             'WHERE scope=%s AND answer_message_id=%s AND chip_index=0', (alice, third)))
        conn.rollback()
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        # a forged row for someone else's scope is refused by the row policy
        expect('42501', lambda: conn.execute('INSERT INTO cj_lio_chip(scope,conversation_id,generation,answer_message_id,chip_index,ticket,'
                                             "label_sha256,depth,expires_at) VALUES(%s,'c','g','m',0,%s,%s,1,now()+interval '1 hour')",
                                             (bob, 'z' * 43, DIGEST)))
        conn.rollback()
        # an other account's rows are not even visible
        conn.execute("SELECT set_config('cj.message_scope',%s,false)", (alice,))
        assert conn.execute('SELECT count(*) FROM cj_lio_chip WHERE scope=%s', (bob,)).fetchone()[0] == 0
    print('PASS runtime role: no rewrite of label, level or expiry, no delete or truncate, no second or out-of-transaction spend, row policy holds')

    # --- erasure --------------------------------------------------------------------------------------------------------
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_lio_chip WHERE scope=%s', (alice,)).fetchone()[0] > 0
        actions = {r[0]: r[1] for r in conn.execute(
            "SELECT conname,confdeltype FROM pg_constraint WHERE conrelid='cj_lio_chip'::regclass AND contype='f'")}
        assert set(actions.values()) == {'c'} and len(actions) == 2                      # cascade from chat and receipt
        from cj_cleanup.account_hooks import MESSAGE
        assert 'cj_lio_chip' not in {table for table, _ in MESSAGE}                      # erased by cascade, not listed
        erase(conn, alice)           # the cleanup hook's own table order, which never lists cj_lio_chip
        assert conn.execute('SELECT count(*) FROM cj_lio_chip WHERE scope=%s', (alice,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM cj_lio_chip WHERE scope=%s', (bob,)).fetchone()[0] > 0
    print('PASS erasure: chips cascade away with the account\'s receipts; other accounts keep theirs')

    # --- down migration: refused while tickets exist, restores the 0052 function otherwise ------------------------------------
    with owner() as conn:
        conn.autocommit = True
        migrations = migrate.load()
        try:
            migrate.down(conn, migrations, 58)
        except psycopg.Error as error:
            assert 'retained private data' in str(error)
        else:
            raise AssertionError('down ran with tickets present')
        erase(conn, bob)
        erase(conn, carol)
        migrate.down(conn, migrations, 58)
        assert conn.execute("SELECT to_regclass('public.cj_lio_chip')").fetchone()[0] is None
        assert 'cj_lio_chip' not in conn.execute("SELECT prosrc FROM pg_proc WHERE proname='cj_demo_accept_question'").fetchone()[0]
        migrate.up(conn, migrations, 59)
        assert conn.execute("SELECT to_regclass('public.cj_lio_chip')").fetchone()[0] is not None
    print('PASS down refused while tickets exist; after they are gone it restores the 0052 quota function and up re-applies')


if __name__ == '__main__':
    path = Path(os.environ['CJ_E2E_CONNINFO'])
    main(json.loads(path.read_text()), path)
