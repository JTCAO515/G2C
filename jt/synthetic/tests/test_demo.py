from collections import defaultdict
import re

import pytest

from jt.playbook import CaseWorkflow, IntakeDenied
from jt.synthetic import DEMO_SEED, generate_dataset, generate_demo_dataset


def test_demo_seed_replays_exact_events_case_ids_snapshots_and_audit():
    first = generate_demo_dataset()
    replay = generate_demo_dataset(DEMO_SEED)
    assert first == replay
    assert first.workflow is not replay.workflow
    assert {case.case.case_id for case in first.cases}.isdisjoint(
        case.case.case_id for case in generate_demo_dataset(DEMO_SEED + 1).cases
    )


def test_demo_cases_cover_all_priorities_and_real_transitions():
    demo = generate_demo_dataset()
    cases = {case.case.severity: case for case in demo.cases}
    history = defaultdict(list)
    for event in demo.history:
        history[event.case_id].append(event.action)
        assert event.outcome == "applied"
    assert set(cases) == {"P0", "P1", "P2", "P3", "P4"}
    assert [cases[severity].case.playbook_id for severity in sorted(cases)] == [
        "p0_assistance", "document_loss", "flight_change", "demo_itinerary_change", "ai_failure",
    ]
    assert cases["P0"].draft and "会合" in cases["P0"].draft
    assert history[cases["P1"].case.case_id][-1] == "reject"
    assert cases["P1"].draft is None and cases["P1"].active_step.step_id == "draft_document_guidance"
    assert history[cases["P2"].case.case_id][-2:] == ["record_customer_consent", "confirm"]
    assert cases["P2"].active_step.step_id == "simulate_paid_rebooking"
    assert not cases["P2"].customer_consent_recorded
    assert cases["P4"].case.status == "closed"
    for case, signal in zip(demo.cases, demo.signals, strict=True):
        assert demo.workflow.get(case.case.case_id) == case
        assert case.case.signal_ids == (signal.signal_id,)
        assert case.case.case_id.version == 4


def test_bilingual_demo_text_uses_tokens_and_is_independent_of_the_old_seed():
    demo = generate_demo_dataset()
    text = " ".join(fragment for signal in demo.signals for fragment in signal.redacted_fragments)
    assert "Guangzhou bilingual business escort" in text and "广州展会" in text
    for placeholder in ("<NAME_1>", "<PHONE_1>", "<PASSPORT_1>", "<LOCATION_1>", "<FLIGHT_1>"):
        assert placeholder in text
    for signal in demo.signals:
        assert any(re.search(r"[\u4e00-\u9fff]", fragment) for fragment in signal.redacted_fragments)
        assert any(fragment.startswith(("Traveler:", "CJ:")) for fragment in signal.redacted_fragments)
    assert not re.search(r"\d{7,}|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    assert {signal.signal_id for signal in demo.signals}.isdisjoint(
        signal.signal_id for signal in generate_dataset().signals
    )


def test_p3_demo_template_keeps_customer_consent_gate_and_default_mapping():
    demo = generate_demo_dataset()
    signal = next(s for s in demo.signals if s.severity == "P3")
    original = CaseWorkflow()
    with pytest.raises(IntakeDenied, match="no playbook"):
        original.ingest(signal)

    current = next(case for case in demo.cases if case.case.severity == "P3")
    workflow = demo.workflow
    prepared = workflow.advance(
        current.case.case_id, expected_revision=current.revision, actor_id="demo-staff-02",
    ).execution
    drafted = workflow.advance(
        current.case.case_id, expected_revision=prepared.revision, actor_id="demo-staff-02",
    ).execution
    assert "广州商务陪同" in drafted.draft
    blocked = workflow.confirm(
        current.case.case_id, expected_revision=drafted.revision, actor_id="demo-staff-02",
    )
    assert blocked.audit.reason == "customer_consent_required"
    assert blocked.execution == drafted
