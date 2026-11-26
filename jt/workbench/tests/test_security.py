import base64
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from jt.workbench import auth as auth_module
from jt.workbench.app import PRE_LOGIN_COOKIE, SESSION_COOKIE, create_app
from jt.workbench.auth import LOCKOUT, SESSION_IDLE, SESSION_LIFETIME, SETUP_LIFETIME, AccessDenied, Auth
from jt.workbench.security import PasswordHash, token_digest, totp_at_step
from jt.workbench.store import AuditAction, AuditEvent, AuditResult, MemoryStore, Role


ORIGIN = "https://127.0.0.1:8443"
ADMIN = "local-supervisor"
ADMIN_PASSWORD = "synthetic local passphrase"
STAFF = "sample-reviewer"
STAFF_PASSWORD = "synthetic staff passphrase"
ADMIN_SEED = bytes(range(20))
STAFF_SEED = bytes(range(20, 40))
UUID_MARKER = "00000000-1510-4500-9000-000000000000"


@dataclass
class Clock:
    now: int = 1_734_000_000

    def __call__(self) -> int:
        return self.now

    def code(self, seed: bytes = ADMIN_SEED) -> str:
        return totp_at_step(seed, self.now // 30)


class CsrfInput(HTMLParser):
    value: str

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "input" and attrs.get("name") == "csrf":
            self.value = attrs["value"]


def csrf(response) -> str:
    parser = CsrfInput()
    parser.feed(response.text)
    return parser.value


def seed_text(seed: bytes) -> str:
    return base64.b32encode(seed).decode()


def client(auth: Auth) -> TestClient:
    return TestClient(create_app(auth, port=8443), base_url=ORIGIN, follow_redirects=False)


def post(browser: TestClient, path: str, data: dict, origin: str = ORIGIN):
    return browser.post(path, data=data, headers={"Origin": origin})


def sign_in(browser: TestClient, clock: Clock, *, username: str = ADMIN, password: str = ADMIN_PASSWORD, code: str | None = None):
    return post(browser, "/login", {
        "csrf": csrf(browser.get("/login")), "username": username, "password": password,
        "code": clock.code() if code is None else code,
    })


def staff_form(token: str, *, action: str = "create", role: str = "reviewer") -> dict:
    return {"csrf": token, "username": STAFF, "role": role, "action": action}


def setup_code(response) -> str:
    return re.search(r'<section class="notice" role="status">.*?<code>([A-Za-z0-9_-]{43})</code>', response.text).group(1)


def bind(browser: TestClient, clock: Clock, grant: str, *, password: str = STAFF_PASSWORD, seed: bytes = STAFF_SEED):
    return post(browser, "/setup", {"csrf": csrf(browser.get("/setup")), "username": STAFF,
                                    "setup_code": grant, "password": password,
                                    "seed": seed_text(seed), "code": clock.code(seed)})


@pytest.fixture
def local():
    clock = Clock()
    store = MemoryStore()
    auth = Auth(store, clock=clock, monotonic=clock)
    auth.bootstrap_admin(ADMIN, ADMIN_PASSWORD, seed_text(ADMIN_SEED), clock.code())
    clock.now += 30
    return clock, store, auth


def test_rfc_6238_sha1_reference_vectors():
    seed = b"12345678901234567890"
    for timestamp, expected in (
        (59, "94287082"), (1_111_111_109, "07081804"), (1_111_111_111, "14050471"),
        (1_234_567_890, "89005924"), (2_000_000_000, "69279037"), (20_000_000_000, "65353130"),
    ):
        assert totp_at_step(seed, timestamp // 30, digits=8) == expected


def test_login_bootstrap_hash_and_cookie_policy(local):
    clock, store, auth = local
    with client(auth) as browser:
        assert browser.get("/").status_code == 401
        login = browser.get("/login")
        assert login.status_code == 200
        assert 'lang="zh-CN"' in login.text
        assert "no-store" == login.headers["cache-control"]
        assert "default-src 'none'" in login.headers["content-security-policy"]
        assert PRE_LOGIN_COOKIE in login.headers["set-cookie"]
        response = sign_in(browser, clock)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        cookie = next(value for value in response.headers.get_list("set-cookie") if value.startswith(SESSION_COOKIE))
        assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"))
        assert "Domain=" not in cookie
        assert PRE_LOGIN_COOKIE not in browser.cookies
        assert browser.get("/").status_code == 200
        token = browser.cookies[SESSION_COOKIE]
        assert store.session(token_digest(token)).username == ADMIN
        assert store.session(token.encode()) is None
        assert browser.get("/", headers={"Host": "outside.example.test"}).status_code == 400
        assert browser.get("http://127.0.0.1:8443/").status_code == 400
    account = store.account(ADMIN)
    assert account.role is Role.ADMIN
    assert isinstance(account.password, PasswordHash)
    assert account.password.matches(ADMIN_PASSWORD)
    assert account.password.digest != ADMIN_PASSWORD.encode()
    assert ADMIN_PASSWORD not in repr(account)
    assert repr(ADMIN_SEED) not in repr(account)
    with pytest.raises(AccessDenied):
        auth.bootstrap_admin(STAFF, STAFF_PASSWORD, seed_text(STAFF_SEED), clock.code(STAFF_SEED))
    assert [event.action for event in store.audit_events()] == [AuditAction.ACCOUNT_CREATED, AuditAction.LOGIN]


def test_role_isolation_and_csrf_protect_all_writes(local):
    clock, store, auth = local
    with client(auth) as admin, client(auth) as staff:
        assert staff.get("/admin/accounts").status_code == 401
        assert staff.get("/admin/audit").status_code == 401
        assert post(staff, "/admin/accounts", staff_form("bad")).status_code == 401
        assert post(staff, "/register", staff_form("bad")).status_code == 404
        assert sign_in(admin, clock).status_code == 303
        form = staff_form(csrf(admin.get("/admin/accounts")))
        assert post(admin, "/admin/accounts", form, "https://outside.example.test").status_code == 403
        assert post(admin, "/admin/accounts", {**form, "csrf": "tampered"}).status_code == 403
        assert store.account(STAFF) is None
        created = post(admin, "/admin/accounts", form)
        assert created.status_code == 201
        grant = setup_code(created)
        assert grant not in admin.get("/admin/accounts").text
        assert post(admin, "/admin/accounts", form).status_code == 400
        assert store.account(STAFF).role is Role.REVIEWER
        assert store.account(STAFF).password is None
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(STAFF_SEED)).status_code == 401
        assert bind(staff, clock, grant).status_code == 200
        assert bind(staff, clock, grant).status_code == 401
        clock.now += 30
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(STAFF_SEED)).status_code == 303
        assert staff.get("/admin/accounts").status_code == 403
        assert staff.get("/admin/audit").status_code == 403
        intruder = {**staff_form(csrf(staff.get("/"))), "role": "admin", "username": "another-admin"}
        assert post(staff, "/admin/accounts", intruder).status_code == 403
        assert store.account("another-admin") is None
        old_token = staff.cookies[SESSION_COOKIE]
        assert post(staff, "/logout", {"csrf": "tampered"}).status_code == 403
        assert post(staff, "/logout", {"csrf": csrf(staff.get("/"))}).status_code == 303
        assert store.session(token_digest(old_token)) is None
        assert staff.get("/").status_code == 401


