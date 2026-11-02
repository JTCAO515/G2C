# CJOfflineTrip

CJ-022 isolated Swift package. Production factory is closed (`SnapshotCodec.appFactoryAvailable == false`). No public raw-key provider or content reader; codec/store and canonical key consumer remain internal pending CLEANUP and offline authorization integration. AcceptedDetailSnapshotCache now consumes the fixed sealed Trip detail handle and its exact raw-byte hook; it does not grant offline permission. CanonicalSnapshotAccess consumes CJ007 dedicated offline-snapshot purpose with mandatory expectedID lookup and current-session/source fences; it never creates keys. Public pure evaluator and read-only state do not grant authorization.

Contract, reproduction, limitations and evidence: [offline-trip](../../../contracts/offline-trip/README.md).

M3 #418: the existing `AtomicSnapshotStore` constructor and `clearLocalEntry()` are
public for physical local cleanup only. Ciphertext read/write and plaintext access
stay internal; App factory remains closed. The same store must be retained by the
future host so unresolved writes continue to block cleanup. No device-wide or
server cleanup completion is implied.
