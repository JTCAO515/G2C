# USAGE-host 9d shared SDK pin — compatibility only

Starting consumer/business head: `f931d5834d8a5162b223a8607b83d27d3639afe7`.
Separate fixed original-owner dependency preparation/product commit parent:
`701280a71b1f7381ea1363b266a8aadf19f1f099` (parent f931).
Product head is the commit containing this report. Exact product diff is one
CJTripClient/Package.swift path replacement plus this evidence folder. All Trip
Sources, Tests, accepted hook, lock and public POST gates remain byte-identical.

Fixed shared input: `e450e3828577feb211467e63177254f909b06b91`
from cj-009-memory-api-pin. Official SDK identity:
`9d0f4b4c1e89b28d01de18092b5bf695de5bcde7` from cj-005-foundation.
The sole shared path is:

`../CJMessageClient/.generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7/CJFoundation`

## Dependency preparation versus product

Preparation imports four exact original-owner files: shared Package.swift,
prepare_generated.py, generated-pin.json and CJMessageHTTP/Transport.swift.
The transport is the sole shared runtime source difference from this clone's
previous input and equals e450/94's fixed bytes, SHA256
`fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472`.
It includes the owner's narrow preview Host guard, not a new transport authored by
this task. All16 generated export files equal the fixed official API git objects.
Original shared dual-PASS evidence is reused as supplied by Main; its Host suite
was not rerun or claimed as new local Trip evidence. Exclude this local preparation
from the product diff and consume the full accepted shared input through its owner.

No other consumer, Shell or root generation/source was edited. The actual local
Trip module graph has no other owner module requiring a c5 CJFoundation: both
Trip and Message dependency edges resolve to the same9d path. This is a verified
module graph, not the final CJ006 App graph or a claim about unrelated consumers.

## Checks actually run

- PASS: old c5 paths23, schemas86, generated schema declarations86 and SDK blocks75
  (25 old operations across Client/Operations/convenience methods) remain exact.
  SDK manifest/lock and Memory date helper are byte-identical.
- PASS: all80 previous export files (c5,c02,201156,d688,9dc) retain exact hashes.
  The573 export was already absent in this clone and was not deleted.
- PASS:5 targeted existing test functions/2 suites: four getTrip snapshot codec
  tests (exact bytes/record/trace/binding, null/legacy detail, illegal nonnull
  fallback and invalid records) plus the public Trip write-gate test with the
  repaired default NoRedirectTransport. No runtime socket/POST is issued.
- PASS: compile-only unchanged public new/legacy consumer succeeds against9d;
  external snapshot/request construction fails as expected. Compiler outputs and
  original probe source hashes are in `public-api-check.json`.
- PASS: actual package graph has one CJFoundation identity/path,9d; unsigned generic
  iOS Simulator compilation succeeds with automatic resolution disabled and locked
  versions. No simulator/app launch or signing.
- PASS: every Trip business source/test and Package.resolved matches f931; unchanged
  accepted source retains its declared c02 identity. The old getTrip contract and
  codec remain identical under the larger9d SDK. `provenance.json` records hashes,
  exact owner transport, old exports and the new manifest.

Earlier business/current-guard evidence is reused, not rerun or relabelled as9d.
The new readonly RUN source interface remains with its original owner; no attempt
source, provider, allowance, usable attempt or complete I behavior is inferred here.
Current business gates are unchanged by this pure pin. Shared transport metadata
and guard-source equality do not constitute actual DNS/virtual-host traffic.

Read-only provenance reproduction:

```sh
swift package --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-9d-package-graph.json
# After the preceding command finishes:
python3 ios/Modules/CJTripClient/evidence/9d-api-pin/check_pin.py \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-9d-package-graph.json
```

Independent pin gates are pending. No actual network, Keychain, permission change,
PG, real account/provider/attempt, cache write, device/UI, CI, deployment,
push/PR/merge/main mutation or Issue closure. Existing generated-import/SwiftPM
warnings are retained in log excerpts; no generated source was altered to suppress
warnings. Task requested Sol6.1/medium/default; effective model/tier not verified.
