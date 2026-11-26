import asyncio
import json

from jt.eval import score
from jt.eval.dataset import EVAL_SEED, generate_eval_cases
from jt.eval.score import CaseOutcome, run_evaluation, score_cases


def test_fixed_seed_reproduces_cases_and_default_evaluation():
    cases = generate_eval_cases()
    assert cases == generate_eval_cases(EVAL_SEED)
    assert cases != generate_eval_cases(EVAL_SEED + 1)
    assert len(cases) == len({case.case_id for case in cases}) == 62

    report = asyncio.run(run_evaluation())
    assert report.seed == EVAL_SEED
    assert report.cases == len(cases)
    assert report.p0_gate == "PASS"
    assert report.p0_detected == report.p0_labeled == 27
    assert report.p0_missed == ()
    assert report.p0_recall == 1.0
    assert report.classes["safety"].emitted == report.classes["safety"].correct == 12
    assert report.classes["illness"].emitted == report.classes["illness"].correct == 15
    assert report.classes["complaint"].labeled == 2
    assert report.classes["complaint"].precision == "UNKNOWN"
    assert report.classes["complaint"].recall == "UNKNOWN"


def test_one_p0_miss_fails_even_when_other_cases_pass(monkeypatch, capsys):
    outcomes = (
        CaseOutcome("syn-hit-1", "safety", "P0", "safety", "P0"),
        CaseOutcome("syn-hit-2", "illness", "P0", "illness", "P0"),
        CaseOutcome("syn-missed", "safety", "P0", "itinerary_disruption", "P2"),
    )
    report = score_cases(outcomes)
    assert report.p0_gate == "FAIL"
    assert report.p0_detected == 2
    assert report.p0_recall == 2 / 3
    assert report.p0_missed == ("syn-missed",)

    async def run_missed_case():
        return report

    monkeypatch.setattr(score, "run_evaluation", run_missed_case)
    assert score.main() == 1
    assert json.loads(capsys.readouterr().out)["p0_missed"] == ["syn-missed"]


def test_metrics_use_separate_denominators_for_precision_and_recall():
    outcomes = (
        CaseOutcome("syn-hit-1", "safety", "P0", "safety", "P0"),
        CaseOutcome("syn-hit-2", "safety", "P0", "safety", "P0"),
        CaseOutcome("syn-hit-3", "safety", "P0", "safety", "P0"),
        CaseOutcome("syn-false-positive", None, None, "safety", "P0"),
        CaseOutcome("syn-false-negative", "safety", "P0", None, None),
        CaseOutcome("syn-false-negative-2", "safety", "P0", "illness", "P0"),
    )
    report = score_cases(outcomes)
    safety = report.classes["safety"]
    assert (safety.labeled, safety.emitted, safety.correct) == (5, 4, 3)
    assert safety.precision == 3 / 4
    assert safety.recall == 3 / 5
    # A wrong subtype still sent an urgent alert, but affects the classifier score.
    assert report.p0_missed == ("syn-false-negative",)


def test_no_labeled_p0_cannot_pass_the_gate():
    report = score_cases((CaseOutcome("syn-neutral", None, None, None, None),))
    assert report.p0_gate == "UNKNOWN"
    assert report.p0_recall == "UNKNOWN"
