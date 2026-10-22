# Feedback c02 shared SDK pin — no business activation

Original fixed parent **f19b0150fe336f303af6e05aa7bb38f665530ee1**, clean before work.
Original clone/branch: cj-023-feedback-client / cj/023-feedback-client.
This is the Main-authorized pin needed for the new RUN client84f41e same-App graph,
not another Feedback feature, architecture or permission change.

Separate preparation **1b79913cc4c9f5dcbf86ae11f426e6843e7e9f21** imports exactly
shared owner **540da02a335e96e98917ffd3d94a395f8ca2d892** CJMessageClient subtree.
Both subtree IDs are **5a4eeb016652f0abcfd306eec3c8a5bb61e8afad**. Those8 paths are
upstream preparation, not Feedback product differences. Official existing prepare
script exports fixed root **c02cf08e52a0d8ffc2fefac99226654a7e01539c**. Later root
Evidence-only a5f is not used as a different SDK identity.

Product diff begins at **1b79913cc4c9f5dcbf86ae11f426e6843e7e9f21**. Sole non-evidence
change: Feedback Package.swift path201156 →
`../CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation`.
Final pin head is the commit containing this report, supplied in the owner response.
No Feedback Sources/Tests/Package.resolved edits, no root/API/CJShell/other consumer
edits, no new SDK identity or handwritten wire/date helper. AUTH unchanged.

## Direct fixed-input verification

compatibility.json records checks performed against git-show of the exact official
201156 and c02 commits in cj-005-foundation, rather than relying only on upstream prose:

- All **21** previous OpenAPI paths and **79** schemas compare exactly equal.
- Only new path /v1/run-display and its2 schemas are added.
- Official ios/Package.swift, ios/Package.resolved and
  ios/Sources/CJAPI/MemoryClientConfiguration.swift are byte-identical.
- All16 newly exported official package/source/test files match generated-pin.json.
- All16 pre-existing201156 export files in this clone remain hash-identical. Other
  historic export directories were absent here, not regenerated, removed or claimed
  to have been locally tested. Shared owner's prior-export provenance remains separate.
- All15 existing Feedback Sources/Tests/Package.resolved files remain hash-identical
  before/after builds (including f19b repair and byte-exact independent counterexample).

## Necessary consumer checks

PASS `swift test --package-path ios/Modules/CJFeedbackClient --filter 'officialExactBodyAndOriginalQuery|officialUTC|nullAndMalformedLookupNeverAllowResend|badLinkedSourceRejected|malformedReceiptRejected'`

5 unchanged functions /21 expanded cases under c02. Actual official Client is used
with an in-process interceptor: exact original POST bytes/hash/minimal source refs,
original GET, general/linked, whole/fractional UTC, null and illegal oneOf, wrong refs,
wrong action/hash, message-input-hash confusion, duplicate/missing/additional fields.
No real HTTP is issued. Raw codecs.txt retained. This does not test new RUN semantics.

PASS `swift package --package-path ios/Modules/CJFeedbackClient show-dependencies --format json`

dependency-graph.json records the actual resolved unique graph and raw graph hash.
Exactly one CJFoundation location, shared c02 path. Existing SDK versions unchanged;
Feedback and shared locks untouched. Raw graph retained in ignored .build/c02-pin-graph.json.

PASS `xcodebuild -scheme CJFeedbackClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios-unsigned CODE_SIGNING_ALLOWED=NO build`
from module directory. Unsigned arm64/x86_64 module compile under c02; no boot/launch/
signing/device. ios-build.txt summary and lossless ios-build-full.txt.xz preserve
actual result. Official generated-code import warnings are unchanged; no generation edits.

PASS exact diff scope/whitespace and source/lock/export preservation checked before
commit. No new test failure occurred. Original69d/f19b before/after evidence is intact.

## Remaining gates

Only pin/codec/graph/module compilation PASS. Unaffected business evidence is reused;
no full old suite, PG, Keychain, provider, live network/account or device rerun. Default
POST remains disabled because business Sources are byte-identical. Original f19b
repair, independent Review/Testing status and69d/b868 HOLD are preserved; a pure pin
cannot waive them. Main routes fixed candidate to original dual gates, and CJ006 owns
coordinated App graph integration. Full App/two-entry/I/deployment remain UNRUN/open.
No push/PR/merge/issue closure or service/permission changes.
