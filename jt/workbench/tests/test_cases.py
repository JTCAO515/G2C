"""Staff-page permissions and the actual synthetic CaseWorkflow transitions."""

import re

import psycopg
from fastapi.testclient import TestClient

from jt.synthetic import generate_dataset
from jt.workbench.app import SESSION_COOKIE, create_app
from jt.workbench.auth import Auth
from jt.workbench.cases import CaseWorkspace
from jt.workbench.security import PasswordHash, totp_at_step
from jt.workbench.store import Account, AuditResult, MemoryStore, Role


ORIGIN = "https://127.0.0.1:8443"
NOW = 1_734_000_030
PASSWORD = "synthetic local case password"


def setup_workspace(store: MemoryStore | None = None):
    store = store if store is not None else MemoryStore()
    auth = Auth(store, clock=lambda: NOW, monotonic=lambda: NOW)
    password = PasswordHash.make(PASSWORD)
    actors = {"first-operator": Role.OPERATOR, "other-operator": Role.OPERATOR,
              "demo-reviewer": Role.REVIEWER, "demo-admin": Role.ADMIN}
    tokens = {}
    for index, (username, role) in enumerate(actors.items(), 1):
        seed = bytes([index]) * 20
        store.save_account(Account(username, role, password, seed))
        tokens[username] = auth.login(username, PASSWORD, totp_at_step(seed, NOW // 30))

    signal = next(s for s in generate_dataset().signals if s.signal_type == "itinerary_disruption")
    workspace = CaseWorkspace.from_signals((signal,))
    record, _ = workspace.listing("first-operator")[0]
    return store, workspace, create_app(auth, cases=workspace), tokens, record.case.case_id, signal


def client(app, token=None):
    browser = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    if token is not None:
        browser.cookies.set(SESSION_COOKIE, token)
    return browser


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def post(browser, path, nonce, *, origin=ORIGIN, **fields):
    return browser.post(path, data={"csrf": nonce, **fields}, headers={"Origin": origin})


def test_case_scope_role_and_csrf():
    store, _workspace, app, tokens, identifier, signal = setup_workspace()
    path = f"/cases/{identifier}"
    with client(app) as anonymous, client(app, tokens["first-operator"]) as owner:
        assert anonymous.get("/cases").status_code == 401
        assert anonymous.get(path).status_code == 401
        for name in ("demo-reviewer", "demo-admin"):
            with client(app, tokens[name]) as denied:
                assert denied.get("/cases").status_code == 403
                assert post(denied, path + "/claim", csrf(denied.get("/"))).status_code == 403

        listing = owner.get("/cases")
        assert str(identifier) in listing.text and "航班变动" in listing.text
        assert signal.signal_id not in listing.text
        assert signal.source_events[0].conversation_id not in listing.text
        assert owner.get(path).status_code == 404
        nonce = csrf(listing)
        assert post(owner, path + "/claim", nonce, origin="https://outside.example.test").status_code == 403
        assert post(owner, path + "/claim", "wrong").status_code == 403
        assert post(owner, path + "/claim", nonce).status_code == 303
        assert owner.get(path).status_code == 200
        assert post(owner, path + "/action", nonce, action="record_customer_consent", revision="0").status_code == 400
        assert post(owner, path + "/action", nonce, action="advance", revision="-1").status_code == 400
        assert owner.get("/cases/invalid-case").status_code == 404
        with client(app, tokens["other-operator"]) as other:
            assert str(identifier) not in other.get("/cases").text
            assert other.get(path).status_code == 404
            other_nonce = csrf(other.get("/"))
            assert post(other, path + "/claim", other_nonce).status_code == 404
            assert post(other, path + "/action", other_nonce, action="advance", revision="0").status_code == 404

    claims = [e for e in store.audit_events() if e.case_detail and e.case_detail.action == "claim"]
    assert len(claims) == 1 and claims[0].actor == "first-operator"
    assert claims[0].case_id == str(identifier)


def test_case_workflow_draft_rejection_stale_revision_and_separate_consent():
    store, workspace, app, tokens, identifier, _signal = setup_workspace()
    path = f"/cases/{identifier}"
    with client(app, tokens["first-operator"]) as browser:
        nonce = csrf(browser.get("/cases"))
        assert post(browser, path + "/claim", nonce).status_code == 303

        def act(action, revision):
            return post(browser, path + "/action", nonce, action=action, revision=str(revision))

        assert act("advance", 0).status_code == 303
        assert act("advance", 1).status_code == 303
        detail = browser.get(path)
        assert "合成演练草稿" in detail.text and "本步骤仍需客户同意" in detail.text
        no_consent = act("confirm", 2)
        assert no_consent.status_code == 409
        assert "当前步骤仍需独立的客户同意" in no_consent.text
        stale = act("reject", 1)
        assert stale.status_code == 409 and "案件已更新" in stale.text
        assert act("reject", 2).status_code == 303
        assert "生成合成草稿" in browser.get(path).text
        assert act("advance", 3).status_code == 303
        consent = workspace.workflow.record_synthetic_customer_consent(
            identifier, expected_revision=4, step_id="draft_itinerary_change",
        )
        assert consent.audit.outcome == "applied"
        assert act("confirm", 5).status_code == 303
        assert act("advance", 6).status_code == 409
        consent = workspace.workflow.record_synthetic_customer_consent(
            identifier, expected_revision=6, step_id="simulate_paid_rebooking",
        )
        assert consent.audit.outcome == "applied"
        assert act("advance", 7).status_code == 303
        assert "案件已结束" in browser.get(path).text

    details = [(e.case_detail.action, e.result, e.case_detail.reason)
               for e in store.audit_events() if e.case_detail]
    assert details.count(("confirm", AuditResult.DENIED, "customer_consent_required")) == 1
    assert details.count(("advance", AuditResult.DENIED, "customer_consent_required")) == 1
    assert ("reject", AuditResult.DENIED, "stale_revision") in details
    assert ("reject", AuditResult.SUCCESS, None) in details
    with client(app, tokens["demo-admin"]) as admin:
        audit = admin.get("/admin/audit?action=decide")
        assert "案件 确认草稿" in audit.text and str(identifier) in audit.text
        assert "当前步骤仍需独立的客户同意" in audit.text
        assert "合成演练草稿" not in audit.text


def test_unaudited_synthetic_transition_is_not_served():
    class UnavailableAudit(MemoryStore):
        def append_audit(self, event):
            if event.case_detail and event.case_detail.action == "advance":
                raise psycopg.OperationalError("synthetic database unavailable")
            super().append_audit(event)

    _store, workspace, app, tokens, identifier, _signal = setup_workspace(UnavailableAudit())
    path = f"/cases/{identifier}"
    with client(app, tokens["first-operator"]) as browser:
        nonce = csrf(browser.get("/cases"))
        assert post(browser, path + "/claim", nonce).status_code == 303
        failure = post(browser, path + "/action", nonce, action="advance", revision="0")
        assert failure.status_code == 503
        assert "synthetic database unavailable" not in failure.text
        assert workspace.failed
        assert browser.get(path).status_code == 503
        assert browser.get("/cases").status_code == 503
