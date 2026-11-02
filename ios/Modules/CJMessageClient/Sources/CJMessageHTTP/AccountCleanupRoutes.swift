import Foundation
import HTTPTypes

/// Producer-fixed CLEANUP-API@1 exits, separate from current-ALLOWED legacy GET.
/// No device invalidation/receipt or arbitrary cleanup-domain dispatch is enabled.
enum LocalAccountCleanupRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 16384, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil else { return false }
        switch operationID {
        case "registerCleanupDeviceV1":
            return request.method == .post && hasBody && path == "/v1/cleanup-devices"
        case "prepareAccountCleanupV1":
            return request.method == .post && hasBody && path == "/v1/account-cleanup-operations"
        case "confirmAccountCleanupV1":
            return request.method == .post && hasBody && parts.query == nil &&
                segment(parts.percentEncodedPath, suffix: "/confirmation") != nil
        case "queryAccountCleanupPreparationV1":
            guard request.method == .get, !hasBody, parts.percentEncodedPath == "/v1/account-cleanup-preparations",
                  let query = parts.queryItems, query.count == 1, query[0].name == "action_id",
                  let action = query[0].value else { return false }
            return identifier(action)
        case "readOriginalAccountCleanupV1":
            return request.method == .get && !hasBody && parts.query == nil &&
                segment(parts.percentEncodedPath, suffix: "") != nil
        default: return false
        }
    }
    private static func segment(_ path: String, suffix: String) -> String? {
        let prefix = "/v1/account-cleanup-operations/"
        guard path.hasPrefix(prefix), path.hasSuffix(suffix) else { return nil }
        let remainder = path.dropFirst(prefix.count)
        guard remainder.count >= suffix.count else { return nil }
        let encoded = String(remainder.dropLast(suffix.count))
        guard !encoded.contains("/"), let original = encoded.removingPercentEncoding, identifier(original),
              encoded == original.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/%?#"))) else { return nil }
        return original
    }
    private static func identifier(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        guard (1...160).contains(bytes.count), let first = bytes.first,
              (48...57).contains(first) || (65...90).contains(first) || (97...122).contains(first) else { return false }
        return bytes.allSatisfy { (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || [95,46,58,47,45].contains($0) }
    }
}
