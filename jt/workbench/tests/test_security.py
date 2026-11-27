import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from jt.workbench import auth as auth_module
from jt.workbench.app import PRE_LOGIN_COOKIE, SESSION_COOKIE, create_app
from jt.workbench.auth import LOCKOUT, SESSION_IDLE, SESSION_LIFETIME, AccessDenied, Auth, InvalidAccount
from jt.workbench.security import PasswordHash, token_digest
from jt.workbench.store import Account, AuditAction, AuditEvent, AuditResult, MemoryStore, Role


ORIGIN = "https://127.0.0.1:8443"
ADMIN = "local-supervisor"
ADMIN_PASSWORD = "synthetic local passphrase"
STAFF = "sample-reviewer"
STAFF_PASSWORD = "synthetic staff passphrase"
NEW_PASSWORD = "another synthetic passphrase"
UUID_MARKER = "00000000-1510-4500-9000-000000000000"


@dataclass
class Clock:
    now: int = 1_734_000_000

    def __call__(self) -> int:
        return self.now


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


def client(auth: Auth) -> TestClient:
    return TestClient(create_app(auth, port=8443), base_url=ORIGIN, follow_redirects=False)


def post(browser: TestClient, path: str, data: dict, origin: str = ORIGIN):
    return browser.post(path, data=data, headers={"Origin": origin})


def sign_in(browser: TestClient, *, username: str = ADMIN, password: str = ADMIN_PASSWORD):
    return post(browser, "/login", {"csrf": csrf(browser.get("/login")), "username": username, "password": password})


def create_staff(admin: TestClient, *, role: str = "reviewer", password: str = STAFF_PASSWORD, confirm: str | None = None,
                 username: str = STAFF):
    return post(admin, "/admin/accounts/create", {
        "csrf": csrf(admin.get("/admin/accounts")), "username": username, "role": role, "password": password,
        "confirm": password if confirm is None else confirm,
    })


def manage(admin: TestClient, action: str, *, role: str = "reviewer", username: str = STAFF):
    return post(admin, "/admin/accounts", {
        "csrf": csrf(admin.get("/admin/accounts")), "username": username, "role": role, "action": action,
    })


def reset_password(admin: TestClient, password: str, *, username: str = STAFF, confirm: str | None = None):
    return post(admin, "/admin/accounts/password", {
        "csrf": csrf(admin.get("/admin/accounts")), "username": username, "password": password,
        "confirm": password if confirm is None else confirm,
    })


@pytest.fixture
def local():
    clock = Clock()
    store = MemoryStore()
    auth = Auth(store, clock=clock, monotonic=clock)
    auth.bootstrap_admin(ADMIN, ADMIN_PASSWORD)
    return clock, store, auth


def test_login_bootstrap_hash_and_cookie_policy(local):
    clock, store, auth = local
    with client(auth) as browser:
        assert browser.get("/").status_code == 401
        login = browser.get("/login")
        assert login.status_code == 200
        assert 'lang="zh-CN"' in login.text
        assert "验证码" not in login.text and 'name="code"' not in login.text and "/setup" not in login.text
        assert "no-store" == login.headers["cache-control"]
        assert "same-origin" == login.headers["referrer-policy"]
        assert "default-src 'none'" in login.headers["content-security-policy"]
        assert PRE_LOGIN_COOKIE in login.headers["set-cookie"]
        response = sign_in(browser)
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
        assert browser.get("/setup").status_code == 404
    account = store.account(ADMIN)
    assert account.role is Role.ADMIN
    assert isinstance(account.password, PasswordHash)
    assert account.password.matches(ADMIN_PASSWORD)
    assert account.password.digest != ADMIN_PASSWORD.encode()
    assert len(account.password.salt) == 16
    assert ADMIN_PASSWORD not in repr(account)
    with pytest.raises(AccessDenied):
        auth.bootstrap_admin(STAFF, STAFF_PASSWORD)
    assert [event.action for event in store.audit_events()] == [AuditAction.ACCOUNT_CREATED, AuditAction.LOGIN]


