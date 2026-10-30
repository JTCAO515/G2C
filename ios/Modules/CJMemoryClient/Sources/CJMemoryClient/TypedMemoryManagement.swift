import Foundation
import CJAPI

public enum TypedMemoryOperation: String, Sendable { case pause, resume, edit, stopUse }
enum TypedMemoryLifecycleAction {
    case management(Components.Schemas.MemoryManagementActionV2)
    case stopUse(Components.Schemas.MemoryStopUseActionV2)
    var header: (id: String,item: String,version: Int,source: Int) {
        switch self {
        case .management(.MemoryStatusActionV2(let a)):(a.action_id,a.item_id,a.expected_version,a.expected_source_version)
        case .management(.MemoryEditActionV2(let a)):(a.action_id,a.item_id,a.expected_version,a.expected_source_version)
        case .stopUse(let a):(a.action_id,a.item_id,a.expected_version,a.expected_source_version)
        }
    }
}
public struct TypedMemoryManagementPending: Codable, Sendable, MemoryJournalRecord {
    public let actionID: String
    public let originalUTF8: Data
    public let expectedSHA256: String
    public let sourceID: String
    public let originalStatus: String
    var journalID: String { actionID }
    var action: TypedMemoryLifecycleAction {
        get throws {
            var parser = StrictMemoryJSON(bytes:Array(originalUTF8));try parser.check()
            guard let object = try JSONSerialization.jsonObject(with:originalUTF8) as? [String:Any] else { throw MemoryFailure.invalidInput }
            let decoder = JSONDecoder()
            switch object["version"] as? String {
            case "MEMORY-management.2":return .management(try decoder.decode(Components.Schemas.MemoryManagementActionV2.self,from:originalUTF8))
            case "MEMORY-STOP-USE@2":return .stopUse(try decoder.decode(Components.Schemas.MemoryStopUseActionV2.self,from:originalUTF8))
            default:throw MemoryFailure.invalidInput
            }
        }
    }
    public var operation: TypedMemoryOperation {
        get throws {
            switch try action {
            case .management(.MemoryStatusActionV2(let a)):a.operation == .pause ? .pause : .resume
            case .management(.MemoryEditActionV2):.edit
            case .stopUse:.stopUse
            }
        }
    }
    /// Read-only text from this original action, never from the current item.
    public var editText: String? {
        get throws {
            if case .management(.MemoryEditActionV2(let value)) = try action { return value.text }
            return nil
        }
    }
    init(operation: TypedMemoryOperation,read: TypedMemoryRead,text: String?,travel: MemoryTravelSelection?) throws {
        let item = read.item.value,command = item.command,id = UUID().uuidString.lowercased()
        let bytes: Data
        let encoder = JSONEncoder();encoder.outputFormatting = [.sortedKeys,.withoutEscapingSlashes]
        switch operation {
        case .pause,.resume:
            guard text == nil,travel == nil,operation == .pause ? item.status == .active : item.status == .disabled else { throw MemoryFailure.invalidInput }
            bytes = try encoder.encode(Components.Schemas.MemoryStatusActionV2(action_id:id,operation:operation == .pause ? .pause : .resume,
                item_id:command.item_id,expected_version:item.version,expected_source_version:command.source_version,version:.MEMORY_hyphen_management_period_2))
        case .edit:
            guard let text,memoryText(text),command.kind != .inference,item.status == .active || item.status == .disabled else { throw MemoryFailure.invalidInput }
            let context: Components.Schemas.MemoryEditActionV2.contextPayload
            switch read.item.scope {
            case .longTerm:guard travel == nil else { throw MemoryFailure.invalidInput };context = .CJExplicitJSONNull(.init())
            case .legacyConversation:throw MemoryFailure.liveWriteUnavailable // V1 consumer remains available; no scope reinterpretation.
            case .travel(let original):
                guard let travel,same(travel.id,original.id) else { throw MemoryFailure.invalidInput }
                context = .MemoryTravelSelectionV2(.init(kind:.travel,id:travel.id,expected_version:Int(travel.expectedVersion)))
            }
            bytes = try encoder.encode(Components.Schemas.MemoryEditActionV2(action_id:id,operation:.edit,item_id:command.item_id,
                expected_version:item.version,expected_source_version:command.source_version,version:.MEMORY_hyphen_management_period_2,text:text,context:context))
        case .stopUse:
            guard text == nil,travel == nil,item.status != .withdrawn else { throw MemoryFailure.invalidInput }
            bytes = try encoder.encode(Components.Schemas.MemoryStopUseActionV2(action_id:id,operation:.withdraw,item_id:command.item_id,
                expected_version:item.version,expected_source_version:command.source_version,version:.MEMORY_hyphen_STOP_hyphen_USE_commat_2,source_id:command.source_id))
        }
        actionID = id;sourceID = command.source_id;originalStatus = item.status.rawValue
        originalUTF8 = bytes;expectedSHA256 = digest(bytes)
        try validate()
    }
    func validate() throws {
        guard originalUTF8.count <= 32768,same(digest(originalUTF8),expectedSHA256),memoryText(sourceID),
              ["active","candidate","disabled","withdrawn"].contains(originalStatus) else { throw MemoryFailure.invalidInput }
        let action = try action,h = action.header
        guard same(h.id,actionID),memoryText(h.id),memoryText(h.item),h.version > 0,h.version < Int64.max,h.source > 0 else { throw MemoryFailure.invalidInput }
        switch action {
        case .management(.MemoryStatusActionV2):break
        case .management(.MemoryEditActionV2(let value)):
            guard memoryText(value.text),originalStatus == "active" || originalStatus == "disabled" else { throw MemoryFailure.invalidInput }
            if case .MemoryTravelSelectionV2(let travel) = value.context {
                var parser = StrictMemoryJSON(bytes:Array(originalUTF8));try parser.check()
                guard let version = parser.unsignedIntegers[["context","expected_version"]],version > 0 else { throw MemoryFailure.invalidInput }
                _ = try MemoryTravelSelection(id:travel.id,expectedVersion:version)
            }
        case .stopUse(let value):guard same(value.source_id,sourceID) else { throw MemoryFailure.invalidInput }
        }
    }
}
public enum TypedMemoryManagementResult: Sendable {
    case historicalReceipt(Components.Schemas.MemoryManagementReceiptV2)
    case notObserved
    case rejected(Int,String)
}
