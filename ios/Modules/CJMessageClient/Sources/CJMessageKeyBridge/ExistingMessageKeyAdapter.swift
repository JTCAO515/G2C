import Foundation
import CJMessageClient
import CJMessageKeys

/// Host explicitly maps a verified local storage partition to the official namespace.
/// Only reads existing keys. No create/clear/reconcile/rotation or session-material path.
@MainActor public final class ExistingMessageKeyAdapter: CJMessageClient.MessageEncryptionKeyProvider {
    private let provider: any CJMessageKeys.MessageEncryptionKeyProvider
    private let scope: StorageScope
    private let namespace: MessageKeyNamespace
    private var active = true
    public init(provider: any CJMessageKeys.MessageEncryptionKeyProvider, scope: StorageScope,
                namespace: MessageKeyNamespace) throws {
        guard provider.namespace == namespace else { throw MessageKeyFailure.invalidConfiguration }
        self.provider = provider; self.scope = scope; self.namespace = namespace
    }
    public func existing(for requested: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? {
        guard active, Data(requested.environment.utf8) == Data(scope.environment.utf8),
              Data(requested.account.utf8) == Data(scope.account.utf8), provider.namespace == namespace else {
            throw MessageKeyFailure.inactiveNamespace
        }
        let operation = try provider.begin(.lookup)
        guard provider.isCurrent(operation) else { throw MessageKeyFailure.staleOperation }
        let key = try provider.existing(expectedID: expectedID, for: operation)
        guard active, provider.isCurrent(operation) else { throw MessageKeyFailure.staleOperation }
        guard let key else { return nil }
        guard key.namespace == namespace, expectedID == nil || key.id == expectedID else { throw MessageKeyFailure.keyMismatch }
        return key.withSymmetricKey { MessageStorageKey(id: key.id, key: $0) }
    }
    /// Host also invalidates MessageRecovery immediately on lifecycle/clear failure.
    public func invalidate() { active = false; provider.invalidate() }
}
