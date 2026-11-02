# CJOfflineTrip

CJ-022 isolated Swift package. Production factory is closed (`SnapshotCodec.appFactoryAvailable == false`). No public raw-key provider or content reader; codec/store and canonical key consumer remain internal pending CLEANUP and offline authorization integration. AcceptedDetailSnapshotCache now consumes the fixed sealed Trip detail handle and its exact raw-byte hook; it does not grant offline permission. CanonicalSnapshotAccess consumes CJ007 dedicated offline-snapshot purpose with mandatory expectedID lookup and current-session/source fences; it never creates keys. Public pure evaluator and read-only state do not grant authorization.

Contract, reproduction, limitations and evidence: [offline-trip](../../../contracts/offline-trip/README.md).

M3 #408: `OfflinePolicy.acceptedTrip` explicitly supplies JT's fourteen-day maximum
(1,209,600 elapsed seconds). `deadline(syncedAt:)` derives a new deadline for each
successful sync; overflow and invalid time fail closed. Missing policy still denies
reads and a larger later policy cannot extend an old authenticated deadline.
Injected-clock tests cover the exact boundary and renewal. This policy alone does
not enable the App factory: CLEANUP@1.0 and trusted session/clock host integration
remain required by #24. Device offline evidence stays in #29.
