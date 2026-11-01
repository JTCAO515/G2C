import Foundation
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

struct RunReadTransport: ClientTransport {
    var travel = false
    var discussion = false
    var edit = false
    var scopedResults = false
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let bearer: String
    let originalMessageID: String
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        try await validate()
        guard baseURL == endpoint.url, operationID == (edit ? (scopedResults ? "getTripEditRunDisplayV5" : "getTripEditRunDisplayV4") : discussion ? "getTripRunDisplayV3" : travel ? "getTravelRunDisplay" : "getRunDisplaySnapshot"), request.method == .get, body == nil,
              let path = request.path, let components = URLComponents(string: path), components.path == (edit ? (scopedResults ? "/v5/run-display" : "/v4/run-display") : discussion ? "/v3/run-display" : travel ? "/v2/run-display" : "/v1/run-display"),
              let query = components.queryItems, query.count == 1, query[0].name == "message_id",
              let id = query[0].value, exact(id, originalMessageID) else { throw RunDisplayFailure.invalidReference }
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        try await validate()
        let (response, body) = try await underlying.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let body else { throw RunDisplayFailure.invalidResponse }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let controls = response.headerFields.filter { $0.name.canonicalName == "cache-control" }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              controls.count == 1, controls.first?.value.lowercased() == "no-store" else { throw RunDisplayFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try await validate()
        var strict = StrictRunJSON(bytes: Array(bytes)); try strict.check()
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let requestID = object["request_id"] as? String, exact(requestID, trace) else { throw RunDisplayFailure.invalidResponse }
        return (response, HTTPBody(bytes))
    }
}
