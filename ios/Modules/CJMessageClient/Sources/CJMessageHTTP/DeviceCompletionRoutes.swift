import Foundation
import HTTPTypes

enum LocalDeviceCompletionRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard operationID == "readCleanupDeviceCompletionV1", request.method == .get, !hasBody,
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 16384, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil else { return false }
        let prefix = "/v1/cleanup-device-completions/"
        guard parts.percentEncodedPath.hasPrefix(prefix) else { return false }
        let encoded = String(parts.percentEncodedPath.dropFirst(prefix.count))
        guard !encoded.contains("/"), let invocation = encoded.removingPercentEncoding,
              LocalAccountCleanupRoute.identifier(invocation),
              encoded == invocation.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/%?#"))),
              let values = parts.queryItems, values.count == 1, values[0].name == "request_digest", let hash = values[0].value,
              hash.utf8.count == 64, hash.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { return false }
        return true
    }
}
