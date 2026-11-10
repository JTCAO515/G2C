"""The #763 Fake seam. Real B/D wiring requires a separate, authorized change."""
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Protocol

from backend.strict_json.cj_strict_json import reject_duplicates

VERSION = "G2C-offline-candidate.1"
SLOTS = ("prompt.answer_style", "tool.lookup.description", "example.clarification")
SEED = dict(zip(SLOTS, ("Be helpful.", "Look up public travel facts.", "Ask for missing details.")))
TASKS = [{"id": "fake-en", "language": "en"}, {"id": "fake-zh", "language": "zh"}]
TARGETS = dict(zip(SLOTS, (
    "Answer the travel question directly; clarify only a required missing detail.",
    "Look up public travel facts; report a failed lookup explicitly.",
    "Missing destination: ask which city. 已有目的地：直接回答。",
)))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates(ValueError, "duplicate JSON key"))


def fragments(value, keys=SLOTS):
    # External proposal / persisted configuration boundary. Text is never executable.
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("candidate may contain only the selected Fake text slots")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 16000 for v in value.values()):
        raise ValueError("invalid text fragment")
    return dict(value)


@dataclass(frozen=True)
class Limits:
    task_calls: int = 48
    score_calls: int = 48
    reflection_calls: int = 6
    seconds: float = 300
    seed: int = 7

    def __post_init__(self):
        for n in (self.task_calls, self.score_calls, self.reflection_calls):
            if type(n) is not int or not 1 <= n <= 10000:
                raise ValueError("call limits must be integers in 1..10000")
        if not math.isfinite(self.seconds) or not 0 < self.seconds <= 86400:
            raise ValueError("seconds must be in (0, 86400]")
        if type(self.seed) is not int or not 0 <= self.seed <= 2**32 - 1:
            raise ValueError("invalid seed")


class KnownFailure(Exception):
    """A definite failed attempt, with no uncertain external effect."""


class Halt(BaseException):
    """Control-flow stop; bypass GEPA's catch-Exception reflection retry."""


class RejectedResult(Halt):
    """A definite rejection of a recorded response, with no automatic retry."""


class TaskCaller(Protocol):
    def call(self, task: dict, candidate: dict[str, str], *, attempt_id: str, timeout: float) -> dict: ...


class Scorer(Protocol):
    def score(self, task: dict, observation: dict, *, attempt_id: str, timeout: float) -> dict: ...


class Reflector(Protocol):
    def propose(self, candidate: dict[str, str], feedback: dict, components: list[str],
                *, attempt_id: str, timeout: float) -> dict[str, str]: ...


class FakeCalls:
    """Deterministic public synthetic controls. No SDK, credentials, tools or network."""
    def call(self, task, candidate, *, attempt_id, timeout):
        return {"version": "fake-observation.1", "task_id": task["id"], "attempt_id": attempt_id,
                "matched_slots": sum(candidate[k] == TARGETS[k] for k in SLOTS)}

    def score(self, task, observation, *, attempt_id, timeout):
        return {"version": "fake-score.1", "status": "PASS", "score": observation["matched_slots"] / 3,
                "feedback": "Synthetic slot-match control only; no real quality inference."}

    def propose(self, candidate, feedback, components, *, attempt_id, timeout):
        return {key: TARGETS[key] for key in components}


def observation(value, task, attempt_id):
    if (not isinstance(value, dict) or set(value) != {"version", "task_id", "attempt_id", "matched_slots"}
            or value["version"] != "fake-observation.1" or value["task_id"] != task["id"]
            or value["attempt_id"] != attempt_id or type(value["matched_slots"]) is not int
            or not 0 <= value["matched_slots"] <= 3):
        raise ValueError("invalid or misbound Fake observation")
    return value


def score_result(value):
    if (not isinstance(value, dict) or set(value) != {"version", "status", "score", "feedback"}
            or value["version"] != "fake-score.1" or value["status"] not in {"PASS", "FAIL", "UNKNOWN", "UNRUN"}
            or not isinstance(value["feedback"], str)):
        raise ValueError("invalid Fake score")
    if value["status"] in {"UNKNOWN", "UNRUN"}:
        raise Halt("score evidence incomplete; no candidate selection")
    if (type(value["score"]) not in (int, float) or not math.isfinite(value["score"])
            or not 0 <= value["score"] <= 1 or (value["status"] == "FAIL" and value["score"] != 0)):
        raise ValueError("invalid score magnitude")
    return value
