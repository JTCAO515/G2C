import Foundation
import HTTPTypes

enum PreservedHistoryRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard request.method == .get, !hasBody, request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 65536, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil,
              parts.percentEncodedQuery?.contains("+") == false, let values = parts.queryItems,
              Set(values.map(\.name)).count == values.count,
              values.allSatisfy({ $0.value.map { !$0.isEmpty && !$0.utf8.contains(0) } == true }) else { return false }
        let fields = Dictionary(uniqueKeysWithValues: values.map { ($0.name, $0.value!) })
        switch operationID {
        case "readPreservedMessageHistoryV5":
            guard parts.percentEncodedPath == "/v5/message-history",
                  Set(fields.keys) == ["conversation_id", "limit"] || Set(fields.keys) == ["conversation_id", "limit", "cursor"],
                  let conversation = fields["conversation_id"], conversation.utf8.count <= 256,
                  let limit = fields["limit"], let count = Int(limit), String(count) == limit, (1...100).contains(count) else { return false }
            return true
        case "readPreservedRunDisplayV6":
            return parts.percentEncodedPath == "/v6/run-display" && Set(fields.keys) == ["message_id"]
                && fields["message_id"]!.utf8.count <= 16384
        default: return false
        }
    }
}
