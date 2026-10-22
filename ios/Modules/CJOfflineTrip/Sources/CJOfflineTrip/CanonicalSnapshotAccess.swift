import Foundation
import CJMessageKeys
import CJSession

/// Module-only composition. No App factory, accepted-source constructor, or key creation.
/// The host source token is a lifetime fence, not server acceptance or offline authorization.
@MainActor final class CanonicalSnapshotAccess {
    private let store: AtomicSnapshotStore
    private let provider: ScopedMessageKeyProvider
    private let session: SessionLifecycle
    private let sessionOperation: SessionOperation
    private let namespace: OfflineNamespace
    private let expectedKeyID: UUID
    private let sourceToken: UUID
    private let currentSource: () -> UUID?
    private var active = true
    private var inFlight = false

    init(store: AtomicSnapshotStore, provider: ScopedMessageKeyProvider, session: SessionLifecycle,
         sessionOperation: SessionOperation, namespace: OfflineNamespace, expectedKeyID: UUID,
         sourceToken: UUID, currentSource: @escaping () -> UUID?) throws {
        self.store = store; self.provider = provider; self.session = session
        self.sessionOperation = sessionOperation; self.namespace = namespace
        self.expectedKeyID = expectedKeyID; self.sourceToken = sourceToken; self.currentSource = currentSource
        try checkConcrete()
    }
    func invalidate() { active = false }
    private func beginOperation() throws {
        guard !inFlight else { throw OfflineFailure.unavailable }
        inFlight = true
    }

    private var keyNamespace: MessageKeyNamespace {
        .init(environment: namespace.backend, account: namespace.account, purpose: .localOfflineTripSnapshotV1)
    }
    // All methods/properties here are concrete canonical owner APIs: no persistence/host callback.
    private func checkConcrete(operation: MessageKeyOperation? = nil) throws {
        guard active, session.isCurrent(sessionOperation), provider.namespace == keyNamespace else {
            throw OfflineFailure.unavailable
        }
        if let operation, !provider.isCurrent(operation) { throw OfflineFailure.keyUnavailable }
    }
    private func existingKey() throws -> (MessageEncryptionKey, MessageKeyOperation) {
        try checkConcrete()
        do {
            let operation = try provider.begin(.lookup)
            guard let key = try provider.existing(expectedID: expectedKeyID, for: operation),
                  key.id == expectedKeyID, key.namespace == keyNamespace else { throw OfflineFailure.keyUnavailable }
            try checkConcrete(operation: operation)
            return (key, operation)
        } catch {
            // Storage errors may carry platform details; do not expose key material or retry/create.
            try checkConcrete()
            throw OfflineFailure.keyUnavailable
        }
    }
    /// The last external callback returns before concrete lifetime/key checks and exact file check.
    private func finishCallback(operation: MessageKeyOperation, original: Data?) throws {
        let observed = currentSource()
        try checkConcrete(operation: operation)
        guard observed == sourceToken else { throw OfflineFailure.unavailable }
        guard try store.read() == original else { throw OfflineFailure.corrupt }
        try checkConcrete(operation: operation)
    }
    func read(minimumVersion: Int64) throws -> OfflineSnapshot? {
        try beginOperation(); defer { inFlight = false }
        try checkConcrete()
        try store.requireNoPendingWrite()
        let original = try store.read()
        let (key, operation) = try existingKey()
        let snapshot = try original.map { raw in
            try key.withSymmetricKey {
                try SnapshotCodec.open(raw, namespace: namespace, key: $0,
                                       expectedKeyID: expectedKeyID, minimumVersion: minimumVersion)
            }
        }
        try finishCallback(operation: operation, original: original)
        // Still internal: host must evaluate explicit offline policy/trusted clock before display.
        return snapshot
    }
    func write(_ snapshot: OfflineSnapshot) throws {
        try beginOperation(); defer { inFlight = false }
        try checkConcrete()
        try store.requireNoPendingWrite()
        guard snapshot.metadata.namespace == namespace, snapshot.metadata.keyID == expectedKeyID else {
            throw OfflineFailure.wrongNamespace
        }
        let original = try store.read()
        let (key, operation) = try existingKey()
        try store.requireNoPendingWrite()
        let sealed = try key.withSymmetricKey { try SnapshotCodec.seal(snapshot, key: $0) }
        try finishCallback(operation: operation, original: original)
        try store.write(sealed)
        // No callbacks occur in the production store; tests can inject a post-rename fault/callback.
        try finishCallback(operation: operation, original: sealed)
    }
    func reconcileOriginalWrite() throws -> AtomicSnapshotStore.Settlement {
        try beginOperation(); defer { inFlight = false }
        try checkConcrete()
        let original = try store.read()
        let (_, operation) = try existingKey()
        try finishCallback(operation: operation, original: original)
        // Only retained exact attempted/original ciphertext is compared; never reseal or write.
        return store.reconcileOriginalWrite()
    }
}
