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

/// Minimal local-only metadata. Neither type is a server-history or sending authority.
public struct LocalActionReference: Sendable {
    public let messageID: String
    public let phase: ActionPhase
}

public struct LocalDraftReference: Sendable {
    public let conversationID: String
}

/// Unordered in-memory projection; not Codable and not valid after a lease change.
/// Caller must revalidate after every await before display or further local use.
public struct LocalRecoveryProjection: Sendable {
    public let actions: [LocalActionReference]
    public let drafts: [LocalDraftReference]
    fileprivate let lease: Lease
}

public struct DraftSaveRecord: Codable, Sendable {
    public let conversationID: String
    public let generation: String
    public let expectedRevision: Int64
    public let originalUTF8: Data
    fileprivate let editorRevision: UUID?
    public fileprivate(set) var confirmedRevision: Int64?
}
public struct DraftSaveOperation: Sendable {
    fileprivate let lease: Lease
    fileprivate let key: String
    fileprivate let nonce: UUID
}

public struct Snapshot: Codable, Sendable {
    var version = 1
    var actions: [String: ActionRecord] = [:]
    var drafts: [String: Data] = [:]
    var draftEdits: [String: UUID] = [:]
    var draftSaves: [String: DraftSaveRecord] = [:]
    enum CodingKeys: String, CodingKey { case version, actions, drafts, draftEdits, draftSaves }
    init() { }
    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(Int.self, forKey: .version)
        actions = try c.decode([String:ActionRecord].self, forKey: .actions)
        drafts = try c.decode([String:Data].self, forKey: .drafts)
        // Older local snapshots predate any PUT capability; no pending PUT can be lost.
        draftEdits = try c.decodeIfPresent([String:UUID].self, forKey: .draftEdits) ?? [:]
        draftSaves = try c.decodeIfPresent([String:DraftSaveRecord].self, forKey: .draftSaves) ?? [:]
    }
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
    private var activationGeneration = UUID()
    private var lease: Lease?
    private var scope: StorageScope?
    private var snapshot = Snapshot()
    private var operations: [String: Operation] = [:]
    private var draftOperations: [String: UUID] = [:]
    // Never Codable or stored in Snapshot. Consumed before any storage callback.
    private struct FreshAuthorization {
        let lease: Lease
        let digest: String
    }
    private var fresh: [String: FreshAuthorization] = [:]
    // Process-local denial memory only, not a durable authority or external ledger.
    // Survives coordinator replacement/account switching; no API clears it.
    private static var observed: [Data: Set<String>] = [:]

    public init(storage: any SecureMessageStorage) { self.storage = storage }

    public func activate(_ scope: StorageScope) throws -> Lease {
        invalidate()
        let requestedGeneration = activationGeneration
        var restored = try storage.load(scope: scope) ?? Snapshot()
        // A synchronous dependency may activate another account or invalidate us.
        // Check before touching restored data, observed IDs, scope or the new lease.
        guard activationGeneration == requestedGeneration else { throw RecoveryError.inactive }
        guard restored.version == 1 else { throw RecoveryError.invalidSnapshot }
        for (key, record) in restored.actions {
            guard key == Self.key(record.messageID), !record.messageID.isEmpty,
                  String(data: record.originalUTF8, encoding: .utf8) != nil,
                  (record.phase == .accepted) == (record.receipt != nil) else {
                throw RecoveryError.invalidSnapshot
            }
        }
        for (key, record) in restored.draftSaves {
            guard key == Self.key(record.conversationID), !record.conversationID.isEmpty, !record.generation.isEmpty,
                  record.expectedRevision >= 0, record.expectedRevision < Int64.max,
                  String(data:record.originalUTF8,encoding:.utf8) != nil,
                  record.confirmedRevision == nil || record.confirmedRevision == record.expectedRevision + 1 else { throw RecoveryError.invalidSnapshot }
        }
        // Authentic ciphertext does not prove freshness. Every loaded staged action
        // is ambiguous (including one that never left the device): query only.
        for key in restored.actions.keys {
            if restored.actions[key]?.phase == .staged { restored.actions[key]?.phase = .queryRequired }
        }
        for record in restored.actions.values {
            Self.remember(record.messageID, digest: record.inputSHA256, scope: scope)
        }
        let next = Lease(instance: instance, generation: UUID())
        self.scope = scope; snapshot = restored; lease = next
        return next
    }

    /// Immediate local fence; does not claim remote logout/deletion or erase recovery data.
    public func invalidate() {
        activationGeneration = UUID()
        lease = nil; scope = nil; snapshot = Snapshot(); operations = [:]; draftOperations = [:]; fresh = [:]
    }

    public func validateScope(_ expected: StorageScope, lease: Lease) throws {
        try check(lease)
        guard scope?.binding == expected.binding else { throw RecoveryError.inactive }
    }

    public func localProjection(scope: StorageScope, lease: Lease) throws -> LocalRecoveryProjection {
        try validateScope(scope, lease: lease)
        // No storage calls/awaits or mutations: enumeration cannot refresh identity,
        // mint fresh authorization, acknowledge a message or rewrite a snapshot.
        let drafts = try Set(snapshot.drafts.keys).union(snapshot.draftSaves.keys).map { encoded -> LocalDraftReference in
            guard let bytes = Data(base64Encoded: encoded),
                  let id = String(data: bytes, encoding: .utf8), !id.isEmpty,
                  Self.key(id) == encoded else { throw RecoveryError.invalidSnapshot }
            return LocalDraftReference(conversationID: id)
        }
        let actions = snapshot.actions.values.map {
            LocalActionReference(messageID: $0.messageID, phase: $0.phase)
        }
        return LocalRecoveryProjection(actions: actions, drafts: drafts, lease: lease)
    }

    public func validateProjection(_ projection: LocalRecoveryProjection, scope: StorageScope, lease: Lease) throws {
        try validateScope(scope, lease: lease)
        guard projection.lease == lease else { throw RecoveryError.inactive }
    }

    public func saveDraft(_ bytes: Data, conversationID: String, lease: Lease) throws {
        try check(lease)
        guard !conversationID.isEmpty, String(data: bytes, encoding: .utf8) != nil else { throw RecoveryError.invalidInput }
        var next = snapshot; next.drafts[Self.key(conversationID)] = bytes
        next.draftEdits[Self.key(conversationID)] = UUID()
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
        guard let scope else { throw RecoveryError.inactive }
        let record = ActionRecord(messageID: messageID, originalUTF8: originalUTF8, phase: .staged)
        let seen = Self.observed[scope.binding] ?? []
        guard !seen.contains("id:" + key), !seen.contains("body:" + record.inputSHA256) else {
            throw RecoveryError.queryOnly
        }
        // Reserve before save: an unknown save or reentrant caller cannot mint again.
        Self.remember(messageID, digest: record.inputSHA256, scope: scope)
        var next = snapshot; next.actions[key] = record
        try persist(next)
        fresh[key] = FreshAuthorization(lease: lease, digest: record.inputSHA256)
    }

    public func draftSave(conversationID: String, lease: Lease) throws -> DraftSaveRecord? {
        try check(lease); return snapshot.draftSaves[Self.key(conversationID)]
    }

    public func beginDraftSave(conversationID: String, generation: String, expectedRevision: Int64, originalUTF8: Data, lease: Lease) throws -> DraftSaveOperation {
        try check(lease)
        guard !conversationID.isEmpty, !generation.isEmpty, expectedRevision >= 0, expectedRevision < Int64.max,
              String(data: originalUTF8, encoding: .utf8) != nil else { throw RecoveryError.invalidInput }
        let key = Self.key(conversationID)
        guard draftOperations[key] == nil else { throw RecoveryError.queryOnly }
        if let old = snapshot.draftSaves[key] {
            guard old.confirmedRevision == expectedRevision, Data(old.generation.utf8) == Data(generation.utf8) else { throw RecoveryError.queryOnly }
        }
        var next = snapshot
        next.draftSaves[key] = DraftSaveRecord(conversationID:conversationID,generation:generation,
            expectedRevision:expectedRevision,originalUTF8:originalUTF8,editorRevision:snapshot.draftEdits[key])
        let nonce = UUID(); draftOperations[key] = nonce
        try persist(next)
        return DraftSaveOperation(lease:lease,key:key,nonce:nonce)
    }

    public func draftConfirmationMatchesEditor(conversationID: String, revision: Int64, lease: Lease) throws -> Bool {
        try check(lease)
        let key = Self.key(conversationID)
        guard let record = snapshot.draftSaves[key], record.confirmedRevision == revision else { return false }
        return record.editorRevision == snapshot.draftEdits[key] && record.originalUTF8 == snapshot.drafts[key]
    }

    /// Confirms only this PUT's original CAS response; never changes editor contents.
    public func confirmDraftSave(_ operation: DraftSaveOperation, conversationID: String, generation: String,
                                 revision: Int64, originalUTF8: Data) throws -> Bool {
        try check(operation.lease)
        guard draftOperations[operation.key] == operation.nonce,
              var record = snapshot.draftSaves[operation.key] else { throw RecoveryError.staleOperation }
        guard Self.key(conversationID) == operation.key, Data(generation.utf8) == Data(record.generation.utf8),
              revision == record.expectedRevision + 1, originalUTF8 == record.originalUTF8 else { throw RecoveryError.receiptMismatch }
        let matchesEditor = snapshot.draftEdits[operation.key] == record.editorRevision && snapshot.drafts[operation.key] == originalUTF8
        record.confirmedRevision = revision
        var next = snapshot; next.draftSaves[operation.key] = record
        try persist(next); draftOperations.removeValue(forKey:operation.key)
        return matchesEditor
    }

    public func action(messageID: String, lease: Lease) throws -> ActionRecord? {
        try check(lease); return snapshot.actions[Self.key(messageID)]
    }

    public func beginSubmission(messageID: String, lease: Lease) throws -> Submission {
        try check(lease)
        let key = Self.key(messageID)
        guard var record = snapshot.actions[key] else { throw RecoveryError.invalidInput }
        guard record.phase == .staged, let authorization = fresh[key],
              authorization.lease == lease, authorization.digest == record.inputSHA256 else {
            throw RecoveryError.queryOnly
        }
        fresh.removeValue(forKey: key) // BEFORE persist can invoke an injected callback.
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
    private static func remember(_ id: String, digest: String, scope: StorageScope) {
        observed[scope.binding, default: []].formUnion(["id:" + key(id), "body:" + digest])
    }
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
        guard let scope, let originalLease = lease else { throw RecoveryError.inactive }
        do { try storage.save(next, scope: scope) }
        catch {
            // Atomic rename may have succeeded before an I/O error. Reopen/read before
            // doing anything else; do not retry or keep an in-memory success illusion.
            if lease == originalLease { invalidate() }
            throw RecoveryError.persistenceUnknown
        }
        // Sync dependency callbacks can reenter; never overwrite a newly activated scope.
        try check(originalLease)
        snapshot = next
    }
}
