import Foundation
import CJStrictJSON

/// Closed native4 envelopes. Original requests and nested receipt bytes are never regenerated.
enum LioNative4Envelope {
    static func firstQuestion(_ bytes: Data, messageID: String) throws -> String {
        guard bytes.count <= 16_384 else { throw MessageHTTPFailure.invalidConfiguration }
        var parser = StrictJSON(bytes: Array(bytes))
        let fields = try CardJSON.fields(parser.document(), "version message_id text locale new_conversation")
        guard try CardJSON.text(fields["version"]) == "LIO-message.4",
              try CardJSON.text(fields["message_id"]).utf8.elementsEqual(messageID.utf8),
              LioTimelineWire.Locale(rawValue: try CardJSON.text(fields["locale"])) != nil,
              case .boolean(true)? = fields["new_conversation"],
              case .string(let text)? = fields["text"] else { throw MessageHTTPFailure.invalidConfiguration }
        return text
    }

    static func rejection(_ bytes: Data, expected: String) throws {
        var parser = StrictJSON(bytes: Array(bytes))
        let fields = try CardJSON.fields(parser.document(), "failure")
        guard try CardJSON.text(fields["failure"]) == expected else { throw MessageHTTPFailure.invalidResponse }
    }

    static func confirm(_ bytes: Data, original: LioTimelineWire.Send) throws -> String {
        guard bytes.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
        var parser = StrictJSON(bytes: Array(bytes))
        return try conversation(in: parser.document(), original: original)
    }

    static func lookup(_ bytes: Data, original: LioTimelineWire.Send) throws -> (id: String, receipt: Data)? {
        guard bytes.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
        var parser = StrictJSON(bytes: Array(bytes))
        let fields = try CardJSON.fields(parser.document(), "version receipt")
        guard try CardJSON.text(fields["version"]) == "LIO-message-lookup.4" else {
            throw MessageHTTPFailure.invalidResponse
        }
        if case .null? = fields["receipt"] { return nil }
        let id = try conversation(in: fields["receipt"], original: original)
        // The shared parser records each validated root member's exact byte range.
        return (id, bytes.subdata(in: parser.rootMemberRanges["receipt"]!))
    }

    private static func conversation(in value: StrictJSONValue?, original: LioTimelineWire.Send) throws -> String {
        let fields = try CardJSON.fields(value, "version message_id conversation_id")
        let id = try CardJSON.text(fields["conversation_id"])
        guard try CardJSON.text(fields["version"]) == "LIO-message-receipt.4",
              try CardJSON.text(fields["message_id"]).utf8.elementsEqual(original.messageID.utf8),
              LioTimelineWire.validConversationID(id),
              original.conversationID.map({ $0.utf8.elementsEqual(id.utf8) }) ?? true else {
            throw MessageHTTPFailure.invalidResponse
        }
        return id
    }
}
