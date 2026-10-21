"""CJ-003 P2 regression: S1 -> S2 correction must retain both source fences.

Uses the real installed ReMe component via probe workers, each with networking
disabled. This is a local experiment, not an auth or production schema test.
"""

import asyncio
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

from probe import ROOT, invoke, row, sample, search
from fence import Conflict, FenceExperiment


async def reject_replay(fence, source, item_id):
    replay = {**sample("A", "preference"), "id": item_id,
              "source_id": source, "text": "HistoricalReplayAlpha old preference"}
    try:
        await fence.save(replay, 0)
    except Conflict:
        assert fence.item(item_id) is None
        return
    effective = fence.context(await search(fence.store, "HistoricalReplayAlpha"))
    raise AssertionError(f"historical source {source} accepted under new id {item_id}; effective_context={effective!r}")


async def exercise(fence, phase):
    results = []
    if phase == "history_seed":
        original = {**sample("A", "preference"), "source_id": "S1",
                    "text": "HistoryOriginalAlpha mild meals"}
        await fence.save(original, 0)
        # A distinct neighboring source id must not be revoked by a prefix match.
        await fence.save({**sample("A", "fact"), "source_id": "S1-neighbor",
                          "text": "HistoryNeighborAlpha speaks English"}, 0)
        await fence.save({**sample("A", "experience"), "source_id": "S3",
                          "text": "HistoryOtherAlpha visited a museum"}, 0)
        await fence.save({**original, "source_id": "S2",
                          "text": "HistoryCorrectedAlpha spicy meals"}, 1)
        assert fence.context(await search(fence.store, "HistoryCorrectedAlpha"))
        results.append(row("CJ_history_S1_to_S2_correction", "PASS",
                           "real component correction persisted before separate-process delete"))
        # Previous experiment workspaces cannot reconstruct overwritten provenance.
        legacy = Path("legacy.sqlite3")
        with sqlite3.connect(legacy) as db:
            db.execute("CREATE TABLE items (id TEXT PRIMARY KEY)")
            db.execute("INSERT INTO items VALUES ('existing-synthetic-item')")
        try:
            old = FenceExperiment(legacy, fence.store)
        except RuntimeError as error:
            assert "lacks historical sources" in str(error)
        else:
            old.close()
            raise AssertionError("legacy authority without source history accepted")
        with sqlite3.connect(legacy) as db:
            assert db.execute("SELECT id FROM items").fetchall() == [("existing-synthetic-item",)]
            assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='item_sources'").fetchone()
        results.append(row("CJ_history_legacy_workspace_rejected", "PASS",
                           "populated old schema rejected without inventing historical associations or overwriting data"))
    elif phase == "history_delete":
        assert fence.item("preference")[0] == 2
        cached = await search(fence.store, "HistoryCorrectedAlpha")
        assert cached
        await fence.delete("preference", 2)
        assert not fence.context(cached)
        # Exact Review repro: historical S1, new item id, valid expected=0.
        await reject_replay(fence, "S1", "new-from-S1")
        await reject_replay(fence, "S2", "new-from-S2")
        results.append(row("CJ_history_delete_rejects_S1_and_S2_new_ids", "PASS",
                           "historical and current sources blocked before cleanup, not just old item id"))
        await asyncio.gather(reject_replay(fence, "S1", "late-history-S1"),
                             fence.rebuild(fence.epoch()))
        assert not await search(fence.store, "HistoryOriginalAlpha")
        assert not await search(fence.store, "HistoryCorrectedAlpha")
        assert not await search(fence.store, "HistoricalReplayAlpha")
        results.append(row("CJ_history_replay_rebuild_interleave", "PASS",
                           "historical source replay rejected while authoritative rebuild runs"))
        # Update surviving entries as well as reading them: no overbroad write fence.
        for kind, token in (("fact", "HistoryNeighborAlpha"), ("experience", "HistoryOtherAlpha")):
            survivor = json.loads(fence.item(kind)[3])
            updated = await fence.save({**survivor, "text": survivor["text"] + " updated"}, 1)
            assert fence.context(await search(fence.store, token)) == [updated["text"]]
        results.append(row("CJ_history_neighbor_and_other_item_unaffected", "PASS",
                           "S1-neighbor and distinct S3 item remain readable and editable after target deletion"))
        fresh = {**sample("A", "preference"), "id": "fresh-preference", "source_id": "S4",
                 "text": "HistoryFreshAlpha explicit new save"}
        await fence.save(fresh, 0)
        assert fence.context(await search(fence.store, "HistoryFreshAlpha"))
        await fence.cleanup("preference")
        results.append(row("CJ_history_new_explicit_source_allowed", "PASS",
                           "new S4 save is allowed; deleted target cleanup completes independently"))
    elif phase == "history_restart":
        assert fence.item("preference")[2:] == (1, None, "complete")
        await reject_replay(fence, "S1", "restart-history-S1")
        await reject_replay(fence, "S2", "restart-history-S2")
        await fence.rebuild(fence.epoch())
        for token in ("HistoryNeighborAlpha", "HistoryOtherAlpha", "HistoryFreshAlpha"):
            assert fence.context(await search(fence.store, token))
        assert not await search(fence.store, "HistoricalReplayAlpha")
        results.append(row("CJ_history_revocations_survive_restart", "PASS",
                           "both source fences persist across cleanup/restart/rebuild; surviving entries retained"))
    else:
        raise ValueError(phase)
    return results


def main():
    run = ROOT / ".data" / ("source-history-" + uuid.uuid4().hex)
    run.mkdir(parents=True, exist_ok=False)
    results = []
    evidence = ROOT / "evidence" / "source-history"
    evidence.mkdir(exist_ok=True)
    try:
        for phase in ("history_seed", "history_delete", "history_restart"):
            results += invoke(run, "guarded", "A", phase)
    finally:
        for path in run.glob("*.log"):
            shutil.copyfile(path, evidence / path.name)
    report = {"data_path": str(run.relative_to(ROOT)), "scope": "CJ source-history regression only",
              "network": "probe workers reject socket.connect", "results": results}
    (evidence / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
