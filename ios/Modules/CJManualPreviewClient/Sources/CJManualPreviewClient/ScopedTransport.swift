import Foundation
import CJMessageHTTP
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

/// Exact C routes only, explicitly activated by the DEBUG simulator root.
/// Ordinary NoRedirectTransport remains read-only. No MESSAGE/model operation.
enum TripCandidateTransportProfile: Sendable { case scoped,needsPlanning,scopedDisplay }
final class ScopedTransport: ClientTransport, Sendable {
    private let session: URLSession
    private let transport: URLSessionTransport
    private let endpoint: URL
    private let validate: @MainActor @Sendable () throws -> Void
    private let profile:TripCandidateTransportProfile
    init(endpoint: MessageEndpoint,profile:TripCandidateTransportProfile = .scoped, validate: @escaping @MainActor @Sendable () throws -> Void) throws {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port) else { throw PreviewFailure.unavailable }
        self.endpoint = endpoint.url; self.validate = validate;self.profile=profile
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
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }) else { throw PreviewFailure.invalidInput }
        let permitted:Bool
        switch profile {
        case .scoped:
            permitted =
              (request.method == .get && body == nil && request.path?.hasPrefix("/v1/trip-scoped-discovery?") == true && operationID == "discoverScopedTripV1") ||
              (request.method == .get && body == nil && request.path?.hasPrefix("/v1/trip-scoped-action-receipts?") == true && operationID == "readScopedTripReceiptV1") ||
              (request.method == .get && body == nil && request.path?.hasPrefix("/v5/trip-structured?") == true && operationID == "readScopedFormalTripV1") ||
              (request.method == .post && body != nil && request.path == "/v1/trip-scoped-actions" && operationID == "actOnScopedTripV1")
        case .scopedDisplay:
            if request.method == .get,body == nil,operationID == "readScopedDisplayV1",let path=request.path,
               let parts=URLComponents(string:path),parts.path == "/v1/trip-scoped-results",parts.scheme == nil,parts.host == nil,parts.fragment == nil,
               let query=parts.queryItems,query.count == 1,query[0].name == "result_id",let id=query[0].value,
               id.range(of:"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",options:.regularExpression) == id.startIndex..<id.endIndex { permitted=true }
            else { permitted=false }
        case .needsPlanning:
            permitted =
              (request.method == .get && body == nil && request.path?.hasPrefix("/v1/trip-needs-discovery?") == true && operationID == "discoverNeedsPlanningV1") ||
              (request.method == .get && body == nil && request.path?.hasPrefix("/v1/trip-needs-action-receipts?") == true && operationID == "readNeedsPlanningReceiptV1") ||
              (request.method == .get && body == nil && request.path?.hasPrefix("/v5/trip-structured?") == true && operationID == "readNeedsPlanningFormalV1") ||
              (request.method == .post && body != nil && request.path == "/v1/trip-needs-actions" && operationID == "actOnNeedsPlanningV1")
        }
        guard permitted else { throw PreviewFailure.invalidInput }
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = nil }
        try await validate()
        return try await transport.send(request, body: bytes.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
    }
}
private final class ScopedRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? { nil }
}
