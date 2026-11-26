import re
from asyncio import run
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jt.common import Case, PlaybookStep
from jt.synthetic import generate_dataset
from jt.workbench.app import SESSION_COOKIE, create_app
from jt.workbench.auth import SESSION_IDLE, Auth
from jt.workbench.queue import MemoryQueue, SignalConflict, response_deadline
from jt.workbench.security import PasswordHash, totp_at_step
from jt.workbench.store import Account, AuditAction, AuditResult, MemoryStore, Role


ORIGIN = "https://127.0.0.1:8443"
CASE_ID = UUID("d97c4c0c-49e4-4687-a931-9170728527d6")
PRIVATE_UUID = "108a9a2c-3c85-4c78-84d3-9d1bea559bfd"


def instant(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 2, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(("discovered", "deadline"), [
    (instant(23, 59), datetime(2026, 1, 3, 0, 19, tzinfo=UTC)),
    (instant(0), instant(0, 5)),
    (instant(13, 59), instant(14, 4)),
    (instant(14), instant(14, 20)),
])
def test_response_deadline_uses_beijing_boundaries(discovered, deadline):
    assert response_deadline(discovered) == deadline


def test_queue_is_priority_then_due_discovery_and_private_id():
    p0, p1 = (next(signal for signal in generate_dataset().signals if signal.severity == level)
              for level in ("P0", "P1"))
    before_day = datetime(2026, 1, 1, 23, 45, tzinfo=UTC)
    signals = (
        p1.model_copy(update={"signal_id": "earlier-p1", "detected_at": before_day}),
        p0.model_copy(update={"signal_id": "p0-zz", "detected_at": instant(0)}),
        p0.model_copy(update={"signal_id": "p0-aa", "detected_at": instant(0)}),
        p0.model_copy(update={"signal_id": "p0-earlier-discovery", "detected_at": before_day}),
        p0.model_copy(update={"signal_id": "p0-later-deadline", "detected_at": before_day.replace(minute=56)}),
    )
    queue = MemoryQueue(signals)
    assert [item.signal.signal_id for item in queue.snapshot()] == [
        "p0-earlier-discovery", "p0-aa", "p0-zz", "p0-later-deadline", "earlier-p1",
    ]


def test_signal_sink_deduplicates_without_realert_and_rejects_conflict():
    queue = MemoryQueue()
    signal = next(sample for sample in generate_dataset().signals if sample.severity == "P0")
    run(queue.publish(signal))
    first = queue.snapshot()[0]
    run(queue.publish(signal.model_copy()))
    assert queue.snapshot() == (first,)
    assert queue.alerts() == (1, 1)
    with pytest.raises(SignalConflict, match="conflicting signal"):
        run(queue.publish(signal.model_copy(update={"redacted_fragments": ("changed",)})))
    assert queue.snapshot() == (first,)
    assert queue.alerts() == (1, 1)


@dataclass
class Clock:
    now: int = 1_734_000_030

    def __call__(self) -> int:
        return self.now


@dataclass
class LocalWorkbench:
    app: FastAPI
    queue: MemoryQueue
    store: MemoryStore
    auth: Auth
    clock: Clock
    p0: str

    def browser(self, role: Role | None = None) -> TestClient:
        browser = TestClient(self.app, base_url=ORIGIN, follow_redirects=False)
        if role is not None:
            seed = self.store.account(role.value).totp_seed
            code = totp_at_step(seed, self.clock.now // 30)
            token = self.auth.login(role.value, "synthetic workbench credential", code)
            assert token is not None
            browser.cookies.set(SESSION_COOKIE, token)
        return browser


@pytest.fixture
def local():
    dataset = generate_dataset()
    p0 = next(signal for signal in dataset.signals if signal.severity == "P0")
    record = p0.model_copy(update={"redacted_fragments": (*p0.redacted_fragments, f"<unsafe> {PRIVATE_UUID}")})
    signals = tuple(record if signal.signal_id == p0.signal_id else signal for signal in dataset.signals)
    case = Case(schema_version="jt-case.v1", case_id=CASE_ID, signal_ids=(record.signal_id,), severity="P0",
                created_at=record.detected_at, status="open", playbook_id="synthetic-playbook", playbook_version="v1",
                steps=(PlaybookStep(step_id="check", mode="human_only", requires_customer_confirmation=False),))
    queue = MemoryQueue(signals, cases=(case,))
    clock, store = Clock(), MemoryStore()
    auth = Auth(store, clock=clock, monotonic=clock)
    password = PasswordHash.make("synthetic workbench credential")
    for index, role in enumerate(Role):
        store.save_account(Account(role.value, role, password, bytes([index + 1]) * 20))
    app = create_app(auth, port=8443, queue=queue)
    reference = next(item.reference for item in queue.snapshot() if item.signal.signal_id == record.signal_id)
    return LocalWorkbench(app, queue, store, auth, clock, reference)


def csrf(response) -> str:
    return re.search(r'name="csrf" value="([A-Za-z0-9_-]{43})"', response.text).group(1)


def submit(browser: TestClient, reference: str, token: str, *, origin: str = ORIGIN, **values):
    return browser.post("/queue/review", headers={"Origin": origin}, data={
        "signal": reference, "csrf": token, "actual_severity": "P1", "false_positive": "0", "missed": "1",
        "note": "复核备注", **values,
    })


def test_queue_detail_and_filters_hide_source_ids(local):
    with local.browser(Role.REVIEWER) as browser:
        item = local.queue.item(local.p0)
        signal = item.signal
        page = browser.get("/queue", params={"signal": local.p0, "type": signal.signal_type, "status": "pending"})
        assert page.status_code == 200
        assert 'lang="zh-CN"' in page.text and "北京时间" in page.text
        assert signal.rules_version in page.text and signal.redaction_version in page.text
        assert "无模型输出" in page.text
        model_item = next(row for row in local.queue.snapshot() if row.signal.model_outputs)
        model_page = browser.get("/queue", params={"signal": model_item.reference})
        for observation in model_item.signal.model_outputs:
            assert observation.model_version in model_page.text
            assert f"{observation.output.confidence:.1%}" in model_page.text
        assert str(CASE_ID) in page.text
        assert "&lt;unsafe&gt; [编号已隐藏]" in page.text
        private_values = (PRIVATE_UUID, signal.signal_id, signal.source_events[0].event_id,
                          signal.source_events[0].conversation_id, "synthetic-playbook")
        assert all(value not in page.text for value in private_values)
        assert page.text.count('class="queue-item"') == sum(
            queued.signal.signal_type == signal.signal_type for queued in local.queue.snapshot())
        assert "当前筛选下没有信号" in browser.get("/queue?status=reviewed").text
        assert "未建单" in browser.get("/queue").text
        for bad in ("?type=unknown", "?status=unknown"):
            assert browser.get(f"/queue{bad}").status_code == 400
        assert browser.get("/queue", params={"signal": signal.signal_id}).status_code == 404
        assert "script-src 'sha256-" in page.headers["content-security-policy"]
        assert "connect-src 'self'" in page.headers["content-security-policy"]
        assert "<script src=" not in page.text and "https://" not in page.text
    assert any(event.action == AuditAction.VIEW and event.case_id == str(CASE_ID)
               and event.signal_reference == local.p0 for event in local.store.audit_events())


def test_reviewer_annotation_export_and_audit_are_narrow(local):
    with local.browser(Role.REVIEWER) as browser:
        reference = local.p0
        token = csrf(browser.get("/queue", params={"signal": reference}))
        assert submit(browser, reference, "tampered").status_code == 403
        assert submit(browser, reference, token, origin="https://outside.example.test").status_code == 403
        assert submit(browser, reference, token, false_positive="1").status_code == 400
        assert "当前筛选下没有信号" in browser.get("/queue?status=reviewed").text
        saved = submit(browser, reference, token, note=f"备注 {PRIVATE_UUID} <unsafe>")
        assert saved.status_code == 303
        history = browser.get(saved.headers["location"])
        assert "标注历史" in history.text and "漏报" in history.text
        assert "备注 [编号已隐藏] &lt;unsafe&gt;" in history.text
        assert browser.get("/queue?status=reviewed").text.count('class="queue-item"') == 1
        export = browser.get("/queue/export")
        assert export.status_code == 200 and "attachment;" in export.headers["content-disposition"]
        assert export.json()["schema_version"] == "jt-workbench-review-export.v1"
        [sample] = export.json()["samples"]
        assert sample["case_id"] == str(CASE_ID) and sample["detected_severity"] == "P0"
        assert sample["review"] == {"actual_severity": "P1", "false_positive": False, "missed": True,
                                    "note": "备注 [编号已隐藏] <unsafe>",
                                    "recorded_at": datetime.fromtimestamp(local.clock.now, UTC).isoformat()}
        assert not any(value in export.text for value in (PRIVATE_UUID, reference, "signal_id", "source_events", "actor"))
        another = next(item for item in local.queue.snapshot() if item.reference != reference)
        assert submit(browser, another.reference, token, actual_severity="", false_positive="1", missed="0").status_code == 303
        assert len(browser.get("/queue/export").json()["samples"]) == 2
    events = local.store.audit_events()
    annotations = [event for event in events if event.action == AuditAction.ANNOTATE]
    assert [event.result for event in annotations] == [AuditResult.DENIED, AuditResult.SUCCESS, AuditResult.SUCCESS]
    assert annotations[0].signal_reference == local.p0 and annotations[-1].case_id is None
    assert PRIVATE_UUID not in repr(events) and local.p0 not in repr(events)
    with local.browser(Role.ADMIN) as admin:
        audit = admin.get("/admin/audit")
        assert str(CASE_ID) in audit.text and "导出评测" in audit.text and "标注" in audit.text
        assert local.p0 not in audit.text and "复核备注" not in audit.text


def test_queue_roles_and_alert_poll_does_not_keep_session_alive(local):
    with local.browser() as anonymous, local.browser(Role.ADMIN) as admin, local.browser(Role.OPERATOR) as operator:
        for path in ("/queue", "/queue/alerts", "/queue/export"):
            assert anonymous.get(path).status_code == 401
            assert admin.get(path).status_code == 403
        assert submit(anonymous, local.p0, "csrf").status_code == 401
        assert submit(admin, local.p0, csrf(admin.get("/"))).status_code == 403
        detail = operator.get("/queue", params={"signal": local.p0})
        assert detail.status_code == 200 and "保存标注" not in detail.text
        assert operator.get("/queue/export").status_code == 403
        assert submit(operator, local.p0, csrf(detail)).status_code == 403
        pending, revision = local.queue.alerts()
        count = len(local.store.audit_events())
        local.clock.now += SESSION_IDLE - 1
        assert operator.get("/queue/alerts").json() == {"pending": pending, "revision": revision}
        local.clock.now += 1
        assert operator.get("/queue/alerts").status_code == 401
        assert len(local.store.audit_events()) == count
        assert local.queue.item(local.p0).reviews == ()
