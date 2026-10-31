import Foundation
import CJAPI

/// B selection data only. Saving still requires the signed API's actual owned
/// active travel/version lease and explicit collection policy.
public struct MemoryTravelSelection: Sendable, Equatable {
    public let id: String
    public let expectedVersion: Int64
    public init(id: String,expectedVersion: Int64) throws {
        guard id.utf8.count == 32,id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              expectedVersion > 0 else { throw MemoryFailure.invalidInput }
        self.id = id;self.expectedVersion = expectedVersion
    }
}

/// Exact additive MEMORY-manual.2 original, kept separate from V1 journals and
/// conversation scope. This domain enforces the frozen conditional constraints
/// the pinned generator currently represents as OpenAPIValueContainer.
public struct TypedMemoryCommand: Sendable {
    public let operationID: String
    public let itemID: String
    public let subject: String
    public let slot: String
    public let text: String
    public let occurredAt: String
    public let kind: Components.Schemas.MemoryManualSaveCommand.kindPayload
    public let travelContext: MemoryTravelSelection?
    public let originalUTF8: Data
    public init(operationID: String,itemID: String,subject: String,slot: String,text: String,occurredAt: String,
                kind: Components.Schemas.MemoryManualSaveCommand.kindPayload,travelContext: MemoryTravelSelection?) throws {
        guard [operationID,itemID,subject,slot,text,occurredAt].allSatisfy(memoryText) else { throw MemoryFailure.invalidInput }
        let context: Any
        if let travelContext { context = ["kind":"travel","id":travelContext.id,"expected_version":travelContext.expectedVersion] }
        else { context = NSNull() }
        let raw = try JSONSerialization.data(withJSONObject:["version":"MEMORY-manual.2","operation_id":operationID,
            "item_id":itemID,"subject":subject,"slot":slot,"text":text,"occurred_at":occurredAt,"kind":kind.rawValue,
            "extent":travelContext == nil ? "long_term" : "current","context":context],options:[.sortedKeys,.withoutEscapingSlashes])
        guard raw.count <= 32768 else { throw MemoryFailure.invalidInput }
        self.operationID = operationID;self.itemID = itemID;self.subject = subject;self.slot = slot;self.text = text
        self.occurredAt = occurredAt;self.kind = kind;self.travelContext = travelContext;originalUTF8 = raw
    }
    /// Persisted/network boundary: preserve bytes, do not normalize/rebuild them.
    init(originalUTF8 raw: Data) throws {
        guard raw.count <= 32768 else { throw MemoryFailure.invalidInput }
        var parser = StrictMemoryJSON(bytes:Array(raw));try parser.check()
        guard let object = try JSONSerialization.jsonObject(with:raw) as? [String:Any],
              Set(object.keys) == ["version","operation_id","item_id","subject","slot","text","occurred_at","kind","extent","context"],
              object["version"] as? String == "MEMORY-manual.2",
              let operation = object["operation_id"] as? String,let item = object["item_id"] as? String,
              let subject = object["subject"] as? String,let slot = object["slot"] as? String,
              let text = object["text"] as? String,let time = object["occurred_at"] as? String,
              [operation,item,subject,slot,text,time].allSatisfy(memoryText),
              let kindValue = object["kind"] as? String,let kind = Components.Schemas.MemoryManualSaveCommand.kindPayload(rawValue:kindValue) else { throw MemoryFailure.invalidInput }
        let travel: MemoryTravelSelection?
        if object["extent"] as? String == "long_term" {
            guard object["context"] is NSNull else { throw MemoryFailure.invalidInput };travel = nil
        } else {
            guard object["extent"] as? String == "current",let context = object["context"] as? [String:Any],
                  Set(context.keys) == ["kind","id","expected_version"],context["kind"] as? String == "travel",
                  let id = context["id"] as? String,let version = parser.unsignedIntegers[["context","expected_version"]] else { throw MemoryFailure.invalidInput }
            travel = try MemoryTravelSelection(id:id,expectedVersion:version)
        }
        operationID = operation;itemID = item;self.subject = subject;self.slot = slot;self.text = text
        occurredAt = time;self.kind = kind;travelContext = travel;originalUTF8 = raw
    }
}

struct TypedMemoryPending: MemoryJournalRecord, Sendable {
    let operationID: String
    let itemID: String
    let originalUTF8: Data
    let expectedSHA256: String
    let inference: Bool
    var journalID: String { operationID }
    init(_ command: TypedMemoryCommand) {
        operationID = command.operationID;itemID = command.itemID;originalUTF8 = command.originalUTF8
        expectedSHA256 = digest(command.originalUTF8);inference = command.kind == .inference
    }
    func validate() throws {
        let command = try TypedMemoryCommand(originalUTF8:originalUTF8)
        guard same(command.operationID,operationID),same(command.itemID,itemID),digest(originalUTF8) == expectedSHA256,
              inference == (command.kind == .inference) else { throw MemoryFailure.invalidResponse }
    }
}
