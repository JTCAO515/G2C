# Shared d688 API pin — compatibility candidate only

Business source base: `12df1c1590174ab327d7d01782d736bd20ec199c`.
Separate local dependency preparation: `a120093bf96b555305afc86ff0e61ee8a2ae2f59`.
The product pin diff starts at that preparation commit and changes only this module's
`Package.swift` plus `evidence/d688-api-pin/**`. Head is the commit containing this
report. No Trip Sources, Tests, Package.resolved, CJShell or backend change.

Fixed shared export owner: CJ009
`165a0c0137e9baa59c1cf93df7a67d342b6d5b6a` from `cj-009-memory-api-pin`.
Exact official API input: `d688c01dc0fb18488a1e9c49414a039ce0126204` from
`cj-005-foundation`. Replaces the previous9dc package reference with:

`../CJMessageClient/.generated/d688c01dc0fb18488a1e9c49414a039ce0126204/CJFoundation`

The old README/earlier evidence describes the original9dc candidate. This report
and Package.swift record the new dependency. Both references in the local package
graph (CJTripClient and CJMessageClient) resolve to the same CJFoundation identity
and path. The9dc export remains present. No parallel SDK, rewritten generated file,
date parser or compatibility layer was created.

Preparation imported only owner-authored shared Package.swift/prepare_generated.py
and its generated-pin manifest, separately from the product diff. All16 generated
files were produced with that exact owner script and equal the official fixed git
objects. Do not publish this local preparation over the shared owner's integrated
branch. Publish/CJ006 must compose the accepted full165 shared dependency first.

## Checks actually run

- PASS: unchanged15 old OpenAPI paths and34 old schemas; all34 prior generated
  schema declarations and51 SDK blocks (17 old operations across Client,
  Operations and convenience API declarations) remain exact. API manifest/lock
  and MemoryClientConfiguration.swift are byte-identical. See `provenance.json`.
- PASS: existing8 targeted Swift tests/2 suites under the new generated Client.
  Proposal states; formal list/detail and historical receipt; C keysets/cursors;
  actual null and illegal nonnull fallback; reject-null/accept-version; original
  `Action.raw` bytes encrypted before dispatch and sent unchanged. No test source
  was edited. `codec-tests.txt` includes the actual selected tests and result.
- PASS: official `Configuration.memory` date transcoder handles whole and fractional
  RFC3339, round-trip and rejects invalid date. `DateConfigurationCheck.swift` is
  a pin evidence probe, not product code or a new parser. `date-check.txt` is output.
  The first probe compile put a throwing expression in precondition's nonthrowing
  autoclosure; it failed before execution, then was fixed by a local value. The
  diagnostic is preserved in `date-compile-initial-failure.txt`; final compile exit0.
- PASS: package graph has a single CJFoundation path; unsigned generic iOS Simulator
  compile succeeds with automatic package resolution disabled. No simulator/app
  launch or signing. `ios-build.txt` is a compiler/status excerpt.
- PASS: all Trip Sources/Tests and Package.resolved remain byte-identical to12df.
  Hashes and the new Package.swift hash are recorded in `provenance.json`.

The codec test command uses `--force-resolved-versions --skip-update` and a filter
for these existing method names:

```
officialRawBytesFreezeBeforeAwaitAndSurviveReopen
receiptIsHistoricalAndFormalEntrancesReadCurrentVersion
nonNullOneOfFallbackNeverMeansAbsent
rejectRequiresNullAndMismatchedReceiptCannotSettle
keysetUsesCOrderAndEmptyPageEndsTraversal
nonemptyPageNeedsExactLastID
terminalProposalReadableWithoutGrantingWrite
illegalRejectVersionFallbackAndWrongAcceptVersionFail
```

`--skip-update` is deprecated by this installed SwiftPM; generated SDK compilation
also emits unused-public-import warnings. Neither was hidden or fixed in generated
source. The8 selected tests and compilation completed successfully.

Read-only provenance reproduction:

```sh
swift package --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-d688-package-graph.json
python3 ios/Modules/CJTripClient/evidence/d688-api-pin/check_pin.py \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-d688-package-graph.json
```

The original34-test and P2-repair evidence is reused, not rerun or erased. The
12df two-P2 business repair remains **pending independent gates** as specified by
Main; this pin PASS does not release its HOLD. New pin independent Review/Testing
is also PENDING. Public POST remains disabled. No PG, real Keychain, product HTTP,
account/confirmation issuer, provider, rendered UI/device, CI, deployment,
push/PR/merge or Issue closure was performed.
