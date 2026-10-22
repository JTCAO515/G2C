# NEEDS post-3625 pure RUN-display SDK pin

Previous consumer head: `3625cff8ba285296a92d3ea7cc34eec659a0e091` (clean at start).
Canonical shared input: `540da02a335e96e98917ffd3d94a395f8ca2d892`.
Official API identity: `c02cf08e52a0d8ffc2fefac99226654a7e01539c`; subsequent API
evidence-only commits are not substituted for this source identity.

An independent preparation commit imports exactly the shared owner's eight changed
files, including original tests/evidence, without rewriting them. Its full hash is
`prep_commit` in `provenance.json`; it is this pure-pin commit's parent. Import
attribution remains with CJ009, not NEEDS product authorship. Source owner trees
remain read-only. No other consumer, root or CJShell is changed.

The authored product diff changes exactly one dependency path in this module's
Package.swift, from201156 to the sole shared:
`../CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation`.
All other authored files are this minimal evidence directory. Business Sources,
Tests and locks are byte-identical to3625; timezone cd33 and directory-fence5ef
repairs are retained. Existing POST-disabled behavior, business gates and HOLD
remain unchanged. This pin does not accept or activate RUN/other-domain behavior.

## Actual scoped checks

- PASS: fixed official201156→c02 comparison retains all **21 previous paths / 79
  schemas** as identical parsed JSON definitions. SDK Package.swift, Package.resolved
  and MemoryClientConfiguration.swift are byte-identical. Hashes in provenance.json.
- PASS: the existing owner export script produces16 exact official files at c02.
  Existing201156 andd688 exports each retain16 exact files. No local generated
  modifications, duplicate SDK authority, package upgrade or rewritten date helper.
- PASS: **5 selected test functions / 9 expanded cases**, `codec.txt`: absent/four
  states, malformed observation decoding, actual generated detail/revision alias
  preservation, and all four official NEEDS operations with exact original bytes.
  Command:
  `swift test --package-path ios/Modules/CJNeedsClient --filter 'absentAndFourStatesUseOfficialGeneratedTypes|malformedGeneratedObservationsReject|generatedDetailPreservesLegalAlias|generatedRevisionPreservesOriginalAliasBytes|actualOfficialClientUsesFourOperationsAndExactBytes'`
- PASS: actual package graph contains one physical CJFoundation location, c02;
  `package-graph.json`. Full same-App graph is CJ006's responsibility and UNRUN here.
- PASS: unsigned generic iOS Simulator SDK compile, full log losslessly archived in
  `ios-full.txt.xz`; command, original size and SHA256 in `ios-log.json`. No launch.
- PASS: all15 business Sources/Tests/lock files unchanged, fixed shared subtree
  matches540da, scoped diff whitespace. Exact checks recorded in provenance.json.

REUSED: prior3625 43-function/67-case business evidence and original P2 before/after
artifacts. They were not rerun as an unrelated full suite, rewritten, or upgraded
to independent acceptance. This pin's compatibility PASS cannot waive any existing
business review/HOLD or true-service gate.

UNRUN: real account/resources, Keychain, product HTTP/SQL/PG, App/device/model,
CI/deployment and original Issue14 integrated acceptance. No new privileges,
credentials, real services, push, PR, merge, Issue closure or chat creation.
Main should route the fixed pure-pin diff and its separate preparation attribution
through original Review/Testing, with CJ006 coordinating the one-SDK App graph.
