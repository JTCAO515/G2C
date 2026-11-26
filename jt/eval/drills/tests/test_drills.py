import asyncio
import json

from jt.eval.drills import __main__ as cli
from jt.eval.drills.runner import run_drills


def test_batch_exercises_each_level_and_checks_real_playbooks():
    results = asyncio.run(run_drills())
    assert tuple(result.severity for result in results) == ("P0", "P1", "P2", "P3", "P4")
    by_level = {result.severity: result for result in results}
    assert [(by_level[level].status, by_level[level].playbook_id) for level in ("P0", "P1", "P2", "P4")] == [
        ("PASS", "p0_assistance"),
        ("PASS", "document_loss"),
        ("PASS", "flight_change"),
        ("PASS", "ai_failure"),
    ]
    assert [action.action for action in by_level["P0"].actions].count("reject") == 1

    p2 = by_level["P2"]
    consent_steps = ("draft_itinerary_change", "simulate_paid_rebooking")
    assert tuple(action.step_id for action in p2.actions if action.reason == "customer_consent_required") == consent_steps
    assert tuple(action.step_id for action in p2.actions if action.action == "record_customer_consent") == consent_steps


def test_cli_reports_every_level_and_fails_the_batch_on_any_case_failure(capsys):
    status = cli.main()
    report = json.loads(capsys.readouterr().out)
    assert [case["severity"] for case in report["cases"]] == ["P0", "P1", "P2", "P3", "P4"]
    failures = [case for case in report["cases"] if case["status"] == "FAIL"]
    assert status == (1 if failures else 0)
    assert report["status"] == ("FAIL" if failures else "PASS")
    assert all(case["error"] for case in failures)


def test_cli_refuses_to_pass_without_all_five_levels(monkeypatch, capsys):
    async def omit_p3():
        return tuple(result for result in await run_drills() if result.severity != "P3")

    monkeypatch.setattr(cli, "run_drills", omit_p3)
    assert cli.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["missing_levels"] == ["P3"]
    assert all(case["status"] == "PASS" for case in report["cases"])
