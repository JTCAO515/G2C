# NEEDS formal dc29 consumer compatibility candidate

Starting branch/head verified clean: `cj/013-needs-client`,
`e03da1b2f1c22a28da5b8c9110166108a44af936`; old e03/f87 evidence and exports
remain intact. Requested6.1Sol medium/default, non-Fast; effective UNKNOWN.
Fixed shared input `9b4852dfad418d124d60366ada8efb380a8ffc1d`, official SDK
`dc29bb3634e63d8f065c38d39a7a0059f76cfa53`.

The actual formal `ios/Modules/CJNeedsClient/Package.swift` is updated20aa→dc29.
It remains the sole consumer dependency declaration, with the original shared path
layout and package identity. This is not only a temporary test-graph change.
The prepared consumer manifest is byte-identical to this formal manifest; both
SHA256 values are recorded and compared in provenance.json. No test-only alias,
alternate SDK, generated edit or package override is introduced.

Only Package.swift and this owned prepare/evidence directory are authored. The
accepted ignored fixed-Git preparation pattern under `.build/dc29-validation`
snapshots exact9b shared inputs, checks16 SDK files against canonical SHA and root
Git bytes, and links the existing official dc29 export. No shared/peer tracked
path is written or SDK copied. Final SHA/conflict checks pass after compilation.
The original20aa prepared manifest and older official exports are retained.

## Requested actual checks

- PASS: local Swift6.4/macOS official consumer/public module compile and six existing
  functions /ten expanded cases, compatibility.txt: four official NEEDS operations
  with original bytes; generated detail and historical revision alias reads;
  409 preserves source/edit/version after latest read; lost ACK reopening queries
  the original without resending; binding callback reentry cannot adopt new work.
- PASS: prepared actual graph has exactly one logical and one physical CJFoundation,
  the existing canonical dc29 package. package-graph.json/provenance.json retain paths.
- PASS: all28 prior20aa paths /97 schemas remain identical parsed definitions in
  dc29. SDK manifest/lock/datehelper and Transport94 are byte-identical. Transport
  SHA fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472.
- PASS: all15 owned business Sources/Tests/lock files equal e03 exactly. Actual source
  hashes are in provenance.json; the public API, unknown/CAS/binding implementations
  and closed-write policy are unchanged. Prior broader business evidence is reused.
- PASS: candidate formal manifest equals old formal manifest with only the exact
  SDK path replacement. Prepared manifest SHA equals formal manifest SHA.
- PASS: scoped diff whitespace; no Shell/FEASclient/P2 modification.

Reproduce preparation with `python3 evidence/api-dc29-pin/prepare_validation.py /path/to/cj-009-memory-api-pin /path/to/cj-005-foundation`.
From repository root use:
`swift test --package-path ios/Modules/CJNeedsClient/.build/dc29-validation/Modules/CJNeedsClient --force-resolved-versions --skip-update --filter 'actualOfficialClientUsesFourOperationsAndExactBytes|conflictPreservesDraftAndOriginalVersionAfterLatestRead|bindingCallbackReentryCannotAdoptNewWork|lostACKReopenQueriesOriginalThenHistoricalRevision|generatedDetailPreservesLegalAlias|generatedRevisionPreservesOriginalAliasBytes'`
and that same package path's `swift package ... show-dependencies --format json`.
No full suite, PG, Keychain, product request or dependency update ran.

Main/shared owner must provide canonical9b dependency preparation when integrating
this formal consumer into the complete host graph. The original clone's sibling
Message remains33 and its original canonical dc29 export is absent; its unprepared
root graph and full App are therefore UNRUN, not substituted by the scoped graph
result. No known-conflicting root build or peer edit was attempted. Independent
shared double-gate PASS is input attribution, not this consumer's independent review.

Default POST/factories/Auth/source authority remain closed/unchanged. New iOS/device,
real service/network/model/cache/SQL/CI/deployment and original IssueI are UNRUN.
No main update, push/PR/merge, new thread or external message. Main should collect
the fixed formal pin plus explicit host preparation condition for original dual gates.
