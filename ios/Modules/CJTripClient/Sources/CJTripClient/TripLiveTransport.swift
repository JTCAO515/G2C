import Foundation
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession
import CJMessageHTTP

/// Constructed only by the explicit TripLiveWrites initializer. The ordinary
/// NoRedirectTransport remains read-only; MESSAGE writes are never enabled here.
final class TripLiveTransport: ClientTransport, Sendable {
    private let reads: NoRedirectTransport
    private let endpoint: URL
    private let session: URLSession
    private let writes: URLSessionTransport

    init(reads: NoRedirectTransport, endpoint: URL) {
        self.reads = reads; self.endpoint = endpoint
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil
        configuration.urlCache = nil
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 60
        let session = URLSession(configuration: configuration, delegate: TripRedirectBlocker(), delegateQueue: nil)
        self.session = session
        writes = URLSessionTransport(configuration: .init(session: session))
    }

    deinit { session.invalidateAndCancel() }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        if request.method == .get || request.method == .head {
            return try await reads.send(request, body: body, baseURL: baseURL, operationID: operationID)
        }
        guard baseURL == endpoint, request.method == .post, body != nil,
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              (operationID == "prepareTripConfirmation" && request.path == "/v1/trip-confirmations") ||
              (operationID == "actOnTripProposal" && request.path == "/v1/trip-actions") else {
            throw TripFailure.liveWriteUnavailable
        }
        // TripTransport already checks the current lifetime and durable original
        // immediately before this call and validates/bounds the response afterward.
        return try await writes.send(request, body: body, baseURL: baseURL, operationID: operationID)
    }
}

private final class TripRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest) async -> URLRequest? { nil }
}
