# CJ022 dc29 formal consumer candidate

Base `8694d958ae038880cce84da70251af69cf9b9587`, clean at the first live check. Formal CJOfflineTrip/Package.swift changes one SDK path20aa→dc29bb3634e63d8f065c38d39a7a0059f76cfa53. This is the actual tracked consumer manifest change needed by the single-SDK product frontier. Business Sources, Tests and locks are byte-identical to base; old20aa/f87 candidates, exports, mirrors and original FAIL logs remain. Only CJOfflineTrip paths are written.

## Fixed graph inputs

`scripts/prepare_dc29_validation.py` exports exact Git objects to a NEW ignored `.build/dc29-validation-9b4852d-7bcab1b` directory, refusing existing output. Canonical peer/shared/Trip paths are read-only.

- shared CJ009 `9b4852dfad418d124d60366ada8efb380a8ffc1d`;
- Trip CJ015 `7bcab1b13bc683c205f3ff0fa4446657427a5225` (its candidate gate is separate);
- AUTH `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e`;
- official dc29 SDK, all16 original inputs including lock matched to the exact shared manifest;
- local CJ022 formal manifest plus unchanged base source/test/lock bytes.

Every original path/owner/hash is recorded in inputs.json and rehashed after validation. No moving HEAD inputs, second tracked SDK, typealias, new wire model or business abstraction. The preparation script and all new evidence are within this module; no producer/peer tracked file is changed.

## Actual verification

All Swift commands run under outer sandbox-exec `(version 1) (allow default) (deny network*)`, with SwiftPM inner sandbox disabled under that outer restriction, versions forced from existing lock and updates skipped. Dependency working copies come from existing local package cache.

- PASS actual isolated CJ022 dependency graph (`closure.json`): four references to one unique CJFoundation path, all dc29; no mixed20aa/f87/33 SDK root.
- PASS public-only consumer typecheck against freshly built modules (`PublicConsumer.swift`, measured exit0 in checks.json/public-compile.log). Package and test targets compile on macOS.
- PASS two minimal codec cases (`tests.log`): exact original bytes/nonce roundtrip and invalid draft/null/duplicate/mismatched-original rejection. These are memory-only synthetic fixtures, with no cache save or keychain operation. Old unaffected file/clock/accepted-source/reentry evidence is reused.
- PASS all fixed mirror/SDK input hashes after validation; normalized TripRecord/TripDetailResponse/TripDocument/TripDocumentItem/getTrip equality20aa→dc29; unchanged local Sources/Tests/locks (`checks.json`), plus git diff --check.

Generated upstream import warnings and --skip-update warning remain. dc29 iOS target build and whole App graph/build/runtime are UNRUN in this minimal pass. Integration requires this candidate together with the exact shared9b/Trip7b/Auth4eac inputs and official dc29 export at the canonical path; other App consumers/host and producer candidate gates are outside this module's proof.

Factory/permission/actual-source boundaries stay closed. No guessed real TTL, trusted time, account root, actual cache, Keychain, save/cleanup, PG/network/device or provider operation. No issue closure, push/PR/merge/main update/deploy. Candidate awaits Main's original independent Review/Testing before Publish.
