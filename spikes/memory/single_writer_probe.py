"""Actual multiprocess exclusive writer/physical-cleanup delta, no network.

Each process uses the real installed ReMe store through WorkspaceWriter.
Persistent control logs live outside the workspace whose bytes are compared.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

from probe import ROOT, deny_network, projection, row, sample, search
from fence import FenceExperiment
from writer import WorkspaceWriter, WriterBusy, WriterClosed


PREFIX = "CJ003_WRITER="
TOKEN = "PreferenceAlpha"


def emit(event, **details):
    print(PREFIX + json.dumps({"event": event, "pid": os.getpid(), **details}), flush=True)


def physical_snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def assert_cleaned():
    import zstandard
    assert not Path("digest/preference.md").exists()
    for path in [Path("authority.sqlite3"), *Path("metadata").rglob("*")]:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if path.suffix == ".zst":
            with path.open("rb") as stream:
                raw = zstandard.ZstdDecompressor().stream_reader(stream).read()
        assert TOKEN.lower().encode() not in raw.lower(), path


async def worker(role):
    try:
        writer = await WorkspaceWriter.open()
    except WriterBusy:
        emit("busy")
        return
    fence = None
    original = sample("A", "preference")
    captured = projection(original)
    try:
        if role == "seed":
            try:
                duplicate = await WorkspaceWriter.open()
            except WriterBusy:
                pass
            else:
                await duplicate.close()
                raise AssertionError("same PID opened a second writer instance")
        if role != "empty":
            fence = FenceExperiment(Path("authority.sqlite3"), writer)
        if role == "seed":
            await fence.save(original, 0)
            await fence.save(sample("A", "fact"), 0)
            assert await search(writer, TOKEN)
        if role == "observer":
            assert fence.item("preference")[2:] == (1, None, "complete")
            assert not await search(writer, TOKEN)
            assert await search(writer, "FactAlpha")
            assert_cleaned()
        emit("opened", role=role, lock_inode=Path(".cj003-writer.lock").stat().st_ino,
             same_pid_duplicate_rejected=(role == "seed"))
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            command = json.loads(line)["command"]
            if command == "cleanup":
                await fence.delete("preference", 1)
                await fence.cleanup("preference")
                assert fence.item("preference")[4] == "complete"
                assert_cleaned()
                emit("cleanup_complete")
            elif command == "release":
                # Close ReMe under ownership; keep the old Python objects alive.
                await writer.close()
                emit("released")
            elif command == "stale":
                attempts = []
                calls = [
                    ("upsert", lambda: writer.upsert([captured])),
                    ("dump", writer.dump),
                    ("reindex", lambda: writer.reindex("bm25")),
                    ("delete", lambda: writer.delete("digest/fact.md")),
                    ("clear", writer.clear),
                    ("optimize", writer.optimize_index),
                    ("project_source", lambda: fence.project(original)),
                    ("save_authority", lambda: fence.save({**original, "id": "late"}, 0)),
                    ("delete_authority", lambda: fence.delete("fact", 1)),
                    ("cleanup", lambda: fence.cleanup("preference")),
                    ("rebuild", lambda: fence.rebuild(0)),
                ]
                for name, call in calls:
                    try:
                        await call()
                    except WriterClosed:
                        attempts.append(name)
                    else:
                        raise AssertionError(f"released writer allowed {name}")
                await writer.close()  # A stale late close must be a no-op too.
                emit("stale_rejected", attempts=attempts)
            elif command == "observe":
                assert fence.item("preference")[2:] == (1, None, "complete")
                assert not await search(writer, TOKEN)
                assert await search(writer, "FactAlpha")
                assert_cleaned()
                emit("clean_observed")
            elif command == "exit":
                break
            else:
                raise ValueError(command)
    finally:
        if fence is not None:
            fence.close()
        await writer.close()


class Process:
    def __init__(self, workspace, role, logs):
        workspace.mkdir(parents=True, exist_ok=True)
        env = {"PATH": str(Path(sys.executable).parent), "PYTHONNOUSERSITE": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "worker", role],
                                     cwd=workspace, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        self.log = (logs / f"{self.proc.pid}-{role}.log").open("wb")
        self.buffer = b""

    def event(self, expected):
        deadline = time.monotonic() + 20
        with selectors.DefaultSelector() as selector:
            selector.register(self.proc.stdout, selectors.EVENT_READ)
            while True:
                while b"\n" in self.buffer:
                    line, self.buffer = self.buffer.split(b"\n", 1)
                    if line.startswith(PREFIX.encode()):
                        event = json.loads(line[len(PREFIX):])
                        assert event["event"] == expected, event
                        return event
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError(f"worker {self.proc.pid} waiting for {expected}")
                data = os.read(self.proc.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError(f"worker {self.proc.pid} exited {self.proc.poll()} before {expected}; see logs")
                self.log.write(data)
                self.log.flush()
                self.buffer += data

    def command(self, command):
        self.proc.stdin.write((json.dumps({"command": command}) + "\n").encode())
        self.proc.stdin.flush()

    def finish(self, code=0):
        assert self.proc.wait(timeout=20) == code
        # Drain final close/checkpoint logs after process exit.
        remaining = self.proc.stdout.read()
        if remaining:
            self.log.write(remaining)
            self.log.flush()

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self.log.close()
        self.proc.stdin.close()
        self.proc.stdout.close()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        sys.addaudithook(deny_network)
        asyncio.run(worker(sys.argv[2]))
        return
    run = ROOT / ".data" / ("single-writer-" + uuid.uuid4().hex)
    workspace, other = run / "workspace", run / "other-workspace"
    evidence = ROOT / "evidence" / "single-writer"
    logs = evidence / "workers"
    logs.mkdir(parents=True, exist_ok=True)
    processes = []
    results = []
    events = []

    def start(path, role):
        process = Process(path, role, logs)
        processes.append(process)
        return process

    try:
        old = start(workspace, "seed")
        opened = old.event("opened")
        events.append(opened)
        assert opened["same_pid_duplicate_rejected"]
        results.append(row("CJ_writer_same_process_second_instance_rejected", "PASS",
                           "same PID cannot open a second managed ReMe instance for its workspace"))
        before = physical_snapshot(workspace)
        competitor = start(workspace, "empty")
        busy = competitor.event("busy")
        events.append(busy)
        competitor.finish()
        assert physical_snapshot(workspace) == before
        assert busy["pid"] != opened["pid"]
        results.append(row("CJ_writer_second_process_rejected", "PASS",
                           "actual second PID refused before ReMe startup/authority IO; physical bytes unchanged"))

        independent = start(other, "empty")
        events.append(independent.event("opened"))
        independent.command("exit")
        independent.finish()
        results.append(row("CJ_writer_other_workspace_independent", "PASS", "another workspace can own its writer concurrently"))

        old.command("cleanup")
        events.append(old.event("cleanup_complete"))
        before = physical_snapshot(workspace)
        post_cleanup = start(workspace, "empty")
        events.append(post_cleanup.event("busy"))
        post_cleanup.finish()
        assert physical_snapshot(workspace) == before
        results.append(row("CJ_writer_cleanup_complete_keeps_exclusivity", "PASS",
                           "second PID still refused after cleanup complete and before owner close; cleaned bytes unchanged"))
        old.command("release")
        events.append(old.event("released"))
        current = start(workspace, "observer")
        restarted = current.event("opened")
        events.append(restarted)
        assert restarted["lock_inode"] == opened["lock_inode"]
        results.append(row("CJ_writer_graceful_restart_releases_lock", "PASS",
                           "new process opens same persistent lock inode and sees cleanup complete with deleted bytes absent"))

        before = physical_snapshot(workspace)
        old.command("stale")
        events.append(old.event("stale_rejected"))
        assert physical_snapshot(workspace) == before
        current.command("observe")
        events.append(current.event("clean_observed"))
        results.append(row("CJ_writer_stale_instance_cannot_restore_physical_storage", "PASS",
                           "old live PID rejected at 11 mutation entrypoints and late close; source/SQLite/ReMe snapshot hashes unchanged"))
        current.command("exit")
        current.finish()

        crash = start(workspace, "observer")
        events.append(crash.event("opened"))
        crash.proc.kill()  # Only this probe-owned child; no finally/unlock runs.
        crash.finish(-9)
        after_crash = start(workspace, "observer")
        reopened = after_crash.event("opened")
        events.append(reopened)
        assert reopened["lock_inode"] == opened["lock_inode"]
        results.append(row("CJ_writer_abrupt_exit_releases_lock", "PASS",
                           "holder SIGKILL exit -9 without finally; new PID owns same inode and sees cleaned state"))
        before = physical_snapshot(workspace)
        old.command("stale")
        events.append(old.event("stale_rejected"))
        assert physical_snapshot(workspace) == before
        after_crash.command("observe")
        events.append(after_crash.event("clean_observed"))
        results.append(row("CJ_writer_stale_instance_stays_invalid_after_crash_recovery", "PASS",
                           "original released writer remains rejected across later ownership generations; cleaned bytes stay absent"))
        after_crash.command("exit")
        after_crash.finish()
        old.command("exit")
        old.finish()
        report = {"delta_base": "56b85ebd93f9a4d48a057757a5305704a25fec11",
                  "data_path": str(run.relative_to(ROOT)), "network": "workers reject socket.connect",
                  "scope": "managed local single-writer entrypoints only; native unwrapped FAILs retained",
                  "results": results, "events": events, "final_workspace_sha256": physical_snapshot(workspace)}
        (evidence / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        for process in processes:
            process.stop()


if __name__ == "__main__":
    main()
