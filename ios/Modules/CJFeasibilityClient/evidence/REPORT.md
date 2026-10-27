# CJ035 iOS current NEEDS evaluation — author evidence, candidate CLOSED

Historical c607/0c917 evidence below. Testing subsequently confirmed Observation
reentry P2; this candidate is HOLD. See [repair evidence](observation-reentry/REPORT.md)
for its separate author fix and pending independent re-review. Original47 logs
and executed-source manifest below are retained as historical bytes.

Product base: `02f672605ad5521f9360e42be8f43ebfd022a0e8`.
Tested source commit: `0c917f8267816f20eda078deb89f52d17732f856`.
Branch/root: `cj/035-feasibility-client`,
`<local>/Documents/Codex/2026-10-21/cj-035-feasibility-client`.
Evidence-only follow-up commit is the final candidate HEAD; no product files
change after the tested source commit. Sole owned subtree is
`ios/Modules/CJFeasibilityClient/**`. No push, PR or external message was sent.

## Fixed inputs

- Root official SDK/wire: `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`.
- Shared export: `9b4852dfad418d124d60366ada8efb380a8ffc1d` (parent cc9).
- Auth/CJSession: exact product-base Git snapshot, not a moving sibling directory.
- Shared canonical Transport94 `Sources/CJMessageHTTP/Transport.swift` SHA256:
  `fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472`.
- [inputs.json](inputs.json) contains complete shared/Auth fixed Git blob hashes
  and all16 official SDK hashes. Preparation verifies SDK bytes against BOTH the
  fixed shared manifest and root dc29 Git blobs, snapshots shared/Auth inside this
  module's ignored `.prepare`, and links the canonical owner's SDK directory.
- [executed-source-sha256.json](executed-source-sha256.json) records tested product,
  test, script, manifest, lock and documentation bytes. No second SDK is copied.

## Author results

- PASS — 15 Swift Testing functions,47 expanded cases, including all validation
  callback boundaries. [tests-final.log](tests-final.log). Official generated
  operation GET exact selector/body-free request; canonical NoRedirectTransport94
  + CJSession fixture composition; CONFLICT/UNKNOWN with overallUNKNOWN; exact
  decomposed UTF8 and decimal string; original null declaration preservation.
- PASS — strict malformed/duplicate/truncated/invalidUTF8 JSON, missing/null/extra
  fields, official version/enums, bool/fraction revision, content/source hashes,
  original NEEDS/action/source revision and evidence relation; collection and
  byte limits, media/cache/request-ID and redirect rejection. BASE503
  FEASIBILITY_INPUT_INVALID stays explicit rejected503, with exactly one request.
- PASS — owner-bound one-use token; account/environment/selection/session changes,
  missing source, credentials-stage switch, final callback reentry, cancellation,
  late response body/cancellation after replacement, accepted revision/hash
  mismatch, and public factory refusal. No automatic read/retry/poll.
- PASS — normal-import host typecheck, opaque token construction rejection and
  public symbol graph. [public-api.json](public-api.json), [PublicAPI.swift](PublicAPI.swift).
  The only public model initializer is `init(session:currentBinding:)`; internal
  fixture transport/parser are hidden. No host-visible live enable flag/factory.
- PASS — Xcode27.1(27A9275)/Swift6.4 local iOS Simulator generic build, arm64 and
  x86_64, deployment target17.0, no signing/runtime launch. [ios-final.log](ios-final.log).
  This is compile evidence; no rendered UI/VoiceOver or runtime acceptance claim.
- PASS — prepared package graph one logical and one physical canonical dc29 SDK,
  [graph-check.json](graph-check.json), [package-graph.json](package-graph.json).
  Shared/Auth prepared blob equality rechecked after testing; module Package lock
  is byte-identical to accepted base CJUsageClient lock. Sibling modules untouched.
- PASS — staged/complete diff whitespace check and owned-path scope check.

Initial fixture test compile FAIL was `??` around a throwing expression; fixed
with an explicit optional response-body branch. Original compiler diagnostics are
preserved in [tests-first.log](tests-first.log); subsequent41-case first pass in
[tests.log](tests.log), final expanded47-case pass above. This was fixture syntax,
not a hidden accepted assertion change. Initial graph export had a trailing blank line flagged by diff whitespace check;
removed only that blank line and rechecked. SDK generated unused-public-import and
`--skip-update` deprecation warnings remain; no product compilation errors.

Full iOS build logs remain inside local ignored `.prepare`; tracked excerpts name
the exact full-log path and SHA256. No source credentials/private user data occur
in these synthetic fixtures. [build.log](build.log) is the local macOS package build.

Commands executed from this repository unless noted:

```sh
python3 ios/Modules/CJFeasibilityClient/scripts/prepare.py <local>/Documents/Codex/2026-10-21/cj-009-memory-api-pin <local>/Documents/Codex/2026-10-21/cj-005-foundation
swift test --package-path ios/Modules/CJFeasibilityClient/.prepare/Modules/CJFeasibilityClient --force-resolved-versions --skip-update
swift package --package-path ios/Modules/CJFeasibilityClient/.prepare/Modules/CJFeasibilityClient show-dependencies --format json
python3 ios/Modules/CJFeasibilityClient/scripts/check_public_api.py
```

From `.prepare/Modules/CJFeasibilityClient`:

```sh
xcodebuild -scheme CJFeasibilityClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios -clonedSourcePackagesDirPath .build/ios-packages -disableAutomaticPackageResolution CODE_SIGNING_ALLOWED=NO build
```

## Integration boundaries and remaining conditions

Original root/shared independent gates were pending at dispatch; this author
report cannot release them. Default/public FEAS factory remains hard CLOSED,
with no network/credentials object or alternate production enable path.

The product-base whole App still pins20aa. Prepared dc29 local module compatibility
is a separate graph; the original clone's unprepared graph is not a candidate
App build. Before integration, original owners must provide accepted root/shared
compatibility including cohost pin handling, unify the App on ONE SDK graph, and
implement/review explicit host enablement using real current NEEDS selection,
canonical session and NoRedirectTransport/credentials. Host current binding must
be real and fresh; constructing the context, observing the report, localPASS or
clicking evaluation confers no authority or global atomic freshness.

No provider facts are translated, money rounded, timestamps reconstructed, solver
or history replay copied, or FEASIBLE/write/Trip confirmation permit produced.
Private source texts stay only in memory; no persistent store/cache/log exists.
No CJNeedsClient/CJShell/shared/Auth/backend/global lock changes occurred.

UNRUN — real route/network HTTP, PG/accounts/C2, Keychain, provider/model calls,
permissions, VoiceOver/rendered UI, simulator runtime/device, whole App behavior,
independent Review/Testing, CI, merge, deployment/release, Issue18 complete/I
acceptance. Source's existing PG/solver evidence is upstream evidence, not rerun
or claimed as this consumer's acceptance. No Issue closure or activation requested.