def test_password_policy_and_salted_hashes(local):
    _clock, store, auth = local
    assert PasswordHash.make(ADMIN_PASSWORD).salt != PasswordHash.make(ADMIN_PASSWORD).salt
    empty = Auth(MemoryStore())
    for password in ("", "elevenchars", "x" * 129):
        with pytest.raises(InvalidAccount):
            empty.bootstrap_admin("first-admin", password)
    empty.bootstrap_admin("first-admin", "exactly12chr")
    with client(auth) as admin:
        assert sign_in(admin).status_code == 303
        assert create_staff(admin, password="elevenchars").status_code == 400
        assert create_staff(admin, password="x" * 129).status_code == 400
        assert store.account(STAFF) is None
        assert create_staff(admin, password="exactly12chr").status_code == 200
        assert reset_password(admin, "short").status_code == 400
        assert store.account(STAFF).password.matches("exactly12chr")


def test_role_isolation_and_csrf_protect_all_writes(local):
    clock, store, auth = local
    with client(auth) as admin, client(auth) as staff:
        for path in ("/admin/accounts", "/admin/accounts/create", "/admin/accounts/password"):
            assert post(staff, path, {"csrf": "bad"}).status_code in (400, 401)
        assert staff.get("/admin/accounts").status_code == 401
        assert staff.get("/admin/audit").status_code == 401
        assert post(staff, "/register", {"csrf": "bad"}).status_code == 404
        assert sign_in(admin).status_code == 303
        token = csrf(admin.get("/admin/accounts"))
        form = {"csrf": token, "username": STAFF, "role": "reviewer", "password": STAFF_PASSWORD, "confirm": STAFF_PASSWORD}
        assert post(admin, "/admin/accounts/create", form, "https://outside.example.test").status_code == 403
        assert admin.post("/admin/accounts/create", data=form).status_code == 403
        assert post(admin, "/admin/accounts/create", {**form, "csrf": "tampered"}).status_code == 403
        assert store.account(STAFF) is None
        assert create_staff(admin).status_code == 200
        assert create_staff(admin).status_code == 400
        assert store.account(STAFF).role is Role.REVIEWER
        assert sign_in(staff, username=STAFF, password="incorrect value").status_code == 401
        assert sign_in(staff, username=STAFF, password=STAFF_PASSWORD).status_code == 303
        # A signed-in non-administrator is refused on every management and audit route.
        assert staff.get("/admin/accounts").status_code == 403
        assert staff.get("/admin/audit").status_code == 403
        own = csrf(staff.get("/"))
        for path, data in (
            ("/admin/accounts/create", {"csrf": own, "username": "another-admin", "role": "admin",
                                        "password": STAFF_PASSWORD, "confirm": STAFF_PASSWORD}),
            ("/admin/accounts/password", {"csrf": own, "username": ADMIN, "password": NEW_PASSWORD, "confirm": NEW_PASSWORD}),
            ("/admin/accounts", {"csrf": own, "username": ADMIN, "role": "reviewer", "action": "disable"}),
            ("/admin/accounts", {"csrf": own, "username": ADMIN, "role": "reviewer", "action": "delete"}),
        ):
            assert post(staff, path, data).status_code == 403
        assert store.account("another-admin") is None
        assert store.account(ADMIN).enabled and store.account(ADMIN).password.matches(ADMIN_PASSWORD)
        old_token = staff.cookies[SESSION_COOKIE]
        assert post(staff, "/logout", {"csrf": "tampered"}).status_code == 403
        assert post(staff, "/logout", {"csrf": csrf(staff.get("/"))}).status_code == 303
        assert store.session(token_digest(old_token)) is None
        assert staff.get("/").status_code == 401


def test_login_rejects_bad_credentials_and_csrf(local):
    clock, store, auth = local
    with client(auth) as browser:
        nonce = csrf(browser.get("/login"))
        form = {"csrf": nonce, "username": ADMIN, "password": ADMIN_PASSWORD}
        assert post(browser, "/login", form, "https://outside.example.test").status_code == 403
        assert browser.post("/login", data=form).status_code == 403
        assert post(browser, "/login", form, "null").status_code == 403
        assert post(browser, "/login", {**form, "csrf": "tampered"}).status_code == 403
        assert post(browser, "/login", {**form, "code": "123456"}).status_code == 400
        assert sign_in(browser, password="incorrect").status_code == 401
        assert sign_in(browser, username="unknown-user").status_code == 401
        assert SESSION_COOKIE not in browser.cookies
        assert sign_in(browser).status_code == 303
        old_token = browser.cookies[SESSION_COOKIE]
        assert sign_in(browser).status_code == 303
        assert browser.cookies[SESSION_COOKIE] != old_token
        assert store.session(token_digest(old_token)) is None


