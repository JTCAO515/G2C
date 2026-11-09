import CoreFoundation
import Foundation
import HTTPTypes

/// The #707 additive Beta route. Old MESSAGE send versions never activate it.
enum DemoDialogueRoute {
    static let path = "/v1/demo-dialogue/messages"
    static let submit = "submitDemoDialogueMessageV1"
    static let original = "readDemoDialogueMessageV1"
    static let maximumRequestBytes = 16_384

    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path else { return false }
        let credentials = request.headerFields.filter { $0.name == .authorization }
        guard credentials.count == 1, let value = credentials.first?.value, value.hasPrefix("Bearer ") else { return false }
        let token = value.dropFirst(7)
        guard !token.isEmpty, !token.contains(","), !token.contains(where: \.isWhitespace) else { return false }
        if request.method == .post {
            return hasBody && operationID == submit && path == Self.path
        }
        guard request.method == .get, !hasBody, operationID == original,
              let components = URLComponents(string: path), components.percentEncodedPath == Self.path,
              components.scheme == nil, components.host == nil, components.fragment == nil,
              let encoded = components.percentEncodedQuery, !encoded.contains("+"), components.string == path,
              let query = components.queryItems, query.count == 1, query[0].name == "message_id",
              let value = query[0].value else { return false }
        return validID(value)
    }

    static func validateOriginal(_ raw: Data) throws {
        guard raw.count <= maximumRequestBytes else { throw MessageHTTPFailure.invalidConfiguration }
        try validateUnambiguousJSON(raw)
        guard let value = try JSONSerialization.jsonObject(with: raw) as? [String: Any] else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        let required: Set<String> = ["version", "message_id", "text", "locale"]
        let keys = Set(value.keys)
        guard required.isSubset(of: keys), keys.isSubset(of: required.union(["conversation_id", "new_conversation"])),
              value["version"] as? String == "DEMO-dialogue-message.1",
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
            guard let id = conversation as? String, id.hasPrefix("demo-dialogue-"),
                  id.utf8.count == 46, id.utf8.dropFirst(14).allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })
            else { throw MessageHTTPFailure.invalidConfiguration }
        }
    }

    private static func validID(_ id: String) -> Bool {
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            !id.utf8.contains(0) && id.utf8.count <= 256
    }
}
