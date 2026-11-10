"""Behavior and interruption evidence, executed in the isolated locked environment."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from .checkpoint import Journal, atomic_json, exclusive
from .contracts import (FakeCalls, Halt, KnownFailure, Limits, SEED, SLOTS, TARGETS,
                        digest, fragments, read_json, score_result)
from .runner import Adapter, ROOT, manifest, run


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "run"
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def checkpoint(self):
        return read_json(self.directory / "checkpoint.json")["state"]

    def test_actual_gepa_closed_loop_no_network(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            state = run(self.directory)
        self.assertEqual(state["status"], "COMPLETED")
        selected = read_json(self.directory / "candidate.json")
        self.assertEqual(selected["fragments"], TARGETS)
        self.assertFalse(selected["runtime_eligible"])
        self.assertEqual(selected["promotion"], "UNRUN")
        self.assertEqual(selected["evidence"], "FAKE_ONLY")
        self.assertEqual(len(list(self.directory.glob("candidate-*.json"))), 4)
        operations = state["operations"]
        self.assertEqual(len(operations), 43)
        self.assertEqual(len({op["attempt_id"] for op in operations}), len(operations))
        self.assertEqual([sum(op["kind"] == k for op in operations) for k in ("task", "score", "reflection")], [20, 20, 3])
        self.assertTrue(all(op["outcome"] == "COMPLETED" for op in operations))
        for path in self.directory.glob("candidate-*.json"):
            candidate = read_json(path)
            self.assertEqual(candidate["candidate_id"], digest(candidate["fragments"]))
            self.assertEqual(set(candidate["fragment_sha256"]), set(SLOTS))
            self.assertEqual(candidate["provenance"]["gepa"], "0.1.4")
            self.assertIn("git_head", candidate["provenance"]["code"])
            self.assertIn("source_sha256", candidate["provenance"]["code"])
        count = len(operations)
        with patch.object(FakeCalls, "call", side_effect=AssertionError("completed run resent")):
            self.assertEqual(run(self.directory, resume=True)["status"], "COMPLETED")
        self.assertEqual(len(self.checkpoint()["operations"]), count)

    def test_stop_mid_iteration_resume_uses_original_receipts(self):
        calls = []
        original = FakeCalls.call

        def stop_after_third(fake, task, candidate, **kwargs):
            calls.append(kwargs["attempt_id"])
            result = original(fake, task, candidate, **kwargs)
            if len(calls) == 3:
                (self.directory / "STOP").touch()
            return result

        with patch.object(FakeCalls, "call", stop_after_third):
            state = run(self.directory)
        self.assertEqual(state["status"], "STOPPED")
        previous = list(state["operations"])
        self.assertEqual(len(previous), 5)  # Three calls, two receipts scored before STOP.
        first_ids = list(calls)

        def trace(fake, task, candidate, **kwargs):
            calls.append(kwargs["attempt_id"])
            return original(fake, task, candidate, **kwargs)

        with patch.object(FakeCalls, "call", trace):
            self.assertEqual(run(self.directory, resume=True)["status"], "STOPPED")
            state = run(self.directory, resume=True, clear_stop=True)
        self.assertEqual(state["status"], "COMPLETED")
        self.assertEqual(calls[:3], first_ids)
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(len(calls), 20)
        self.assertEqual(state["operations"][:len(previous)], previous)
        self.assertIn("STOPPED", [event["status"] for event in state["events"]])

    def test_all_three_call_bounds_persist_across_resume(self):
        for kind in ("task", "score", "reflection"):
            with self.subTest(kind=kind):
                directory = Path(self.temp.name) / kind
                limits = Limits(**{kind + "_calls": 1})
                state = run(directory, limits)
                # GEPA may finish itself at the task metric bound; other bounds stop dispatch.
                self.assertIn(state["status"], {"STOPPED", "COMPLETED"})
                ops = state["operations"]
                self.assertEqual(sum(op["kind"] == kind for op in ops), 1)
                state = run(directory, limits, resume=True)
                self.assertEqual(len(state["operations"]), len(ops))

    def test_timeout_during_call_unknown_never_resent(self):
        with patch.object(FakeCalls, "call", side_effect=lambda *a, **k: time.sleep(1)):
            state = run(self.directory, Limits(seconds=0.05))
        self.assertEqual(state["status"], "UNKNOWN")
        self.assertEqual(state["operations"][0]["outcome"], "UNKNOWN")
        with patch.object(FakeCalls, "call", side_effect=AssertionError("resent")):
            state = run(self.directory, Limits(seconds=0.05), resume=True)
        self.assertEqual(len(state["operations"]), 1)

    def test_sigterm_in_flight_records_unknown(self):
        def terminate(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
        before = signal.getsignal(signal.SIGTERM)
        with patch.object(FakeCalls, "call", terminate):
            self.assertEqual(run(self.directory)["status"], "UNKNOWN")
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)
        self.assertEqual(self.checkpoint()["operations"][0]["error"], "Halt")

    def test_stop_on_last_receipt_does_not_publish_selection(self):
        original = FakeCalls.score
        count = 0

        def stop_last(fake, *args, **kwargs):
            nonlocal count
            count += 1
            value = original(fake, *args, **kwargs)
            if count == 20:
                (self.directory / "STOP").touch()
            return value

        with patch.object(FakeCalls, "score", stop_last):
            state = run(self.directory)
        self.assertEqual(state["status"], "STOPPED")
        self.assertFalse((self.directory / "candidate.json").exists())
        with patch.object(FakeCalls, "call", side_effect=AssertionError("resent")):
            self.assertEqual(run(self.directory, resume=True, clear_stop=True)["status"], "COMPLETED")

    def test_sigkill_pending_becomes_unknown_on_resume(self):
        script = """
