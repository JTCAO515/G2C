# Single shared CJAPI NEEDS export candidate — not activated

Same cj-009-memory-api-pin tree/branch, exact parent4fb05cc1f28382c5a4e97efdd833d5f079997c96.
Separate context-query bf79a948c36a7c5cecf40d840cb9623c2d2e9d7c tree remains untouched.
Fixed producer d688c01dc0fb18488a1e9c49414a039ce0126204, not claimed merged/accepted wire.
Only this module Package.swift/prepare pin, export hash evidence and local consumer tests
change; no root lock/generated authority, other consumer, runtime gate or endpoint change.

One shared candidate export:
`ios/Modules/CJMessageClient/.generated/d688c01dc0fb18488a1e9c49414a039ce0126204/CJFoundation`

Existing prepare mechanism exports16 exact official files; MemoryClientConfiguration.swift
remains required. Exact file hashes in generated-pin.json. Both prior9dc and573 export
inventories rehashed byte-identical against their fixed parent manifests; they remain
available for current delivery. No second active CJFoundation package identity is created.

Read-only comparison9dc→d688: all15 old paths and34 old component schemas unchanged;
official ios Package.swift/Package.resolved/Memory date helper byte-identical. Additions
are actOnNeeds, queryNeedsAction, getNeeds and getNeedsRevision. No handwritten wire
model, generated edit or default NEEDS business/write activation introduced.

PASS: standalone Swift6.4/macOS build and35 tests in6 suites. Existing32 Message/Draft/
history/required-null/Memory/Trip compile-consumption checks reused at the new producer;
three new checks compile the four NEEDS methods without invoking them and decode the
actual official NEEDS response types: valid receipt branch; required null receipt/needs/
revision; absent required keys fail; a non-null fallback remains non-null and cannot be
interpreted as absence. This is bounded codec evidence, not full NEEDS semantic validation,
authentication, operation success or UI acceptance. The export interceptor fails if called.

PASS: actual standalone SwiftPM dependency graph resolves CJFoundation at ONLY the d688
location. Every resolved SDK revision matches the existing fixed-main Auth/Shell locks;
no upgrade. Automatic standalone lock expansion preserved only in ignored build evidence,
then source lock restored. needs-api-pin-provenance.json captures hashes/version inventory;
needs-api-pin-tests.txt is concise output, raw full log preserved locally under ignored
.build/needs-pin-evidence. No old PostgreSQL or other real resource touched.

Full App three-consumer graph remains UNRUN: Main must coordinate the same pin with
original owners in order. Current mainPR74/9dc and4fb delivery are not changed by this
unmerged successor. No CJShell/CJMemoryClient manifest edits, real network/Keychain/POST,
server, signing, push, PR or deployment. Independent Review/Testing pending.
