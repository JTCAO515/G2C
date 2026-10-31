import Foundation
import CJMessageHTTP
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

/// Exact C routes only, explicitly activated by the DEBUG simulator root.
/// Ordinary NoRedirectTransport remains read-only. No MESSAGE/model operation.
final class ScopedTransport: ClientTransport, Sendable {
    private let session: URLSession
    private let transport: URLSessionTransport
    private let endpoint: URL
    init(endpoint: MessageEndpoint) throws {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port) else { throw PreviewFailure.unavailable }
        self.endpoint = endpoint.url
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil; configuration.urlCache = nil; configuration.urlCredentialStorage = nil
        configuration.timeoutIntervalForRequest = 15; configuration.timeoutIntervalForResource = 30
        session = URLSession(configuration: configuration, delegate: ScopedRedirectBlocker(), delegateQueue: nil)
        transport = URLSessionTransport(configuration: .init(session: session))
        #else
        throw PreviewFailure.unavailable
        #endif
    }
    deinit { session.invalidateAndCancel() }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint, request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              (request.method == .get && body == nil && request.path?.hasPrefix("/v1/trip-scoped-discovery?") == true && operationID == "discoverScopedTripV1") ||
              (request.method == .get && body == nil && request.path?.hasPrefix("/v1/trip-scoped-action-receipts?") == true && operationID == "readScopedTripReceiptV1") ||
              (request.method == .get && body == nil && request.path?.hasPrefix("/v5/trip-structured?") == true && operationID == "readScopedFormalTripV1") ||
              (request.method == .post && body != nil && request.path == "/v1/trip-scoped-actions" && operationID == "actOnScopedTripV1") else { throw PreviewFailure.invalidInput }
        return try await transport.send(request, body: body, baseURL: baseURL, operationID: operationID)
    }
}
private final class ScopedRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? { nil }
}
