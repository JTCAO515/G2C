# CJ013 NEEDS client — local author candidate

Date: 2026-10-22 Asia/Shanghai. Owner workspace:
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-013-needs-client`, branch `cj/013-needs-client`.
Unique Main: `01a15e24-928b-7540-97a4-14b52e6ee995`.
Requested Astra/high; fast not set; effective UNKNOWN.

## Fixed diff and dependency boundary

Main base `2ca62479d82c761272c4ad3f8357467f9e5eba8c` → separate unchanged dependency
preparation `7fe71617e4d4c6ef15c658532f3909edeec87865` → candidate commit containing
this report. **Product review base is 7fe7161; every authored path is exclusively
`ios/Modules/CJNeedsClient/**`.** No root schema, domain backend, shell, other
module source or shared lock was authored. The source trees remain read-only.

The preparation contains exact CJMessageClient165a and CJAuth668d subtrees, including
already-existing source/tests/historical evidence. It is dependency preparation,
not NEEDS product authorship or approval of their still-independent gates. Publish
must consume only the scoped product commit after Main's original Review/Testing,
with the exact dependencies available; do not blindly cherry-pick preparation.
The NEEDS module directly references the one shared d688 CJFoundation export.
Dependency pin hashes and author real-chain pointer are in `dependencies.json`.

## Delivered behavior

- Public embeddable bilingual detail/revision/editor/pending components and a
  trusted-host presentation model. No shell edits. No model extraction/source
  binding pretended to be integrated. Public live POST remains closed.
- Official generated `NeedsCommand`, observations, responses and four Client
  operations. No handwritten wire/parser or second SDK. Input validation is
  domain-local bounds/semantics on generated types. Absent fields remain absent;
  explicit four states, collection clearing, decimal lexical form, local dates,
  IANA zone, source text, companions and user booking/locked intent are retained.
- Only user-edited fields enter a patch. Existing event/list/map replacements keep
  the fixed producer semantics. Drafts keep their expected version and text after
  409; latest detail does not silently rebase or resubmit.
- One-shot original POST after encrypted durable append. Reopen queries original
  ID only. Both POST and query receipts require their exact historical revision
  and matching original UTF8 bytes before settlement. Null, bad oneOf and errors
  leave pending unresolved. Latest detail never unlocks a new action.
- Opaque prepare/perform work is captured before Task creation. Credential,
  binding, provider and store callbacks recheck the original owner/lifetime;
  newer selection/account state survives old completion/error. Final directory
  and original ciphertext checks have no callback after the last resource callback.
  Cancellation leaves no stuck loading state for the still-owned operation.

## Actual checks

| Check | Result and evidence |
|---|---|
| Local affected Swift suite | **PASS**, 36 test functions, 51 parameter-expanded cases, 8 suites; `tests.txt` |
| Actual official Client four operations | **PASS**, intercepted transport, exact POST bytes and receipt→revision request sequence; `ClientTests.swift` |
| Absence/four states, partial patch, exact money, local DST/timezone, source UTF8 | **PASS**, `ContractTests.swift`; two device timezone settings produce identical original bytes |
| Unknown/CAS/history | **PASS**, query/revision null/errors/bad oneOf, identity/version/body/Unicode mismatch, lost ACK reopen, latest-detail non-proof, repeated action prevention |
| Callback/identity/durability | **PASS**, `BoundaryTests.swift`: queued A/B and foreign work, credential/binding/key return/throw reentry, account switch during await, directory displacement and original-file removal before zero outflow, ciphertext change before zero settlement, nested pending load, cancellation |
| Existing public key-provider seam | **PASS**, `KeyProviderTests.swift`; actual ScopedMessageKeyProvider with synthetic in-memory persistence, only original lookup, no creation/deletion/random-key fallback, missing/invalidated/wrong-purpose key withheld |
| Fixed producer consumes Swift-generated fixture | **PASS**, `generated-command.json`, `producer-compatibility.json`, reproducible `check_producer_fixture.py`; pure validator only, no SQL/HTTP |
| Unsigned iOS Simulator SDK compile | **PASS**, final source build, `ios-build.txt`; full original output compressed losslessly in `ios-final-full.txt.xz` |
| Single SDK physical path / unchanged imports | **PASS**, `package-graph.json`, `verification.json`; own Package.resolved only |
| Product diff whitespace / source manifest | **PASS**, `source-sha256.json`, `git diff --cached --check` before commit |

Full Xcode logs were compressed losslessly, with uncompressed hashes in
`build-log-archives.json`. This is artifact packaging, not replacement evidence.
Source hashes cover final Package/Sources/Tests. Test fixtures are explicitly
synthetic and do not imply real source/provider/booking confirmation.

## Preserved failures and limits

- `initial-build.txt`: core module compiled, then test command exited because no
  tests had been added yet; not a test PASS.
- `ui-first-build.txt`: missing CJAPI import in presentation; corrected in product.
- `tests-first.txt.xz`, `tests-second.txt`, `tests-final.txt`: test setup/compiler
  failures (required Session restorePolicy, throwing assertion, missing `func`
  keyword). Fixed and retained; no assertions weakened. Intermediate successful
  `tests-third.txt`, `tests-provider.txt`, `tests-final-after.txt` retained separately.
- SPM dependencies were resolved from existing caches into this module's build
  area, with versions recorded in its own lock. No global configuration changed.
- **UNRUN:** rendered UI/preview/simulator interaction, VoiceOver, real device,
  actual host account/resources/collection policy, real Keychain, product HTTP,
  model/source extraction, SQL/PG, CJShell integration, CI, deployment and full
  original Issue 14 I acceptance. No provider/paid/signed/store/release actions.
- API a624 real PG/HTTP/Swift evidence is the API author's separate evidence; its
  initial initdb-before failure remains in that original tree, not recharacterized
  here. No old PostgreSQL or unrelated full suite was rerun.
- Independent Review/Testing **PENDING**. No push, PR, merge, Issue close or new
  chat creation. The candidate is ready for Main to collect and route through
  the existing dual gates and unique Publish.

Final packaging added module-local `.gitignore` for build caches and removed only
source trailing whitespace after the successful checks; behavior is unchanged.
No build cache or embedded dependency repositories are part of the product commit.
