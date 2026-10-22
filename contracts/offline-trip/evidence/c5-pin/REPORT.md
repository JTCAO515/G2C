# CJ022 c5 SDK pin candidate

Base `adce521e964ce405bb19ab7211a36234cc5c09df`, initially clean. Original history and FAIL logs retained. Product delta is exactly one CJOfflineTrip/Package.swift line, c02→c5. Business Sources, Tests and local/root/shared locks are unchanged. No 9d input.

## Fixed prerequisite prep (excluded from product delta)

- shared CJ009 `94c50ab6650e9defb0f7df6d7ccbb2bff250c947`: unchanged Package.swift, Sources/CJMessageHTTP/Transport.swift, scripts/prepare_generated.py and evidence/generated-pin.json.
- Trip `f931d5834d8a5162b223a8607b83d27d3639afe7`: unchanged Package.swift. All other Trip Sources already matched that fixed owner input.
- AUTH Sources/Package still exactly `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e`.

All owner-input SHA256s and exact imported-file lists are in prep.json. Canonical c5 `c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a` export is ignored local generation at CJMessageClient/.generated, not tracked SDK duplication. All16 exported inputs including original SDK lock match owner manifest hashes. The unchanged original prep script used local CJ005 Git objects; the shared owner's clone itself lacked the c5 Git tree, so that first export attempt failed before writing output. No remote fetch.

## Actual validation

All validation ran under outer `sandbox-exec` profile `(version 1) (allow default) (deny network*)`. SwiftPM's inner sandbox had to be disabled because nested sandbox application failed; the outer network-deny remained active. The initial nested-sandbox failures and incorrect CLI argument placement are retained in logs. No real network/provider/cache/Keychain action.

- PASS: actual `swift package show-dependencies --format json` graph (`closure.json`) contains four references to exactly one CJFoundation path, all c5, no c02/9d dependency path. Local resolved versions forced; no remote version update or lock change.
- PASS: public-only consumer typecheck using the actual built CJOfflineTrip/Trip modules and `swift-frontend`, exit0 (`PublicConsumer.swift`, `public-compile-final.log`, checks.json). Initial swiftc driver's nested sandbox failure retained in public-driver-sandbox-fail.log; direct frontend typecheck preserves the outer network deny.
- PASS:13 selected functions (`tests-final.log`): two affected codec controls plus10 accepted-source controls and the exact independent one-attempt reentry probe. Exact bytes/namespace/source/key/store combination and the repaired reservation stay correct under c5. Old crypto/file/clock suites are reused, not rerun.
- PASS: unsigned arm64 iOS17 simulator-target module build on SDK27.1 (`ios-build.log`), including actual shared94/Tripf931/AUTH4eac dependency graph. This is compile only.
- PASS: normalized official schemas TripRecord, TripDetailResponse, TripDocument and the schema referenced by TripDocument.items (TripDocumentItem) are identical in c02/c5; see checks.json. The initial schema-check name guess was corrected by following that original $ref. Frozen codec AAD/source identifier and AcceptedTripDetailSnapshot.apiSourceCommit remain unchanged business-format identifiers, not a second package dependency.
- PASS: business Sources/Tests/locks byte-checked against adce521 and `git diff --check`.

Generated upstream import warnings and --skip-update deprecation are retained. Public App factory stays closed. No new offline permission, policy/TTL/clock anchor/cache root/CLEANUP, real cache/key, service/device/UI/CI/deployment or Issue24/I acceptance is claimed. Candidate still needs original independent Review/Testing. No push/PR/merge/deploy.