def test_concurrent_logins_each_get_their_own_session(local):
    clock, store, auth = local
    with ThreadPoolExecutor(2) as pool:
        attempts = [pool.submit(auth.login, ADMIN, ADMIN_PASSWORD) for _ in range(2)]
        tokens = [attempt.result() for attempt in attempts]
    assert all(tokens) and tokens[0] != tokens[1]
    assert [event.action for event in store.audit_events()[1:]] == [AuditAction.LOGIN, AuditAction.LOGIN]


def test_idle_and_absolute_expiry(local):
    clock, store, auth = local
    with client(auth) as browser:
        assert sign_in(browser).status_code == 303
        clock.now += SESSION_IDLE
        assert browser.get("/admin/audit").status_code == 401
        assert SESSION_COOKIE not in browser.cookies
        assert sign_in(browser).status_code == 303
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
            assert sign_in(browser, password="incorrect").status_code == 401
        assert sign_in(browser).status_code == 401
        assert store.failures(ADMIN, clock.now).count == auth_module.FAILURE_LIMIT
        clock.now += LOCKOUT
        assert sign_in(browser).status_code == 303
        clock.now += 60
        monkeypatch.setattr(auth_module, "RATE_LIMIT", 2)
        for username in ("anonymous-one", "anonymous-two"):
            assert sign_in(browser, username=username).status_code == 401
        assert sign_in(browser).status_code == 401
        assert store.failures(ADMIN, clock.now).count == 0
        clock.now += auth_module.RATE_WINDOW
        assert sign_in(browser).status_code == 303


def test_audit_append_only_and_no_secret_echo(local, caplog):
    clock, store, auth = local
    with client(auth) as browser:
        invalid = sign_in(browser, username=UUID_MARKER[:32])
        assert invalid.status_code == 401
        assert sign_in(browser).status_code == 303
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
        assert all(value not in output for value in (ADMIN_PASSWORD, UUID_MARKER[:32]))


def test_admin_manages_accounts_with_audit_and_no_password_in_records(local):
    clock, store, auth = local
    with client(auth) as admin, client(auth) as staff:
        assert sign_in(admin).status_code == 303
        page = create_staff(admin)
        assert page.status_code == 200 and STAFF_PASSWORD not in page.text and "正常" in page.text
        assert post(admin, "/admin/accounts/create", {
            "csrf": csrf(page), "username": "mistyped-one", "role": "operator", "password": STAFF_PASSWORD,
            "confirm": "a different confirmation",
        }).status_code == 400
        assert store.account("mistyped-one") is None
        assert sign_in(staff, username=STAFF, password=STAFF_PASSWORD).status_code == 303
        assert "复核员" in staff.get("/").text
        # Failed attempts lock the account; the administrator unlocks it.
        for _ in range(auth_module.FAILURE_LIMIT):
            assert sign_in(staff, username=STAFF, password="incorrect").status_code == 401
        assert "已锁定" in admin.get("/admin/accounts").text
        assert sign_in(staff, username=STAFF, password=STAFF_PASSWORD).status_code == 401
        assert manage(admin, "unlock").status_code == 200
        assert sign_in(staff, username=STAFF, password=STAFF_PASSWORD).status_code == 303
        # Changing the role and resetting the password end the employee's sessions.
        assert manage(admin, "change_role", role="operator").status_code == 200
        assert staff.get("/").status_code == 401
        assert sign_in(staff, username=STAFF, password=STAFF_PASSWORD).status_code == 303
        assert "值班处理员" in staff.get("/").text
        assert reset_password(admin, NEW_PASSWORD, confirm="does not match this").status_code == 400
        assert reset_password(admin, NEW_PASSWORD).status_code == 200
        assert staff.get("/").status_code == 401
        assert sign_in(staff, username=STAFF, password=STAFF_PASSWORD).status_code == 401
        assert sign_in(staff, username=STAFF, password=NEW_PASSWORD).status_code == 303
        # Disable, re-enable, then retire. Deleting needs a disabled account and clears the password.
        assert manage(admin, "delete").status_code == 400
        assert manage(admin, "disable").status_code == 200
        assert staff.get("/").status_code == 401
        assert sign_in(staff, username=STAFF, password=NEW_PASSWORD).status_code == 401
        assert reset_password(admin, STAFF_PASSWORD).status_code == 400
        assert manage(admin, "enable").status_code == 200
        assert sign_in(staff, username=STAFF, password=NEW_PASSWORD).status_code == 303
        assert manage(admin, "disable").status_code == 200
        deleted = manage(admin, "delete")
        assert deleted.status_code == 200 and "已删除" in deleted.text
        assert store.account(STAFF).password is None and not store.account(STAFF).enabled
        assert manage(admin, "enable").status_code == 400
        assert sign_in(staff, username=STAFF, password=NEW_PASSWORD).status_code == 401
        assert create_staff(admin).status_code == 400
        # The administrator can neither disable, delete nor demote the own account.
        for action in ("disable", "delete", "change_role"):
            assert manage(admin, action, username=ADMIN).status_code == 400
        assert admin.get("/").status_code == 200
        assert manage(admin, "disable", username="no-such-user").status_code == 400
        assert post(admin, "/admin/accounts", {"csrf": csrf(admin.get("/admin/accounts")), "username": STAFF,
                                                "role": "reviewer", "action": "create"}).status_code == 400
        events = store.audit_events()
        assert {AuditAction.ACCOUNT_CREATED, AuditAction.PASSWORD_RESET, AuditAction.ACCOUNT_DISABLED,
                AuditAction.ACCOUNT_ENABLED, AuditAction.ACCOUNT_DELETED, AuditAction.ACCOUNT_UNLOCKED,
                AuditAction.ROLE_CHANGED} <= {event.action for event in events}
        assert any(event.action is AuditAction.ACCOUNT_DELETED and event.actor == ADMIN
                   and event.staff_target == STAFF and event.result is AuditResult.SUCCESS for event in events)
        assert any(event.action is AuditAction.ACCOUNT_DELETED and event.result is AuditResult.DENIED for event in events)
        audit_page = admin.get("/admin/audit").text
        assert "重设密码" in audit_page and "删除账号" in audit_page
        everything = repr(events) + audit_page + admin.get("/admin/accounts").text
        assert all(secret not in everything for secret in (STAFF_PASSWORD, NEW_PASSWORD, ADMIN_PASSWORD))


