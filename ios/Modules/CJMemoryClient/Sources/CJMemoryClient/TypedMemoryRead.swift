import Foundation
import CJAPI

public enum TypedMemoryScope: Sendable, Equatable {
    case longTerm
    case legacyConversation(String)
    case travel(MemoryTravelSelection)
}
public struct TypedMemoryItem: Sendable {
    public let value: Components.Schemas.MemoryItemV2
    public let scope: TypedMemoryScope
    init(_ value: Components.Schemas.MemoryItemV2) throws {
        let command = value.command
        guard value.version > 0,command.source_version > 0,
              [command.operation_id,command.item_id,command.subject,command.slot,command.text,command.occurred_at,command.source_id].allSatisfy(memoryText),
              command.kind != .inference || value.status != .active else { throw MemoryFailure.invalidResponse }
        // An opaque generated allOf branch also accepts null. Inspect its
        // actual JSON value rather than treating the chosen union case as kind.
        let contextValue: Any
        switch command.context {
        case .CJExplicitJSONNull:contextValue = NSNull()
        case .MemoryStoredContextV2(let payload):
            contextValue = try JSONSerialization.jsonObject(with:JSONEncoder().encode(payload),options:.fragmentsAllowed)
        }
        let scope: TypedMemoryScope
        if contextValue is NSNull {
            guard command.extent == .long_term else { throw MemoryFailure.invalidResponse };scope = .longTerm
        } else {
            guard command.extent == .current,let context = contextValue as? [String:Any],
                  Set(context.keys) == ["kind","id","expected_version"],let id = context["id"] as? String,memoryText(id) else { throw MemoryFailure.invalidResponse }
            switch context["kind"] as? String {
            case "legacy":
                guard context["expected_version"] is NSNull else { throw MemoryFailure.invalidResponse };scope = .legacyConversation(id)
            case "travel":
                let raw = try JSONSerialization.data(withJSONObject:context)
                var parser = StrictMemoryJSON(bytes:Array(raw));try parser.check()
                guard let version = parser.unsignedIntegers[["expected_version"]] else { throw MemoryFailure.invalidResponse }
                scope = .travel(try MemoryTravelSelection(id:id,expectedVersion:version))
            default:throw MemoryFailure.invalidResponse
            }
        }
        self.value = value;self.scope = scope
    }
}
/// Session-only read proof. Data is never an execution lease or source approval.
public struct TypedMemoryRead: Sendable {
    public let item: TypedMemoryItem
    let owner: UUID
    let generation: UUID
    let binding: MemoryBinding
    let stamp: UUID
}
public struct TypedMemoryCursor: Sendable {
    let owner: UUID
    let generation: UUID
    let binding: MemoryBinding
    let after: String
}
public struct TypedMemoryPage: Sendable {
    public let items: [TypedMemoryRead]
    public let next: TypedMemoryCursor?
}
