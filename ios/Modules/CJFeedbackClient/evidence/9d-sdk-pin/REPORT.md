# Feedback 9d pin for USAGE49 host graph

2026-10-23. Branch cj/023-feedback-client; exact original parent
**9b677b057a164595be673199a9a34dff12c588ba**, initially clean. No reset/unrelated edits.
This is Main-authorized host dependency consumption, not Feedback/USAGE functionality.

Separate prep **e0599558bb56030c5e7f435b8bfb9f104c8c265d** imports exactly shared
**e450e3828577feb211467e63177254f909b06b91** CJMessageClient subtree, tree
**d8b2158e9b3f508a1b51f0e8ed872cca8ed24c53**. Those17 upstream preparation paths
are excluded from product diff. This consumes the specified Host-guard Transport;
no downstream source or permission is inferred from its presence.
Existing prepare script exports16 exact official files from
**9d0f4b4c1e89b28d01de18092b5bf695de5bcde7** in cj-005-foundation.

Product base/parent: **e0599558bb56030c5e7f435b8bfb9f104c8c265d**. Final fixed head is
the commit containing this report, supplied in owner final. Sole non-evidence change:
Package.swift path c5→shared .generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7/CJFoundation.
Sources/Tests/Package.resolved, AUTH, root/API/CJShell and other consumers unchanged.

PASS fixed official c5/9d git-show comparison (compatibility.json): all prior **23 paths /
86 schemas** exactly unchanged; only USAGE status path/schema additions. Official SDK
manifest, lock and MemoryClientConfiguration.swift date helper byte-identical. All16
new official export hashes match shared generated-pin.json. All15 Feedback business/
lock files and48 pre-existing201156+c02+c5 exported files match pre-edit hashes.

PASS actual graph (`swift package --package-path ios/Modules/CJFeedbackClient show-dependencies --format json`):
one CJFoundation, exact9d path. dependency-graph.json records unique resolved nodes and
raw graph hash; raw .build/9d-pin-graph.json retained. Local module has no missing c5
owner dependency; this proves the isolated Feedback graph, not full CJ006 App graph.
No SDK revision/lock changes. A SwiftPM lock wait ended normally without retry/failure.

PASS6 unchanged test functions /22 cases /2 suites; targeted.txt:
`swift test --package-path ios/Modules/CJFeedbackClient --filter 'officialExactBodyAndOriginalQuery|officialUTC|nullAndMalformedLookupNeverAllowResend|badLinkedSourceRejected|malformedReceiptRejected|publicClientCannotPostEvenWithTrustedSessionAndResources'`
Actual generated Client in-process codec/body/query/source/hash/UTC/nullable checks,
including public constructor's disabled POST, pass. No real HTTP is issued. This
neither implements nor validates USAGE attempt/read-only source functionality.

PASS unsigned arm64/x86_64 module/public-API compile:
`xcodebuild -scheme CJFeedbackClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios-unsigned CODE_SIGNING_ALLOWED=NO build`
from module directory. Summary ios-build.txt and lossless ios-build-full.txt.xz.
No boot/launch/render, real account/network/Keychain, SQL/old DB/provider or deployment.

PASS final whitespace/scope/byte preservation checks. Previous valid business evidence
is reused without full-suite rerun; all historical FAIL/repair evidence preserved.
Default Feedback POST and existing business gates remain unchanged. This pin cannot
waive independent review, host integration or Issue15/I. Main routes final fixed head
to original dual gates and CJ006. No push/PR/merge/closure or full-I claim.
