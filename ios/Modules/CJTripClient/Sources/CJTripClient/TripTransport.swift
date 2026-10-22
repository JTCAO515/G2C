import Foundation
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

public typealias TripEndpoint = MessageEndpoint
public typealias TripCredentialCallback = @MainActor (TripBinding) async throws -> String?

struct TripTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: TripEndpoint
    let bearer: String
    let testWrites: Bool
    let detailCapture: TripDetailResponseCapture?
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let paths = ["getTripProposal": "/v1/trip-proposals", "getTrip": "/v1/trip-details", "listTrips": "/v1/trips",
                     "queryTripAction": "/v1/trip-action-receipts", "actOnTripProposal": "/v1/trip-actions"]
        guard baseURL == endpoint.url, let path = paths[operationID],
              request.path?.split(separator: "?", maxSplits: 1).first.map(String.init) == path,
              request.method == (operationID == "actOnTripProposal" ? .post : .get),
              operationID != "actOnTripProposal" || testWrites else { throw TripFailure.liveWriteUnavailable }
        var request = request; request.headerFields[.authorization] = "Bearer " + bearer
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: endpoint.maximumRequestBytes) } else { bytes = nil }
        try await validate()
        let (response, responseBody) = try await underlying.send(request, body: bytes.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw TripFailure.invalidResponse }
        let data = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
        try await validate()
        var strict = StrictTripJSON(bytes: Array(data)); try strict.check()
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let requestID = object["request_id"] as? String, same(trace, requestID) else { throw TripFailure.invalidResponse }
        if operationID == "getTrip", response.status.code == 200, let detailCapture {
            try await detailCapture.record(data, trace: trace)
            try await validate()
        }
        return (response, HTTPBody(data))
    }
}
