# Original MESSAGE field bounds P2 — author repair

Base ae1df694f1654859abe8993cafcd5380a6b9315c. Only this module changed.

Cause: capture and association validation reused USAGE validID for MESSAGE refs.
SDK33 MessageReceipt/OriginalUsageAssociation message_id/conversation_id/generation
are nonempty without maxLength200. The consumer incorrectly rejected legal201 and
multibyte references while canonical MESSAGE/root could accept them within budgets.

Repair: both boundaries now require these3 refs to be nonempty and keep existing
configured original/receipt/request/response byte budgets; no truncation/normalization.
Attempt/operation limits and old UsageViewModel/USAGE status schema stay unchanged.
Run is kept separately bounded according to the actual fixed RUN usage-command codec
(backend/run/cj_run/usage_binding.py, all3 command IDs <=200 scalars) and USAGE status
run_id schema, rather than treating it as an unbounded MESSAGE reference.
MessageReceipt/association run field alone has no schema max; this source's underlying
stored usage binding cannot carry a longer run command. No producer/schema change.
Exact receipt UTF8 equality, sequence, trace/JSON/no-store, body/path budgets and all
preparation/actor/session/source/selection/revision/lifecycle guards are unchanged.

Actual targeted evidence:

- reference-bounds-before.txt: exact unchanged Testing source probe,2 functions/12
  cases before repair =6 PASS controls and6 FAIL201 cases. Original FAIL preserved.
- reference-bounds-after.txt: SAME source bytes/12 cases after repair all PASS.
- reference-review-before.txt: original Review executable produced6 FAIL (exit1).
- reference-review-after.txt: SAME original Review probe source recompiled against
  repaired module produced6 PASS (exit0). Module/probe argv and original source SHA in
  reference-review-replay.json; no original Review files or assertions modified.
- reference-field-controls.txt:3 functions/15 cases PASS: six empty refs rejected;
  attempt/operation/run each200 accepted and201 rejected using4-byte Unicode scalars;
  three canonical-query accepted201-scalar/804-byte MESSAGE refs captured and wire
  validated. Each also checks capture rejects over its configured original/receipt caps.
- reference-transport-caps.txt:1 additional function PASS; legal long MESSAGE field
  remains subject to actual response-body cap and encoded GET path request cap.
- Current module compiled in Swift Testing and independent exact-source probe replay.
  No broad suite or iOS/App build repeated; prior unaffected proof reused.

reference-field-contracts.json records exact fixed schemas and RUN codec authority;
reference-repair-provenance.json records originals/hashes/scope. Any .txt.gz log is a
lossless archive preserving compiler whitespace, decompressed SHA recorded there.
All prior ae1/49 source evidence and original failures retained. Ordinary10/30 PASS
is not used to clear this P2. Main's original Review/Testing must assess this fixed
repair before HOLD is cleared.

No SDK33/shared693/AUTH/lock, producer/root/host/App or authority change. Real original
association writer remains synthetic-only; account/keychain/cache/network/SQL/provider/
fees/dispatch/App/device/full Issue9 I remain UNRUN. No push/PR/merge/issue closure.
