"""Local queue state for shared JT signals and human reviews."""

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol

from jt.common import Case, Severity, Signal, SignalSink

from .security import new_token


BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")
UUID_TEXT = re.compile(r"(?i)[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def display_text(value: str) -> str:
    return UUID_TEXT.sub("[编号已隐藏]", value)


def response_deadline(detected_at: datetime) -> datetime:
    minutes = 5 if 8 <= detected_at.astimezone(BEIJING).hour < 22 else 20
    return detected_at + timedelta(minutes=minutes)


@dataclass(frozen=True)
class Review:
    actual_severity: Severity | None
    false_positive: bool
    missed: bool
    note: str
    actor: str
    recorded_at: datetime


@dataclass(frozen=True)
class QueueItem:
    reference: str
    signal: Signal
    due_at: datetime
    case_id: str | None
    reviews: tuple[Review, ...] = ()

    @property
    def status(self) -> str:
        return "reviewed" if self.reviews else "pending"


class SignalConflict(ValueError):
    pass


class QueueStore(SignalSink, Protocol):
    def snapshot(self) -> tuple[QueueItem, ...]: ...
    def item(self, reference: str) -> QueueItem | None: ...
    def append_review(self, item: QueueItem, review: Review) -> None: ...
    def alerts(self) -> tuple[int, int]: ...


class MemoryQueue:
    def __init__(self, signals: tuple[Signal, ...] = (), *, cases: tuple[Case, ...] = ()) -> None:
        self._lock = RLock()
        self._items: dict[str, QueueItem] = {}
        self._references: dict[str, str] = {}
        self._case_ids: dict[str, str] = {}
        self._alert_revision = 0
        for case in cases:
            for signal_id in case.signal_ids:
                case_id = str(case.case_id)
                if self._case_ids.setdefault(signal_id, case_id) != case_id:
                    raise ValueError("signal has multiple case references")
        for signal in signals:
            self._accept(signal)

    def _accept(self, signal: Signal) -> None:
        current = self._references.get(signal.signal_id)
        if current is not None:
            if self._items[current].signal != signal:
                raise SignalConflict("conflicting signal")
            return
        reference = new_token()
        self._references[signal.signal_id] = reference
        self._items[reference] = QueueItem(reference, signal, response_deadline(signal.detected_at),
                                           self._case_ids.get(signal.signal_id))
        if signal.severity == "P0":
            self._alert_revision += 1

    async def publish(self, signal: Signal) -> None:
        with self._lock:
            self._accept(signal)

    def snapshot(self) -> tuple[QueueItem, ...]:
        with self._lock:
            return tuple(sorted(self._items.values(), key=lambda item: (
                item.signal.severity, item.due_at, item.signal.detected_at, item.signal.signal_id,
            )))

    def item(self, reference: str) -> QueueItem | None:
        with self._lock:
            return self._items.get(reference)

    def append_review(self, item: QueueItem, review: Review) -> None:
        with self._lock:
            current = self._items[item.reference]
            self._items[item.reference] = replace(current, reviews=(*current.reviews, review))

    def alerts(self) -> tuple[int, int]:
        with self._lock:
            count = sum(item.signal.severity == "P0" and not item.reviews for item in self._items.values())
            return count, self._alert_revision
