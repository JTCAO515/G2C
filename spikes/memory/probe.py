"""Real ReMe component probe. No model or authentication simulation.

Each worker owns a cwd/workspace in .data. Network connects are denied in workers.
Expected native limitations are evidence rows, not hidden failing assertions.
"""

import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parent


def deny_network(event, args):
    if event == "socket.connect":
        raise RuntimeError("CJ-003 worker network is disabled")


def row(name, status, detail):
    return {"check": name, "status": status, "detail": detail}


def sample(owner, kind, revision=1, enabled=True):
    suffix = "Alpha" if owner == "A" else "Beta"
    text = {
        "fact": f"Fact{suffix} speaks English 英语",
        "experience": f"Experience{suffix} visited a museum 参观过博物馆",
        "preference": f"Preference{suffix} mild meals 清淡饮食",
    }[kind]
    return {"id": kind, "owner": owner, "kind": kind, "text": text,
            "revision": revision, "enabled": enabled, "source_id": f"chat-{owner}-{kind}",
            "source_revision": 1, "recorded_at": "2026-10-21T00:00:00Z",
            "confirmed": True, "scope": "synthetic-user", "occurrence": "synthetic"}


def projection(item):
    from reme.schema import FileChunk, FileFrontMatter, FileNode
    path = f"digest/{item['id']}.md"
    node = FileNode(path=path, st_mtime=1.0, front_matter=FileFrontMatter(**item))
    chunk = FileChunk(id=f"{item['id']}-v{item['revision']}", path=path,
                      text=item["text"], start_line=1, end_line=1, metadata=item)
    return node, [chunk]


async def new_store():
    from reme.components.file_store import LocalFileStore
    store = LocalFileStore(name="cj003", embedding_store="")
    await store.start()
    assert store.embedding_store is None
    return store


async def search(store, text):
    return await store.keyword_search(text, 20, {})


async def native(owner, phase):
    store = await new_store()
    results = []
    try:
        if phase == "seed":
            for kind in ("fact", "experience", "preference"):
                item = sample(owner, kind)
                path = Path("digest") / f"{kind}.md"
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
                await store.upsert([projection(item)])
            # A store mutation alone is not a durable receipt: explicit checkpoint.
            await store.dump()
            results.append(row("seed_three_independent_items", "PASS", owner))
        elif phase == "restart":
            suffix, other = ("Alpha", "Beta") if owner == "A" else ("Beta", "Alpha")
            for kind in ("fact", "experience", "preference"):
                own = await search(store, f"{kind}{suffix}")
                foreign = await search(store, f"{kind}{other}")
                assert len(own) == 1 and not foreign, (owner, kind)
                assert own[0].metadata == sample(owner, kind)
                zh = {"fact": "英语", "experience": "参观过博物馆", "preference": "清淡饮食"}[kind]
                assert [c.id for c in await search(store, zh)] == [own[0].id]
                results.append(row(f"{owner}_{kind}_restart_and_partition", "PASS",
                                   "separate workspace; source metadata roundtrips; English/Chinese lexical lookup same item; no auth/semantic claim"))
        elif phase == "interleave":
            original = sample(owner, "preference")
            newer = {**original, "revision": 2, "text": "CorrectedAlpha spicy meals 辣味"}
            await store.upsert([projection(newer)])
            assert not await search(store, "PreferenceAlpha")
            assert await search(store, "CorrectedAlpha")
            results.append(row("native_correction_replaces_chunks", "PASS", "upsert same path removes old chunks"))
            # An old extraction has captured v1 and commits after the edit.
            await store.upsert([projection(original)])
            assert await search(store, "PreferenceAlpha")
            results.append(row("native_late_write_revision_fence", "FAIL", "v1 overwrote v2; caller must enforce versions"))
            disabled = {**original, "revision": 3, "enabled": False}
            await store.upsert([projection(disabled)])
            assert await search(store, "PreferenceAlpha")
            results.append(row("native_disable_enforced", "FAIL", "enabled metadata alone does not suppress search"))
            await store.delete("digest/preference.md")
            await store.reindex("bm25")
            assert not await search(store, "PreferenceAlpha")
            results.append(row("native_delete_then_reindex", "PASS", "current chunks do not resurrect on keyword rebuild"))
            assert Path("digest/preference.md").exists()
            results.append(row("native_delete_removes_source_file", "FAIL", "LocalFileStore.delete only deletes derived records"))
            await store.upsert([projection(original)])
            await store.reindex("bm25")
            assert await search(store, "PreferenceAlpha")
            results.append(row("native_delete_late_source_reimport_fence", "FAIL", "captured source may recreate deleted path"))
            # Safe local cleanup of this synthetic derivative only.
            await store.delete("digest/preference.md")
            await store.optimize_index()
            await store.dump()
            assert not await search(store, "PreferenceAlpha")
            results.append(row("native_delete_optimize_checkpoint", "PASS", "component cleanup hooks ran; source intentionally retained as counterexample"))
        elif phase == "after_delete_restart":
            assert not await search(store, "PreferenceAlpha")
            assert await search(store, "FactAlpha")
            results.append(row("native_deleted_projection_stays_absent_after_restart", "PASS", "unrelated fact preserved"))
        elif phase == "crash":
            await store.upsert([projection({**sample(owner, "fact"), "text": "UncheckpointedAlpha"})])
            # Intentional abrupt child exit, no dump/close. No external side effects.
            os._exit(0)
        elif phase == "after_crash":
            found = bool(await search(store, "UncheckpointedAlpha"))
            assert not found
            results.append(row("native_upsert_ack_is_crash_durable", "FAIL", "uncheckpointed upsert lost across abrupt process exit"))
        elif phase == "multi_instance":
            await store.upsert([projection(sample(owner, "preference"))])
            await store.dump()
            stale_instance = await new_store()
            try:
                await store.delete("digest/preference.md")
                await store.dump()
                # Instance-local locks do not fence another instance's old snapshot.
                await stale_instance.dump()
                observer = await new_store()
                try:
                    assert await search(observer, "PreferenceAlpha")
                    results.append(row("native_multi_instance_snapshot_fence", "FAIL",
                                       "second stale instance checkpoint restored deleted projection; one writer per workspace required"))
                finally:
                    await observer.close()
            finally:
                await stale_instance.close()
        else:
            raise ValueError(phase)
    finally:
        await store.close()
    return results


