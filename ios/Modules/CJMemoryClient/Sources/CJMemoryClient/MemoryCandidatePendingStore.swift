import Foundation
import CryptoKit
import CJMessageKeys

struct MemoryCandidatePending: MemoryJournalRecord, Sendable {
    let actionID: String
    let candidateID: String
    let jobID: String
    let attemptID: String
    let originalUTF8: Data
    let expectedSHA256: String
    var journalID: String { actionID }
    init(_ action: MemoryCandidateAction) {
        actionID = action.actionID; candidateID = action.candidateID
        jobID = action.producer.jobID; attemptID = action.producer.attemptID
        originalUTF8 = action.originalUTF8; expectedSHA256 = action.inputSHA256
    }
    func action() throws -> MemoryCandidateAction { try MemoryCandidateAction(originalUTF8: originalUTF8) }
    func validate() throws {
        let original = try action()
        guard same(actionID, original.actionID), same(candidateID, original.candidateID),
              same(jobID, original.producer.jobID), same(attemptID, original.producer.attemptID),
              same(expectedSHA256, original.inputSHA256) else { throw MemoryFailure.invalidResponse }
    }
}

/// Separate candidate domain in the canonical Memory key namespace. The App must
/// register its actual exact root/sidecar and use an additive device cleanup version
/// before provisioning it; this module alone does not create an App storage root.
@MainActor public final class MemoryCandidatePendingStore {
    private let storage: MemoryEncryptedRecords<MemoryCandidatePending>
    typealias Durability = MemoryEncryptedRecords<MemoryCandidatePending>.Durability
    public init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            binding: binding, expectedKeyID: expectedKeyID, provider: provider, domain: "CJMemoryCandidatePendingV1")
    }
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            namespace: namespace, keyID: keyID, domain: "CJMemoryCandidatePendingV1", key: key)
    }
    public func clearLocalFiles() throws { try storage.clearLocalFiles() }
    func validate(_ binding: MemoryBinding) throws { try storage.validate(binding) }
    func append(_ original: MemoryCandidatePending, validate: () throws -> Void) throws { try storage.append(original, validateBinding: validate) }
    func prove(_ original: MemoryCandidatePending) throws -> Durability { try storage.proveOriginal(original) }
    func validate(_ proof: Durability) throws { try storage.validateDurability(proof) }
    func records() throws -> [MemoryCandidatePending] { try storage.pending() }
    func validateInventory(_ records: [MemoryCandidatePending]) throws { try storage.validateInventory(records) }
    struct Decline {
        let record: MemoryRejectedOperation<MemoryCandidatePending>
        let storage: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryCandidatePending>>
        let proof: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryCandidatePending>>.Durability
    }
    func rejection(for original: MemoryCandidatePending) throws -> Decline? {
        let records: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryCandidatePending>>? = try storage.adjacentRecords(domain: "CJMemoryCandidateRejectionsV1", create: false)
        guard let records, let value = try records.pending().first(where: { same($0.journalID, original.journalID) }) else { return nil }
        guard value.originalUTF8 == original.originalUTF8, same(value.expectedSHA256, original.expectedSHA256) else { throw MemoryFailure.storageUnavailable }
        return Decline(record: value, storage: records, proof: try records.proveOriginal(value))
    }
    func validate(_ decline: Decline) throws { try decline.storage.validateDurability(decline.proof) }
    func recordRejection(_ original: MemoryCandidatePending, status: Int, code: String, validate: () throws -> Void) throws {
        try storage.recordRejection(original, status: status, code: code, domain: "CJMemoryCandidateRejectionsV1", validateBinding: validate)
    }
}
