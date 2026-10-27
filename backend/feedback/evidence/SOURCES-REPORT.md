# CJ023 full local domain candidate: submit → receipt → source location

2026-10-22; author verification only. Base
`8f2ff45519d1d09f178f1fa766b6829d81bda77a`, branch `cj/023-feedback`, clone
`<local>/Documents/Codex/2026-10-21/cj-023-feedback`.
`fc55f6cb69cbd8d5cd2ead53165698c434c7d066` is the standalone core product commit.
Two unchanged dependency imports are separate: MESSAGE `7182df3` (owner `bf79a948`),
RUN `cf6aed7` (owner `eadda152`). Current FEEDBACK delta starts after `cf6aed7` and
only edits `backend/feedback/**` + `contracts/feedback/**`. Complete author product
is core + current FEEDBACK delta, with separately approved dependencies present.
Source manifest: `sources-sha256.json`; full provenance: contracts/feedback/DEPENDENCIES.json.

## Verified outcome

- **47 tests PASS** in a new private PostgreSQL 16.15 cluster: 6 input/domain,
  22 receipt/persistence/AUTH boundary and 19 canonical MESSAGE/RUN composition.
  Cached Python 3.14.7 and psycopg 3.3.4; no installation/network/provider.
- Public `HistoryReadContext.query_message` and `read_diagnostic` use the actual
  pinned code and actual local PostgreSQL repositories. AUTH checker is canonical,
  but verifier/member facts are synthetic fixtures, not actual user accounts.
- Positive message-only and message+matching-run feedback persists minimal original
  association and read-time status/highwater. Raw chat/RUN/effect sentinels are
  absent from both feedback row and receipt. Versions/usage/tools/failure-stage
  fields are absent rather than invented; their semantic value is UNKNOWN.
- Foreign/missing IDs have the same rejection. Run substitution, wrong MESSAGE
  scope, wrong RUN scope, corrupt message hash, inactive chat/run scope, expired
  RUN and accepted-message-with-no-RUN all fail without a feedback row.
- MESSAGE association changes during RUN read or before feedback commit reject and
  roll back. RUN observation changes before commit also reject. Identity changes,
  source read failure, read cancellation and unknown read commit never become
  null/success. Source change after commit during final projection withholds the
  response; original query/replay preserves the exact historical receipt.
- General feedback checks remain PASS: A/B/environment isolation, 4-way duplicate
  concurrency, conflicting-byte race, original bytes, lost commit ACK, cancellation
  before/after commit, close interrupt, fresh connection ownership, post-commit
  revocation/identity changes, context lifetime, deferred and swallowed failures.
- **Actual PostgreSQL restart PASS** for both text-only and source-linked original
  receipts. Stored source observation is reread unchanged; no source payload is
  regenerated and no new action is created.
- Private server/command logs contain none of the submitted/exception sentinels.
  A deliberately interrupted cleanup emits only a fixed safe warning.
- Final cluster stopped; all four task-private clusters are preserved without
  postmaster.pid. `sources-final-inventory.json` records the exact private path,
  Unix socket, explicit new roles/port and empty passfile. No ambient PG/LIBPQ
  configuration, TCP listener, old DB or other owner instance was used.

The first composition run had 44 PASS. The final run adds three focused source
unknown-commit/identity/changed-observation cases and linked-receipt restart to
resolve the remaining integration concerns; it does not rerun unrelated domains'
full suites. Logs/inventories from both runs and the initial unsupported-Python
failure remain preserved. The new runner applies only the existing exact canonical
source SQL plus FEEDBACK candidate to a new empty private cluster. Source mutations
in tests are local fixture seeding/fault injection, not production cross-domain SQL.

## Limits and handoff

This demonstrates a local domain loop, not a real answer, live provider, real AUTH
account, App UI, production RLS/DB or device acceptance. Cross-domain reads and the
feedback write are separate transactions; source observation is explicitly read-time
and cannot promise atomic source-retirement/feedback ordering. Existing AUTH also
has no integrated distributed revocation lock. These limits are stated in the
contract and were not hidden behind a successful fixture or extra authority.

Main should route this complete fixed candidate plus dependency pins to original
Review/Testing; independent conclusions are **PENDING**. Then CJ005 owns formal
FEEDBACK wire, BASE mapping, canonical SQL/storage/cleanup registration. The existing
App answer/Memory-tab entry points and original Issue 15 I prerequisites remain
**UNRUN**. Model/rule version, usage, duration, tool results and failure stage stay
**UNKNOWN** until real canonical evidence exists. Trip/Memory refs remain rejected.
No production migration/deletion, key access, real provider, push/PR/merge, Issue
closure, third-party communication, deployment or release was performed.
