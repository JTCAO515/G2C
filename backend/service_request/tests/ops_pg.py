"""#1771 operations console on a fresh restricted PG (scripts/pg_suites.py service_ops).

Staff sign in with the App's own local session credential (scripts/dev_auth.py tokens checked by
the App's local admission checker); the roster holds synthetic test values only. Reads/audit/note
clearing run as cj_ops_console, state changes as cj_m1_runtime, cleanup as cj_local_cleanup; only
setup and inspection use the cluster owner. Synthetic data only.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import dev_auth  # noqa: E402
import migrate  # noqa: E402
from cj_api.local_app import ISSUER, scope_for  # noqa: E402
from cj_api.local_worker_context import checker_for  # noqa: E402
from cj_api.ops_console_routes import PREFIX, register_ops_console_routes  # noqa: E402
from cj_cleanup.coordinator import Coordinator  # noqa: E402
from cj_cleanup.core import digest, encode  # noqa: E402
from cj_cleanup.hooks_v1_1 import Selection  # noqa: E402
from cj_cleanup.registry import freeze  # noqa: E402
from cj_cleanup.store import Store  # noqa: E402
from cj_service_request.lifecycle import ServiceRequestHook, ServiceStaffAuditHook  # noqa: E402
from cj_service_request.ops import OpsConsole, Roster  # noqa: E402
from cj_service_request.store import Repository  # noqa: E402

POLICY = {'cancellation_policy': {'text_en': 'Free cancellation until arranged.', 'text_zh': '安排前可免费取消。'},
          'refund_by': {'text_en': 'Refunded manually by the operator.', 'text_zh': '由运营主体人工退款。'}}
QUOTE = {'amount_minor': 80000, 'currency': 'CNY', 'payment': 'outside_app',
         'instructions_en': 'Staff will tell you how to pay outside the app.', 'instructions_zh': '工作人员会告知 App 外的付款方式。'}
ESCORT = {'escort_display_name': 'Escort T', 'arrival': {'local_time': '2026-12-10T08:45', 'place': 'Synthetic Hall A lobby'}}
STAFF_REF = 'ops-test-01'
NOTE = 'SENSITIVE_NOTE_MISRECEIVED'


def body(cid, **change):
    value = dict(client_request_id=cid, service_type='gz_business_escort_zh_en', service_date='2026-12-10',
                 time_window='half_day_am', venue='Synthetic Hall A', customer_name='Test Customer',
                 contact_phone='+85200000000', meeting_purpose='Supplier meeting',
                 counterpart={'company': 'Synthetic Co', 'name': 'Ms Test'}, note=NOTE,
                 consents=dict(location_sensitive=True, share_with_escort=True, cross_border=True,
                               text_version='svc-consent-1'))
    value.update(change)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def raises(fn, *args):
    try:
        fn(*args)
    except psycopg.Error:
        return True
    return False


def main(config):
    runtime = lambda: psycopg.connect(**dict(config, user='cj_m1_runtime'))
    ops = lambda: psycopg.connect(**dict(config, user='cj_ops_console'))
    owner = lambda: psycopg.connect(**config)
    cleanup = lambda: psycopg.connect(**dict(config, user='cj_local_cleanup'))
    service_flag, console_flag = {'on': True}, {'on': True}
    customer_scope = scope_for(ISSUER, 'customer')
    customer = Repository(runtime, customer_scope, policy=POLICY, flag=lambda: service_flag['on'])
    console = OpsConsole(ops, runtime, policy=POLICY, flag=lambda: service_flag['on'])

    auth = Path(tempfile.mkdtemp(prefix='cj1771-auth-'))
    dev_auth.init(auth, ['customer', 'staff1', 'intruder'])
    roster = Roster([{'issuer': ISSUER, 'subject': 'staff1', 'staff_ref': STAFF_REF}])
    app = FastAPI()

    @app.middleware('http')
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)
    register_ops_console_routes(app, checker_for(auth), console, roster, enabled=lambda: console_flag['on'])
    client = TestClient(app)
    bearer = lambda s: {'Authorization': 'Bearer ' + dev_auth.token(auth, s, 30)}
    staff = bearer('staff1')

    def call(method, path, status=200, headers=None, **kw):
        response = client.request(method, PREFIX + path, headers=staff if headers is None else headers, **kw)
        assert response.status_code == status, (method, path, response.status_code, response.text)
        return response.json()

    def step(rid, target, evidence, status=200, **extra):
        return call('POST', f'/{rid}/transitions', status, json=dict(target=target, evidence_body=evidence, **extra))

    def audit(rid=None):
        with owner() as conn:
            if rid is None:
                return conn.execute('SELECT staff_ref,action,request_id FROM cj_service_request_staff_audit ORDER BY audit_id').fetchall()
            return [a for (a,) in conn.execute('SELECT action FROM cj_service_request_staff_audit WHERE request_id=%s '
                                                'ORDER BY audit_id', (rid,)).fetchall()]

    # 1. One Guangzhou zh-en business escort request, submitted to completed, read back by the customer.
    raw = body('gz-1')
    rid = customer.submit(raw)['request_id']
    listed = call('GET', '')['requests']
    assert [r['request_id'] for r in listed] == [rid] and listed[0]['state'] == 'submitted'
    detail = call('GET', f'/{rid}')
    assert detail['details']['note'] == NOTE and detail['staff_targets'] == ['accepted', 'unavailable', 'user_cancelled']
    assert 'scope' not in json.dumps(detail) and customer_scope not in json.dumps(detail)
    step(rid, 'accepted', 'desk accepted')
    step(rid, 'quoted', 'quote v1', quote=QUOTE)
    step(rid, 'arranged', 'escort confirmed', escort=ESCORT)
    step(rid, 'in_progress', 'escort arrived')
    step(rid, 'completed', None, 400)  # completion_summary required
    step(rid, 'completed', '', 400)
    done = step(rid, 'completed', 'met supplier; summary')
    assert done['state'] == 'completed'
    assert [h['actor'] for h in done['history'][2:]] == [{'kind': 'staff', 'staff_ref': STAFF_REF}] * 5
    back = customer.get(rid)
    assert back['state'] == 'completed' and back['quote'] == QUOTE
    assert back['human_service']['escort_display_name'] == 'Escort T'
    assert back['human_service']['arrival'] == ESCORT['arrival'] and back['human_service']['provided_by_human'] is True
    text = json.dumps(back, ensure_ascii=False)
    assert STAFF_REF not in text and 'summary' not in text and 'escort confirmed' not in text
    print('PASS internal staff account: submitted -> accepted -> quoted -> arranged -> in_progress -> completed; '
          'customer read-back has human_service and quote, no staff ref or evidence text')

    # 2. Not on the roster, no token, invalid token: refused, nothing audited.
    before = len(audit())
    call('GET', '', 403, headers=bearer('intruder'))
    call('GET', f'/{rid}', 403, headers=bearer('customer'))
    call('POST', f'/{rid}/transitions', 403, headers=bearer('intruder'), json=dict(target='unavailable', evidence_body='x'))
    call('GET', '', 401, headers={})
    call('GET', '', 401, headers={'Authorization': 'Bearer not.a.token'})
    assert len(audit()) == before
    print('PASS non-roster App accounts 403, missing/invalid session 401, nothing audited')

    # 3. Every staff action audited (who, when, what, which request).
    assert audit(rid) == ['view', 'accepted', 'quoted', 'arranged', 'in_progress', 'completed', 'completed', 'completed']
    with owner() as conn:
        rows = conn.execute('SELECT staff_ref,at IS NOT NULL,scope FROM cj_service_request_staff_audit').fetchall()
        assert all(r[0] == STAFF_REF and r[1] for r in rows)
        assert {r[2] for r in rows} == {None, customer_scope}  # list carries no request
    print('PASS each list/view/transition attempt audited with staff ref, time, action and request')

    # 4. Illegal transitions refused through check_transition; state unchanged.
    second = customer.submit(body('gz-2'))['request_id']
    step(second, 'completed', 'x', 409)
    step(second, 'in_progress', 'x', 409)
    step(second, 'submitted', 'x', 400)
    step(second, 'quoted', 'q', 400)  # wrong state is checked after payload: missing quote first
    step(second, 'quoted', 'q', 409, quote=QUOTE)
    step(rid, 'unavailable', 'x', 409)  # terminal
    call('POST', f'/{second}/transitions', 400, content=b'{"target":"accepted","state":"x"}')
    call('GET', '/sr_' + '0' * 32, 404)
    assert call('GET', f'/{second}')['state'] == 'submitted'
    print('PASS illegal transitions 409, unknown targets/payload 400, missing request 404; state unchanged')

    # 5. Misreceived note cleared (PIPIA 7): gone from details and stored bytes; replay still exact.
    cleared = call('POST', f'/{second}/clear-note')
    assert cleared['details']['note'] is None and cleared['note_cleared_at']
    call('POST', f'/{second}/clear-note', 400)
    with owner() as conn:
        stored = bytes(conn.execute('SELECT original_input FROM cj_service_request WHERE request_id=%s', (second,)).fetchone()[0])
    assert NOTE.encode() not in stored and json.loads(stored)['note'] is None
    assert customer.get(second)['details']['note'] is None
    assert customer.submit(body('gz-2'))['request_id'] == second  # original bytes still an exact replay
    assert audit(second)[-2:] == ['view', 'clear_note']
    print('PASS misreceived note cleared from details and stored original bytes, audited, once only; replay exact')

    # 6. CJ_SERVICE_REQUEST_ENABLED off: old requests readable and can be brought to an end.
    third = customer.submit(body('gz-3'))['request_id']
    fourth = customer.submit(body('gz-4'))['request_id']
    step(fourth, 'accepted', 'ok')
    step(fourth, 'quoted', 'q', quote=QUOTE)
    step(fourth, 'arranged', 'a', escort=ESCORT)
    service_flag['on'] = False
    assert call('GET', f'/{third}')['state'] == 'submitted' and len(call('GET', '')['requests']) == 4
    step(third, 'accepted', 'x', 404)
    step(fourth, 'in_progress', 'x', 404)
    assert step(third, 'unavailable', 'no escort')['state'] == 'unavailable'
    assert step(fourth, 'outcome_unknown', 'no report')['state'] == 'outcome_unknown'
    assert step(fourth, 'completed', 'late report')['state'] == 'completed'
    assert customer.get(third)['state'] == 'unavailable'
    service_flag['on'] = True
    console_flag['on'] = False
    call('GET', '', 404)
    call('GET', f'/{rid}', 404)
    console_flag['on'] = True
    print('PASS service switch off: existing requests readable, non-terminal progress 404, terminal progress allowed; '
          'console switch off: 404')

    # 7. Ops role negatives: no conversations/memory/trip, no other field, no delete/truncate, append-only audit.
    with owner() as conn:
        assert conn.execute("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname='cj_ops_console'").fetchone() == (False, False)
        assert conn.execute("SELECT count(*) FROM information_schema.role_table_grants WHERE grantee='cj_ops_console' "
                            "AND privilege_type IN ('DELETE','TRUNCATE')").fetchone()[0] == 0
        tables = {t for (t,) in conn.execute("SELECT table_name FROM information_schema.role_table_grants "
                                              "WHERE grantee='cj_ops_console' UNION SELECT table_name FROM "
                                              "information_schema.role_column_grants WHERE grantee='cj_ops_console'").fetchall()}
        assert tables == {'cj_service_request', 'cj_service_request_history', 'cj_service_request_scope',
                          'cj_service_request_staff_audit'}, tables
        assert conn.execute("SELECT count(*) FROM pg_proc WHERE prosecdef AND proname LIKE 'cj_service_request%%'").fetchone()[0] == 0
    forbidden = ['SELECT 1 FROM cj_message_chat', 'SELECT 1 FROM cj_service_message', 'SELECT 1 FROM cj_memory_item',
                 'SELECT 1 FROM cj_trip_record', 'SELECT 1 FROM cj_service_request_view',
                 'SELECT 1 FROM cj_service_request_staff_audit',
                 "UPDATE cj_service_request SET state='completed'",
                 "UPDATE cj_service_request SET quote=NULL",
                 "UPDATE cj_service_request SET details=details||'{\"venue\":\"x\"}'::jsonb",
                 "UPDATE cj_service_request SET details=details||'{\"note\":\"other\"}'::jsonb,note_cleared_at=now()",
                 "UPDATE cj_service_request SET details=details||'{\"note\":null}'::jsonb,note_cleared_at=now()",  # bytes kept
                 'UPDATE cj_service_request_history SET evidence_body=NULL',
                 'DELETE FROM cj_service_request', 'DELETE FROM cj_service_request_history',
                 'DELETE FROM cj_service_request_staff_audit', 'TRUNCATE cj_service_request_staff_audit',
                 "UPDATE cj_service_request_staff_audit SET action='view'",
                 "INSERT INTO cj_service_request_staff_audit(staff_ref,action,at) VALUES('x','list',now()-interval '1 year')",
                 "INSERT INTO cj_service_request_history(scope,request_id,seq,to_state,actor_kind,evidence_kind) "
                 "SELECT scope,request_id,99,'completed','staff','completion_summary' FROM cj_service_request LIMIT 1"]
    for sql in forbidden:
        with ops() as conn:
            if sql.startswith('UPDATE cj_service_request SET'):
                sql += f" WHERE request_id='{third}'"
            assert raises(conn.execute, sql), sql
    with owner() as conn:
        assert conn.execute("SELECT count(*) FROM cj_service_request_history WHERE seq=99").fetchone()[0] == 0
        expect_note = conn.execute('SELECT details->>%s,note_cleared_at FROM cj_service_request WHERE request_id=%s',
                                   ('note', third)).fetchone()
        assert expect_note == (NOTE, None)
        assert raises(conn.execute, "UPDATE cj_service_request_staff_audit SET staff_ref='rewritten'")
    print('PASS cj_ops_console: no BYPASSRLS/DELETE/TRUNCATE/SECURITY DEFINER; no conversation/memory/trip/escort-audit read; '
          'only note->null (with its stored bytes) writable; history/audit not rewritable')

    # 8. Retention: the 12-month request deletion takes its audit rows (cascade).
    with owner() as conn:
        conn.execute("UPDATE cj_service_request SET first_terminal_at=clock_timestamp()-interval '13 months' WHERE request_id=%s", (third,))
    assert customer.purge_expired(cleanup)['requests_deleted'] == 1
    assert audit(third) == []
    print('PASS 12-month request deletion removes its staff audit rows')

    # 9. Account erasure still passes; audit keeps staff/time/action only, de-linked rows end after 12 months.
    subject = digest(b'synthetic customer subject')
    store = Store(cleanup, subject, lambda stage: None)
    targets = ('business/service-requests', 'business/service-staff-audit')
    registry = encode(dict(version='service-ops-local-proof', stores=[dict(id='business', objects=[
        dict(id='service-requests', cleanup_protocol='CLEANUP@1.1'),
        dict(id='service-staff-audit', cleanup_protocol='CLEANUP@1.1')])]))
    frozen = freeze(registry, targets, versions=('CLEANUP@1.1',))
    hooks = {targets[0]: ServiceRequestHook(store, customer_scope), targets[1]: ServiceStaffAuditHook(store, customer_scope)}
    host = Coordinator(store, lambda: frozen, hooks)
    host.create('erase-customer', digest(b'synthetic confirmation'), 'account',
                {t: {'domain_scope': customer_scope, 'selection': {'kind': 'account'}} for t in targets})
    linked = len(audit()) - sum(1 for r in audit() if r[2] is None)
    assert linked > 0
    requests = [host.request('erase-customer', t, customer_scope, Selection('account')) for t in targets]
    for request in requests:
        status = host.advance(request)['status']
    assert status == 'complete', host.query('erase-customer')
    assert all(host.reconcile(r)['status'] == 'complete' for r in requests)
    with owner() as conn:
        assert conn.execute('SELECT count(*) FROM cj_service_request WHERE scope=%s', (customer_scope,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM cj_service_request_staff_audit WHERE scope IS NOT NULL '
                            'OR request_id IS NOT NULL').fetchone()[0] == 0
        kept = conn.execute('SELECT staff_ref,action FROM cj_service_request_staff_audit').fetchall()
        assert len(kept) >= linked and all(r[0] == STAFF_REF for r in kept)
    assert call('GET', '')['requests'] == []
    call('GET', f'/{rid}', 404)
    try:
        customer.get(rid)
    except Exception as exc:
        assert not isinstance(exc, AssertionError)
    else:
        raise AssertionError('erased request still readable')
    assert OpsConsole.purge_delinked_audit(cleanup) == 0
    with owner() as conn:
        total = conn.execute('SELECT count(*) FROM cj_service_request_staff_audit').fetchone()[0]
        conn.execute("ALTER TABLE cj_service_request_staff_audit DISABLE TRIGGER service_request_staff_audit_append_only")
        conn.execute("UPDATE cj_service_request_staff_audit SET at=clock_timestamp()-interval '13 months'")
        conn.execute("ALTER TABLE cj_service_request_staff_audit ENABLE TRIGGER service_request_staff_audit_append_only")
    assert OpsConsole.purge_delinked_audit(cleanup) == total  # every row is de-linked and now expired
    print('PASS account erasure: requests erased, staff audit keeps staff/time/action only (request id and scope cleared); '
          'de-linked audit deleted after 12 months')

    # 10. Down with retained audit refused.
    with ops() as conn:
        conn.execute("INSERT INTO cj_service_request_staff_audit(staff_ref,action) VALUES('ops-test-01','list')")
    try:
        with psycopg.connect(**config, autocommit=True) as conn:
            migrate.down(conn, migrate.load(), 57)
    except psycopg.Error:
        pass
    else:
        raise AssertionError('0058 down dropped retained staff audit')
    print('PASS 0058 down refused while staff audit is retained')


if __name__ == '__main__':
    main(json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text()))
