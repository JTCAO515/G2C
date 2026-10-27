# Original-association33 SDK pin — compatibility only

Starting consumer/business head: `ba61baa2cd18ae9d13bc9733c1175b936512a786`.
Separate original-owner dependency preparation/product parent:
`750bed24ada10d7704dbb7609bcb2590748c8bf1` (parent ba61).
Head is the commit containing this report. Exact product diff: replace one
CJTripClient/Package.swift path and add this evidence folder. Sources, Tests,
accepted hook, business factories, lock and public POST gates remain unchanged.

Fixed shared input: `6936a632ecc5cdbfd615b80c75312a09ed64b23a`
from cj-009-memory-api-pin. Official SDK:
`33cec5ba71d74820cb0acd3c89ecbe39ba125590` from cj-005-foundation.
Sole shared package path:

`../CJMessageClient/.generated/33cec5ba71d74820cb0acd3c89ecbe39ba125590/CJFoundation`

Preparation imports only exact original-owner shared Package.swift, generation
script and generated-pin manifest. Its runtime Sources are identical to the prior
shared input, including Transport94 SHA256
`fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472`.
All 16 exported files equal the fixed official API objects. The local prep is not a
product/shared implementation rewrite; consume the accepted shared input via its
original owner and exclude prep from the product diff.

## Actual verification

- PASS: old 9d: 24 paths, 88 schemas, 88 generated declarations and 78 SDK blocks
  (26 operations across Client/Operations/convenience APIs) remain exact.
  SDK manifest/lock and Memory date helper are byte-identical.
- PASS: all 96 previous exported files retain exact hashes. Existing exports are
  preserved; the573 export was already absent in this isolated clone.
- PASS:4 existing getTrip/snapshot codec functions/1 suite with the new33 Client:
  exact received bytes and typed record/trace/binding; actual null and old detail;
  four illegal nonnull fallback cases; six wrong/invalid-record cases.
- PASS: unchanged public consumer compiles new snapshot and legacy APIs; external
  snapshot/request construction still fails as expected. Commands, source hashes
  and compiler outputs are in `public-api-check.json` and adjacent text files.
- PASS: actual resolved graph has one CJFoundation identity/path,33. This Trip
  module depends directly on shared MessageClient/Auth, not another owner Trip
  consumer; no missing external consumer was substituted or guessed. Generic
  unsigned iOS Simulator compilation succeeds; no launch/signing/network request.
- PASS: every Trip source/test and Package.resolved matches ba61; unchanged sealed
  accepted source retains its declared c02 identity. `provenance.json` records
  protected files, old exports, exact shared bytes and new Package.swift hash.

No other consumer, root or CJShell path changed. These results cover the local
module graph, not the final CJ006 App graph. Prior business, closed-source/current
lifetime, Transport94 and default-write-gate evidence is reused; no whole-suite,
real network, cache or Keychain rerun. Existing compiler warnings remain visible
in the logs and no generated source was edited to hide them.

Read-only provenance reproduction:

```sh
swift package --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-33-package-graph.json
# Wait for successful completion, then:
python3 ios/Modules/CJTripClient/evidence/33-api-pin/check_pin.py \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-33-package-graph.json
```

Independent pin Review/Testing remains pending; no business gate is changed by
this pin PASS. Factory, permissions, real-source and public POST boundaries are
unchanged. No actual association/source/provider, usable attempt, full I, real
account, PG, device/UI, CI, push/PR/merge/main edit, deployment or Issue closure
is claimed. CJ006 owns subsequent final App composition.
