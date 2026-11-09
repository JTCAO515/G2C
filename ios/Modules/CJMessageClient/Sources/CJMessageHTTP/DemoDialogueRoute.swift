import CoreFoundation
import Foundation
import HTTPTypes

/// The #707 additive Beta route. Old MESSAGE send versions never activate it.
enum DemoDialogueRoute {
    static let path = "/v1/demo-dialogue/messages"
    static let submit = "submitDemoDialogueMessageV1"
    static let original = "readDemoDialogueMessageV1"
    static let eventStream = "readDemoDialogueEventsV1"
    static let eventsPath = "/v1/demo-dialogue/events"
    static let actionsPath = "/v1/demo-dialogue/actions"
    static let submitAction = "submitDemoDialogueNeedsActionV1"
    static let originalAction = "readDemoDialogueNeedsActionV1"
    static let maximumRequestBytes = 16_384
    static let maximumActionBytes = 32_768

    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path else { return false }
        let credentials = request.headerFields.filter { $0.name == .authorization }
        guard credentials.count == 1, let value = credentials.first?.value, value.hasPrefix("Bearer ") else { return false }
        let token = value.dropFirst(7)
        guard !token.isEmpty, !token.contains(","), !token.contains(where: \.isWhitespace) else { return false }
        if request.method == .post {
            return hasBody && ((operationID == submit && path == Self.path) ||
                (operationID == submitAction && path == actionsPath))
        }
        let expected: (path: String, parameter: String)
        switch operationID {
        case original: expected = (Self.path, "message_id")
        case originalAction: expected = (actionsPath, "action_id")
        case eventStream: expected = (eventsPath, "message_id")
        default: return false
        }
        guard request.method == .get, !hasBody,
              let components = URLComponents(string: path), components.percentEncodedPath == expected.path,
              components.scheme == nil, components.host == nil, components.fragment == nil,
              let encoded = components.percentEncodedQuery, !encoded.contains("+"), components.string == path,
              let query = components.queryItems, query.count == 1, query[0].name == expected.parameter,
              let value = query[0].value, validID(value) else { return false }
        let cursors = request.headerFields.filter { $0.name.canonicalName == "last-event-id" }
        if operationID != eventStream { return cursors.isEmpty }
        let accept = request.headerFields.filter { $0.name == .accept }
        guard accept.count == 1, accept.first?.value == "text/event-stream", cursors.count <= 1 else { return false }
        return cursors.first.map { validEventCursor($0.value) } ?? true
    }

    struct Original {
        let messageID: String
        let conversationID: String?
    }

    @discardableResult
    static func validateOriginal(_ raw: Data) throws -> Original {
        guard raw.count <= maximumRequestBytes else { throw MessageHTTPFailure.invalidConfiguration }
        try validateUnambiguousJSON(raw)
        guard let value = try JSONSerialization.jsonObject(with: raw) as? [String: Any] else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        let required: Set<String> = ["version", "message_id", "text", "locale"]
        let keys = Set(value.keys)
        guard required.isSubset(of: keys), keys.isSubset(of: required.union(["conversation_id", "new_conversation"])),
              let version = value["version"] as? String,
              ["DEMO-dialogue-message.1", "DEMO-dialogue-message.2"].contains(version),
              let id = value["message_id"] as? String, validID(id),
              let text = value["text"] as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !text.utf8.contains(0), text.utf8.count <= 12_000,
              let locale = value["locale"] as? String, ["zh", "en"].contains(locale) else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        if let new = value["new_conversation"] {
            guard let flag = new as? NSNumber, CFGetTypeID(flag) == CFBooleanGetTypeID(),
                  flag.boolValue, value["conversation_id"] == nil else { throw MessageHTTPFailure.invalidConfiguration }
        }
        if let conversation = value["conversation_id"] {
            guard let id = conversation as? String, validConversationID(id) else {
                throw MessageHTTPFailure.invalidConfiguration
            }
        }
        return Original(messageID: id, conversationID: value["conversation_id"] as? String)
    }

    struct NeedsActionOriginal {
        let actionID: String
        let conversationID: String
        let cardID: String
        let expectedVersion: Int64
        let operation: String
    }

    @discardableResult
    static func validateNeedsAction(_ raw: Data) throws -> NeedsActionOriginal {
        guard raw.count <= maximumActionBytes else { throw MessageHTTPFailure.invalidConfiguration }
        var parser = StrictJSON(bytes: Array(raw))
        try parser.check()
        guard let value = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
              value["version"] as? String == "DEMO-dialogue-action.1",
              let action = value["action_id"] as? String, validID(action),
              let conversation = value["conversation_id"] as? String, validConversationID(conversation),
              let card = value["card_id"] as? String, validID(card),
              let revision = parser.topLevelUnsignedIntegers["expected_version"], revision > 0,
              let operation = value["operation"] as? String else { throw MessageHTTPFailure.invalidConfiguration }
        let required: Set<String> = ["version", "action_id", "conversation_id", "card_id", "expected_version", "operation"]
        switch operation {
        case "confirm_needs":
            guard Set(value.keys) == required else { throw MessageHTTPFailure.invalidConfiguration }
        case "correct_needs":
            guard Set(value.keys) == required.union(["changes"]),
                  let changes = value["changes"] as? [String: Any], !changes.isEmpty else {
                throw MessageHTTPFailure.invalidConfiguration
            }
        default:
            throw MessageHTTPFailure.invalidConfiguration
        }
        return NeedsActionOriginal(actionID: action, conversationID: conversation, cardID: card,
                                   expectedVersion: revision, operation: operation)
    }

    static func validEventCursor(_ value: String) -> Bool {
        guard !value.isEmpty, value.utf8.allSatisfy({ (48...57).contains($0) }),
              let cursor = Int64(value), cursor >= 0 else { return false }
        return String(cursor) == value
    }

    static func validConversationID(_ id: String) -> Bool {
        let prefix = "demo-dialogue-"
        return id.hasPrefix(prefix) && id.utf8.count == prefix.utf8.count + 32 &&
            id.utf8.dropFirst(prefix.utf8.count).allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    private static func validID(_ id: String) -> Bool {
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            !id.utf8.contains(0) && id.utf8.count <= 256
    }
}
