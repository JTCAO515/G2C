"""Opt-in integration tests which create their own socket-only PostgreSQL cluster."""

import base64
import os
import re
import socket
import subprocess
import sys
import time
from asyncio import run
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from jt.synthetic import generate_dataset
from jt.workbench import __main__ as local_cli, production
from jt.workbench.app import HEALTH_HOST, ProxyEntry, SESSION_COOKIE, create_app
from jt.workbench.auth import SESSION_IDLE, AccessDenied, AccountAction, Auth, AuthenticationRequired, InvalidAccount
from jt.workbench.postgres import PostgresStore, migrate
from jt.workbench.queue import Review
from jt.workbench.security import totp_at_step
from jt.workbench.store import AuditAction, AuditEvent, AuditResult, CaseAuditDetail, MemoryStore, OperationsAuditDetail


ORIGIN = "https://127.0.0.1:8443"
ADMIN = "synthetic-admin"
STAFF = "synthetic-reviewer"
PASSWORD = "synthetic local database test password"
SEED = bytes(range(20))
STAFF_SEED = bytes(range(20, 40))
NOW = 1_734_000_030


@pytest.fixture(scope="module")
def cluster():
    bindir = os.environ.get("JT_WORKBENCH_TEST_PG_BINDIR")
    if not bindir:
        pytest.skip("set JT_WORKBENCH_TEST_PG_BINDIR to exercise a private PostgreSQL cluster")
    env = {"PATH": os.defpath, "LC_ALL": "C"}

    def command(name, *args):
        result = subprocess.run([str(Path(bindir) / name), *args], env=env, capture_output=True, text=True)
        if result.returncode:
            pytest.fail(f"{name} failed in isolated cluster: {result.stderr or result.stdout}", pytrace=False)

    with TemporaryDirectory(prefix="jt-pg-", dir="/tmp") as directory:
        data = Path(directory) / "db"
        command("initdb", "-D", str(data), "-A", "trust", "-U", "jt_test_admin", "--no-locale", "-E", "UTF8")
        command("pg_ctl", "-D", str(data), "-l", f"{directory}/postgres.log", "-o",
                f"-c listen_addresses= -c unix_socket_permissions=0700 -k {directory} -p 55485", "-w", "start")
        try:
            admin = make_conninfo(host=directory, port=55485, dbname="postgres", user="jt_test_admin")
            with psycopg.connect(admin, autocommit=True) as db:
                db.execute("CREATE ROLE jt_workbench_owner LOGIN")
                db.execute("CREATE ROLE jt_workbench_runtime LOGIN")
                db.execute("CREATE DATABASE unrelated_cj")
                db.execute("REVOKE ALL ON DATABASE unrelated_cj FROM PUBLIC")
            yield admin
        finally:
            command("pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop")


@pytest.fixture
def database(cluster):
    with psycopg.connect(cluster, autocommit=True) as db:
        db.execute("CREATE DATABASE jt_workbench OWNER jt_workbench_owner")
        db.execute("REVOKE ALL ON DATABASE jt_workbench FROM PUBLIC")
        db.execute("GRANT CONNECT ON DATABASE jt_workbench TO jt_workbench_runtime")
    owner = make_conninfo(cluster, dbname="jt_workbench", user="jt_workbench_owner")
    runtime = make_conninfo(cluster, dbname="jt_workbench", user="jt_workbench_runtime")
    try:
        yield owner, runtime
    finally:
        with psycopg.connect(cluster, autocommit=True) as db:
            db.execute("DROP DATABASE jt_workbench")


def seed_text(seed):
    return base64.b32encode(seed).decode()


def account_auth(store, at=NOW):
    return Auth(store, clock=lambda: at, monotonic=lambda: at)


