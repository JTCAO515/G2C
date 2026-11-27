import asyncio
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from jt.eval.drills import runner
from jt.eval.drills.report import make_report
from jt.eval.drills.runner import Drill, prepare_arrivals
from jt.workbench.app import SESSION_COOKIE, create_app
from jt.workbench.auth import Auth
from jt.workbench.security import PasswordHash
from jt.workbench.store import Account, AuditAction, MemoryStore, Role


_ORIGIN = "https://127.0.0.1:8443"
_PASSWORD = "synthetic local drill test password"


def test_ten_cases_use_unique_engine_signals_and_absolute_schedule(monkeypatch):
    arr = asyncio.run(prepare_arrivals(10, 30, 1, starts_at=datetime.now(UTC)))
    assert Counter(item.signal.severity for item in arr) == {"P0": 1, "P1": 3, "P2": 2, "P3": 2, "P4": 2}
    assert len({item.signal.signal_id for item in arr}) == 10
    assert [item.offset_seconds for item in arr] == list(range(0, 1800, 180))

    drill = Drill(arr, MemoryStore())
    now = 1000.0
    waits = []

    async def sleep(seconds):
        nonlocal now
        waits.append(seconds)
        now += seconds

    monkeypatch.setattr(runner.time, "monotonic", lambda: now)
    monkeypatch.setattr(runner.asyncio, "sleep", sleep)
    asyncio.run(drill.release(15))
    assert waits == [15] + [180] * 9
    assert len(drill.queue.snapshot()) == 10


@pytest.mark.parametrize(("count", "minutes", "p0"), [(4, 30, 1), (10, 30, 0), (10, 30, 7), (10, float("inf"), 1)])
def test_invalid_pacing_cannot_omit_a_required_level(count, minutes, p0):
    with pytest.raises(ValueError, match="至少"):
        asyncio.run(prepare_arrivals(count, minutes, p0, starts_at=datetime.now(UTC)))


def _csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def _post(client, path, nonce, **fields):
    return client.post(path, data={"csrf": nonce, **fields}, headers={"Origin": _ORIGIN})


def _login(auth, user, role):
    auth.store.save_account(Account(user, role, PasswordHash.make(_PASSWORD)))
    return auth.login(user, _PASSWORD)


def _workflow(drill, operator, case_id, nonce):
    route = f"/cases/{case_id}"
    assert _post(operator, route + "/claim", nonce).status_code == 303
    current = drill.workspace.workflow.get(case_id)
    for step in current.case.steps:
        action = "advance"
        if step.mode == "ai_draft_human_confirm":
            assert _post(operator, route + "/action", nonce, action=action,
                         revision=str(current.revision)).status_code == 303
            current = drill.workspace.workflow.get(case_id)
            action = "confirm"
        if step.requires_customer_confirmation:
            assert _post(operator, route + "/action", nonce, action=action,
                         revision=str(current.revision)).status_code == 409
            drill.respond_to_synthetic_consent_requests()
            current = drill.workspace.workflow.get(case_id)
            assert current.customer_consent_recorded
        assert _post(operator, route + "/action", nonce, action=action,
                     revision=str(current.revision)).status_code == 303
        current = drill.workspace.workflow.get(case_id)
    assert current.case.status == "closed"


def test_actual_workbench_audit_supplies_five_level_drill_example():
    arrivals = asyncio.run(prepare_arrivals(5, 0, 1, starts_at=datetime.now(UTC)))
    drill = Drill(arrivals, MemoryStore())
    auth = Auth(drill.store)
    operator_token = _login(auth, "synthetic-operator", Role.OPERATOR)
    reviewer_token = _login(auth, "synthetic-reviewer", Role.REVIEWER)
    app = create_app(auth, queue=drill.queue, cases=drill.workspace)

    initial = make_report(drill)
    assert initial["status"] == "INCOMPLETE"
    assert all(row["staff_minutes"] is None for row in initial["cases"])

    with TestClient(app, base_url=_ORIGIN, follow_redirects=False) as operator, \
            TestClient(app, base_url=_ORIGIN, follow_redirects=False) as reviewer:
        operator.cookies.set(SESSION_COOKIE, operator_token)
        reviewer.cookies.set(SESSION_COOKIE, reviewer_token)
        for arrival in arrivals:
            identifier = drill.workspace.case_for_signal(arrival.signal.signal_id)
            if identifier:
                listing = operator.get("/cases")
                assert identifier not in listing.text
                assert _post(operator, f"/cases/{identifier}/claim", _csrf(listing)).status_code == 404
            asyncio.run(drill.inject(arrival))
            item = next(item for item in drill.queue.snapshot() if item.signal == arrival.signal)
            staff = operator if identifier else reviewer
            detail = staff.get("/queue", params={"signal": item.reference})
            assert detail.status_code == 200
            assert any(event.action == AuditAction.VIEW and event.signal_reference == item.reference
                       for event in drill.store.audit_events())
            time.sleep(0.06)
            if identifier:
                _workflow(drill, operator, UUID(identifier), _csrf(detail))
            else:
                assert arrival.signal.severity == "P3"
                rejected = _post(
                    reviewer, "/queue/review", _csrf(detail), signal=item.reference, actual_severity="",
                    false_positive="0", missed="0", note="合成演练漏填真实级别",
                )
                assert rejected.status_code == 400
                response = _post(
                    reviewer, "/queue/review", _csrf(detail), signal=item.reference, actual_severity="P3",
                    false_positive="0", missed="0", note="合成演练已复核",
                )
                assert response.status_code == 303

    report = make_report(drill)
    assert report["status"] == "COMPLETE"
    rows = {row["severity"]: row for row in report["cases"]}
    assert set(rows) == {"P0", "P1", "P2", "P3", "P4"}
    assert {row["playbook"] for row in rows.values() if row["playbook"]} == {
        "p0_assistance", "document_loss", "flight_change", "ai_failure",
    }
    assert rows["P3"]["playbook"] is None
    assert rows["P2"]["blockers"] == [
        "draft_itinerary_change/customer_consent_required",
        "simulate_paid_rebooking/customer_consent_required",
    ]
    assert rows["P3"]["blockers"] == ["review_denied"]
    consent_steps = [
        event.case_detail.step_id for event in drill.store.audit_events()
        if event.case_detail and event.case_detail.action == "record_customer_consent"
    ]
    assert consent_steps == ["draft_itinerary_change", "simulate_paid_rebooking"]
    assert rows["P0"]["p0_alert_to_first_processing_seconds"] >= 0.05
    assert rows["P0"]["first_viewed_at"] < rows["P0"]["first_processed_at"]
    for row in report["cases"]:
        assert row["injected_at"] <= row["first_viewed_at"] <= row["completed_at"]
        assert row["staff_minutes"] is not None
    print(json.dumps(report, ensure_ascii=False))
