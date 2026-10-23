import Foundation
import CryptoKit
import CJAPI
import CJMessageKeys

/// Created only from a validated list/detail result held by this MemoryClient.
public struct MemoryManagementSelection: Sendable {
    public let itemID: String
    public let expectedVersion: Int
    public let expectedSourceVersion: Int
    public let sourceID: String
    let owner: UUID
    let binding: MemoryBinding
    let readStamp: UUID
}
struct MemoryAcceptedItem {
    let item: Components.Schemas.MemoryItem
    let binding: MemoryBinding
    let stamp = UUID()
}
public struct MemoryManagementPending: Codable, Sendable, MemoryJournalRecord {
    public let actionID: String
    public let originalUTF8: Data
    public let expectedSHA256: String
    public let sourceID: String
    var journalID: String { actionID }
    var command: Components.Schemas.MemoryManagementAction {
        get throws { try JSONDecoder().decode(Components.Schemas.MemoryManagementAction.self, from: originalUTF8) }
    }
    init(operation: Components.Schemas.MemoryManagementAction.operationPayload, selection: MemoryManagementSelection) throws {
        let action = Components.Schemas.MemoryManagementAction(action_id: UUID().uuidString.lowercased(), operation: operation,
            item_id: selection.itemID, expected_version: selection.expectedVersion, expected_source_version: selection.expectedSourceVersion)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        actionID = action.action_id; sourceID = selection.sourceID
        originalUTF8 = try encoder.encode(action); expectedSHA256 = digest(originalUTF8)
        try validate()
    }
    func validate() throws {
        var parser = StrictMemoryJSON(bytes: Array(originalUTF8)); try parser.check()
        let action = try command
        guard same(action.action_id, actionID), memoryText(action.action_id), memoryText(action.item_id), memoryText(sourceID),
              action.expected_version > 0, action.expected_version < Int64.max,
              action.expected_source_version > 0, originalUTF8.count <= 32768,
              same(digest(originalUTF8), expectedSHA256) else { throw MemoryFailure.invalidInput }
    }
}
/// Dedicated lifecycle journal/directory and AES-GCM AD; never the save or Message ledger.
/// Uses the accepted Memory key purpose with a separate ciphertext domain.
@MainActor public final class MemoryManagementPendingStore {
    private let storage: MemoryEncryptedRecords<MemoryManagementPending>
    public init(directory: URL, maximumBytes: Int, maximumRecords: Int, binding: MemoryBinding,
                expectedKeyID: UUID, provider: any MessageEncryptionKeyProvider) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            binding: binding, expectedKeyID: expectedKeyID, provider: provider, domain: "CJMemoryManagementPending")
    }
    init(directory: URL, maximumBytes: Int, maximumRecords: Int, namespace: MessageKeyNamespace, keyID: UUID,
         key: @escaping () throws -> SymmetricKey) throws {
        storage = try MemoryEncryptedRecords(directory: directory, maximumBytes: maximumBytes, maximumRecords: maximumRecords,
            namespace: namespace, keyID: keyID, domain: "CJMemoryManagementPending", key: key)
    }
    func validate(_ binding: MemoryBinding) throws { try storage.validate(binding) }
    func validateDirectory() throws { try storage.validateDirectory() }
    func append(_ record: MemoryManagementPending, validateBinding: () throws -> Void) throws { try storage.append(record, validateBinding: validateBinding) }
    func requireOriginal(_ record: MemoryManagementPending) throws { try storage.requireOriginal(record) }
    public func pending() throws -> [MemoryManagementPending] { try storage.pending() }
}
public enum MemoryManagementResult: Sendable {
    /// Confirms this original action only. Never updates current list/detail state.
    case historicalReceipt(Components.Schemas.MemoryManagementReceipt)
    case notObserved
}
