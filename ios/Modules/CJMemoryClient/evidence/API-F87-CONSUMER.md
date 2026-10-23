# Fixed-input Memory f87 consumer supplement — 2026-10-23

Parent `7690a5f56717c22b4f0cfd96e50bcd5044c94da6`, clean start. This supplement
closes the missing module-consumer checks from API-F87-PIN.md, using Main's newly
specified private fixed-input composition. It does not change the product pin,
Sources, Tests, lock files, sibling tracked files, factories or write gates.

## Exact private inputs

New directory under this module's ignored `.build`:
`f87-consumer-7690a5-c4d624f8/Modules`.
Build inputs were read directly from fixed Git objects, exported to the normal
relative package layout, SHA256 verified and made read-only. No manifest overlay
or rewrite and no new SDK identity:
- CJMemoryClient: `7690a5f56717c22b4f0cfd96e50bcd5044c94da6`.
- CJMessageClient/shared: `5075bcf604e959d5c4592071a1e9de39d8687395`.
- Canonical AUTH: `b24cc77c307bbb1dd9c552aeb92a148213534541`; all its required
  Package/Sources/Tests/lock bytes equal this tree's accepted AUTH build inputs.
- Single official CJFoundation export: `f87a78a9d8984c59905e385483f17dddd8144d8a`.

[Provenance and every build-input SHA](api-f87-consumer-provenance.json) records
exact paths/commits. Hashes were rechecked after tests and iOS compilation; none
changed. The original tree's shared 33 manifest was left unchanged and was not
used for this private graph. Its known conflict no longer blocks this independent
module evidence; actual host integration still belongs to the original owners.

## Missing consumer evidence now completed

- PASS: actual CJMemoryClient and its existing tests compiled against the fixed
  graph via `swift test`; this is the consumer module, not just an SDK typecheck.
- PASS: **6 existing test methods**, including two date arguments, exercise all
  five official Memory operations with in-process interception: list/detail/groups,
  persisted-original receipt query and candidate save/query. Whole/fractional dates,
  invalid non-null receipt rejection and opaque IDs remain covered.
  [Tests and command](api-f87-consumer-tests.txt).
- PASS: resolved dependency graph has exactly one canonical f87 CJFoundation path,
  referenced by Memory and Message. No older SDK identity is resolved in this graph.
- PASS: actual Memory consumer generic iOS Simulator SDK compile, signing disabled
  ([build](api-f87-consumer-ios.txt)). No App launch/device/Keychain access.
- PASS: original product Sources/Tests/Package/lock and tracked Message/Auth trees
  equal parent7690a5, and own diff whitespace/scope checks pass.

The already-passed SDK bytes/typecheck and earlier business gates were reused;
no full test suite, PG or independent SDK verification rerun. Full local logs:
`/tmp/cj011-f87-consumer-tests.log`, `/tmp/cj011-f87-consumer-ios.log`; private graph
and build artifacts are retained under the recorded `.build` directory.

This is author fixed-input consumer evidence, not independent gate or full App
acceptance. Whole Cleanup/CJShell graph remains **UNRUN**. The new wire gate,
real-source/factory/permission boundaries and existing business HOLDs remain;
POST stays closed. No real request/account/Keychain/provider/old-data/deployment,
push/merge/Issue closure or message to other threads.
