import Foundation
import HTTPTypes

/// Explicit accepted wire selection. Restored originals keep their own version.
public enum CleanupDeviceVersion: String, Codable, Sendable {
    case v3 = "CLEANUP-DEVICE@3", v4 = "CLEANUP-DEVICE@4"
    public var route: String { self == .v3 ? "v3" : "v4" }
    public var operationSuffix: String { self == .v3 ? "V3" : "V4" }
    public var completionRoute: String { self == .v3 ? "v1" : "v2" }
    public var completionOperation: String { self == .v3 ? "readCleanupDeviceCompletionV1" : "readCleanupDeviceCompletionV2" }
    public var completionWire: String { self == .v3 ? "CLEANUP-DEVICE-COMPLETION@1" : "CLEANUP-DEVICE-COMPLETION@2" }
}

/// Six producer-fixed CLEANUP-DEVICE@3 paths, not an account/business capability.
enum LocalDeviceCleanupRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String, version: CleanupDeviceVersion = .v3) -> Bool {
        guard request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 16384, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil else { return false }
        // A separate, bounded current-identity check is needed before the
        // session_invalid control action. It cannot select an existing message.
        if operationID == "verifyDeviceCleanupIdentity" + version.operationSuffix {
            guard request.method == .get, !hasBody, parts.percentEncodedPath == "/v1/message-receipts",
                  let query = parts.queryItems, query.count == 1, query[0].name == "message_id",
                  let id = query[0].value, id.hasPrefix("cleanup-check-"),
                  UUID(uuidString: String(id.dropFirst("cleanup-check-".count)))?.uuidString == String(id.dropFirst("cleanup-check-".count)) else { return false }
            return true
        }
        let post: String?
        switch operationID {
        case "registerCleanupDevice" + version.operationSuffix: post = "/" + version.route + "/cleanup-devices"
        case "createCleanupDeviceCall" + version.operationSuffix: post = "/" + version.route + "/cleanup-device-calls"
        case "reportCleanupDeviceReceipt" + version.operationSuffix: post = "/" + version.route + "/cleanup-device-receipts"
        default: post = nil
        }
        if let post { return request.method == .post && hasBody && path == post }
        guard request.method == .get, !hasBody else { return false }
        if operationID == "queryCleanupDeviceInvocation" + version.operationSuffix {
            let prefix = "/" + version.route + "/cleanup-device-calls/"
            guard parts.query == nil, parts.percentEncodedPath.hasPrefix(prefix) else { return false }
            let segment = String(parts.percentEncodedPath.dropFirst(prefix.count))
            guard !segment.contains("/"), let id = segment.removingPercentEncoding, LocalAccountCleanupRoute.identifier(id),
                  segment == id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/%?#"))) else { return false }
            return true
        }
        let queryPath: String
        switch operationID {
        case "queryCleanupDeviceRegistration" + version.operationSuffix: queryPath = "/" + version.route + "/cleanup-device-registrations"
        case "queryCleanupDeviceCallAction" + version.operationSuffix: queryPath = "/" + version.route + "/cleanup-device-call-actions"
        default: return false
        }
        guard parts.percentEncodedPath == queryPath, let query = parts.queryItems, query.count == 2,
              Set(query.map(\.name)) == ["action_id", "input_sha256"],
              let action = query.first(where: { $0.name == "action_id" })?.value,
              let digest = query.first(where: { $0.name == "input_sha256" })?.value,
              LocalAccountCleanupRoute.identifier(action), digest.utf8.count == 64,
              digest.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { return false }
        return true
    }
}
