# CJ014 author validation — 2026-10-23

Original `da88ed8` was subsequently held for Review's DST fold source mismatch.
Its PASS/FAIL logs remain unchanged. See `source-fold/REPORT.md` for the targeted
repair and new author results; independent re-review is still required.

Base: `8ea1b35756726f60727f10deaf157c40b8df1072`, repository
`JTCAO515/G2C`, branch `cj/014-draft`. New task root was absent; independently
cloned and branched at exactly that base. Issue 19 was read through the official
GitHub connector, state OPEN. Earlier planning wording does not supersede this
round's explicit local candidate implementation authorization.

Write scope: only `backend/draft/**` and `contracts/draft/**`. No dependency
installation or global changes; no PostgreSQL, network listener, secrets,
Keychain, provider, model, account, budget, deployment or remote write action.

## Results

- PASS: 23 synthetic local tests on existing `/opt/homebrew/bin/python3.14`
  (3.14.7); exact command in `backend/draft/README.md`. Log `final-run.txt`.
- PASS: all 12 actually imported canonical upstream Python source files match
  the fixed base byte-for-byte; hashes and candidate source/test hashes are in
  `input-manifest.json`. No moving owner tree was consumed.
- PASS: staged diff whitespace check and changed-path scope inspection.
- Original FAIL preserved: `first-run.txt` used shell `python3`, which resolves
  to Xcode Python 3.9.6. Upstream TRIP's `int | None` failed during import; no
  behavioral test executed in that attempt. Switched to already installed 3.14;
  did not change upstream compatibility code or install another interpreter.
  Initial 21-test successful log is `python314-run.txt`; after two additional
  revision/removal checks and the fixed false publication field, final 23 PASS.

Covered: complete NEEDS history; exact original source bytes differing at the
same revision; revision increase; MEMORY epoch, raw content, removal, subject
and context changes; disabled/inference/previous-trip records refused; missing
dependencies; canonical Proposal validation, duplicate IDs, extra date fields;
immutable original bytes/content hash; original item/evidence/source association;
duplicate/conflicting/cross-item refs; unresolved/no-source UNKNOWN; no unsupported
verified claims; existing FEAS arrival/departure CONFLICT and its original source
bytes retained; explicit cancellation and expiry discard; closed production factory.

## Limits and remaining scope

This is a pure **historical** structured-result checker and source/version
composition candidate. There is no accepted model/tool dispatch claim, trusted
live cancellation ledger, complete daily itinerary, truth verification, translation
verification, durable candidate, current-context authority or formal Trip save.
`Review.content_sha256` is not TRIP's scoped candidate hash. No extra provider,
solver, parallel domain DTO or candidate repository was created.

Canonical NEEDS ProtectedReader and MEMORY consume_current were inspected but
are not composed or weakened. Their guards/held-lock lifetime and same-principal
binding cannot be replaced with detached objects or version equality. The
minimal source/atomic-publication seams are listed in `contracts/draft/README.md`.
Production generation/factory/publication remain closed pending the owners'
accepted seams. Accept/reject remain exclusively TRIP's responsibility.

Independent Review/Testing, CI, real DB/current-reader integration, real model,
PLACE/FACT calls, costs, App/device, persistence/reopen, deployment and production
acceptance: **UNRUN**. Prior upstream FAIL evidence remains untouched. This does
not close Issue 19 or its I dependencies and is submitted only for Main's normal
fixed-head collection and independent gates.
