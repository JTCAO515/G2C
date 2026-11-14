"""Pinned GEPA adapter with durable task, scoring and reflection attempts."""
from dataclasses import asdict
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import signal
import subprocess

import gepa
from gepa.core.adapter import EvaluationBatch

from .checkpoint import Journal, atomic_json, exclusive, verify_artifacts
from .contracts import (FakeCalls, Halt, KnownFailure, Limits, SEED, SLOTS, TASKS, TARGETS,
                        VERSION, Reflector, RejectedResult, Scorer, TaskCaller, digest, fragments, observation,
                        read_json, score_result)

ROOT = Path(__file__).resolve().parents[2]


def source_identity():
    files = sorted(Path(__file__).parent.glob("*.py")) + [
        Path(__file__).with_name("pyproject.toml"), Path(__file__).with_name("uv.lock"),
        ROOT / "backend/strict_json/cj_strict_json/__init__.py"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return {"git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_sha256": digest(hashes), "files": hashes}


def manifest(limits):
    return {"experiment": {"issue": "#763", "source": "public-synthetic-controls.1", "mode": "fake-only"},
            "code": source_identity(), "gepa": importlib.metadata.version("gepa"),
            "python": platform.python_version(), "adapter": "g2c-fake-gepa.1",
            "models": {"task": "fake-task.1", "reflection": "fake-reflector.1", "scorer": "fake-score.1"},
            "parameters": asdict(limits), "dataset_sha256": digest(TASKS),
            "controls_sha256": digest(TARGETS), "seed_sha256": digest(SEED),
            "allowed_slots": list(SLOTS), "policy": "synthetic-text-only.1"}


class Adapter:
    def __init__(self, journal: Journal, task: TaskCaller, scorer: Scorer, reflector: Reflector):
        self.journal, self.task, self.scorer, self.reflector = journal, task, scorer, reflector

    def candidate(self, value, parent=None):
        candidate = fragments(value)
        candidate_id = digest(candidate)
        path = self.journal.directory / ("candidate-" + candidate_id + ".json")
        if candidate_id not in self.journal.state["candidates"]:
            record = {"version": VERSION, "candidate_id": candidate_id, "fragments": candidate,
                      "fragment_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in candidate.items()},
                      "parent_candidate_id": parent, "run_id": self.journal.state["run_id"],
                      "provenance": self.journal.manifest, "runtime_eligible": False,
                      "promotion": "UNRUN", "evidence": "FAKE_ONLY"}
            if path.exists() and read_json(path) != record:
                raise ValueError("unregistered candidate artifact differs from replay")
            atomic_json(path, record)
            self.journal.state["candidates"][candidate_id] = digest(record)
            self.journal.save()
        return candidate

    def evaluate(self, batch, candidate, capture_traces=False):
        candidate = self.candidate(candidate)
        outputs, scores = [], []
        for task in batch:
            request = {"task": task, "candidate": candidate, "candidate_id": digest(candidate)}
            try:
                value = self.journal.action("task", request,
                    lambda aid, timeout: self.task.call(task, candidate, attempt_id=aid, timeout=timeout),
                    lambda value, aid: observation(value, task, aid))
            except KnownFailure:
                result = {"version": "fake-score.1", "status": "FAIL", "score": 0,
                          "feedback": "Definite task failure; original attempt retained."}
            else:
                result = self.journal.action("score", {"task": task, "observation": value},
                    lambda aid, timeout: self.scorer.score(task, value, attempt_id=aid, timeout=timeout),
                    lambda value, aid: score_result(value))
            outputs.append({"task": task, "assessment": result})
            scores.append(result["score"])
        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=outputs if capture_traces else None)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        return {key: [{"Inputs": row["task"], "Generated Outputs": row["assessment"],
                       "Feedback": row["assessment"]["feedback"]} for row in eval_batch.trajectories]
                for key in components_to_update}

    def propose_new_texts(self, candidate, reflective_dataset, components_to_update):
        request = {"candidate": candidate, "feedback": reflective_dataset, "components": components_to_update}
        try:
            texts = self.journal.action("reflection", request,
                lambda aid, timeout: self.reflector.propose(candidate, reflective_dataset, components_to_update,
                                                          attempt_id=aid, timeout=timeout),
                lambda value, aid: fragments(value, components_to_update))
        except Exception as error:
            # GEPA 0.1.4 retries ordinary reflection exceptions, even with raise_on_exception=True.
            raise RejectedResult("reflection stopped: " + type(error).__name__) from None
        self.candidate({**candidate, **texts}, digest(candidate))
        return texts


def run(directory, limits=Limits(), *, resume=False, clear_stop=False):
    """Only Fake implementations are constructible here; real callers have no CLI path."""
    directory = Path(directory)
    with exclusive(directory):
        journal = Journal(directory, manifest(limits), resume=resume)
        verify_artifacts(directory, journal.state)
        if journal.unresolved():
            journal.note("UNKNOWN", "original attempt unresolved; no dispatch")
            return journal.state
        if clear_stop:
            if not resume:
                raise ValueError("clear-stop requires resume")
            (directory / "STOP").unlink(missing_ok=True)
        if journal.state["status"] == "COMPLETED":
            return journal.state
        fake = FakeCalls()
        adapter = Adapter(journal, fake, fake, fake)
        previous = {}

        def halt(signum, frame):
            raise Halt("signal stop " + str(signum))

        try:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
                previous[sig] = signal.signal(sig, halt)
            if journal.remaining() <= 0:
                raise Halt("active time budget exhausted")
            signal.setitimer(signal.ITIMER_REAL, journal.remaining())
            journal.note("RUNNING", "resume" if resume else "start")
            # Rebuild deterministic engine state from receipts; never load GEPA pickle.
            result = gepa.optimize(seed_candidate=dict(SEED), trainset=TASKS, valset=TASKS,
                adapter=adapter, seed=limits.seed, max_metric_calls=limits.task_calls,
                stop_callbacks=lambda state: len(state.program_candidates) >= 4,
                reflection_minibatch_size=2, skip_perfect_score=False, use_merge=False,
                cache_evaluation=False, run_dir=None, raise_on_exception=True,
                display_progress_bar=False, use_wandb=False, use_mlflow=False)
            if (directory / "STOP").exists() or journal.remaining() <= 0:
                raise Halt("stop before offline selection publication")
            best = fragments(result.best_candidate)
            adapter.candidate(best)
            verify_artifacts(directory, journal.state)
            selection = {
                "version": "G2C-offline-selection.1", "candidate_id": digest(best), "fragments": best,
                "candidate_file": "candidate-" + digest(best) + ".json",
                "run_id": journal.state["run_id"], "provenance": journal.manifest,
                "synthetic_score": result.val_aggregate_scores[result.best_idx],
                "runtime_eligible": False, "promotion": "UNRUN", "evidence": "FAKE_ONLY"}
            atomic_json(directory / "candidate.json", selection)
            journal.state["selection_sha256"] = digest(selection)
            journal.note("COMPLETED", "Fake GEPA selection complete")
        except RejectedResult as error:
            journal.note("UNKNOWN" if journal.unresolved() else "FAILED", str(error))
        except Halt as error:
            journal.note("UNKNOWN" if journal.unresolved() else "STOPPED", str(error))
        except BaseException as error:
            journal.note("UNKNOWN" if journal.unresolved() else "FAILED", type(error).__name__)
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            journal.save()
        return journal.state
