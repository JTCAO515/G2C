# Single shared CJAPI Feedback candidate — no business activation

Exact parent165a0c0137e9baa59c1cf93df7a67d342b6d5b6a on the existing
cj-009-memory-api-pin branch. Fixed official producer201156c9bf9850f9b8e87dc1f986452ce1ae789f,
not a claim of merged main or independently accepted wire. Separate bf79 context-query
tree remains unchanged. Current App d688 integration is not modified here.

One versioned candidate path:
`ios/Modules/CJMessageClient/.generated/201156c9bf9850f9b8e87dc1f986452ce1ae789f/CJFoundation`

Existing prepare mechanism exports16 exact official package/source files; non-Generated
MemoryClientConfiguration.swift still mandatory. All source hashes in generated-pin.json.
No handwritten model, generated authority edit, alternate SDK/package identity or consumer
manifest outside this module. All prior d688/9dc/573 export files rehashed unchanged.

Fixed d688→201156 comparison: all19 previous paths and73 previous component schemas
exactly unchanged. Official SDK Package.swift/Package.resolved/datehelper bytes unchanged.
New operations submitFeedback and queryFeedbackAction, with six official Feedback schema
types; no runtime transport/business integration, route permission or write flag added.

PASS: Swift6.4/macOS standalone build and38 tests in7 suites. Existing35 Message/Draft/
history/Memory/Trip/Needs compatibility checks plus3 new Feedback checks: generated method
references compile without requests, required receipt null/missing/non-null fallback are
distinct, and actual official FeedbackReceipt submitted_at decodes UTC whole/fractional
seconds using unchanged Configuration.memory.dateTranscoder. Source:null is checked as
actual nil. JSON fixtures use the official generated types; no duplicate wire structs.
These are synthetic codec observations, not a real submitted feedback record or endpoint.

PASS: actual standalone package graph contains CJFoundation at exactly the201156 path.
All resolved SDK states match existing fixed-main locks, no version upgrade. Automatic
standalone lock expansion preserved locally then source lock restored; no root/shared
lock changes. Exact provenance/raw log hash in feedback-api-pin-provenance.json; concise
output feedback-api-pin-tests.txt and raw log in ignored .build/feedback-pin-evidence.

Full App combined graph remains UNRUN until Main coordinates every consumer on this
same pin. Do not activate d688 and201156 simultaneously in one App graph. Existing live
POST/PUT disabled gates are unchanged. No CJShell/CJMemoryClient/Auth changes, true network,
account/Keychain/PG, signing, push, PR, merge or deployment. Independent review pending.
