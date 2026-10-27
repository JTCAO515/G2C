# Readonly manual-preview c5 SDK pin — compatibility only

Starting consumer/business head: `2b2991871ce4e04bd1bfb5a92f3098e01512800a`.
Separate original-owner dependency preparation/this product commit's parent:
`7fab50dea3bbaf6ae0d50fe09f1df94db97a611e` (parent2b299).
Product head is the commit containing this report. Exact product diff: replace
one CJTripClient/Package.swift path and add this evidence folder. All Sources,
Tests, accepted detail hook, Package.resolved and POST gates remain byte-identical.

Fixed shared owner input: `3090777b4e10a6135823e3342e5e8b6c34aa9e6b`
from cj-009-memory-api-pin. Official SDK identity:
`c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a` from cj-005-foundation.
Sole shared dependency path:

`../CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation`

The preparation imports the shared owner's exact Package.swift, generation script
and generated-pin manifest, separately from product work. All16 exported package
files equal the fixed official API git objects. Publish/CJ006 must consume the
accepted original-owner dependency through its own lane; this preparation is not
a shared implementation rewrite. No other consumer, Shell or root source changed.

## Checks

- PASS: all old c02 paths22, schemas81, generated schema declarations81 and SDK
  blocks72 (24 old operations across Client/Operations/convenience methods) remain
  exact. API manifest, SDK lock and date helper remain byte-identical.
- PASS: all64 preexisting export files (c02,201156,d688,9dc) retain exact hashes.
  The573 export was already absent in this isolated clone; none was removed.
- PASS:4 existing snapshot/getTrip codec functions run with c5: exact received
  bytes/typed record/trace/binding/redaction; true null and legacy detail; four
  invalid nonnull fallback cases; six wrong-record/ignored-field cases.
  `gettrip-codecs.txt` records the selected tests and result. No Tests edits.
- PASS: unchanged compile-only public consumer uses new snapshot and old detail
  APIs against the rebuilt c5 module. Both snapshot/request constructors still
  fail external construction as expected. Source hashes and command are in
  `public-api-check.json`; compiler outputs are retained.
- PASS: package graph has one CJFoundation identity/path, c5, for both dependency
  edges; unsigned generic iOS Simulator compile passes with automatic resolution
  disabled and the existing locked versions. No simulator/app launch or signing.
- PASS: protected Sources/Tests/Package.resolved match2b299; old-export hashes,
  exact new export checks and new Package.swift hash are in `provenance.json`.

The accepted hook's declared formal source `apiSourceCommit` remains c02 exactly
as in2b299, as required by the Sources freeze. The shared SDK now includes preview
capabilities at c5 while its old getTrip contract/codec remain byte-identical.
There is no second CJFoundation identity, no reinterpretation of the sealed source
as caller authority, and no change to snapshot current guards or offline policy.

The original29-test/other independent business evidence is reused. This task did
not rerun the full business suites or infer their current gate outcome. Existing
compiler import warnings and SwiftPM --skip-update deprecation are retained in
log excerpts; no generated source was edited to suppress them.

Read-only provenance reproduction:

```sh
swift package --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-c5-package-graph.json
# Wait for the command to finish, then:
python3 ios/Modules/CJTripClient/evidence/c5-api-pin/check_pin.py \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-c5-package-graph.json
```

Pin independent Review/Testing remains pending. No business gate is released by
this compatibility PASS. Real POST stays closed; no actual preview use, product
HTTP, Keychain, permission change, cache write, PG, provider, account/device,
CI, deployment, push/PR/merge or Issue closure. The new ManualPreview client and
final CJShell graph remain their original owners' integration work.
