import Foundation
import CJAPI
import CJTripClient
import CJMessageKeys
import CJSession

/// Explicit metadata from an approved host clock/policy is still required for production.
/// No defaults, TTL grant or clock authority is created here.
struct OfflineSyncMetadata {
    let syncedAt: Int64
    let deadline: Int64
    let boot: UUID
    let uptime: Double
}

/// An internal one-attempt source→key→file composition, never a new accepted-handle factory.
@MainActor final class AcceptedDetailSnapshotCache {
    struct Receipt {
        let version: Int64
        let responseHash: String
        let syncedAt: Int64
    }
    let snapshot: OfflineSnapshot
    private let access: CanonicalSnapshotAccess
    private let store: AtomicSnapshotStore
    private let validateOriginal: () throws -> Void
    private var attempted = false

    convenience init(client: TripClient, accepted: AcceptedTripDetailSnapshot, store: AtomicSnapshotStore,
         provider: ScopedMessageKeyProvider, session: SessionLifecycle, sessionOperation: SessionOperation,
         expectedKeyID: UUID, sync: OfflineSyncMetadata) throws {
        try store.requireNoPendingWrite()
        guard AcceptedTripDetailSnapshot.apiSourceCommit == "c02cf08e52a0d8ffc2fefac99226654a7e01539c" else {
            throw OfflineFailure.unsupportedFormat
        }
        try client.validateDetailSnapshot(accepted)
        let snapshot = try client.withCurrentDetailSnapshot(accepted) { bytes, record, trace, binding in
            let namespace = try OfflineNamespace(account: binding.account, backend: binding.environment, trip: record.trip_id)
            let value = try SnapshotCodec.capture(response: bytes, namespace: namespace, syncedAt: sync.syncedAt,
                deadline: sync.deadline, boot: sync.boot, uptime: sync.uptime, keyID: expectedKeyID)
            let response = try JSONDecoder().decode(Components.Schemas.TripDetailResponse.self, from: bytes)
            guard value.trip == record, Data(response.request_id.utf8) == Data(trace.utf8) else {
                throw OfflineFailure.invalidSnapshot
            }
            return value
        }
        try self.init(snapshot: snapshot, store: store, provider: provider, session: session,
            operation: sessionOperation, expectedKeyID: expectedKeyID,
            validateOriginal: { try client.validateDetailSnapshot(accepted) })
    }
    convenience init(client: TripClient, accepted: AcceptedStructuredTripSnapshot, store: AtomicSnapshotStore,
         provider: ScopedMessageKeyProvider, session: SessionLifecycle, sessionOperation: SessionOperation,
         expectedKeyID: UUID, sync: OfflineSyncMetadata) throws {
        try store.requireNoPendingWrite()
        try client.validateStructuredSnapshot(accepted)
        let snapshot = try client.withCurrentStructuredSnapshot(accepted) { bytes, record, _, binding in
            let namespace = try OfflineNamespace(account: binding.account, backend: binding.environment, trip: record.tripID)
            return try SnapshotCodec.captureStructured(response: bytes, namespace: namespace, syncedAt: sync.syncedAt,
                deadline: sync.deadline, boot: sync.boot, uptime: sync.uptime, keyID: expectedKeyID)
        }
        try self.init(snapshot: snapshot, store: store, provider: provider, session: session,
            operation: sessionOperation, expectedKeyID: expectedKeyID,
            validateOriginal: { try client.validateStructuredSnapshot(accepted) })
    }
    private init(snapshot: OfflineSnapshot, store: AtomicSnapshotStore, provider: ScopedMessageKeyProvider,
                 session: SessionLifecycle, operation: SessionOperation, expectedKeyID: UUID,
                 validateOriginal: @escaping () throws -> Void) throws {
        self.snapshot = snapshot; self.store = store; self.validateOriginal = validateOriginal
        let lifetime = UUID()
        access = try CanonicalSnapshotAccess(store: store, provider: provider, session: session,
            sessionOperation: operation, namespace: snapshot.metadata.namespace, expectedKeyID: expectedKeyID,
            sourceToken: lifetime, currentSource: {
                do { try validateOriginal(); return lifetime } catch { return nil }
            })
    }
    func writeOnce() throws -> Receipt {
        try store.requireNoPendingWrite() // before any new attempt, lookup or nonce generation
        guard !attempted else { throw OfflineFailure.unavailable }
        // Reserve before source validation: Trip's host binding callback can reenter.
        // Never release this one-attempt reservation, including failed validation.
        attempted = true
        try validateOriginal() // also covers a consumer await between construction and write
        try access.write(snapshot)
        return Receipt(version: snapshot.version, responseHash: snapshot.metadata.responseHash, syncedAt: snapshot.syncedAt)
    }
    func reconcileOriginalWrite() throws -> AtomicSnapshotStore.Settlement {
        guard attempted else { throw OfflineFailure.unavailable }
        return try access.reconcileOriginalWrite()
    }
}
