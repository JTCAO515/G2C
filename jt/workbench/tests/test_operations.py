"""Demo routes, contract transitions, role gates and the first administrator."""

import re

import psycopg
import pytest
from fastapi.testclient import TestClient

from jt.workbench.app import SESSION_COOKIE, create_app
from jt.workbench.auth import AccessDenied, Auth, InvalidAccount
from jt.workbench.operations import DemoOperations
from jt.workbench.security import PasswordHash
from jt.workbench.store import Account, MemoryStore, Role


ORIGIN = "https://127.0.0.1:8443"
NOW = 1_734_000_030
PASSWORD = "synthetic demo operations password"


def clients(audit_store=None):
    store = audit_store if audit_store is not None else MemoryStore()
    auth = Auth(store, clock=lambda: NOW, monotonic=lambda: NOW)
    password = PasswordHash.make(PASSWORD)
    tokens = {}
    for role in Role:
        store.save_account(Account(role.value, role, password))
        tokens[role] = auth.login(role.value, PASSWORD)
    source = DemoOperations()
    app = create_app(auth, operations=source)
    return store, source, app, tokens


def client(app, token=None):
    browser = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    if token is not None:
        browser.cookies.set(SESSION_COOKIE, token)
    return browser


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def post(browser, path, nonce, *, origin=ORIGIN, **values):
    return browser.post(path, data={"csrf": nonce, **values}, headers={"Origin": origin})


def test_staff_operations_use_fixtures_and_separate_customer_view():
    store, source, app, tokens = clients()
    with client(app) as anonymous, client(app, tokens[Role.REVIEWER]) as reviewer, client(app, tokens[Role.OPERATOR]) as operator:
        assert anonymous.get("/operations").status_code == 401
        assert reviewer.get("/operations/leads").status_code == 403
        listing = operator.get("/operations")
        assert "演示数据" in listing.text and "结果未知" in listing.text
        assert all(state in listing.text for state in ("已接单", "已报价", "双方已确认", "已到场", "已完成", "已取消", "无法提供"))
        path = "/operations/requests/sr_demo_01"
        detail = operator.get(path)
        assert "演示数据" in detail.text and "+10000000001" in detail.text
        public, staff = detail.text.split('aria-label="员工专用字段"')
        assert "对客字段" in public and "演示收件" not in public and "ev_sr_demo" not in public
        assert "演示收件" in staff
        nonce = csrf(detail)
        form = {"target": "accepted", "seq": "2", "evidence": "合成接单", "amount": ""}
        assert post(operator, path, "bad", **form).status_code == 403
        assert post(operator, path, nonce, origin="https://outside.example.test", **form).status_code == 403
        assert post(operator, path, nonce, **{**form, "target": "completed"}).status_code == 409
        assert post(operator, path, nonce, **{**form, "evidence": ""}).status_code == 400
        assert post(operator, path, nonce, **form).status_code == 303
        assert post(operator, path, nonce, **form).status_code == 409
        assert source.request("sr_demo_01").state == "accepted"
        quote = {"target": "quoted", "seq": "3", "evidence": "演示报价", "amount": "48000"}
        assert post(operator, path, nonce, **quote).status_code == 303
        assert "¥480.00" in operator.get(path).text

        # A terminal unknown remains distinct from success until an evidenced adjustment.
        unknown = source.request("sr_demo_09")
        assert unknown.state == "outcome_unknown"
        assert post(operator, "/operations/requests/sr_demo_09", nonce, target="completed",
                    seq=str(len(unknown.history)), amount="", evidence="演示完成凭据").status_code == 303

    records = [e.operations_detail for e in store.audit_events() if e.operations_detail]
    assert [d.action for d in records] == ["request:accepted", "request:quoted", "request:completed"]
    with client(app, tokens[Role.ADMIN]) as admin:
        report = admin.get("/admin/audit?action=decide")
        assert "request:accepted" in report.text and "sr_demo_01" in report.text
        assert "+10000000001" not in report.text and "合成接单" not in report.text


def test_lead_actions_and_audit_failure_do_not_apply_the_change():
    class BrokenAudit(MemoryStore):
        def append_audit(self, event):
            if event.operations_detail and event.operations_detail.action == "lead:closed":
                raise psycopg.OperationalError("synthetic database unavailable")
            super().append_audit(event)

    store, source, app, tokens = clients(BrokenAudit())
    with client(app, tokens[Role.OPERATOR]) as operator:
        page = operator.get("/operations/leads")
        assert "演示数据" in page.text and "待联系" in page.text
        nonce = csrf(page)
        lead = "/operations/leads/demo_lead_01"
        assert post(operator, lead, nonce, target="contacted").status_code == 303
        assert post(operator, lead, nonce, target="converted").status_code == 303
        assert post(operator, lead, nonce, target="converted").status_code == 409
        converted = source.request("sr_demo_lead_01")
        assert converted.state == "submitted" and converted.history[0].to == "user_confirmed"
        failed = post(operator, "/operations/leads/demo_lead_02", nonce, target="closed")
        assert failed.status_code == 503
        assert "synthetic database unavailable" not in failed.text
        assert next(row for row in source.leads() if row.client_request_id == "demo_lead_02").state == "pending"
    assert [e.operations_detail.action for e in store.audit_events() if e.operations_detail] == [
        "lead:contacted", "lead:converted",
    ]


def test_queue_opens_linked_cases_from_all_four_playbooks():
    _store, _source, app, tokens = clients()
    with client(app, tokens[Role.OPERATOR]) as operator:
        inventory = operator.get("/cases").text
        assert all(label in inventory for label in ("紧急协助", "护照丢失", "航班变动", "助手反复失败"))
        listing = operator.get("/queue")
        assert "演示数据" in listing.text
        links = re.findall(r'class="queue-item" href="([^"]+)"', listing.text)
        detail = operator.get(links[0])
        match = re.search(r'action="(/cases/[^"]+/claim)"', detail.text)
        assert match and "认领并查看案件" in detail.text
        response = post(operator, match.group(1), csrf(detail))
        assert response.status_code == 303
        assert "当前步骤" in operator.get(response.headers["location"]).text
        assert response.headers["location"] in operator.get(links[0]).text


def test_first_administrator_is_created_once_and_never_logs_the_password():
    store = MemoryStore()
    auth = Auth(store, clock=lambda: NOW, monotonic=lambda: NOW)
    username = "demo-initial"
    assert not auth.has_admin()
    for invalid in ("short-pass", "x" * 129):
        with pytest.raises(InvalidAccount):
            auth.bootstrap_admin(username, invalid)
    with pytest.raises(InvalidAccount):
        auth.bootstrap_admin("Not Valid", PASSWORD)
    assert store.accounts() == ()
    auth.bootstrap_admin(username, PASSWORD)
    assert auth.has_admin()
    account = store.account(username)
    assert account.role is Role.ADMIN and account.enabled and account.password.matches(PASSWORD)
    assert PASSWORD not in repr(store.audit_events()) + repr(account)
    with pytest.raises(AccessDenied):
        auth.bootstrap_admin("different-admin", PASSWORD)
    assert store.account("different-admin") is None
    assert auth.login(username, PASSWORD)
    assert auth.login(username, "wrong password value") is None
