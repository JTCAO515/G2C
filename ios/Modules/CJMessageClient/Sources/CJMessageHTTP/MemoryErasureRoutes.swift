import Foundation
import HTTPTypes

enum LocalMemoryErasureRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 65536, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil else { return false }
        if operationID == "eraseMemoryV1" { return request.method == .post && hasBody && path == "/v1/memory-erasures" }
        guard operationID == "readMemoryErasureProgressV1", request.method == .get, !hasBody,
              parts.percentEncodedPath == "/v1/memory-erasure-progress", parts.percentEncodedQuery?.contains("+") == false,
              let values = parts.queryItems, values.count == 1, values[0].name == "action_id", let value = values[0].value else { return false }
        return !value.contains("\0") && !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && value.utf8.count <= 16384 && value.unicodeScalars.count <= 4096
    }
}
