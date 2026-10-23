import Foundation
import CoreFoundation
import CJAPI
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime

struct CleanupTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let bearer: String
    let originalOperationID: String
    let maximumSteps: Int
    let validate: @MainActor @Sendable () throws -> Void

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL,
              operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint.url, request.method == .get, body == nil,
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              operationID == Operations.getCurrentAccountCleanupProgress.id,
              let path = request.path, path.utf8.count <= endpoint.maximumRequestBytes,
              let components = URLComponents(string: path),
              components.path == "/v1/account-cleanup-progress",
              components.queryItems?.count == 1,
              components.queryItems?.first?.name == "operation_id",
              components.queryItems?.first?.value == originalOperationID else { throw CleanupFailure.unavailable }
        try await validate()
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        request.headerFields[.cacheControl] = "no-store"
        let (response, body) = try await underlying.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let body else { throw CleanupFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try await validate()
        let media = response.headerFields.filter { $0.name == .contentType }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let cache = response.headerFields.filter { $0.name == .cacheControl }
        guard media.count == 1, let type = media.first?.value.lowercased(),
              type == "application/json" || type == "application/json; charset=utf-8",
              cache.count == 1, cache.first?.value.lowercased() == "no-store",
              traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              String(data: bytes, encoding: .utf8) != nil else { throw CleanupFailure.invalidResponse }
        var parser = StrictCleanupJSON(bytes: Array(bytes)); try parser.check()
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let bodyTrace = object["request_id"] as? String,
              Data(trace.utf8) == Data(bodyTrace.utf8) else { throw CleanupFailure.invalidResponse }
        if response.status.code == 200 {
            // Generated decoders own the wire shape/enums. Check numeric JSON type
            // because Foundation decoding may otherwise accept integral floating values.
            guard let row = object["progress"] as? [String: Any],
                  let revision = row["revision"] as? NSNumber,
                  CFGetTypeID(revision) != CFBooleanGetTypeID(),
                  !["d", "f"].contains(String(cString: revision.objCType)) else { throw CleanupFailure.invalidResponse }
            let decoded = try JSONDecoder().decode(Components.Schemas.CurrentAccountCleanupProgressResponse.self, from: bytes)
            try validateProgress(decoded.progress, operationID: originalOperationID, maximumSteps: maximumSteps)
        }
        try await validate()
        return (response, HTTPBody(bytes))
    }
}

func validateProgress(_ value: CleanupProgress, operationID: String, maximumSteps: Int) throws {
    guard value.operation_id == operationID, cleanupIdentifier(value.operation_id, maximum: 160),
          value.revision >= 0, (1...maximumSteps).contains(value.steps.count),
          Set(value.steps.map(\.target)).count == value.steps.count,
          value.steps.allSatisfy({ cleanupIdentifier($0.target, maximum: 192) }),
          Set(value.reasons).count == value.reasons.count else { throw CleanupFailure.invalidResponse }
    // Fail closed on a contradictory success; preserve all incomplete statuses as sent.
    if value.status == .complete {
        guard value.reasons.isEmpty,
              value.steps.allSatisfy({ $0.state == .confirmed && $0.reason == .original_result_confirmed }) else {
            throw CleanupFailure.invalidResponse
        }
    }
}