def prepare(database):
    owner, runtime = database
    migrate(owner)
    store = PostgresStore(runtime)
    store.check_ready()
    account_auth(store, NOW - 30).bootstrap_admin(
        ADMIN, PASSWORD, seed_text(SEED), totp_at_step(SEED, (NOW - 30) // 30),
    )
    return store, runtime


def test_migration_empty_roundtrip_and_runtime_grants(database, cluster):
    owner, runtime = database
    with pytest.raises(RuntimeError, match="dedicated database, role and host"):
        migrate(runtime)
    migrate(owner)
    migrate(owner)
    PostgresStore(runtime).check_ready()
    migrate(owner, down=True)
    with psycopg.connect(owner) as db:
        assert db.execute("SELECT to_regclass('jt_workbench.audit')").fetchone() == (None,)
    migrate(owner)
    PostgresStore(runtime).check_ready()
    with psycopg.connect(owner, autocommit=True) as db:
        db.execute("GRANT UPDATE (action) ON jt_workbench.audit TO jt_workbench_runtime")
        with pytest.raises(RuntimeError, match="audit grants"):
            PostgresStore(runtime).check_ready()
        db.execute("REVOKE UPDATE (action) ON jt_workbench.audit FROM jt_workbench_runtime")
    with psycopg.connect(runtime, autocommit=True) as db:
        db.execute("INSERT INTO jt_workbench.audit (timestamp, action, result) VALUES (0, 'login_failed', 'denied')")
        for statement in ("UPDATE jt_workbench.audit SET action = 'view'", "DELETE FROM jt_workbench.audit",
                          "TRUNCATE jt_workbench.audit", "SET ROLE jt_workbench_owner"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute(statement)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(make_conninfo(runtime, dbname="unrelated_cj"))
    with pytest.raises(psycopg.errors.RaiseException, match="populated"):
        migrate(owner, down=True)
    with psycopg.connect(owner) as db:
        assert db.execute("SELECT count(*) FROM jt_workbench.audit").fetchone() == (1,)


def worker_login(dsn):
    return account_auth(PostgresStore(dsn)).login(ADMIN, PASSWORD, totp_at_step(SEED, NOW // 30))


def test_workers_share_totp_replay_sessions_and_audit(database):
    store, runtime = prepare(database)
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn")) as pool:
        tokens = tuple(pool.map(worker_login, (runtime, runtime)))
    [token] = [value for value in tokens if value is not None]
    another = account_auth(PostgresStore(runtime))
    assert another.require_session(token).username == ADMIN
    csrf = another.require_session(token).csrf
    with pytest.raises(InvalidAccount):
        another.manage_account(token, csrf, AccountAction.CREATE, ADMIN, "admin")
    another.logout(token, csrf)
    with pytest.raises(AuthenticationRequired):
        account_auth(store).require_session(token)
    with store.locked():
        assert [event.action for event in store.audit_events()] == [
            AuditAction.ACCOUNT_CREATED, AuditAction.LOGIN, AuditAction.LOGIN_FAILED,
            AuditAction.ACCOUNT_CREATED, AuditAction.LOGOUT,
        ]
        assert store.audit_events()[-2].result == AuditResult.DENIED


def test_limits_and_lockouts_are_shared(database):
    store, runtime = prepare(database)
    for i in range(5):
        assert account_auth(PostgresStore(runtime), NOW + i).login(ADMIN, "bad", "123456") is None
    assert account_auth(store, NOW + 5).login(ADMIN, PASSWORD, totp_at_step(SEED, NOW // 30)) is None
    with store.locked():
        assert store.failures(ADMIN, NOW + 5).count == 5

    def attempt(_):
        worker = PostgresStore(runtime)
        with worker.locked():
            return worker.allow_login_attempt(NOW + 600, window=60, limit=3)

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(8))) == 3


def test_seed_review_export_and_audit_survive_restart(database):
    owner, _ = database
    with psycopg.connect(owner, autocommit=True) as db:
        db.execute("ALTER DATABASE jt_workbench SET TimeZone = 'Asia/Hong_Kong'")
    store, runtime = prepare(database)
    signals = generate_dataset().signals
    store.seed(signals)
    other = PostgresStore(runtime)
    other.seed(signals)
    assert other.snapshot() == store.snapshot()
    original = signals[0]
    with pytest.raises(ValueError, match="conflicting signal"):
        run(other.publish(original.model_copy(update={"redacted_fragments": ("different",)})))
    auth = account_auth(store)
    admin_token = auth.login(ADMIN, PASSWORD, totp_at_step(SEED, NOW // 30))
    setup = auth.manage_account(admin_token, auth.require_session(admin_token).csrf,
                                AccountAction.CREATE, STAFF, "reviewer")
    assert account_auth(other).bind_account(STAFF, setup, PASSWORD, seed_text(STAFF_SEED),
                                            totp_at_step(STAFF_SEED, NOW // 30))
    staff_auth = account_auth(PostgresStore(runtime), NOW + 30)
    app = create_app(staff_auth, port=8443, queue=staff_auth.store)
    reference = other.snapshot()[0].reference
    pending = other.alerts()[0]
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as browser:
        response = browser.get("/login")
        csrf = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
        credentials = {
            "username": STAFF, "password": PASSWORD, "code": totp_at_step(STAFF_SEED, (NOW + 30) // 30), "csrf": csrf,
        }
        assert browser.post("/login", headers={"Origin": ORIGIN},
                            data={**credentials, "username": STAFF + "\0"}).status_code == 400
        login = browser.post("/login", headers={"Origin": ORIGIN}, data=credentials)
        assert login.status_code == 303 and SESSION_COOKIE in browser.cookies
        detail = browser.get("/queue", params={"signal": reference})
        csrf = re.search(r'name="csrf" value="([^"]+)"', detail.text).group(1)
        review = browser.post("/queue/review", headers={"Origin": ORIGIN}, data={
            "signal": reference, "csrf": csrf, "actual_severity": "P0", "false_positive": "0", "missed": "0",
            "note": "合成复核",
        })
        assert review.status_code == 303
        assert browser.get("/admin/audit").status_code == 403
        sample = browser.get("/queue/export").json()["samples"][0]["review"]
        assert sample["note"] == "合成复核"
        assert sample["recorded_at"].endswith("+00:00")

    reopened = PostgresStore(runtime)
    assert reopened.item(reference).reviews[0].actor == STAFF
    assert reopened.alerts()[0] == pending - 1
    with reopened.locked():
        assert any(event.action == AuditAction.ANNOTATE and event.signal_reference == reference
                   for event in reopened.audit_events())
    with pytest.raises(AccessDenied):
        account_auth(reopened).bootstrap_admin(ADMIN, PASSWORD, seed_text(SEED), "000000")


def test_review_and_audit_rollback_together(database):
    store, runtime = prepare(database)
    store.seed(generate_dataset().signals)
    item = store.snapshot()[0]
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        with store.locked():
            store.append_review(item, Review("P0", False, False, "合成复核", ADMIN, datetime.fromtimestamp(NOW, UTC)))
            store.append_audit(AuditEvent(NOW, AuditAction.ANNOTATE, ADMIN, "invalid-case-id"))
    after = PostgresStore(runtime)
    assert after.item(item.reference).reviews == ()
    with after.locked():
        assert tuple(event.action for event in after.audit_events()) == (AuditAction.ACCOUNT_CREATED,)


def test_expired_session_cannot_return_after_clock_moves_back(database):
    store, runtime = prepare(database)
    token = account_auth(store).login(ADMIN, PASSWORD, totp_at_step(SEED, NOW // 30))
    another = PostgresStore(runtime)
    with pytest.raises(AuthenticationRequired):
        account_auth(another, NOW + SESSION_IDLE).require_session(token)
    with pytest.raises(AuthenticationRequired):
        account_auth(store).require_session(token)



def unix_request(path, host, target, *, proto=()):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.connect(str(path))
        forwarded = "".join(f"X-Forwarded-Proto: {value}\r\n" for value in proto)
        sock.sendall(f"GET {target} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n{forwarded}\r\n".encode())
        with sock.makefile("rb") as response:
            head = response.read()
    return head.split(b"\r\n\r\n", 1)[0].decode().lower()


def test_production_commands_and_socket_boundary(database, monkeypatch):
    owner, runtime = database
    monkeypatch.setenv(production.DATABASE_VARIABLE, owner)
    monkeypatch.setattr(sys, "argv", ["production", "migrate"])
    production.main()

    monkeypatch.setenv(production.DATABASE_VARIABLE, runtime)
    monkeypatch.setattr(sys, "argv", ["production", "bootstrap-admin"])
    monkeypatch.setattr(local_cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: ADMIN)
    inputs = iter((PASSWORD, seed_text(SEED), totp_at_step(SEED, int(time.time()) // 30)))
    monkeypatch.setattr(local_cli, "getpass", lambda _prompt: next(inputs))
    production.main()
    with pytest.raises(SystemExit) as duplicate:
        production.main()
    assert duplicate.value.code == 2

    host = "jtadmin.go2china.space"
    with TemporaryDirectory(prefix="jt-http-", dir="/tmp") as directory:
        path = Path(directory) / "http.sock"
        env = {"PATH": os.defpath,
               production.DATABASE_VARIABLE: runtime,
               production.HOST_VARIABLE: host,
               production.SOCKET_VARIABLE: str(path)}
        with subprocess.Popen([sys.executable, "-B", "-m", "jt.workbench.production", "serve"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as server:
            try:
                end = time.monotonic() + 8
                while time.monotonic() < end and server.poll() is None:
                    try:
                        if production.probe_health(path):
                            break
                    except OSError:
                        pass
                    time.sleep(.05)
                else:
                    pytest.fail("socket-only workbench did not start")
                subprocess.run([sys.executable, "-B", "-m", "jt.workbench.production", "healthcheck"],
                               env=env, check=True, timeout=5)
                assert path.stat().st_mode & 0o777 == 0o660
                health = unix_request(path, HEALTH_HOST, "/healthz")
                assert health.startswith("http/1.1 200 ")
                login = unix_request(path, host, "/login", proto=("https",))
                assert login.startswith("http/1.1 200 ")
                assert "strict-transport-security: max-age=31536000" in login
                assert "frame-ancestors 'none'" in login and "default-src 'none'" in login
                assert "x-robots-tag: noindex" in login and "x-content-type-options: nosniff" in login
                assert "secure" in login and "httponly" in login and "samesite=strict" in login
                anonymous = unix_request(path, host, "/queue", proto=("https",))
                assert anonymous.startswith("http/1.1 303 ") and "location: /login" in anonymous
                canonical = unix_request(path, host, "/queue/", proto=("https",))
                assert canonical.startswith("http/1.1 307 ") and f"location: https://{host}/queue" in canonical
                assert unix_request(path, host, "/queue/alerts", proto=("https",)).startswith("http/1.1 401 ")
                assert unix_request(path, host, "/healthz", proto=("https",)).startswith("http/1.1 404 ")
                for claimed in ((), ("http",), ("https", "http"), ("https", "https")):
                    assert unix_request(path, host, "/login", proto=claimed).startswith("http/1.1 400 ")
                assert unix_request(path, "outside.example", "/login", proto=("https",)).startswith("http/1.1 400 ")
                assert unix_request(path, host, "/bootstrap-admin", proto=("https",)).startswith("http/1.1 404 ")
            finally:
                server.terminate()
                server.wait(timeout=8)
        assert not path.exists()


def test_tcp_peer_cannot_claim_caddy_or_local_health():
    app = create_app(Auth(MemoryStore()), proxy=ProxyEntry("jtadmin.go2china.space", lambda: None))
    with TestClient(app, base_url="http://jtadmin.go2china.space", follow_redirects=False) as browser:
        assert browser.get("/login", headers={"X-Forwarded-Proto": "https"}).status_code == 400
        assert browser.get("/healthz", headers={"Host": HEALTH_HOST}).status_code == 400
        assert browser.get("https://jtadmin.go2china.space/login").status_code == 400


def test_socket_ownership_conflict_and_restart():
    with TemporaryDirectory(prefix="jt-owned-http-", dir="/tmp") as directory:
        tmp_path = Path(directory)
        path = tmp_path / "http.sock"
        tmp_path.chmod(0o777)
        with pytest.raises(RuntimeError, match="directory"):
            with production.private_listener(path):
                pass
        tmp_path.chmod(0o750)
        path.write_text("retained")
        with pytest.raises(RuntimeError, match="occupied"):
            with production.private_listener(path):
                pass
        assert path.read_text() == "retained"
        path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
            stale.bind(str(path))
        with production.private_listener(path):
            with pytest.raises(BlockingIOError):
                with production.private_listener(path):
                    pass
        assert not path.exists()



def test_case_audit_migrates_from_v1_and_remains_append_only(database):
    owner, runtime = database
    migration = Path(__file__).resolve().parents[1] / "migrations" / "001_up.sql"
    with psycopg.connect(owner) as db:
        db.execute(migration.read_text())
    with psycopg.connect(runtime) as db:
        db.execute("INSERT INTO jt_workbench.audit (timestamp, action, result) VALUES (1, 'login_failed', 'denied')")
    migrate(owner)
    migrate(owner)
    store = PostgresStore(runtime)
    store.check_ready()
    identifier = "654193d5-88f3-4e8b-ab21-e88630eaf7a8"
    detail = CaseAuditDetail("confirm", "draft_itinerary_change", 3, "customer_consent_required")
    with store.locked():
        store.append_audit(AuditEvent(NOW, AuditAction.DECIDE, case_id=identifier,
                                      result=AuditResult.DENIED, case_detail=detail))
    reopened = PostgresStore(runtime)
    with reopened.locked():
        old, current = reopened.audit_events()
        assert old.action == AuditAction.LOGIN_FAILED and old.case_detail is None
        assert current.case_id == identifier and current.case_detail == detail
    with psycopg.connect(runtime, autocommit=True) as db:
        assert db.execute("SELECT version FROM jt_workbench.schema_version").fetchall() == [(1,)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("UPDATE jt_workbench.audit SET case_action = 'advance'")
    with pytest.raises(psycopg.errors.RaiseException, match="populated"):
        migrate(owner, down=True)
    reopened.check_ready()


def test_demo_bootstrap_command_binds_web_and_operations_audit_persists(database, monkeypatch, capsys):
    owner, runtime = database
    # Model an upgrade from the case workbench that already had durable records.
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with psycopg.connect(owner) as db:
        db.execute((migrations / "001_up.sql").read_text())
        db.execute((migrations / "002_up.sql").read_text())
    migrate(owner)
    store = PostgresStore(runtime)
    store.check_ready()
    monkeypatch.setenv(production.DATABASE_VARIABLE, runtime)
    monkeypatch.setattr(sys, "argv", ["production", "bootstrap-admin-code", "--username", ADMIN])
    monkeypatch.setattr(production.sys.stdout, "isatty", lambda: False)
    with pytest.raises(SystemExit) as non_interactive:
        production.main()
    assert non_interactive.value.code == 2
    with store.locked():
        assert store.accounts() == ()
    monkeypatch.setattr(production.sys.stdout, "isatty", lambda: True)
    production.main()
    synthetic_setup_code = capsys.readouterr().out.splitlines()[-1]
    auth = Auth(store, clock=store.clock, monotonic=store.clock)
    with TestClient(create_app(auth), base_url=ORIGIN, follow_redirects=False) as browser:
        setup = browser.get("/setup")
        nonce = re.search(r'name="csrf" value="([^"]+)"', setup.text).group(1)
        response = browser.post("/setup", headers={"Origin": ORIGIN}, data={
            "username": ADMIN, "password": PASSWORD, "seed": seed_text(SEED),
            "setup_code": synthetic_setup_code, "csrf": nonce,
            "code": totp_at_step(SEED, int(time.time()) // 30),
        })
        assert "设置完成" in response.text
        assert PASSWORD not in response.text and synthetic_setup_code not in response.text
    with pytest.raises(SystemExit) as already_bound:
        production.main()
    assert already_bound.value.code == 1
    assert synthetic_setup_code not in capsys.readouterr().out

    detail = OperationsAuditDetail("request:accepted", "sr_demo_01")
    with store.locked():
        store.append_audit(AuditEvent(store.clock(), AuditAction.DECIDE, ADMIN, operations_detail=detail))
    reopened = PostgresStore(runtime)
    with reopened.locked():
        assert reopened.audit_events()[-1].operations_detail == detail
    with psycopg.connect(runtime, autocommit=True) as db:
        assert db.execute("SELECT version FROM jt_workbench.case_audit_version").fetchall() == [(2,)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("UPDATE jt_workbench.audit SET operations_action = 'request:completed'")
