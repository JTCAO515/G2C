# f87 cleanup-host SDK pin — candidate compatibility

Base/parent: `c48016f3188380f33570b8c7e01ded797821c0bd`.
Head is the commit containing this report. Product diff only changes one SDK path
in CJTripClient/Package.swift and adds pin/preparation evidence here. Business
Sources, Tests, accepted-source hook and Package.resolved are byte-identical.
No sibling/shared/root/App source was modified; old FAIL evidence remains intact.

Fixed shared source: cj-009-memory-api-pin
`5075bcf604e959d5c4592071a1e9de39d8687395`.
Official API: cj-005-foundation
`f87a78a9d8984c59905e385483f17dddd8144d8a`.
Candidate path:

`../CJMessageClient/.generated/f87a78a9d8984c59905e385483f17dddd8144d8a/CJFoundation`

## Preparation scope and remaining graph dependency

This turn's authorization forbids sibling writes. The original clone's
CJMessageClient/Package.swift still pins33, its original prepare script/manifest
remain33, and its f87 generated directory is absent. These exact files and prior
exports were checked without modification. **Original-tree full graph is UNRUN**;
no predictably failing build was attempted, and no isolated PASS is labelled as
original-tree/App PASS.

`prepare_validation.py` assembles only under this module's ignored
`.build/f87-pin-validation/assembly/`. It copies fixed Trip/Auth manifests and
Sources/Tests/lock from c480, substitutes the candidate's exact one-path manifest,
and copies shared MessageClient from fixed5075. It checks official SHA and existing
conflicts/symlinks before invoking the original owner's unchanged export script.
All16 exported SDK files exactly match f87 and5075's manifest; there is no handwritten
SDK, new wire or rewritten dependency implementation. Existing conflicting ignored
bytes are refused, not overwritten. The preparation is ignored, not a sibling
prep commit or product-source replacement. `preparation.json` records all inputs.

Main/the original shared owner must install the accepted5075 manifest/export-script/
manifest-hashes and exact ignored f87 export in the original dependency position
before that source-tree graph can be validated. CJ006 still owns the complete App
composition with CJCleanupClient6d5e318; that client is not a dependency of this Trip
module and was not copied, changed or executed here.

## Actual results

- PASS (source compatibility): old33 API's25 paths,90 schemas and all previous SDK
  declarations/operation bodies remain equal. SDK manifest/lock and Memory helper
  are byte-identical; Transport94 remains exact at SHA256
  `fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472`.
- PASS (isolated fixed-input module):4 existing snapshot/getTrip codec functions,
  including parameterized null/fallback/wrong-record cases; official generated
  Client retains exact received bytes, same typed record/trace/binding and closed
  source behavior. No business/test edits or full business-suite rerun.
- PASS (isolated fixed-input module): public new/legacy API consumer compiles;
  external request/snapshot construction fails as expected. Original public probe
  source is reused unchanged, command scope is explicit in `public-api-check.json`.
- PASS (isolated fixed-input module): one actual CJFoundation identity/path, f87,
  and unsigned generic iOS Simulator compilation. No simulator/app launch or signing.
- PASS (original source preservation): protected Trip Sources/Tests/lock match c480;
  original sibling files match c480, and all112 old exported files match official
  fixed git objects. No original f87 directory was created. `provenance.json`.
- UNRUN: original-tree full module graph until the dependency gap above is supplied;
  final App graph and independent pin gates remain with Main/owners.

Reproduce isolated preparation/checks from repository root:

```sh
python3 ios/Modules/CJTripClient/evidence/f87-api-pin/prepare_validation.py \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation
swift package --package-path ios/Modules/CJTripClient/.build/f87-pin-validation/assembly/ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-f87-isolated-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-f87-isolated-graph.json
# Wait for successful completion, then:
python3 ios/Modules/CJTripClient/evidence/f87-api-pin/check_pin.py \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-f87-isolated-graph.json \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin
```

The new wire's independent gate is pending as supplied by Main. All results here
are candidate compatibility only; no factory activation, actual cleanup/progress
request, real source/provider, Keychain, permission change, PG, cache/device work,
CI, push/PR/merge/App edit/deployment or Issue completion. Existing effective business
evidence is reused and its gate state is not changed by this pin. Requested model
Sol6.1/medium/standard/default; runtime effective model/tier was not verified here.
