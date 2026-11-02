import Foundation
import CJStrictJSON

public enum MemoryHistoryChange: String, Codable, Sendable { case enable, disable }

/// Current effective settings from MEMORY-HISTORY@1, not a grant inferred from a receipt.
public struct MemoryHistorySettings: Sendable {
    public let conversationID: String
    public let generation: String
    public let epoch: Int64
    public let enabled: Bool
    public let sourceVersion: Int64
    public let withdrawalEpoch: Int64
    init(_ value: StrictJSONValue, receipt: Bool = false) throws {
        var fields: Set<String> = ["version", "conversation_id", "generation", "epoch", "enabled", "source_version", "withdrawal_epoch"]
        if receipt { fields.formUnion(["action_id", "input_sha256"]) }
        let object = try historyObject(value, fields: fields)
        guard try historyString(object["version"], limit: 64) == "MEMORY-HISTORY@1" else { throw MemoryFailure.invalidResponse }
        conversationID = try historyString(object["conversation_id"], limit: 256)
        generation = try historyString(object["generation"], limit: 1024)
        epoch = try historyInteger(object["epoch"])
        sourceVersion = try historyInteger(object["source_version"])
        withdrawalEpoch = try historyInteger(object["withdrawal_epoch"])
        guard case .boolean(let enabled) = object["enabled"], withdrawalEpoch > 0,
              !enabled || sourceVersion > 0 else { throw MemoryFailure.invalidResponse }
        self.enabled = enabled
    }
}

struct MemoryHistoryAction: Codable, Sendable {
    let version: String
    let actionID: String
    let change: MemoryHistoryChange
    let conversationID: String
    let generation: String
    let epoch: Int64
    let sourceVersion: Int64
    enum CodingKeys: String, CodingKey {
        case version, actionID = "action_id", change = "operation", conversationID = "conversation_id"
        case generation = "expected_generation", epoch = "expected_epoch", sourceVersion = "expected_source_version"
    }
    init(actionID: String, change: MemoryHistoryChange, settings: MemoryHistorySettings) throws {
        guard settings.sourceVersion < Int64.max else { throw MemoryFailure.invalidInput }
        version = "MEMORY-HISTORY@1"; self.actionID = actionID; self.change = change
        conversationID = settings.conversationID; generation = settings.generation
        epoch = settings.epoch; sourceVersion = settings.sourceVersion
    }
    init(raw: Data) throws {
        guard !raw.isEmpty, raw.count <= 32768 else { throw MemoryFailure.invalidInput }
        var parser = StrictMemoryJSON(bytes: Array(raw))
        let object = try historyObject(parser.document(), fields: ["version", "action_id", "operation", "conversation_id", "expected_generation", "expected_epoch", "expected_source_version"])
        version = try historyString(object["version"], limit: 64)
        guard version == "MEMORY-HISTORY@1", let change = MemoryHistoryChange(rawValue: try historyString(object["operation"], limit: 16)) else { throw MemoryFailure.invalidInput }
        self.change = change
        actionID = try historyString(object["action_id"], limit: 4096)
        conversationID = try historyString(object["conversation_id"], limit: 256)
        generation = try historyString(object["expected_generation"], limit: 1024)
        epoch = try historyInteger(object["expected_epoch"])
        sourceVersion = try historyInteger(object["expected_source_version"])
        guard sourceVersion < Int64.max else { throw MemoryFailure.invalidInput }
    }
}

/// Original consent action bytes. Never reconstructed from a current enabled boolean.
public struct MemoryHistoryPending: Codable, Sendable, MemoryJournalRecord, CustomStringConvertible, CustomDebugStringConvertible {
    public let actionID: String
    public let originalUTF8: Data
    public let expectedSHA256: String
    public let conversationID: String
    public let change: MemoryHistoryChange
    let withdrawalEpoch: Int64
    var journalID: String { actionID }
    public var description: String { "<private history action>" }
    public var debugDescription: String { description }
    init(change: MemoryHistoryChange, settings: MemoryHistorySettings) throws {
        let action = try MemoryHistoryAction(actionID: UUID().uuidString, change: change, settings: settings)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        originalUTF8 = try encoder.encode(action); actionID = action.actionID
        expectedSHA256 = digest(originalUTF8); withdrawalEpoch = settings.withdrawalEpoch
        conversationID = action.conversationID; self.change = change
        try validate()
    }
    func action() throws -> MemoryHistoryAction { try MemoryHistoryAction(raw: originalUTF8) }
    func validate() throws {
        let action = try action()
        guard same(actionID, action.actionID), same(expectedSHA256, digest(originalUTF8)),
              same(conversationID, action.conversationID), change == action.change, withdrawalEpoch > 0 else { throw MemoryFailure.invalidResponse }
    }
}

/// Immutable historical receipt; the current switch always comes from a settings GET.
public struct MemoryHistoryReceipt: Sendable {
    public let actionID: String
    public let inputSHA256: String
    public let historical: MemoryHistorySettings
    init(_ value: StrictJSONValue, original: MemoryHistoryPending) throws {
        historical = try MemoryHistorySettings(value, receipt: true)
        guard case .object(let object) = value else { throw MemoryFailure.invalidResponse }
        actionID = try historyString(object["action_id"], limit: 4096)
        inputSHA256 = try historyString(object["input_sha256"], limit: 64)
        let action = try original.action()
        guard same(actionID, original.actionID), same(inputSHA256, original.expectedSHA256),
              same(historical.conversationID, action.conversationID), same(historical.generation, action.generation),
              historical.epoch == action.epoch, historical.sourceVersion == action.sourceVersion + 1,
              historical.enabled == (action.change == .enable), historical.withdrawalEpoch == original.withdrawalEpoch else { throw MemoryFailure.invalidResponse }
    }
}
public enum MemoryHistoryResult: Sendable { case recorded(MemoryHistoryReceipt), notObserved, rejected(Int, String) }

func historyObject(_ value: StrictJSONValue, fields: Set<String>) throws -> [String: StrictJSONValue] {
    guard case .object(let object) = value, Set(object.keys) == fields else { throw MemoryFailure.invalidResponse }
    return object
}
func historyString(_ value: StrictJSONValue?, limit: Int) throws -> String {
    guard case .string(let string) = value, !string.contains("\0"),
          !string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          string.utf8.count <= limit else { throw MemoryFailure.invalidResponse }
    return string
}
func historyInteger(_ value: StrictJSONValue?) throws -> Int64 {
    // Token preserving: true, 1.0, 1e0 and out-of-range integers never become counters.
    guard case .number(let token) = value, let integer = Int64(token), integer >= 0 else { throw MemoryFailure.invalidResponse }
    return integer
}
func historyEnvelope(_ bytes: Data, trace: String) throws -> StrictJSONValue {
    var parser = StrictMemoryJSON(bytes: Array(bytes))
    let object = try historyObject(parser.document(), fields: ["version", "request_id", "result"])
    guard try historyString(object["version"], limit: 64) == "MEMORY-HISTORY-result@1",
          same(try historyString(object["request_id"], limit: 64), trace), UUID(uuidString: trace) != nil,
          let result = object["result"] else { throw MemoryFailure.invalidResponse }
    return result
}