def test_administrator_resets_the_own_password_and_must_sign_in_again(local):
    clock, store, auth = local
    with client(auth) as admin, client(auth) as other:
        assert sign_in(admin).status_code == 303
        assert sign_in(other).status_code == 303
        response = reset_password(admin, NEW_PASSWORD, username=ADMIN)
        assert response.status_code == 303 and response.headers["location"] == "/login"
        assert admin.get("/").status_code == 401 and other.get("/").status_code == 401
        assert sign_in(admin).status_code == 401
        assert sign_in(admin, password=NEW_PASSWORD).status_code == 303
    assert any(event.action is AuditAction.PASSWORD_RESET and event.staff_target == ADMIN for event in store.audit_events())


def test_last_administrator_cannot_be_removed_and_disabled_admins_do_not_count(local):
    clock, store, auth = local
    with client(auth) as admin:
        assert sign_in(admin).status_code == 303
        assert create_staff(admin, role="admin", username="second-admin").status_code == 200
        assert manage(admin, "disable", username="second-admin").status_code == 200
        assert auth.has_admin()
        assert manage(admin, "disable", username=ADMIN).status_code == 400
    # Only a disabled administrator remains: the first-admin command is open again, never alongside an active one.
    store.save_account(Account(ADMIN, Role.ADMIN, None, False))
    assert not auth.has_admin()
    with pytest.raises(InvalidAccount):
        auth.bootstrap_admin(ADMIN, NEW_PASSWORD)
    auth.bootstrap_admin("jtcao01", NEW_PASSWORD)
    assert auth.has_admin()
    with pytest.raises(AccessDenied):
        auth.bootstrap_admin("jtcao02", NEW_PASSWORD)


def test_audit_filters_by_date_actor_action_and_result(local):
    clock, store, auth = local
    with client(auth) as admin:
        assert sign_in(admin).status_code == 303
        store.append_audit(AuditEvent(clock.now, AuditAction.REVEAL, ADMIN, "CASE-DENIED", AuditResult.DENIED))
        store.append_audit(AuditEvent(clock.now, AuditAction.REVEAL, ADMIN, "CASE-OK"))
        filtered = admin.get("/admin/audit", params={"actor": ADMIN, "action": "reveal", "result": "denied", "start": "2024-12-01", "end": "2024-12-31"})
        assert filtered.status_code == 200
        assert "CASE-DENIED" in filtered.text and "CASE-OK" not in filtered.text
        assert "CASE-DENIED" not in admin.get("/admin/audit?end=2024-01-01").text
        assert admin.get("/admin/audit?start=2024-02-01&end=2024-01-01").status_code == 400
