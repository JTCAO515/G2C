# Shared CJAPI Trip export candidate (not activated)

Independent successor on existing cj/009-memory-api-pin branch, exact parent
**d0f396ceaff5a7d51ddc3a623b35e3eef9191412**. Parent remains intact for ongoing573
consumer integration; all16 prior573 exported files rehashed unchanged. No rebasing,
replacement of d0, or edit to other consumers/shared sources.

Official producer fixed **9dc67ced50a0cb7611a84b4adf97ab0b43c88bea**, not claimed
merged main or independently accepted wire. One versioned export location:

`ios/Modules/CJMessageClient/.generated/9dc67ced50a0cb7611a84b4adf97ab0b43c88bea/CJFoundation`

This module's Package.swift and the existing prepare_generated.py pin move to that fixed
source; exact16 exported source hashes recorded in generated-pin.json. Existing source
whitelist still requires the non-Generated MemoryClientConfiguration.swift and manifest/
lock. No manual generated edits, alternate CJFoundation identity or private wire type.
Official ../CJAuth key dependency remains unchanged.

Read-only compatibility checks against573:
- All10 previous OpenAPI paths and24 previous schema objects exactly equal.
- Official ios/Package.swift, Package.resolved and MemoryClientConfiguration.swift bytes
  exactly equal; no SDK versions or configuration defaults changed.
- New operations only: actOnTripProposal, queryTripAction, listTrips, getTrip,
  getTripProposal. This consumer references their generated methods but invokes NONE.

PASS: standalone CJMessageClient compilation,32 tests in5 suites. Existing31 Message/
Draft/history/required-null/Memory configuration checks pass; one new test compiles all
five Trip method references in the SAME imported CJAPI module with .memory configuration.
Its interceptor fails if called: no Trip or genuine network/credential request is made.
Concise output trip-api-pin-tests.txt; raw log/hash and provenance in trip-api-pin-provenance.json
and ignored .build/trip-pin-evidence. This is compile/consumer compatibility, not Trip
business authority or real service acceptance.

PASS: actual SwiftPM standalone dependency graph lists one CJFoundation location, the
new versioned path. Old573 directory remains preserved but is not a second active graph
identity. All resolved dependency states match existing fixed-main SDK locks; no upgrade.
Automatic standalone lock expansion preserved in ignored evidence then restored to source
lock, as for parent; existing shared lock/source authority unchanged.

No CJShell/CJMemoryClient/root generated files or package manifests touched. Full App
combined graph remains UNRUN until Main coordinates ALL consumers onto the SAME new pin;
current573 delivery must continue using parent d0 and its unchanged exported files. This
successor is not permission to activate Trip writes or change live Message/Draft gates.
No real Keychain/PG/service/signing/push/PR/deploy. Independent review/testing pending.
