"""Atomic JSON action checkpoint, single writer, deterministic replay without pickle."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import time
import uuid

from .contracts import Halt, KnownFailure, canonical, digest, read_json


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value):
    temp = path.with_suffix(".tmp")
    with temp.open("w") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_checkpoint(path):
    envelope = read_json(path)
    state = envelope["state"]
    if envelope["sha256"] != digest(state):
        raise ValueError("checkpoint checksum mismatch")
    return state


def verify_artifacts(directory, state):
    for candidate_id, expected_hash in state["candidates"].items():
        if len(candidate_id) != 64 or any(c not in "0123456789abcdef" for c in candidate_id):
            raise ValueError("invalid candidate ID in checkpoint")
        record = read_json(directory / ("candidate-" + candidate_id + ".json"))
        if digest(record) != expected_hash:
            raise ValueError("candidate artifact checksum mismatch")
    if "selection_sha256" in state:
        selection = read_json(directory / "candidate.json")
        if digest(selection) != state["selection_sha256"]:
            raise ValueError("selection artifact checksum mismatch")


@contextmanager
def exclusive(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Halt("run already has a writer") from None
        yield


class Journal:
    def __init__(self, directory, manifest, *, resume=False):
        self.directory = directory
        self.path = directory / "checkpoint.json"
        self.cursor = 0
        self.started = time.monotonic()
        self.manifest = manifest
        if resume:
            self.state = load_checkpoint(self.path)
            if self.state["manifest"] != manifest or self.state["version"] != "G2C-offline-checkpoint.1":
                raise ValueError("resume source, environment or parameters changed")
            for index, op in enumerate(self.state["operations"]):
                if (op["index"] != index or op["request_sha256"] != digest(op["request"])
                        or op["kind"] not in {"task", "score", "reflection"}
                        or op["outcome"] not in {"PENDING", "UNKNOWN", "FAIL", "COMPLETED"}):
                    raise ValueError("invalid checkpoint operation")
                if op["outcome"] == "PENDING":
                    op.update(outcome="UNKNOWN", error="InterruptedBeforeReceipt", finished_at=timestamp())
            self.elapsed = self.state["active_seconds"]
            self.save()
        else:
            if self.path.exists() or any(directory.glob("candidate*.json")):
                raise ValueError("run already exists; use resume")
            self.elapsed = 0
            self.state = {"version": "G2C-offline-checkpoint.1", "run_id": str(uuid.uuid4()),
                          "created_at": timestamp(), "manifest": manifest, "active_seconds": 0,
                          "status": "READY", "operations": [], "events": [], "candidates": {}}
            self.save()

    def note(self, status, reason):
        self.state.update(status=status, reason=reason)
        self.state["events"].append({"status": status, "reason": reason, "at": timestamp(),
                                     "attempts": len(self.state["operations"])})
        self.save()

    def remaining(self):
        return self.manifest["parameters"]["seconds"] - self.elapsed - (time.monotonic() - self.started)

    def save(self):
        self.state["active_seconds"] = self.elapsed + time.monotonic() - self.started
        atomic_json(self.path, {"sha256": digest(self.state), "state": self.state})

    def unresolved(self):
        return [op["attempt_id"] for op in self.state["operations"] if op["outcome"] in {"PENDING", "UNKNOWN"}]

    def action(self, kind, request, invoke, validate=None):
        index = self.cursor
        self.cursor += 1
        operations = self.state["operations"]
        if index < len(operations):
            op = operations[index]
            if op["kind"] != kind or op["request_sha256"] != digest(request):
                raise Halt("replay diverged; no action dispatched")
            if op["outcome"] == "FAIL":
                raise KnownFailure(op["error"])
            if op["outcome"] != "COMPLETED":
                raise Halt("original attempt unresolved; read-only reconciliation required")
            return self.validated(op, validate)
        if self.unresolved():
            raise Halt("original attempt unresolved; no further dispatch")
        if (self.directory / "STOP").exists():
            raise Halt("stop file present")
        if self.remaining() <= 0:
            raise Halt("active time budget exhausted")
        used = sum(op["kind"] == kind for op in operations)
        if used >= self.manifest["parameters"][kind + "_calls"]:
            raise Halt(kind + " call budget exhausted")
        attempt_id = self.state["run_id"] + "/" + str(index)
        op = {"index": index, "kind": kind, "request": json.loads(canonical(request)), "request_sha256": digest(request),
              "attempt_id": attempt_id, "outcome": "PENDING", "started_at": timestamp()}
        operations.append(op)
        self.save()  # Durable intent before invoking any external seam.
        try:
            result = invoke(attempt_id, self.remaining())
            canonical(result)  # A non-JSON response cannot become a committed receipt.
        except KnownFailure as error:
            op.update(outcome="FAIL", error=type(error).__name__, finished_at=timestamp())
            self.save()
            raise
        except BaseException as error:
            op.update(outcome="UNKNOWN", error=type(error).__name__, finished_at=timestamp())
            self.save()
            raise
        op.update(outcome="COMPLETED", result=json.loads(canonical(result)), result_sha256=digest(result),
                  finished_at=timestamp())
        self.save()
        return self.validated(op, validate)

    def validated(self, op, validate):
        value = json.loads(canonical(op["result"]))
        if validate is None:
            return value
        try:
            return validate(value, op["attempt_id"])
        except ValueError as error:
            op.update(outcome="FAIL", error="InvalidResponse", validation_error=str(error))
            self.save()
            raise KnownFailure("InvalidResponse") from None
