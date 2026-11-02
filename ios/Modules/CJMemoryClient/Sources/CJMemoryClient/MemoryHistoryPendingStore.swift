import Foundation
import CryptoKit
import CJMessageKeys

/// Dedicated history-action directory/AD in the existing Memory key namespace.
/// It cannot reinterpret manual, typed or lifecycle originals.
@MainActor public final class MemoryHistoryPendingStore {
    private let storage: MemoryEncryptedRecords<MemoryHistoryPending>
    typealias Durability = MemoryEncryptedRecords<MemoryHistoryPending>.Durability
    public init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            binding: binding, expectedKeyID: expectedKeyID, provider: provider, domain: "CJMemoryHistoryPendingV1")
    }
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            namespace: namespace, keyID: keyID, domain: "CJMemoryHistoryPendingV1", key: key)
    }
    func validate(_ binding: MemoryBinding) throws { try storage.validate(binding) }
    func append(_ original: MemoryHistoryPending, validate: () throws -> Void) throws { try storage.append(original, validateBinding: validate) }
    func prove(_ original: MemoryHistoryPending) throws -> Durability { try storage.proveOriginal(original) }
    func validate(_ proof: Durability) throws { try storage.validateDurability(proof) }
    func validateInventory(_ records: [MemoryHistoryPending]) throws { try storage.validateInventory(records) }
    func records() throws -> [MemoryHistoryPending] { try storage.pending() }
    struct Decline {
        let record: MemoryRejectedOperation<MemoryHistoryPending>
        let storage: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryHistoryPending>>
        let proof: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryHistoryPending>>.Durability
    }
    func rejection(for original: MemoryHistoryPending) throws -> Decline? {
        let records: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryHistoryPending>>? = try storage.adjacentRecords(domain: "CJMemoryHistoryRejectionsV1", create: false)
        guard let records, let value = try records.pending().first(where: { same($0.journalID, original.journalID) }) else { return nil }
        guard value.originalUTF8 == original.originalUTF8, same(value.expectedSHA256, original.expectedSHA256) else { throw MemoryFailure.storageUnavailable }
        return Decline(record: value, storage: records, proof: try records.proveOriginal(value))
    }
    func validate(_ decline: Decline) throws { try decline.storage.validateDurability(decline.proof) }
    func recordRejection(_ original: MemoryHistoryPending, status: Int, code: String, validate: () throws -> Void) throws {
        try storage.recordRejection(original, status: status, code: code, domain: "CJMemoryHistoryRejectionsV1", validateBinding: validate)
    }
}