async def guarded(phase):
    """A deliberately narrow CJ fence experiment around the actual component.

    SQLite is a synthetic authority for this experiment, not a production schema.
    One process/one writer owns the component. Guards do not prove distributed safety.
    """
    from fence import FenceExperiment
    from writer import WorkspaceWriter
    store = await WorkspaceWriter.open()
    fence = None
    try:
        fence = FenceExperiment(Path("authority.sqlite3"), store)
        if phase.startswith("history_"):
            from source_history_probe import exercise
            return await exercise(fence, phase)
        return await fence.probe(phase, sample("A", "preference"), sample("A", "fact"))
    finally:
        if fence is not None:
            fence.close()
        await store.close()


def invoke(workspace, *args):
    workspace.mkdir(parents=True, exist_ok=True)
    # Do not inherit provider credentials, proxy config, or unrelated service env.
    env = {"PATH": str(Path(sys.executable).parent), "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker", *args],
                            cwd=workspace, env=env, text=True, capture_output=True, timeout=60)
    log = workspace / ("-".join(args) + ".log")
    log.write_text(result.stdout + "\nSTDERR\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{args}: exit {result.returncode}; see {log}")
    payloads = [line[len("CJ003_RESULT="):] for line in result.stdout.splitlines()
                if line.startswith("CJ003_RESULT=")]
    if args[-1] == "crash":
        return []
    if len(payloads) != 1:
        raise RuntimeError(f"missing/ambiguous result envelope; see {log}")
    return json.loads(payloads[0])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        sys.addaudithook(deny_network)
        mode, owner, phase = sys.argv[2:]
        result = asyncio.run(native(owner, phase) if mode == "native" else guarded(phase))
        print("CJ003_RESULT=" + json.dumps(result, ensure_ascii=False))
        return
    run = ROOT / ".data" / ("run-" + uuid.uuid4().hex)
    run.mkdir(parents=True, exist_ok=False)
    results = []
    for owner in ("A", "B"):
        results += invoke(run / owner, "native", owner, "seed")
        results += invoke(run / owner, "native", owner, "restart")
    results += invoke(run / "A", "native", "A", "interleave")
    results += invoke(run / "A", "native", "A", "after_delete_restart")
    results += invoke(run / "crash", "native", "A", "crash")
    results += invoke(run / "crash", "native", "A", "after_crash")
    results += invoke(run / "multi-instance", "native", "A", "multi_instance")
    for phase in ("exercise", "restart"):
        results += invoke(run / "guarded", "guarded", "A", phase)
    results += invoke(run / "B", "native", "B", "restart")
    report = {"component": "reme-ai", "version": importlib.metadata.version("reme-ai"),
              "python": platform.python_version(), "platform": platform.platform(),
              "data_path": str(run.relative_to(ROOT)), "network": "worker socket.connect denied",
              "model": "UNRUN", "auth": "UNRUN", "scope": "component plus CJ fence experiment",
              "results": results}
    import hashlib
    import shutil
    logs = ROOT / "evidence" / "workers"
    logs.mkdir(exist_ok=True)
    manifest = []
    for path in sorted(run.rglob("*")):
        if path.is_file():
            manifest.append({"path": path.relative_to(run).as_posix(), "bytes": path.stat().st_size,
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            if path.suffix == ".log":
                shutil.copyfile(path, logs / (path.parent.name + "-" + path.name))
    (ROOT / "evidence" / "data-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    target = ROOT / "evidence" / "results.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
