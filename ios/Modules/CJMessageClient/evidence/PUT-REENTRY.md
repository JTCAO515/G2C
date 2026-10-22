# Same-lease PUT storage reentry P2 repair

Exact parent 3ec7334922d308e6f3ba40fdf71f6efa8384bac8. Input is Testing's fixed
CJ-009-draft-put/IndependentPutReentryTests.swift and independent-reentry.log. No REPORT.md
was present in that evidence directory when read; original repro source/log were consumed.
Copied the two exact test bodies into the module and reran: 2 methods / 5 assertions FAIL,
retained in put-reentry-before.txt. This failure is not offset by earlier 9+3 results.

## State-layer fix

persist now distinguishes committed snapshot from a temporary mutation write-view and
tracks committed in-memory revision. A nested mutation derives from the outer intended
snapshot, so saving new editor bytes cannot drop the pending original CAS. Public reads
still use the last confirmed snapshot, never the temporary write-view. After a nested
save succeeds, an outer save cannot overwrite that newer in-memory revision.

Before returning an outbound operation or confirmation following a nested write, persist
reads back the same scope and requires the durable snapshot to match the latest committed
state with unchanged lease/revision. Unknown/failed/inconsistent readback invalidates the
original lease and throws persistenceUnknown; no operation/saved success is returned and
no automatic repair write/retry occurs. Different-account callback protection remains:
old failures do not invalidate a newer lease. Temporary write-view is not Codable or a
new storage authority; it is discarded after the synchronous transaction stack unwinds.

confirmDraftSave consumes its callback token before persist and computes editor-match
AFTER persistence/reentry settles. Thus newer same-lease editor revision stays in both
memory and storage in the reproduced after-save callback scenario, and old confirmation
returns false rather than marking it saved. No UI-only workaround, key change or data
clear is involved. Read cursor fix94bad80 and live PUT/POST prohibition are unchanged.

## Evidence

Swift6.4/macOS, synthetic synchronous storage/intercepted transport only:
- put-reentry-after.txt: exact original2 repro tests PASS, all9 PUT tests PASS, plus1
  prior cross-account callback regression PASS (12 total).
- put-reentry-uncertainty.txt:2 additional readback failure/inconsistent-store checks
  PASS, plus2 prior once-only/ambiguous-save regressions PASS (4 total).
- No unrelated full-suite, PG, live network or Keychain execution.

The inconsistent-store test deliberately writes an older outer value AFTER its nested
callback committed a new edit. This adapter behavior cannot be made into a guaranteed
nested-write transaction by this interface. It is detected and the outer operation fails
closed: no confirmation/outbound permission or saved-editor claim. The implementation
does not promise to recover bytes already overwritten by such a store; callers must keep
unsaved UI input and surface storage failure. It does not silently rewrite/merge uncertain
durable state. Real host/adapter linearization, fsync, backup rollback and independent
review remain separate requirements. Production live writes remain disabled.

All changes are within CJMessageClient; no backend/wire/credential changes. Original
failure logs preserved. Independent Review/Testing must reassess this fixed new delta;
P2 is not declared independently closed by its author.
