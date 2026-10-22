import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

struct PreviewTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let bearer: String
    let requestBytes: Data
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint.url, operationID == "previewManualTripEdit", request.method == .post,
              request.path == "/v1/trip-manual-previews", let body else { throw PreviewFailure.invalidInput }
        let generated = try await Data(collecting: body, upTo: endpoint.maximumRequestBytes)
        try await validate()
        // Use the official generated request, checking it against the frozen generated model.
        let decoded = try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self, from: generated)
        guard try encoded(decoded) == requestBytes else { throw PreviewFailure.invalidInput }
        var outgoing = request; outgoing.headerFields[.authorization] = "Bearer " + bearer
        let (response, responseBody) = try await underlying.send(outgoing, body: HTTPBody(requestBytes), baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw PreviewFailure.invalidResponse }
        let bytes = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
        try await validate()
        var parser = StrictPreviewJSON(bytes: Array(bytes)); try parser.check()
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let caches = response.headerFields.filter { $0.name == .cacheControl }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              caches.count == 1, caches.first?.value == "no-store",
              let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let bodyTrace = object["request_id"] as? String, exact(trace, bodyTrace) else { throw PreviewFailure.invalidResponse }
        try await validate()
        return (response, HTTPBody(bytes))
    }
}
