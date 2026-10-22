import Foundation
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

public typealias FeedbackEndpoint = MessageEndpoint
public typealias FeedbackCredentialCallback = @MainActor (FeedbackBinding) async throws -> String?

struct FeedbackTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: FeedbackEndpoint
    let bearer: String
    let testWrites: Bool
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let submitting = operationID == "submitFeedback"
        guard baseURL == endpoint.url,
              submitting || operationID == "queryFeedbackAction",
              request.path?.split(separator: "?", maxSplits: 1).first.map(String.init) == (submitting ? "/v1/feedback" : "/v1/feedback-action-receipts"),
              request.method == (submitting ? .post : .get), !submitting || testWrites else { throw FeedbackFailure.liveWriteUnavailable }
        var request = request; request.headerFields[.authorization] = "Bearer " + bearer
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: min(16384, endpoint.maximumRequestBytes)) } else { bytes = nil }
        try await validate()
        let (response, responseBody) = try await underlying.send(request, body: bytes.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw FeedbackFailure.invalidResponse }
        let data = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
        try await validate()
        var strict = StrictFeedbackJSON(bytes: Array(data)); try strict.check()
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let requestID = object["request_id"] as? String, same(trace, requestID) else { throw FeedbackFailure.invalidResponse }
        return (response, HTTPBody(data))
    }
}
