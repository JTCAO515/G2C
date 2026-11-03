# MEMORY-HISTORY-AUGMENT@1

Added explicit methods on C RuntimeMemory and its public TrackedMemory wrapper:

```python
run = memory.with_history(original_run, all_additional_message_refs,
    decision_source_sha256s=all_additional_actual_decision_digests)
```

This does **not** recapture current Memory. It requires the original run's owner
to be that exact runtime and no currently-held Memory lease. It preserves the
original binding, principal, context, snapshot and payload objects and unions all
earlier immutable message/decision hashes with newly validated references.
Combined bounds remain 10000 messages/1000 decisions. A fresh original hold/check
must succeed before the new Fence1 run is returned. Prior capture() and
capture_history() semantics remain unchanged.

TrackedMemory delegates to the actual original runtime and stores that same new
run in its existing registry, so the scoped publisher and model use the same
snapshot and complete reference union. B must call this before acquiring its
Memory hold, based on genuine code-owned typed source context plus the public C
DecisionFence helper, never user text. Each model dispatch and final publication
still needs a fresh hold/check of this enriched run. No source or model grant is
created by these comparison hashes.

Restricted PG tests preserve exact snapshot/payload identity and earlier refs,
reject another runtime owner, and deny a real later-added accepted-Trip digest
after deletion while the initial current-message capture and Memory epoch are
otherwise current. The registry is not replaced on failed augmentation. This
does not claim B's per-model consumer is implemented.
