# NEEDS f87 dependency candidate — owned preparation only

Starting branch/head verified clean: `cj/013-needs-client`,
`e6e949e8fbd2aa57c5a9b14954aade68f1240229`.
Requested Standard/default,6.1Sol medium; effective UNKNOWN.
Fixed shared input: `5075bcf604e959d5c4592071a1e9de39d8687395`.
Official SDK: `f87a78a9d8984c59905e385483f17dddd8144d8a`.

Authored diff is one Package.swift path33→f87 plus this module's preparation script
and evidence. No business Sources/Tests/locks or sibling/shared/root/App files were
modified. This turn does not create a shared prep commit: the current instruction
limits writes to CJNeedsClient. Fixed dependency preparation is isolated under
CJNeedsClient/.build/f87-validation, attributed to5075 rather than product authorship.

`prepare_validation.py` checks all16 canonical exported files against the fixed
shared SHA manifest and actual fixed API Git bytes. It refuses conflicting existing
inputs. It snapshots fixed tracked Message module files inside NEEDS's ignored
area and symlinks the **existing** shared owner's canonical f87 CJFoundation export;
no SDK is copied or generated. Candidate Package/lock are copied for validation,
Sources/Tests and existing Auth are referenced read-only. Final preparation/SHA
recheck passes after tests. See preparation.json and preparation-after.json.

## Actual compatibility

- PASS: local Swift6.4/macOS consumer compile and six existing directed functions /
  ten expanded cases under the fixed prepared graph, compatibility.txt. Four-state/
  absent and invalid observations, generated alias detail/revision reads, four
  official NEEDS calls with exact original bytes, and public write rejection pass.
- PASS: actual prepared dependency graph has one logical and one physical SDK path,
  resolving to the existing canonical shared f87 export; package-graph.json and
  provenance.json. There is no Trip dependency, new SDK or writable sibling input.
- PASS: all25 previous33 paths /90 schemas are identical parsed definitions in f87.
  SDK Package/lock/date helper are byte-identical. Transport94 SHA remains
  fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472.
- PASS: all15 owned Sources/Tests/lock files equal e6e949e; six older exports remain
  exact; shared/auth tracked files in the original clone remain untouched.
- PASS: owned diff whitespace. No new business test, whole-suite or PG rerun.

Commands use fixed resolved versions and skip updates:
`python3 evidence/api-f87-pin/prepare_validation.py /path/to/cj-009-memory-api-pin /path/to/cj-005-foundation`
then from repository root:
`swift test --package-path ios/Modules/CJNeedsClient/.build/f87-validation/Modules/CJNeedsClient --force-resolved-versions --skip-update --filter 'absentAndFourStatesUseOfficialGeneratedTypes|malformedGeneratedObservationsReject|generatedDetailPreservesLegalAlias|generatedRevisionPreservesOriginalAliasBytes|actualOfficialClientUsesFourOperationsAndExactBytes|publicConstructionCannotWrite'`
and the same prepared path with `swift package ... show-dependencies --format json`.
No real request or dependency update is part of those checks.

## Remaining original-tree graph dependency

Original clone CJMessageClient/Package.swift remains fixed6936 with33 path; its
canonical f87 export is absent. Therefore the **unprepared original-tree graph is
UNRUN**, not PASS. No known-conflicting build was attempted. Main/shared owner must
provide original canonical5075 Message dependency preparation/export when consuming
this candidate into the one-App graph. The exact fixed prepared graph above proves
NEEDS consumer compatibility; it does not claim CJ006's actual App graph is ready.

Old accepted business/P2 and iOS compile evidence are reused. New wire independent
gate is pending; this is only candidate compatibility. No factory activation,
permission/source change, usable attempt or full IssueI claim. Default POST stays
closed. Real network/Keychain/PG/device/model/cache/CI/deployment are UNRUN; no push,
PR, merge, main update or messages to other threads. Main should collect this fixed
candidate and remaining dependency for original dual review and host coordination.
