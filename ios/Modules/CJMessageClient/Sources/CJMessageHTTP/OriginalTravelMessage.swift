import Foundation
import CJAPI
import CJMessageClient

/// Frozen MESSAGE-send.2 data, not a B execution lease or caller authority.
/// Kept separate from the legacy parser until an explicit compatible host opts in.
struct OriginalTravelMessageSend {
    struct Selection: Sendable, Equatable {
        let id: String
        let expectedVersion: Int64
    }
    let originalUTF8: Data
    let head: Components.Schemas.MessageHead
    let messageID: String
    let text: String
    let creationIntent: MessageCreationIntent
    let travelContext: Selection?
    let needsReference: Selection?

    init(raw: Data, maximumBytes: Int, expectedMessageID: String? = nil) throws {
        guard raw.count <= maximumBytes else { throw RecoveryError.invalidInput }
        var parser = StrictJSON(bytes: Array(raw));try parser.check()
        guard let value = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
              Set(value.keys) == ["version", "conversation_id", "message_id", "text", "trip_id", "creation_intent",
                                 "expected_generation", "expected_sequence", "travel_context", "needs_reference"],
              value["version"] as? String == "MESSAGE-send.2",value["trip_id"] is NSNull,
              let conversation = value["conversation_id"] as? String,!conversation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              conversation.utf8.count <= 256,!conversation.utf8.contains(0),
              let message = value["message_id"] as? String,!message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              expectedMessageID.map({ Data($0.utf8) == Data(message.utf8) }) ?? true,
              let content = value["text"] as? String,!content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let generation = value["expected_generation"] as? String,!generation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let sequence = parser.topLevelUnsignedIntegers["expected_sequence"],
              let intent = value["creation_intent"] as? String,let kind = MessageCreationIntent(rawValue: intent) else { throw RecoveryError.invalidInput }
        let travel: Selection?
        if value["travel_context"] is NSNull { travel = nil }
        else { travel = try Self.selection(value["travel_context"], path: "travel_context", integers: parser.memberUnsignedIntegers, travel: true) }
        let needs: Selection?
        if kind == .none {
            guard value["needs_reference"] is NSNull else { throw RecoveryError.invalidInput }
            needs = nil
        } else {
            needs = try Self.selection(value["needs_reference"], path: "needs_reference", integers: parser.memberUnsignedIntegers, travel: false)
        }
        originalUTF8 = raw;head = .init(conversation_id: conversation,generation: generation,last_sequence: sequence)
        messageID = message;text = content;creationIntent = kind;travelContext = travel;needsReference = needs
    }
    private static func selection(_ value: Any?, path: String, integers: [[String]: Int64], travel: Bool) throws -> Selection {
        guard let object = value as? [String: Any],Set(object.keys) == ["id", "expected_version"],
              let id = object["id"] as? String,let version = integers[[path, "expected_version"]],version > 0 else { throw RecoveryError.invalidInput }
        if travel {
            guard id.utf8.count == 32,id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw RecoveryError.invalidInput }
        } else {
            let bytes = Array(id.utf8)
            guard (1...96).contains(bytes.count),let first = bytes.first,
                  Self.alphaNumeric(first),bytes.allSatisfy({ Self.alphaNumeric($0) || [95,46,58,45].contains($0) }) else { throw RecoveryError.invalidInput }
        }
        return Selection(id: id,expectedVersion: version)
    }
    private static func alphaNumeric(_ byte: UInt8) -> Bool {
        (48...57).contains(byte) || (65...90).contains(byte) || (97...122).contains(byte)
    }
}
