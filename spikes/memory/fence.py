"""Local single-writer CJ experiment, not a production MEMORY contract or auth.

The actual ReMe store is injected. This file supplies the absent application
semantics and labels their evidence separately from native component behavior.
"""

import asyncio
import json
from pathlib import Path
import sqlite3


class Conflict(Exception):
    pass


class FenceExperiment:
    def __init__(self, path, store):
        self.store = store
        self.lock = asyncio.Lock()
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA secure_delete=ON")
        has_items = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'").fetchone()
        has_sources = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_sources'").fetchone()
        if has_items and not has_sources and self.db.execute("SELECT 1 FROM items LIMIT 1").fetchone():
            self.db.close()
            raise RuntimeError("legacy experiment lacks historical sources; use a fresh synthetic workspace")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, enabled INTEGER NOT NULL,
                deleted INTEGER NOT NULL, payload TEXT, cleanup TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revoked_sources (source_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS item_sources (
                item_id TEXT NOT NULL, source_id TEXT NOT NULL,
                PRIMARY KEY (item_id, source_id));
            CREATE TABLE IF NOT EXISTS epoch (singleton INTEGER PRIMARY KEY CHECK(singleton=1), value INTEGER);
            INSERT OR IGNORE INTO epoch VALUES (1,0);
        """)

    def close(self):
        self.db.close()

    def epoch(self):
        return self.db.execute("SELECT value FROM epoch WHERE singleton=1").fetchone()[0]

    def item(self, item_id):
        return self.db.execute("SELECT revision,enabled,deleted,payload,cleanup FROM items WHERE id=?", (item_id,)).fetchone()

    def bump(self):
        self.db.execute("UPDATE epoch SET value=value+1 WHERE singleton=1")

    async def project(self, item):
        from probe import projection
        path = Path("digest") / f"{item['id']}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        await self.store.upsert([projection(item)])
        await self.store.dump()

    async def save(self, value, expected):
        async with self.lock:
            existing = self.item(value["id"])
            if self.db.execute("SELECT 1 FROM revoked_sources WHERE source_id=?", (value["source_id"],)).fetchone():
                raise Conflict("revoked source")
            if existing and (existing[0] != expected or existing[2]):
                raise Conflict("stale/deleted item")
            if not existing and expected != 0:
                raise Conflict("missing item")
            value = {**value, "revision": expected + 1}
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO items VALUES (?,?,?,0,?,'not_requested')",
                                (value["id"], value["revision"], int(value["enabled"]), json.dumps(value)))
                self.db.execute("INSERT OR IGNORE INTO item_sources VALUES (?,?)",
                                (value["id"], value["source_id"]))
                self.bump()
            if value["enabled"]:
                await self.project(value)
            else:
                await self.store.delete(f"digest/{value['id']}.md")
                await self.store.dump()
            return value

    async def delete(self, item_id, expected):
        async with self.lock:
            current = self.item(item_id)
            if not current or current[0] != expected or current[2]:
                raise Conflict("stale delete")
            sources = self.db.execute("SELECT source_id FROM item_sources WHERE item_id=?", (item_id,)).fetchall()
            if not sources:
                raise Conflict("item has no source history")
            # Durable stop-use and cleanup status precede any derived storage IO.
            with self.db:
                self.db.executemany("INSERT OR IGNORE INTO revoked_sources VALUES (?)", sources)
                self.db.execute("UPDATE items SET revision=revision+1,enabled=0,deleted=1,payload=NULL,cleanup='pending' WHERE id=?", (item_id,))
                self.bump()

    async def cleanup(self, item_id, fail=False):
        async with self.lock:
            current = self.item(item_id)
            if not current or not current[2]:
                raise Conflict("cleanup requires tombstone")
            try:
                if fail:
                    raise OSError("synthetic cleanup IO fault")
                await self.store.delete(f"digest/{item_id}.md")
                Path(f"digest/{item_id}.md").unlink(missing_ok=True)
                await self.store.optimize_index()
                await self.store.dump()
            except Exception:
                with self.db:
                    self.db.execute("UPDATE items SET cleanup='failed' WHERE id=?", (item_id,))
                raise
            with self.db:
                self.db.execute("UPDATE items SET cleanup='complete' WHERE id=?", (item_id,))

    def context(self, chunks):
        # Actual result text must come from the current authoritative revision.
        result = []
        for chunk in chunks:
            current = self.item(chunk.metadata["id"])
            if current and current[1] and not current[2] and current[0] == chunk.metadata["revision"]:
                result.append(json.loads(current[3])["text"])
        return result

    async def rebuild(self, expected_epoch):
        async with self.lock:
            if self.epoch() != expected_epoch:
                raise Conflict("stale rebuild snapshot")
            await self.store.clear()
            values = self.db.execute("SELECT payload FROM items WHERE enabled=1 AND deleted=0").fetchall()
            for (payload,) in values:
                await self.project(json.loads(payload))
            await self.store.reindex("bm25")
            await self.store.dump()

    async def probe(self, phase, original, fact):
        from probe import row, search
        results = []
        if phase == "restart":
            assert self.item("preference")[2:] == (1, None, "failed")
            assert not self.context(await search(self.store, "PreferenceAlpha"))
            results.append(row("CJ_restart_preserves_failed_cleanup_and_fence", "PASS", "not falsely complete; persisted SQLite authority"))
            await self.cleanup("preference")
            assert self.item("preference")[4] == "complete"
            assert not Path("digest/preference.md").exists()
            await self.rebuild(self.epoch())
            assert not await search(self.store, "PreferenceAlpha")
            assert not await search(self.store, "CorrectedAlpha")
            assert await search(self.store, "FactAlpha")
            results.append(row("CJ_cleanup_retry_and_authority_rebuild", "PASS", "actual ReMe delete/optimize/dump/reindex; source removed; unrelated fact preserved"))
            # Inspect controlled local snapshots, not only search/UI disappearance.
            import zstandard
            for path in [Path("authority.sqlite3"), *Path("metadata").rglob("*")]:
                if not path.is_file():
                    continue
                raw = path.read_bytes()
                if path.suffix == ".zst":
                    with path.open("rb") as stream:
                        raw = zstandard.ZstdDecompressor().stream_reader(stream).read()
                assert b"preferencealpha" not in raw.lower(), path
                assert b"correctedalpha" not in raw.lower(), path
            results.append(row("CJ_controlled_snapshot_content_removed", "PASS", "checked SQLite and decompressed ReMe graph/chunks plus BM25 snapshot; no backup/disk erasure claim"))
            return results

        await self.save(original, 0)
        await self.save(fact, 0)
        cached = await search(self.store, "PreferenceAlpha")
        assert cached
        captured_epoch = self.epoch()
        updated = await self.save({**original, "text": "CorrectedAlpha spicy meals 辣味"}, 1)
        try:
            await self.save(original, 1)
            raise AssertionError("stale save accepted")
        except Conflict:
            pass
        assert not self.context(cached)
        assert self.epoch() != captured_epoch  # Also gates publication of in-flight responses.
        assert self.context(await search(self.store, "CorrectedAlpha")) == [updated["text"]]
        results.append(row("CJ_correction_late_write_cache_and_publish_fence", "PASS", "expected revision rejects late v1; stale context/epoch rejected"))
        disabled = await self.save({**updated, "enabled": False}, 2)
        assert not self.context(await search(self.store, "CorrectedAlpha"))
        results.append(row("CJ_disable_excludes_context", "PASS", "authority checked after retrieval; derived removal secondary"))
        enabled = await self.save({**disabled, "enabled": True}, 3)
        cached = await search(self.store, "CorrectedAlpha")
        rebuild_epoch = self.epoch()
        await self.delete("preference", enabled["revision"])
        assert not self.context(cached)
        assert self.item("preference")[4] == "pending"
        try:
            await self.rebuild(rebuild_epoch)
            raise AssertionError("stale rebuild accepted")
        except Conflict:
            pass

        async def late_source():
            try:
                await self.save({**original, "id": "resurrected"}, 0)
                raise AssertionError("revoked source reimport accepted")
            except Conflict:
                return "rejected"

        # Real event-loop interleaving; barrier already committed before both tasks.
        outcome = await asyncio.gather(late_source(), self.rebuild(self.epoch()))
        assert outcome[0] == "rejected"
        assert not await search(self.store, "PreferenceAlpha")
        assert not self.context(cached)
        results.append(row("CJ_delete_late_source_and_rebuild_interleave", "PASS", "source tombstone blocks new-id replay; stale rebuild refused; fresh rebuild omits deleted item"))
        try:
            await self.cleanup("preference", fail=True)
            raise AssertionError("fault injection missing")
        except OSError:
            pass
        assert self.item("preference")[4] == "failed"
        results.append(row("CJ_cleanup_failure_remains_explicit", "PASS", "fence stays active; failure persists for separate-process retry"))
        return results
