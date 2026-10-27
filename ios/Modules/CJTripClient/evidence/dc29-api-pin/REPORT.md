# FEAS current dc29 — formal Trip consumer pin candidate

Base/parent: `b3485ef02bbe4cc9bfcebfc1f9c61a1a67670ce5`.
Head is the commit containing this report. The tracked formal consumer
CJTripClient/Package.swift now points to dc29; this is not merely a test-manifest
change. Product delta is that one path plus this pin/prepare evidence. All business
Sources, Tests, accepted-source hook, factories, locks and old FAIL records remain
unchanged. No peer/shared/Shell/backend path was modified.

Fixed shared source: cj-009-memory-api-pin
`9b4852dfad418d124d60366ada8efb380a8ffc1d`.
Full official SDK identity read from that source:
`dc29bb3634e63d8f065c38d39a7a0059f76cfa53`.
Formal dependency path:

`../CJMessageClient/.generated/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/CJFoundation`

## Candidate composition and actual checks

`prepare_validation.py` uses the accepted fixed-Git-input pattern only under
this module's ignored `.build/dc29-pin-validation/assembly/`. It takes the exact
formal candidate manifest, business files/lock from b348 and shared module from
9b4852d, then invokes the original unchanged export script. SHA/conflict/symlink
checks precede writes. All16 SDK files equal fixed official git bytes and the
owner's manifest. No second SDK implementation, wire, alias or altered consumer
is constructed. `preparation.json` records inputs; the compiled manifest SHA
matches the tracked formal candidate.

- PASS: old20aa's28 paths,97 schemas,97 generated declarations and90 SDK blocks
  (30 existing operations across Client/Operations/convenience methods) remain
  exact. SDK manifest/lock/helper and Transport94 retain their prior bytes.
- PASS:4 unchanged snapshot/getTrip codec functions with parameter cases: exact
  received bytes and typed record/trace/binding, legacy detail/null, illegal nonnull
  fallback, wrong/invalid-record rejection. No old full-suite or feature rerun.
- PASS: public new snapshot and legacy detail API consumer compiles against dc29;
  external snapshot/request constructors remain inaccessible. Original probe
  source hashes and compiler outputs are preserved in `public-api-check.json`.
- PASS: exact formal candidate compiled in a real fixed-input module graph with
  one CJFoundation identity/path, dc29, and passed unsigned generic iOS Simulator
  SDK build. No signing, installation or launch. No actual request was made.
- PASS: protected business Sources/Tests/lock match b348; original sibling files
  remain unchanged. All112 old original-export files match prior official hashes;
  old f87 and20aa preparation inputs/SDK are retained and verified.

The original clone still has sibling MessageClient33 and no dc29 export at that
original sibling path. Its graph remains UNRUN instead of a knowingly failed
build. Main must install the exact accepted9b4852d dependency/export in the final
integration location. The fixed-input candidate graph above is actual compilation
of this formal consumer, but does not substitute for CJ006's entire App graph.
No old fixed head or publication input was amended or overwritten.

## Reproduction / boundaries

```sh
python3 ios/Modules/CJTripClient/evidence/dc29-api-pin/prepare_validation.py \
  <local>/Documents/Codex/2026-10-21/cj-009-memory-api-pin \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation
swift package --package-path ios/Modules/CJTripClient/.build/dc29-pin-validation/assembly/ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-dc29-isolated-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-dc29-isolated-graph.json
# Wait for completion, then:
python3 ios/Modules/CJTripClient/evidence/dc29-api-pin/check_pin.py \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-dc29-isolated-graph.json \
  <local>/Documents/Codex/2026-10-21/cj-009-memory-api-pin
```

Shared dual-PASS is supplied by Main; its FEAS tests were not duplicated here.
New formal consumer candidate still requires original independent Review/Testing.
Prior effective business/current-guard evidence is reused. Management, save and
confirmation boundaries stay closed; no activation, new product feature, real
network/credentials/account/provider, cache, Keychain, PG, device, CI, push/PR/merge,
Shell/App edit/deployment or Issue completion. Compiler warnings are retained and
no generated source was altered to suppress them. Requested Sol6.1/medium/default,
non-Fast; effective model/tier was not independently verified.