import sys,time
from pathlib import Path
from tooling.optimization.contracts import FakeCalls
from tooling.optimization.runner import run
def wait(*args, **kwargs):
    Path(sys.argv[2]).touch()
    time.sleep(30)
FakeCalls.call = wait
run(Path(sys.argv[1]))
"""
        marker = Path(self.temp.name) / "ready"
        child = subprocess.Popen([sys.executable, "-c", script, str(self.directory), str(marker)],
                                 cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), "child failed to persist intent")
            child.kill()
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
        self.assertEqual(self.checkpoint()["operations"][0]["outcome"], "PENDING")
        with patch.object(FakeCalls, "call", side_effect=AssertionError("resent")):
            state = run(self.directory, resume=True)
        self.assertEqual(state["status"], "UNKNOWN")
        self.assertEqual(state["operations"][0]["outcome"], "UNKNOWN")
        self.assertEqual(len(state["operations"]), 1)

    def test_definite_task_failure_retained_and_replayed(self):
        with patch.object(FakeCalls, "call", side_effect=KnownFailure("public fake failure")):
            state = run(self.directory, Limits(task_calls=2))
        self.assertEqual(state["status"], "COMPLETED")
        self.assertTrue(all(op["outcome"] == "FAIL" for op in state["operations"]))
        self.assertEqual(len(state["operations"]), 2)
        with patch.object(FakeCalls, "call", side_effect=AssertionError("failure resent")):
            run(self.directory, Limits(task_calls=2), resume=True)

    def test_reflection_timeout_and_invalid_proposal_never_retried(self):
        for value in (TimeoutError, {"identity": "overwrite"}):
            with self.subTest(value=value):
                directory = Path(self.temp.name) / str(len(list(Path(self.temp.name).iterdir())))
                args = {"side_effect": value} if value is TimeoutError else {"return_value": value}
                with patch.object(FakeCalls, "propose", **args):
                    self.assertEqual(run(directory)["status"], "UNKNOWN")
                state = read_json(directory / "checkpoint.json")["state"]
                self.assertEqual(state["status"], "UNKNOWN")
                self.assertEqual(state["operations"][-1]["kind"], "reflection")
                with patch.object(FakeCalls, "propose", side_effect=AssertionError("resent")):
                    self.assertEqual(run(directory, resume=True)["status"], "UNKNOWN")

    def test_scope_and_score_boundaries(self):
        for key in ("identity", "permissions", "save_condition", "metering", "scorer", "threshold"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                fragments({**SEED, key: "override"})
        with self.assertRaises(ValueError):
            fragments({SLOTS[0]: ""}, [SLOTS[0]])
        for status in ("UNKNOWN", "UNRUN"):
            with self.assertRaises(Halt):
                score_result({"version": "fake-score.1", "status": status, "score": 1, "feedback": "missing"})
        for score in (float("nan"), float("inf"), True, 2, -1):
            with self.assertRaises(ValueError):
                score_result({"version": "fake-score.1", "status": "PASS", "score": score, "feedback": ""})

    def test_resume_rejects_changed_manifest_corruption_and_divergence(self):
        self.directory.mkdir()
        fixed = manifest(Limits())
        journal = Journal(self.directory, fixed)
        journal.action("task", {"input": 1}, lambda aid, timeout: {"id": aid})
        changed = {**fixed, "gepa": "different"}
        with self.assertRaises(ValueError):
            Journal(self.directory, changed, resume=True)
        journal = Journal(self.directory, fixed, resume=True)
        with self.assertRaises(Halt):
            journal.action("task", {"input": 2}, lambda *args: self.fail("divergence dispatched"))
        payload = read_json(journal.path)
        payload["state"]["operations"][0]["outcome"] = "FAIL"
        atomic_json(journal.path, payload)
        with self.assertRaises(ValueError):
            Journal(self.directory, fixed, resume=True)

    def test_single_writer_and_strict_json(self):
        with exclusive(self.directory):
            with self.assertRaises(Halt):
                with exclusive(self.directory):
                    self.fail("second writer acquired lock")
        path = self.directory / "bad.json"
        path.write_text('{"version": 1, "version": 2}')
        with self.assertRaises(ValueError):
            read_json(path)

    def test_limit_configuration_rejected_before_dispatch(self):
        for limits in ({"task_calls": 0}, {"reflection_calls": True}, {"seconds": float("nan")},
                       {"seconds": 0}, {"seed": -1}):
            with self.assertRaises(ValueError):
                Limits(**limits)


if __name__ == "__main__":
    unittest.main()
