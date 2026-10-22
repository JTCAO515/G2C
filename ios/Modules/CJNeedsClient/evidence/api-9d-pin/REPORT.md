# NEEDS pure9d SDK pin for USAGE49 host composition

Verified clean starting branch/head: `cj/013-needs-client`,
`ab7d82c504f6816b2a1224f3747f41df7d651429`. Requested6.1Sol Medium/default;
effective model UNKNOWN. Scope: Package.swift dependency path plus this evidence.

Exact shared input: `e450e3828577feb211467e63177254f909b06b91` from original
cj-009-memory-api-pin. Official SDK identity:
`9d0f4b4c1e89b28d01de18092b5bf695de5bcde7`. No moving/new readonly-source input
or speculative interface is consumed.

Separate preparation parent `28c079214301df00f17992718973743e30b9e0f1` imports
17 shared-owner files unchanged, retaining their original source/tests/evidence and
attribution. This prep is excluded from the authored product diff. Original owner
worktrees were read-only. Existing business Sources/Tests/locks are unchanged.

The only manifest change is c5→9d at the existing shared path:
`../CJMessageClient/.generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7/CJFoundation`.
The actual module graph has one physical CJFoundation at9d; no remaining c5
consumer dependency blocks this module. Full host/App graph is CJ006's separate
responsibility and UNRUN here.

## Scoped verification

- PASS: public module compilation and six existing directed test functions / ten
  expanded cases, compatibility.txt. Checks absence/four-state and invalid codec,
  generated detail/history alias strings, four NEEDS operations/exact original
  bytes and public constructor's closed write path. No test/source modification.
- PASS: graph with fixed resolution and no updates, package-graph.json.
- PASS: all23 previous c5 paths and86 schemas are identical parsed JSON definitions
  in9d. Official SDK manifest/lock/date helper are byte-identical.
- PASS:16 exact official files in each of five retained exports: d688,201156,c02,c5,9d.
  Existing export bytes were preserved. No generated rewrite or second SDK identity.
- PASS:15 NEEDS Sources/Tests/lock files exactly equalab7d. Imported shared subtree
  equals e450. Fixed pins, graph path and source hashes in provenance.json.
- PASS: scoped diff whitespace. No root/other consumer/CJShell edits.

Commands used fixed resolved versions and skipped dependency updates:
`swift test --package-path ios/Modules/CJNeedsClient --force-resolved-versions --skip-update --filter 'absentAndFourStatesUseOfficialGeneratedTypes|malformedGeneratedObservationsReject|generatedDetailPreservesLegalAlias|generatedRevisionPreservesOriginalAliasBytes|actualOfficialClientUsesFourOperationsAndExactBytes|publicConstructionCannotWrite'`
and `swift package --force-resolved-versions --skip-update show-dependencies --format json`.
The skip-update deprecation notice is retained; no command failure occurred.

Prior accepted business gates/P2 evidence and c5 unsigned iOS compilation are
REUSED; this manifest-only migration did not rerun the full business suite or iOS
build. Public API compile evidence here is local Swift6.4/macOS package compilation,
not new iOS App/device/runtime evidence. Default POST, prior HOLD and independent
gates are not changed or waived by this pin.

No real product network, credentials, Keychain, SQL/old database, model, device,
CI/deployment, push, PR, main change or Issue closure. Actual usable attempt/new
readonly-source API/fullI are not claimed. Main should route this fixed pure-pin
through original dual review and provide it to CJ006 for the unified9d host graph.
