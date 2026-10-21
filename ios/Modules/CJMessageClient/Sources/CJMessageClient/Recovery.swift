import Foundation
import CryptoKit

public enum RecoveryError: Error {
    case inactive, staleOperation, invalidInput, inputConflict, queryOnly
    case receiptMismatch, persistenceUnknown, invalidSnapshot, keyUnavailable, unsafeDirectory, legacyStorageFormat, keyMismatch
}

/// Host-provided local partition, not an authentication or authorization assertion.
public struct StorageScope: Codable, Sendable {
    public let environment: String
    public let account: String
    public init(environment: String, account: String) throws {
        guard !environment.isEmpty, !account.isEmpty else { throw RecoveryError.invalidInput }
        self.environment = environment; self.account = account
    }
    var binding: Data {
        var result = Data("CJMessageClient-storage-v1".utf8)
        for value in [environment, account] {
            let bytes = Data(value.utf8)
            var count = UInt64(bytes.count).bigEndian
            withUnsafeBytes(of: &count) { result.append(contentsOf: $0) }
            result.append(bytes)
        }
        return result
    }
}

public struct Lease: Equatable, Sendable {
    fileprivate let instance: UUID
    fileprivate let generation: UUID
}

public enum ActionPhase: String, Codable, Sendable {
    case staged, queryRequired, notObserved, accepted
}

public struct ActionRecord: Codable, Sendable {
    public let messageID: String
    public let originalUTF8: Data
    public fileprivate(set) var phase: ActionPhase
    /// Opaque transport-verified receipt bytes, not a second wire schema.
    public fileprivate(set) var receipt: Data?
    public var inputSHA256: String { SHA256.hash(data: originalUTF8).map { String(format: "%02x", $0) }.joined() }
}

public struct Snapshot: Codable, Sendable {
    var version = 1
    var actions: [String: ActionRecord] = [:]
    var drafts: [String: Data] = [:]
}

/// A save must replace the encrypted snapshot atomically; failure is an unknown write.
/// Single writer per directory/partition; no in-memory/default storage fallback.
@MainActor public protocol SecureMessageStorage: AnyObject {
    func load(scope: StorageScope) throws -> Snapshot?
    func save(_ snapshot: Snapshot, scope: StorageScope) throws
}

public struct Operation: Equatable, Sendable {
    fileprivate let lease: Lease
    fileprivate let actionKey: String
    fileprivate let nonce: UUID
    fileprivate let isQuery: Bool
    public let messageID: String
}

public struct Submission: Sendable {
    public let operation: Operation
    public let originalUTF8: Data
}

/// Synchronous state transitions contain no await/reentrancy points. Caller captures an
/// Operation before async transport and presents it after await; only current binding wins.
@MainActor public final class MessageRecovery {
    private let storage: any SecureMessageStorage
    private let instance = UUID()
    private var lease: Lease?
    private var scope: StorageScope?
    private var snapshot = Snapshot()
    private var operations: [String: Operation] = [:]

    public init(storage: any SecureMessageStorage) { self.storage = storage }

    public func activate(_ scope: StorageScope) throws -> Lease {
        invalidate()
        var restored = try storage.load(scope: scope) ?? Snapshot()
        guard restored.version == 1 else { throw RecoveryError.invalidSnapshot }
        for (key, record) in restored.actions {
            guard key == Self.key(record.messageID), !record.messageID.isEmpty,
                  String(data: record.originalUTF8, encoding: .utf8) != nil,
                  (record.phase == .accepted) == (record.receipt != nil) else {
                throw RecoveryError.invalidSnapshot
            }
        }
        // Authentic ciphertext does not prove freshness. Every loaded staged action
        // is ambiguous (including one that never left the device): query only.
        for key in restored.actions.keys {
            if restored.actions[key]?.phase == .staged { restored.actions[key]?.phase = .queryRequired }
        }
        let next = Lease(instance: instance, generation: UUID())
        self.scope = scope; snapshot = restored; lease = next
        return next
    }

    /// Immediate local fence; does not claim remote logout/deletion or erase recovery data.
    public func invalidate() {
        lease = nil; scope = nil; snapshot = Snapshot(); operations = [:]
    }

    public func validateScope(_ expected: StorageScope, lease: Lease) throws {
        try check(lease)
        guard scope?.binding == expected.binding else { throw RecoveryError.inactive }
    }

    public func saveDraft(_ bytes: Data, conversationID: String, lease: Lease) throws {
        try check(lease)
        guard !conversationID.isEmpty, String(data: bytes, encoding: .utf8) != nil else { throw RecoveryError.invalidInput }
        var next = snapshot; next.drafts[Self.key(conversationID)] = bytes
        try persist(next)
    }

