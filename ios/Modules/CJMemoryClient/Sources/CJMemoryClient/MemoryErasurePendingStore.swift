import Foundation
import CryptoKit
import CJMessageKeys

struct MemoryErasurePending: MemoryJournalRecord, Sendable {
    let actionID: String
    let itemID: String
    let expectedVersion: Int64
    let originalUTF8: Data
    let expectedSHA256: String
    var journalID: String { actionID }
    init(_ action: MemoryErasureAction) {
        actionID = action.actionID; itemID = action.itemID; expectedVersion = action.expectedVersion
        originalUTF8 = action.originalUTF8; expectedSHA256 = action.inputSHA256
    }
    func action() throws -> MemoryErasureAction { try .init(originalUTF8: originalUTF8) }
    func validate() throws {
        let command = try action()
        guard same(command.actionID, actionID), same(command.itemID, itemID), command.expectedVersion == expectedVersion,
              same(command.inputSHA256, expectedSHA256) else { throw MemoryFailure.invalidResponse }
    }
}

/// Immutable first-server association. Changing progress is deliberately absent
/// so a later GET can advance steps without rewriting this original identity.
struct MemoryErasureObservation: MemoryJournalRecord, Sendable {
    let actionID: String
    let requestSHA256: String
    let operationID: String
    let itemVersion: Int64
    let scopeEpoch: Int64
    let originalUTF8: Data
    let expectedSHA256: String
    var journalID: String { actionID }
    init(original: MemoryErasurePending, progress: MemoryErasureProgress) throws {
        actionID = progress.actionID; requestSHA256 = original.expectedSHA256; operationID = progress.operationID
        itemVersion = progress.stoppedItemVersion; scopeEpoch = progress.scopeEpoch
        originalUTF8 = try JSONSerialization.data(withJSONObject: ["version": "CJMemoryErasureObservationV1",
            "action_id": actionID, "input_sha256": requestSHA256, "operation_id": operationID,
            "item_version": itemVersion, "scope_epoch": scopeEpoch], options: [.sortedKeys, .withoutEscapingSlashes])
        expectedSHA256 = digest(originalUTF8)
    }
    func validate() throws {
        var parser = StrictMemoryJSON(bytes: Array(originalUTF8))
        let fields = try historyObject(parser.document(), fields: ["version", "action_id", "input_sha256", "operation_id", "item_version", "scope_epoch"])
        guard same(expectedSHA256, digest(originalUTF8)),
              try historyString(fields["version"], limit: 64) == "CJMemoryErasureObservationV1",
              same(try erasureIdentifier(fields["action_id"]), actionID),
              same(try historyString(fields["input_sha256"], limit: 64), requestSHA256),
              same(try historyString(fields["operation_id"], limit: 128), operationID), validErasureOperationID(operationID),
              try historyInteger(fields["item_version"]) == itemVersion, itemVersion > 0,
              try historyInteger(fields["scope_epoch"]) == scopeEpoch, scopeEpoch > 0 else { throw MemoryFailure.invalidResponse }
    }
    func check(_ original: MemoryErasurePending, progress: MemoryErasureProgress? = nil) throws {
        let (next, overflow) = original.expectedVersion.addingReportingOverflow(1)
        guard same(actionID, original.actionID), same(requestSHA256, original.expectedSHA256),
              !overflow, itemVersion == next else { throw MemoryFailure.storageUnavailable }
        if let progress {
            guard same(progress.actionID, actionID), same(progress.operationID, operationID),
                  progress.stoppedItemVersion == itemVersion, progress.scopeEpoch == scopeEpoch else { throw MemoryFailure.invalidResponse }
        }
    }
}

/// No App directory is provisioned here. Root/observation coverage must be
/// supplied by an additive device version before actual App activation.
@MainActor public final class MemoryErasurePendingStore {
    private let storage: MemoryEncryptedRecords<MemoryErasurePending>
    typealias Durability = MemoryEncryptedRecords<MemoryErasurePending>.Durability
    public init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            binding: binding, expectedKeyID: expectedKeyID, provider: provider, domain: "CJMemoryErasurePendingV1")
    }
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            namespace: namespace, keyID: keyID, domain: "CJMemoryErasurePendingV1", key: key)
    }
    /// Whole provided family for account cleanup, not a per-item erase API.
    public func clearLocalFiles() throws { try storage.clearLocalFiles() }
    func validate(_ binding: MemoryBinding) throws { try storage.validate(binding) }
    func append(_ original: MemoryErasurePending, validate: () throws -> Void) throws { try storage.append(original, validateBinding: validate) }
    func records() throws -> [MemoryErasurePending] { try storage.pending() }
    func prove(_ original: MemoryErasurePending) throws -> Durability { try storage.proveOriginal(original) }
    func validate(_ proof: Durability) throws { try storage.validateDurability(proof) }
    func validateInventory(_ records: [MemoryErasurePending]) throws { try storage.validateInventory(records) }
    struct ObservationProof {
        let value: MemoryErasureObservation
        let storage: MemoryEncryptedRecords<MemoryErasureObservation>
        let durability: MemoryEncryptedRecords<MemoryErasureObservation>.Durability
    }
    func observation(for original: MemoryErasurePending) throws -> ObservationProof? {
        let records: MemoryEncryptedRecords<MemoryErasureObservation>? = try storage.adjacentRecords(domain: "CJMemoryErasureObservationsV1", create: false)
        guard let records, let record = try records.pending().first(where: { same($0.journalID, original.actionID) }) else { return nil }
        try record.check(original)
        return ObservationProof(value: record, storage: records, durability: try records.proveOriginal(record))
    }
    func validate(_ observation: ObservationProof) throws { try observation.storage.validateDurability(observation.durability) }
    func observations(for originals: [MemoryErasurePending]) throws -> [ObservationProof] {
        let records: MemoryEncryptedRecords<MemoryErasureObservation>? = try storage.adjacentRecords(domain: "CJMemoryErasureObservationsV1", create: false)
        guard let records else { return [] }
        let values = try records.pending()
        let proofs = try values.map { value in
            guard let original = originals.first(where: { same($0.actionID, value.actionID) }) else { throw MemoryFailure.storageUnavailable }
            try value.check(original)
            return ObservationProof(value: value, storage: records, durability: try records.proveOriginal(value))
        }
        try records.validateInventory(values)
        return proofs
    }
    func record(_ progress: MemoryErasureProgress, original: MemoryErasurePending, validate: () throws -> Void) throws {
        let proof = try storage.proveOriginal(original)
        if let existing = try observation(for: original) {
            try existing.value.check(original, progress: progress)
            try validate(); try storage.validateDurability(proof); try self.validate(existing)
            return
        }
        let proposed = try MemoryErasureObservation(original: original, progress: progress)
        try proposed.check(original, progress: progress)
        guard let records: MemoryEncryptedRecords<MemoryErasureObservation> = try storage.adjacentRecords(domain: "CJMemoryErasureObservationsV1", create: true) else { throw MemoryFailure.storageUnavailable }
        try validate(); try storage.validateDurability(proof)
        try records.append(proposed, validateBinding: {
            try validate(); try self.storage.validateDurability(proof)
        })
        let result = try records.proveOriginal(proposed)
        try validate(); try storage.validateDurability(proof); try records.validateDurability(result)
    }
}
