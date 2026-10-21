import Foundation
import Security

struct MessageKeyRecord: Equatable {
    let id: UUID
    let bytes: Data
}
@MainActor protocol MessageKeyPersistence {
    func read() throws -> MessageKeyRecord?
    func add(_ record: MessageKeyRecord) throws
    func remove(expectedID: UUID) throws
}

func platformMessageKeyBytes() throws -> Data {
    var bytes = [UInt8](repeating: 0, count: 32)
    let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    guard status == errSecSuccess else { throw MessageKeyFailure.random(status) }
    return Data(bytes)
}

@MainActor public final class ScopedMessageKeyProvider: MessageEncryptionKeyProvider {
    public static let interfaceVersion = "CJ-MESSAGE-KEYS@0.1.0-rc.1"
    public let namespace: MessageKeyNamespace
    private let persistence: any MessageKeyPersistence
    private let randomBytes: () throws -> Data
    private let instance = UUID()
    private var generation = UUID()
    private var active = true
    private var current: MessageKeyOperation?
    private var consumed = false
    private var uncertainCreation: MessageKeyRecord?
    private var uncertainClear: UUID?
    public var canUseRestrictedBusiness: Bool { false }

    init(namespace: MessageKeyNamespace, persistence: any MessageKeyPersistence,
         randomBytes: @escaping () throws -> Data = platformMessageKeyBytes) {
        self.namespace = namespace; self.persistence = persistence; self.randomBytes = randomBytes
    }
    public func begin(_ action: MessageKeyAction) throws -> MessageKeyOperation {
        guard active else { throw MessageKeyFailure.inactiveNamespace }
        let operation = MessageKeyOperation(instance: instance, generation: generation, action: action)
        current = operation; consumed = false
        return operation
    }
    public func isCurrent(_ operation: MessageKeyOperation) -> Bool { active && current == operation }
    private func consume(_ operation: MessageKeyOperation, action: MessageKeyAction) throws {
        guard isCurrent(operation), !consumed,
              operation.belongs(to: instance, generation: generation, action: action) else { throw MessageKeyFailure.staleOperation }
        consumed = true
    }
    private func permitMutation(_ storageState: EncryptedStorageState) throws {
        guard storageState == .confirmedEmpty else { throw MessageKeyFailure.storageNotConfirmedEmpty }
        guard uncertainCreation == nil else { throw MessageKeyFailure.creationUnconfirmed }
        guard uncertainClear == nil else { throw MessageKeyFailure.clearUnconfirmed }
    }
    private func key(_ record: MessageKeyRecord) throws -> MessageEncryptionKey {
        try MessageEncryptionKey(id: record.id, namespace: namespace, bytes: record.bytes)
    }
    public func existing(expectedID: UUID?, for operation: MessageKeyOperation) throws -> MessageEncryptionKey? {
        try consume(operation, action: .lookup)
        guard uncertainCreation == nil else { throw MessageKeyFailure.creationUnconfirmed }
        guard uncertainClear == nil else { throw MessageKeyFailure.clearUnconfirmed }
        guard let record = try persistence.read() else { return nil }
        if let expectedID, record.id != expectedID { throw MessageKeyFailure.keyMismatch }
        return try key(record)
    }
    public func create(storageState: EncryptedStorageState, for operation: MessageKeyOperation) throws -> MessageEncryptionKey {
        try consume(operation, action: .create)
        try permitMutation(storageState)
        guard try persistence.read() == nil else { throw MessageKeyFailure.alreadyExists }
        let record = MessageKeyRecord(id: UUID(), bytes: try randomBytes())
        let candidate = try key(record) // validates 256-bit material before any write
        uncertainCreation = record
        try persistence.add(record) // only add; never replace on duplicate/unknown
        uncertainCreation = nil
        return candidate
    }
    public func reconcileCreation(for operation: MessageKeyOperation) throws -> MessageEncryptionKey {
        try consume(operation, action: .reconcileCreation)
        guard let original = uncertainCreation else { throw MessageKeyFailure.creationUnconfirmed }
        guard let observed = try persistence.read() else { throw MessageKeyFailure.creationUnconfirmed }
        guard observed == original else { throw MessageKeyFailure.keyMismatch }
        uncertainCreation = nil
        return try key(observed)
    }
    public func clear(expectedID: UUID, storageState: EncryptedStorageState, for operation: MessageKeyOperation) throws {
        try consume(operation, action: .clear)
        try permitMutation(storageState)
        guard let original = try persistence.read() else { return }
        guard original.id == expectedID else { throw MessageKeyFailure.keyMismatch }
        uncertainClear = expectedID
        try persistence.remove(expectedID: expectedID)
        uncertainClear = nil
    }
    public func reconcileClear(for operation: MessageKeyOperation) throws -> Bool {
        try consume(operation, action: .reconcileClear)
        guard let expected = uncertainClear else { throw MessageKeyFailure.clearUnconfirmed }
        guard let observed = try persistence.read() else { uncertainClear = nil; return true }
        guard observed.id == expected else { throw MessageKeyFailure.keyMismatch }
        return false // original remains; no hidden deletion retry or key regeneration
    }
    public func invalidate() {
        active = false; generation = UUID(); current = nil
        // No deletion: account switch must not destroy another account's encrypted data.
        uncertainCreation = nil
    }
}
