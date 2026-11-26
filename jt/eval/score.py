"""Run the synthetic recognition evaluation and fail on any missed P0 case."""

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Literal, get_args

from jt.common import Severity, Signal, SignalType
from jt.engine.decision import MOCK_MODEL_VERSION, MockDecisionModel
from jt.engine.recognition import RecognitionEngine

from .dataset import EVAL_SEED, generate_eval_cases


MIN_CLASS_SUPPORT = 3
Score = float | Literal["UNKNOWN"]


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    expected_type: SignalType | None
    expected_severity: Severity | None
    emitted_type: SignalType | None
    emitted_severity: Severity | None


@dataclass(frozen=True)
class ClassScore:
    labeled: int
    emitted: int
    correct: int
    precision: Score
    recall: Score


@dataclass(frozen=True)
class Evaluation:
    seed: int
    cases: int
    p0_detected: int
    p0_labeled: int
    p0_missed: tuple[str, ...]
    p0_recall: Score
    p0_gate: Literal["PASS", "FAIL", "UNKNOWN"]
    min_class_support: int
    classes: dict[SignalType, ClassScore]


def score_cases(outcomes: tuple[CaseOutcome, ...], seed: int = EVAL_SEED) -> Evaluation:
    p0_cases = tuple(case for case in outcomes if case.expected_severity == "P0")
    missed = tuple(case.case_id for case in p0_cases if case.emitted_severity != "P0")
    p0_detected = len(p0_cases) - len(missed)
    by_class: dict[SignalType, ClassScore] = {}
    for signal_type in get_args(SignalType):
        labeled = sum(case.expected_type == signal_type for case in outcomes)
        emitted = sum(case.emitted_type == signal_type for case in outcomes)
        correct = sum(case.expected_type == signal_type == case.emitted_type for case in outcomes)
        by_class[signal_type] = ClassScore(
            labeled=labeled,
            emitted=emitted,
            correct=correct,
            precision=correct / emitted if emitted >= MIN_CLASS_SUPPORT else "UNKNOWN",
            recall=correct / labeled if labeled >= MIN_CLASS_SUPPORT else "UNKNOWN",
        )

    return Evaluation(
        seed=seed,
        cases=len(outcomes),
        p0_detected=p0_detected,
        p0_labeled=len(p0_cases),
        p0_missed=missed,
        p0_recall=p0_detected / len(p0_cases) if p0_cases else "UNKNOWN",
        p0_gate="FAIL" if missed else "PASS" if p0_cases else "UNKNOWN",
        min_class_support=MIN_CLASS_SUPPORT,
        classes=by_class,
    )


class _RecordingSink:
    def __init__(self) -> None:
        self.signal: Signal | None = None

    async def publish(self, signal: Signal) -> None:
        self.signal = signal


async def run_evaluation(seed: int = EVAL_SEED) -> Evaluation:
    outcomes = []
    model = MockDecisionModel()
    for case in generate_eval_cases(seed):
        sink = _RecordingSink()
        engine = RecognitionEngine(sink, model=(MOCK_MODEL_VERSION, model))
        await engine.recognize(case.events)
        signal = sink.signal
        outcomes.append(CaseOutcome(
            case_id=case.case_id,
            expected_type=case.expected_type,
            expected_severity=case.expected_severity,
            emitted_type=signal.signal_type if signal else None,
            emitted_severity=signal.severity if signal else None,
        ))

    return score_cases(tuple(outcomes), seed)


def main() -> int:
    report = asyncio.run(run_evaluation())
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.p0_gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
