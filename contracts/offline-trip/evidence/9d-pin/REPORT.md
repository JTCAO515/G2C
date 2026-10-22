# CJ022 single 9d SDK dependency candidate

Base `34c2fdd556bc70b4d870b71a3fb5af14ed4a1097`. Earlier partial shared/own pin working changes were rechecked and preserved, not overwritten. The Trip wait is now resolved with the exact fixed owner input below; STATUS.md/shared-prep.json preserve the earlier preparation stage, while this report/trip-prep.json/checks.json record the completed graph.

Product difference: one CJOfflineTrip/Package.swift line c5→9d0f4b4c1e89b28d01de18092b5bf695de5bcde7. CJOfflineTrip business Sources/Tests and all locks remain unchanged, as does the closed App factory. Old crypto/file/clock/reentry evidence and original FAIL logs stay retained and are reused where unchanged.

## Original prerequisite inputs, excluded from product delta

- Shared source `e450e3828577feb211467e63177254f909b06b91`: exact Package.swift, scripts/prepare_generated.py and evidence/generated-pin.json copied byte-for-byte. All other shared Sources, including Transport.swift, already match this owner head.
- Trip source `ba61baa2cd18ae9d13bc9733c1175b936512a786`: exact Package.swift copied byte-for-byte; all other Trip Sources already match. No guessed successor or authored producer change.
- AUTH Sources/Package stay exactly `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e`.

All selected fixed-owner source/manifest input hashes and original-prep lists are recorded in shared-prep.json and trip-prep.json. All16 canonical SDK inputs including original SDK lock match the shared manifest hashes, exported by the original script from local CJ005's fixed9d Git object. Ignored generated output is the single canonical CJMessageClient/.generated/9d.../CJFoundation path; no tracked SDK copy or second schema/wire/provider was added.

## Executed validation on the actual complete graph

All commands run under outer sandbox-exec `(version 1) (allow default) (deny network*)`. SwiftPM inner sandbox is disabled only to permit manifest execution under that outer sandbox; forced resolved versions/no remote updates. No real cache/Keychain/network action.

- PASS actual dependency graph: closure.json, exactly one unique CJFoundation path (four graph references), all9d with shared e450/Trip ba61/AUTH4eac. No c5 or c02 dependency root.
- PASS public-only API typecheck: PublicConsumer.swift against the newly built modules, direct swift-frontend, measured exit0 in checks.json/public-compile.log. No testable import in this public sample.
- PASS five minimum consumer functions in tests.log: exact original byte/nonce roundtrip; proposal/null/duplicate/mismatched-original rejection; actual public accepted source→canonical key→encrypted file; unknown-write blocking and exact-original reconciliation; exact independent one-attempt reentry probe. All use task-private synthetic in-process fixtures, not real accepted account/service sync.
- PASS unsigned arm64 iOS17 simulator-target package compilation with SDK27.1 (ios-build.log). Compile only, no boot/launch/device/install.
- PASS normalized official TripRecord, TripDetailResponse, TripDocument, TripDocumentItem and getTrip path schema equality between c5 and9d (checks.json). Existing frozen AAD/source identifiers are preserved business-format identifiers, not alternate package dependencies.
- PASS byte checks of unchanged business Sources/Tests/local lock, fixed AUTH/shared/Trip inputs,16 SDK hashes and git diff --check. No root/shared lock change.

Existing generator import and --skip-update deprecation warnings remain. Prior full valid suites are not rerun. Source acceptance, local attempt evidence and module compilation do not establish offline authorization, production TTL/trusted-clock anchor, real account/cache root, file-protection/device behavior, CLEANUP/logout/reconnect, real Keychain/provider, UI/CI/deploy or Issue24/I acceptance. App factory stays closed. Await Main's independent Review/Testing; no push/PR/merge/deploy.
