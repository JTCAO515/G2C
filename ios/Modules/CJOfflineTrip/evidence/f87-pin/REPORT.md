# CJ022 f87 consumer candidate — isolated fixed-input graph

Base `e590f94ff367a9821d06558b7c35c2d020b40629`, clean before this task. Product manifest changes exactly one SDK path33→f87a78a9d8984c59905e385483f17dddd8144d8a. Business Sources/Tests/Package.resolved remain byte-identical to base; old SDK exports and all prior FAIL/evidence remain. Only CJOfflineTrip paths are changed.

## Exact inputs and preparation

- Shared source repository cj-009-memory-api-pin, fixed `5075bcf604e959d5c4592071a1e9de39d8687395`. Every source/manifest/lock/test byte comes from git show at this commit. Its moving20aa checkout is never read as source.
- Trip source cj-015-trip-client, fixed `a5cc42005c69811ccb05754793107141fb4a9f02`. Original c480 business is unchanged; complete selected package inputs are exported exactly.
- AUTH source cj-007-auth fixed `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e`, using only its exact Git objects.
- Official SDK f87a78a9d8984c59905e385483f17dddd8144d8a:16 original inputs including lock, all verified against shared507's exact generated-pin.json. Exported only to its canonical relative path within this isolated graph.
- CJ022 local manifest and unchanged base business/test/lock inputs are copied into the graph. All source hashes and original owner commits are in inputs.json; all were rechecked after validation, including locks.

`scripts/prepare_f87_validation.py` creates a new ignored `.build/f87-validation-5075bcf-a5cc420-v2` mirror and refuses to replace existing output. It does not write canonical CJMessageClient/CJTripClient/CJAuth tracked paths or their exports. No new SDK/schema/provider abstraction is introduced. The original partial mirror is retained after the initial missing AUTH Git-object failure; preparation-attempts.md records the corrected original-source read. Only the completed v2 mirror is validated.

Reproduce from a fresh checkout with the same fixed owner repositories available: run `python3 scripts/prepare_f87_validation.py` inside CJOfflineTrip; run SwiftPM with `--package-path .build/f87-validation-5075bcf-a5cc420-v2/ios/Modules/CJOfflineTrip`. Never build against the intentionally unchanged canonical siblings in this owner tree. A complete App graph must be prepared by the integration owner.

## Actual verification

All Swift commands run under outer sandbox-exec `(version 1) (allow default) (deny network*)`, with inner SwiftPM sandbox disabled under that outer restriction, resolved versions forced and updates skipped. Existing local package cache supplies dependency checkouts; no real network access. No PG, SecItem/Keychain, device, App cache, save, cleanup or runtime provider operation.

- PASS actual isolated dependency graph (`closure.json`): four references to exactly one unique CJFoundation path, all f87. No mixed33/9d/c5/c02 SDK dependency root. This is the CJ022 closure only.
- PASS public-only API compile against newly built mirror modules, measured exit0 (`PublicConsumer.swift`, public-compile.log, checks.json). Imports only public CJOfflineTrip/Trip API; no handle construction, request dispatch or authorization grant.
- PASS two minimum codec functions (`tests.log`): exact original UTF-8 bytes/nonce roundtrip and invalid draft/null/duplicate/mismatched-original rejection. These use in-memory synthetic crypto fixtures only and do not invoke file-store/cache operations. Full older effective crypto/file/clock/accepted-source/reentry evidence is reused at unchanged business scope, not rerun.
- PASS all mirror input/SDK hashes after validation; unchanged consumer source/tests/locks; official normalized TripRecord/TripDetailResponse/TripDocument/TripDocumentItem/getTrip schema equality33→f87 (`checks.json`). Existing frozen AAD/source-format identifiers stay unchanged, not alternate dependency paths.
- PASS macOS package/test-target build and git diff --check. f87 iOS target build is UNRUN in this minimal pass; full App graph/build/runtime remains UNRUN.

Generated upstream import and --skip-update warnings remain in logs. Candidate gate pending independent Review/Testing and Main/Publish integration. Canonical siblings still have their previous owner-tree pins until the integrator assembles fixed inputs; no claim that this owner's unmixed isolation proves the full App tree. App factory/permissions/real-source/offline TTL/trusted clock/cache root/CLEANUP/device gates remain unchanged and closed. No push/PR/merge/main update/deploy.