def test_login_rejects_invalid_totp_replay_and_csrf(local):
    clock, store, auth = local
    with client(auth) as browser:
        nonce = csrf(browser.get("/login"))
        form = {"csrf": nonce, "username": ADMIN, "password": ADMIN_PASSWORD, "code": clock.code()}
        assert post(browser, "/login", form, "https://outside.example.test").status_code == 403
        assert browser.post("/login", data=form).status_code == 403
        assert post(browser, "/login", {**form, "csrf": "tampered"}).status_code == 403
        wrong_code = str((int(clock.code()) + 1) % 1_000_000).zfill(6)
        assert sign_in(browser, clock, code=wrong_code).status_code == 401
        assert SESSION_COOKIE not in browser.cookies
        assert sign_in(browser, clock).status_code == 303
        old_token = browser.cookies[SESSION_COOKIE]
        assert sign_in(browser, clock).status_code == 401
        clock.now += 30
        assert sign_in(browser, clock).status_code == 303
        assert browser.cookies[SESSION_COOKIE] != old_token
        assert store.session(token_digest(old_token)) is None


def test_concurrent_totp_replay_only_one_session(local):
    clock, store, auth = local
    code = clock.code()
    with ThreadPoolExecutor(2) as pool:
        attempts = [pool.submit(auth.login, ADMIN, ADMIN_PASSWORD, code) for _ in range(2)]
        assert sum(attempt.result() is not None for attempt in attempts) == 1
    assert [event.action for event in store.audit_events()[1:]] == [AuditAction.LOGIN, AuditAction.LOGIN_FAILED]


def test_idle_and_absolute_expiry(local):
    clock, store, auth = local
    with client(auth) as browser:
        assert sign_in(browser, clock).status_code == 303
        clock.now += SESSION_IDLE
        assert browser.get("/admin/audit").status_code == 401
        assert SESSION_COOKIE not in browser.cookies
        assert sign_in(browser, clock).status_code == 303
        started = clock.now
        while clock.now + SESSION_IDLE - 1 < started + SESSION_LIFETIME:
            clock.now += SESSION_IDLE - 1
            assert browser.get("/").status_code == 200
        clock.now = started + SESSION_LIFETIME
        assert browser.get("/").status_code == 401
    assert not any(event.action is AuditAction.VIEW for event in store.audit_events())