    public func draft(conversationID: String, lease: Lease) throws -> Data? {
        try check(lease); return snapshot.drafts[Self.key(conversationID)]
    }

    /// Caller supplies the once-encoded original body/ID. This does not validate the
    /// server wire schema; the later generated transport owns wire validation.
    public func stage(messageID: String, originalUTF8: Data, lease: Lease) throws {
        try check(lease)
        guard !messageID.isEmpty, !originalUTF8.isEmpty,
              String(data: originalUTF8, encoding: .utf8) != nil else { throw RecoveryError.invalidInput }
        let key = Self.key(messageID)
        if let old = snapshot.actions[key] {
            guard old.originalUTF8 == originalUTF8 else { throw RecoveryError.inputConflict }
            return
        }
        // Re-keying the same original body cannot evade an unresolved original action.
        guard !snapshot.actions.values.contains(where: { $0.originalUTF8 == originalUTF8 }) else {
            throw RecoveryError.inputConflict
        }
        var next = snapshot
        next.actions[key] = ActionRecord(messageID: messageID, originalUTF8: originalUTF8, phase: .staged)
        try persist(next)
    }

    public func action(messageID: String, lease: Lease) throws -> ActionRecord? {
        try check(lease); return snapshot.actions[Self.key(messageID)]
    }

    public func beginSubmission(messageID: String, lease: Lease) throws -> Submission {
        try check(lease)
        let key = Self.key(messageID)
        guard var record = snapshot.actions[key] else { throw RecoveryError.invalidInput }
        guard record.phase == .staged else { throw RecoveryError.queryOnly }
        // Persist uncertainty BEFORE handing any bytes to transport. A crash here must
        // recover by query even if the actual POST never started.
        record.phase = .queryRequired
        var next = snapshot; next.actions[key] = record
        try persist(next)
        return Submission(operation: issue(key, record.messageID, lease, false), originalUTF8: record.originalUTF8)
    }

    public func beginQuery(messageID: String, lease: Lease) throws -> Operation {
        try check(lease)
        let key = Self.key(messageID)
        guard let record = snapshot.actions[key], record.phase == .queryRequired || record.phase == .notObserved else {
            throw RecoveryError.queryOnly
        }
        return issue(key, record.messageID, lease, true)
    }

    public func observeUnknown(_ operation: Operation) throws {
        try complete(operation, phase: .queryRequired, receipt: nil)
    }

    public func observeNotObserved(_ operation: Operation) throws {
        guard operation.isQuery else { throw RecoveryError.invalidInput }
        try complete(operation, phase: .notObserved, receipt: nil)
    }

    /// Adapter must first verify/decode the generated wire receipt, then pass its original
    /// ID/digest and opaque payload. No receipt construction or endpoint is defined here.
    public func observeReceipt(_ operation: Operation, messageID: String, inputSHA256: String, receipt: Data) throws {
        try checkOperation(operation)
        guard let record = snapshot.actions[operation.actionKey],
              Self.key(messageID) == operation.actionKey, inputSHA256 == record.inputSHA256,
              !receipt.isEmpty else { throw RecoveryError.receiptMismatch }
        try complete(operation, phase: .accepted, receipt: receipt)
    }

    private static func key(_ id: String) -> String { Data(id.utf8).base64EncodedString() }
    private func check(_ expected: Lease) throws {
        guard lease == expected, scope != nil else { throw RecoveryError.inactive }
    }
    private func checkOperation(_ operation: Operation) throws {
        try check(operation.lease)
        guard operations[operation.actionKey] == operation else { throw RecoveryError.staleOperation }
    }
    private func issue(_ key: String, _ id: String, _ lease: Lease, _ query: Bool) -> Operation {
        let operation = Operation(lease: lease, actionKey: key, nonce: UUID(), isQuery: query, messageID: id)
        operations[key] = operation; return operation
    }
    private func complete(_ operation: Operation, phase: ActionPhase, receipt: Data?) throws {
        try checkOperation(operation)
        guard var record = snapshot.actions[operation.actionKey] else { throw RecoveryError.staleOperation }
        record.phase = phase; record.receipt = receipt
        var next = snapshot; next.actions[operation.actionKey] = record
        try persist(next)
        operations.removeValue(forKey: operation.actionKey)
    }
    private func persist(_ next: Snapshot) throws {
        guard let scope else { throw RecoveryError.inactive }
        do { try storage.save(next, scope: scope) }
        catch {
            // Atomic rename may have succeeded before an I/O error. Reopen/read before
            // doing anything else; do not retry or keep an in-memory success illusion.
            invalidate(); throw RecoveryError.persistenceUnknown
        }
        snapshot = next
    }
}
