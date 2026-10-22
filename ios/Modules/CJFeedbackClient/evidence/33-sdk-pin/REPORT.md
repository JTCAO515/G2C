# Feedback 33 source-association host SDK pin

2026-10-23. Original branch cj/023-feedback-client; exact original parent
**9bd89ddd28aeca566d52961df37cfc0013b7b015**, initially clean. No reset/unrelated edits.
Main-authorized consumer pin for the actual CJ006 host graph; no new Feedback feature.

Separate prep **21b7a330ad9f2a0e028fb591853fd6a67fb27493** imports exactly shared
**6936a632ecc5cdbfd615b80c75312a09ed64b23a** CJMessageClient subtree, tree
**e77025c95be96d306cd76e938faf3766e6fd60a9**. Those8 upstream preparation paths are
excluded from product diff. Shared Transport is byte-identical to prior e450 input
(the accepted exact Host guard); hash recorded. No permission/factory change.
Existing prepare script exports16 exact official files from fixed
**33cec5ba71d74820cb0acd3c89ecbe39ba125590** in cj-005-foundation.

Product base/parent: **21b7a330ad9f2a0e028fb591853fd6a67fb27493**. Final head is the
commit containing this report, supplied in owner final. Sole non-evidence change:
Package.swift path9d→shared .generated/33cec5ba71d74820cb0acd3c89ecbe39ba125590/CJFoundation.
Feedback Sources/Tests/Package.resolved, AUTH, root/API/CJShell and other consumers
unchanged. Module has no Trip dependency and needed no guessed/other-owner head.

PASS fixed official9d/33 git-show comparison (compatibility.json): all prior **24 paths /
88 schemas** exactly unchanged. Added source-association paths/schemas are listed in
that file. Official SDK manifest, lock and MemoryClientConfiguration.swift date helper
byte-identical. All16 new exports match shared generated-pin.json. All15 Feedback
business/lock files and64 pre-existing201156+c02+c5+9d exports retain pre-edit hashes.

PASS actual isolated graph via
`swift package --package-path ios/Modules/CJFeedbackClient show-dependencies --format json`:
exactly one CJFoundation at shared33. Unique nodes and raw graph hash are recorded in
dependency-graph.json, raw .build/33-pin-graph.json retained. No dependency/lock drift
or missing other-owner module. This is not a full CJ006 App graph result. A SwiftPM
lock wait completed normally without retry/failure.

PASS6 unchanged test functions /22 cases /2 suites; targeted.txt:
`swift test --package-path ios/Modules/CJFeedbackClient --filter 'officialExactBodyAndOriginalQuery|officialUTC|nullAndMalformedLookupNeverAllowResend|badLinkedSourceRejected|malformedReceiptRejected|publicClientCannotPostEvenWithTrustedSessionAndResources'`
Actual generated Client exact body/hash/query/source/UTC/nullability and public POST
closed checks pass using synthetic intercepted transport only. No real HTTP/cache/
Keychain/source request, no test modification and no new source-interface capability.

PASS unsigned arm64/x86_64 module/public-API compile from module directory:
`xcodebuild -scheme CJFeedbackClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios-unsigned CODE_SIGNING_ALLOWED=NO build`
Summary ios-build.txt and lossless ios-build-full.txt.xz. No launch/render/signing/device.

PASS final whitespace/scope/byte preservation. Unchanged business evidence is reused,
not a full old-suite rerun. Historical FAIL/repair logs stay intact. Default POST,
factory, original actor/source boundaries and prior business gates unchanged. No real
network/Keychain/SQL/provider/deployment. This pin does not prove actual source/attempt
availability, host behavior or full Issue15/I; Main owns original dual gates and CJ006
integration. No push/PR/merge/main update or issue closure.