def test_account_lockout_and_global_rate_limit(local, monkeypatch):
    clock, store, auth = local
    with client(auth) as browser:
        for _ in range(auth_module.FAILURE_LIMIT):
            assert sign_in(browser, clock, password="incorrect").status_code == 401
        assert sign_in(browser, clock).status_code == 401
        assert store.failures(ADMIN, clock.now).count == auth_module.FAILURE_LIMIT
        clock.now += LOCKOUT
        assert sign_in(browser, clock).status_code == 303
        clock.now += 60
        monkeypatch.setattr(auth_module, "RATE_LIMIT", 2)
        for username in ("anonymous-one", "anonymous-two"):
            assert sign_in(browser, clock, username=username).status_code == 401
        assert sign_in(browser, clock).status_code == 401
        assert store.failures(ADMIN, clock.now).count == 0
        clock.now += auth_module.RATE_WINDOW
        assert sign_in(browser, clock).status_code == 303


def test_audit_append_only_and_no_secret_echo(local, caplog):
    clock, store, auth = local
    with client(auth) as browser:
        invalid = sign_in(browser, clock, username=UUID_MARKER[:32], password=ADMIN_PASSWORD)
        assert invalid.status_code == 401
        assert sign_in(browser, clock).status_code == 303
        first = store.audit_events()
        for action in (AuditAction.VIEW, AuditAction.ANNOTATE, AuditAction.REVEAL):
            store.append_audit(AuditEvent(clock.now, action, ADMIN, "CASE-0042"))
        assert store.audit_events()[:len(first)] == first
        response = browser.get("/admin/audit")
        assert response.status_code == 200
        assert all(label in response.text for label in ("登录失败", "查看", "标注", "揭示", "CASE-0042"))
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert browser.request(method, "/admin/audit").status_code == 405
        output = invalid.text + response.text + caplog.text + repr(store.audit_events())
        assert all(value not in output for value in (ADMIN_PASSWORD, seed_text(ADMIN_SEED), clock.code(), UUID_MARKER[:32]))


def test_admin_unlock_role_rebind_disable_and_grant_expiry(local):
    clock, store, auth = local
    new_seed = bytes(range(40, 60))
    with client(auth) as admin, client(auth) as staff:
        assert sign_in(admin, clock).status_code == 303
        def manage(action: str, *, role: str = "reviewer", username: str = STAFF):
            return post(admin, "/admin/accounts", {
                **staff_form(csrf(admin.get("/admin/accounts")), action=action, role=role), "username": username,
            })
        grant = setup_code(manage("create"))
        clock.now += SETUP_LIFETIME
        assert bind(staff, clock, grant).status_code == 401
        assert sign_in(admin, clock).status_code == 303
        grant = setup_code(manage("rebind"))
        assert bind(staff, clock, grant).status_code == 200
        clock.now += 30
        for _ in range(auth_module.FAILURE_LIMIT):
            assert sign_in(staff, clock, username=STAFF, password="incorrect", code=clock.code(STAFF_SEED)).status_code == 401
        assert "已锁定" in admin.get("/admin/accounts").text
        assert manage("unlock").status_code == 200
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(STAFF_SEED)).status_code == 303
        assert manage("change_role", role="operator").status_code == 200
        assert staff.get("/").status_code == 401
        clock.now += 30
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(STAFF_SEED)).status_code == 303
        assert "值班处理员" in staff.get("/").text
        grant = setup_code(manage("rebind", role="operator"))
        assert staff.get("/").status_code == 401
        assert bind(staff, clock, grant, password="another test passphrase", seed=new_seed).status_code == 401
        assert bind(staff, clock, grant, seed=new_seed).status_code == 200
        clock.now += 30
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(STAFF_SEED)).status_code == 401
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(new_seed)).status_code == 303
        assert manage("disable", role="operator").status_code == 200
        assert staff.get("/").status_code == 401
        clock.now += 30
        assert sign_in(staff, clock, username=STAFF, password=STAFF_PASSWORD, code=clock.code(new_seed)).status_code == 401
        assert manage("disable", username=ADMIN).status_code == 400
        assert admin.get("/").status_code == 200
        assert all(value not in repr(store.audit_events()) for value in (grant, STAFF_PASSWORD, seed_text(new_seed)))


def test_audit_filters_by_date_actor_action_and_result(local):
    clock, store, auth = local
    with client(auth) as admin:
        assert sign_in(admin, clock).status_code == 303
        store.append_audit(AuditEvent(clock.now, AuditAction.REVEAL, ADMIN, "CASE-DENIED", AuditResult.DENIED))
        store.append_audit(AuditEvent(clock.now, AuditAction.REVEAL, ADMIN, "CASE-OK"))
        filtered = admin.get("/admin/audit", params={"actor": ADMIN, "action": "reveal", "result": "denied", "start": "2024-12-01", "end": "2024-12-31"})
        assert filtered.status_code == 200
        assert "CASE-DENIED" in filtered.text and "CASE-OK" not in filtered.text
        assert "CASE-DENIED" not in admin.get("/admin/audit?end=2024-01-01").text
        assert admin.get("/admin/audit?start=2024-02-01&end=2024-01-01").status_code == 400
