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
    public let status: Components.Schemas.MemoryItem.statusPayload
    public let text: String
    public let kind: Components.Schemas.MemorySaveCommand.kindPayload
    let owner: UUID
    let binding: MemoryBinding
    let readStamp: UUID
}
struct MemoryAcceptedItem {
    let item: Components.Schemas.MemoryItem
    let binding: MemoryBinding
    let stamp = UUID()
}
enum MemoryLifecycleAction {
    case management(Components.Schemas.MemoryManagementAction)
    case edit(Components.Schemas.MemoryManagementEditAction)
    case stopUse(Components.Schemas.MemoryStopUseAction)
    var header: (id: String, item: String, version: Int, sourceVersion: Int) {
        switch self {
        case .management(let a): (a.action_id, a.item_id, a.expected_version, a.expected_source_version)
        case .edit(let a): (a.action_id, a.item_id, a.expected_version, a.expected_source_version)
        case .stopUse(let a): (a.action_id, a.item_id, a.expected_version, a.expected_source_version)
        }
    }
}
public struct MemoryManagementPending: Codable, Sendable, MemoryJournalRecord {
    public let actionID: String
    public let originalUTF8: Data
    public let expectedSHA256: String
    public let sourceID: String
    // Only new edit records need the sealed reader's original state. Old records
    // have no value and retain their exact original bytes and ciphertext domain.
    let originalStatus: Components.Schemas.MemoryManagementReceipt.statusPayload?
    var journalID: String { actionID }
    var command: Components.Schemas.MemoryManagementAction {
        get throws { try JSONDecoder().decode(Components.Schemas.MemoryManagementAction.self, from: originalUTF8) }
    }
    var action: MemoryLifecycleAction {
        get throws {
            var parser = StrictMemoryJSON(bytes: Array(originalUTF8)); try parser.check()
            guard let object = try JSONSerialization.jsonObject(with: originalUTF8) as? [String: Any] else { throw MemoryFailure.invalidInput }
            let decoder = JSONDecoder()
            guard let version = object["version"] else { return .management(try command) }
            switch version as? String {
            case "MEMORY-MANAGEMENT-EDIT@1": return .edit(try decoder.decode(Components.Schemas.MemoryManagementEditAction.self, from: originalUTF8))
            case "MEMORY-STOP-USE@1": return .stopUse(try decoder.decode(Components.Schemas.MemoryStopUseAction.self, from: originalUTF8))
            default: throw MemoryFailure.invalidInput
            }
        }
    }
    init(operation: Components.Schemas.MemoryManagementAction.operationPayload, selection: MemoryManagementSelection) throws {
        let a = Components.Schemas.MemoryManagementAction(action_id: UUID().uuidString.lowercased(), operation: operation,
            item_id: selection.itemID, expected_version: selection.expectedVersion, expected_source_version: selection.expectedSourceVersion)
        try self.init(value: a, id: a.action_id, selection: selection, originalStatus: nil)
    }
    init(edit text: String, selection: MemoryManagementSelection) throws {
        guard memoryText(text), selection.kind != .inference,
              let status = Components.Schemas.MemoryManagementReceipt.statusPayload(rawValue: selection.status.rawValue) else { throw MemoryFailure.invalidInput }
        let a = Components.Schemas.MemoryManagementEditAction(action_id: UUID().uuidString.lowercased(), operation: .edit,
            item_id: selection.itemID, expected_version: selection.expectedVersion, expected_source_version: selection.expectedSourceVersion,
            version: .MEMORY_hyphen_MANAGEMENT_hyphen_EDIT_commat_1, text: text)
        try self.init(value: a, id: a.action_id, selection: selection, originalStatus: status)
    }
    init(stopUse selection: MemoryManagementSelection) throws {
        let a = Components.Schemas.MemoryStopUseAction(action_id: UUID().uuidString.lowercased(), operation: .withdraw,
            item_id: selection.itemID, expected_version: selection.expectedVersion, expected_source_version: selection.expectedSourceVersion,
            version: .MEMORY_hyphen_STOP_hyphen_USE_commat_1, source_id: selection.sourceID)
        try self.init(value: a, id: a.action_id, selection: selection, originalStatus: nil)
    }
    private init<T: Encodable>(value: T, id: String, selection: MemoryManagementSelection,
                               originalStatus: Components.Schemas.MemoryManagementReceipt.statusPayload?) throws {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        actionID = id; sourceID = selection.sourceID; self.originalStatus = originalStatus
        originalUTF8 = try encoder.encode(value); expectedSHA256 = digest(originalUTF8)
        try validate()
    }
    func validate() throws {
        guard originalUTF8.count <= 32768, same(digest(originalUTF8), expectedSHA256), memoryText(sourceID) else { throw MemoryFailure.invalidInput }
        let action = try action; let h = action.header
        guard same(h.id, actionID), memoryText(h.id), memoryText(h.item), h.version > 0, h.version < Int64.max,
              h.sourceVersion > 0 else { throw MemoryFailure.invalidInput }
        switch action {
        case .management: guard originalStatus == nil else { throw MemoryFailure.invalidInput }
        case .edit(let a): guard originalStatus != nil, memoryText(a.text) else { throw MemoryFailure.invalidInput }
        case .stopUse(let a): guard originalStatus == nil, same(a.source_id, sourceID) else { throw MemoryFailure.invalidInput }
        }
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
    func rejection(for original: MemoryManagementPending) throws -> MemoryRejectedOperation<MemoryManagementPending>? {
        try storage.rejection(for: original, domain: "CJMemoryManagementRejections")
    }
    func recordRejection(_ original: MemoryManagementPending, status: Int, code: String, validateBinding: () throws -> Void) throws {
        try storage.recordRejection(original, status: status, code: code, domain: "CJMemoryManagementRejections", validateBinding: validateBinding)
    }
    public func pending() throws -> [MemoryManagementPending] { try storage.pending() }
}
public enum MemoryManagementResult: Sendable {
    /// Confirms this original action only. Never updates current list/detail state.
    case historicalReceipt(Components.Schemas.MemoryManagementReceipt)
    case notObserved
    case historicalStopUseReceipt(Components.Schemas.MemoryStopUseReceipt)
    case rejected(Int, String)
}
