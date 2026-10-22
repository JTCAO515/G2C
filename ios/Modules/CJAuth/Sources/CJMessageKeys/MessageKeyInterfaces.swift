import Foundation
import CryptoKit

public enum MessageKeyPurpose: String, Sendable { case localMessageStorageV1 = "local-message-storage-v1" }
public struct MessageKeyNamespace: Equatable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let purpose: MessageKeyPurpose
    public init(environment: UUID, account: UUID, purpose: MessageKeyPurpose) {
        self.environment = environment; self.account = account; self.purpose = purpose
    }
    public var service: String { "G2C.CJAuth.message-key.\(environment.uuidString)" }
    public var slot: String { "\(account.uuidString).\(purpose.rawValue)" }
}

public enum MessageKeyFailure: Error, Equatable, Sendable {
    case invalidConfiguration, malformedRecord, staleOperation, inactiveNamespace
    case storageNotConfirmedEmpty, alreadyExists, creationUnconfirmed, clearUnconfirmed, keyMismatch
    case storageUnavailable, rotationUnsupported
    case keychain(Int32), random(Int32)
}
public enum EncryptedStorageState: Sendable { case confirmedEmpty, containsCiphertext, unknown }
public enum MessageKeyAction: Sendable { case lookup, create, reconcileCreation, clear, reconcileClear }
public struct MessageKeyOperation: Equatable, Sendable {
    fileprivate let instance: UUID
    fileprivate let generation: UUID
    fileprivate let id = UUID()
    fileprivate let action: MessageKeyAction
    init(instance: UUID, generation: UUID, action: MessageKeyAction) {
        self.instance = instance; self.generation = generation; self.action = action
    }
    func belongs(to instance: UUID, generation: UUID, action: MessageKeyAction) -> Bool {
        self.instance == instance && self.generation == generation && self.action == action
    }
}

/// No public raw-byte/session-token constructor, Codable or raw-key property.
public struct MessageEncryptionKey: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let id: UUID
    public let namespace: MessageKeyNamespace
    private let key: SymmetricKey
    init(id: UUID, namespace: MessageKeyNamespace, bytes: Data) throws {
        guard bytes.count == 32 else { throw MessageKeyFailure.malformedRecord }
        self.id = id; self.namespace = namespace; key = SymmetricKey(data: bytes)
    }
    public func withSymmetricKey<T>(_ use: (SymmetricKey) throws -> T) rethrows -> T { try use(key) }
    public var description: String { "<redacted message encryption key>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

@MainActor public protocol MessageEncryptionKeyProvider: AnyObject {
    var namespace: MessageKeyNamespace { get }
    func begin(_ action: MessageKeyAction) throws -> MessageKeyOperation
    func isCurrent(_ operation: MessageKeyOperation) -> Bool
    func existing(expectedID: UUID?, for operation: MessageKeyOperation) throws -> MessageEncryptionKey?
    func create(storageState: EncryptedStorageState, for operation: MessageKeyOperation) throws -> MessageEncryptionKey
    func reconcileCreation(for operation: MessageKeyOperation) throws -> MessageEncryptionKey
    func clear(expectedID: UUID, storageState: EncryptedStorageState, for operation: MessageKeyOperation) throws
    func reconcileClear(for operation: MessageKeyOperation) throws -> Bool
    func invalidate()
}
