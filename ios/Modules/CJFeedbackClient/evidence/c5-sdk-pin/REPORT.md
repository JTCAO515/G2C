# Feedback c5 pin for actual host graph

2026-10-23. Original branch cj/023-feedback-client; original parent
**147a9ae3d9dc9e1b182c6f9b01482dfe5f6fcc53**, exact requested HEAD, initially clean.
No reset or unrelated edits. Necessary consumer migration for CJ006 preview/Trip graph.

Separate prep **909924e1fc77adb4f2775ac1c13824b82310adaf** imports the exact shared
CJMessageClient subtree from **f4c17b59213828543cef042d127c56d8467963d8** (includes
parent3090777). Both tree IDs: **0c58b058b9fe3cc13ce1cd14aaa04118ce055646**.
Only those original shared12 paths are preparation, excluded from product diff.
No later5d/9d input consumed. Existing official prepare script exported exactly
16 files from root **c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a**.

Product base/parent: **909924e1fc77adb4f2775ac1c13824b82310adaf**. Final head is the
commit containing this report, supplied in owner final. Sole non-evidence product
change is one Package.swift path c02→shared .generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation.
Feedback Sources/Tests/Package.resolved are unchanged. Root/API/CJShell and every
other consumer remain untouched. Shared upstream code is not claimed as Feedback work.

PASS fixed official git-show comparison (compatibility.json): all old c02 **22 paths /
81 schemas** exactly unchanged; only manual-preview path/schemas added. Official SDK
manifest, lock and MemoryClientConfiguration.swift date helper byte-identical. All16
c5 export files match shared generated-pin.json. All15 Feedback business/lock files
and all32 pre-existing201156+c02 export files match pre-edit hashes after checks.

PASS targeted existing checks, with official Client and in-process synthetic transport:
`swift test --package-path ios/Modules/CJFeedbackClient --filter 'officialExactBodyAndOriginalQuery|officialUTC|nullAndMalformedLookupNeverAllowResend|badLinkedSourceRejected|malformedReceiptRejected|publicClientCannotPostEvenWithTrustedSessionAndResources'`
**6 functions /22 cases /2 suites**; targeted.txt. Exact feedback body/hash/source refs,
original GET, general/null/linked, UTC whole/fractional, invalid oneOf/malformed refs/
hashes/keys, and public constructor's disabled POST all pass. No new tests added and
no real HTTP sent. This does not validate Trip preview behavior.

PASS actual `swift package --package-path ios/Modules/CJFeedbackClient show-dependencies --format json`:
exactly one CJFoundation at the shared c5 path, recorded in dependency-graph.json.
No SDK revisions or locks changed. Raw graph retained in ignored .build/c5-pin-graph.json;
its hash is recorded. One initial SwiftPM lock wait ended normally, no failure/retry.

PASS unsigned iOS arm64/x86_64 module compile using:
`xcodebuild -scheme CJFeedbackClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios-unsigned CODE_SIGNING_ALLOWED=NO build`
from module directory. Summary ios-build.txt and lossless ios-build-full.txt.xz.
No boot/launch/render, real account/network/Keychain, PG/old DB/provider or deployment.

PASS final whitespace/scope and byte checks. Previous business and f19b repair evidence
are reused, not rerun or upgraded into new business acceptance. Original failures/logs
remain intact. Default Feedback POST stays disabled. Independent gates/HOLD are not
waived by this pin. CJ006 owns full-host unified graph integration; App/two-entry/I/
real-service/device/release remain separate. No push/PR/merge/issue closure.
