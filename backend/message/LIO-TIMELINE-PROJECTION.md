# Protected Lio timeline projection

This server implementation seam is additive to `HISTORY-CONTEXT.md`. It changes no
MESSAGE, Lio timeline, Memory candidate/action, or Travel-reference wire version.

`HistoryReadContext.with_lio_timeline_projection(operation)` runs a synchronous
read projection inside the current Boundary-issued context. The original canonical
MESSAGE scope lock is acquired first and held until the guarded transaction ends.
The context's Lio page, original-message and send-status reads reuse that exact
transaction. They retain their existing chat, raw/digest, immutable reference and
association checks; no unavailable read is converted to an empty result. Each
inner read checks the same canonical principal before and after projection. The
outer repository retains its transaction/commit/return checks, followed by the
history callback's final same-principal/scope check.

The transaction is private. Neither a raw repository nor an independent witness
or live processing permit is exposed. Nested projections, another thread and
expired contexts are refused. The projection state is removed in `finally`,
including after exceptions. Source processing/Travel processing cannot be started
from this read projection. The ordinary context methods, writer/processing paths,
Memory `current` signature, direct actions and original receipts keep their
existing behavior outside this explicitly selected frame.

The timeline captures RUN snapshots once. Only a configured Memory projection
with at least one completed row selects the protected frame; classification and
composition consume those exact same snapshots. Queued/running/failed/unknown
rows alone, and hosts without Memory cards, keep their original path without a
new M acquisition. The timeline materializes its existing fields and checks its
page again before returning. Empty pages keep the old path: an absent owner namespace is not newly
required merely to display an empty history. Candidate eligibility, Memory
transaction/fence, current origin/source filtering and explicit decisions remain
C's existing authority. A pending tag or a historical original never authorizes
Remember, replay, new dispatch or publication.

This only removes repeated acquisition after the first protected acquisition.
If another transaction already owns M before the read, the original bounded wait
and unavailable/503 remain. It is not evidence that App p95 or the target-network
5/15/90 second thresholds pass. Those require separate real-service observations
under the actual source/image and C's accepted measurement procedure.
