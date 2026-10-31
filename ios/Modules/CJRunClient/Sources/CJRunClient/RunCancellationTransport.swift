import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

/// Explicit DEBUG Simulator capability for the frozen original-message cancellation.
/// The shared MESSAGE NoRedirectTransport remains unchanged and rejects this write.
public final class RunCancellationTransport: ClientTransport, Sendable {
    private enum WireMode { case legacy,travel,compatible }
    private let mode: WireMode
    private let endpoint: MessageEndpoint
    private let validate: @MainActor @Sendable () throws -> Void
    private let session: URLSession?
    private let intercepted: (any ClientTransport)?

    public static func development(endpoint: MessageEndpoint,
        validate: @escaping @MainActor @Sendable () throws -> Void) throws -> RunCancellationTransport {
        try local(endpoint:endpoint,mode:.legacy,validate:validate)
    }

    public static func developmentTravel(endpoint: MessageEndpoint,
        validate: @escaping @MainActor @Sendable () throws -> Void) throws -> RunCancellationTransport {
        try local(endpoint:endpoint,mode:.travel,validate:validate)
    }
    /// Explicit compatibility for original legacy and travel receipts. The
    /// canonical original selects its wire before dispatch; failures never retry
    /// under another wire, source or message ID.
    public static func developmentCompatible(endpoint: MessageEndpoint,
        validate: @escaping @MainActor @Sendable () throws -> Void) throws -> RunCancellationTransport {
        try local(endpoint:endpoint,mode:.compatible,validate:validate)
    }
    private static func local(endpoint: MessageEndpoint,mode: WireMode,
        validate: @escaping @MainActor @Sendable () throws -> Void) throws -> RunCancellationTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http",endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port,(1...65535).contains(port) else { throw RunDisplayFailure.invalidConfiguration }
        return RunCancellationTransport(endpoint:endpoint,mode:mode,validate:validate)
        #else
        throw RunDisplayFailure.invalidConfiguration
        #endif
    }

    private init(endpoint: MessageEndpoint, mode: WireMode, validate: @escaping @MainActor @Sendable () throws -> Void) {
        self.endpoint = endpoint; self.mode = mode; self.validate = validate; intercepted = nil
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil; configuration.urlCredentialStorage = nil; configuration.urlCache = nil
        configuration.timeoutIntervalForRequest = 10; configuration.timeoutIntervalForResource = 20
        session = URLSession(configuration: configuration, delegate: CancellationRedirectBlocker(), delegateQueue: nil)
    }
    /// Non-network module-test seam, never a product composition entry.
    init(interceptedTransport: any ClientTransport, endpoint: MessageEndpoint, travel: Bool = false,compatible: Bool = false,
         validate: @escaping @MainActor @Sendable () throws -> Void) {
        self.endpoint = endpoint;mode = compatible ? .compatible : travel ? .travel : .legacy;self.validate = validate
        session = nil; intercepted = interceptedTransport
    }
    deinit { session?.invalidateAndCancel() }

    /// An unbound transport call is not an original-action authorization.
    public func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL,
                     operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        throw RunDisplayFailure.invalidReference
    }
    func sendBound(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL,
                   operationID: String, validateOriginal: @escaping @MainActor @Sendable () throws -> Void) async throws -> (HTTPResponse, HTTPBody?) {
        let validateBinding: @Sendable () async throws -> Void = {
            try await self.validate()
            try await validateOriginal()
        }
        try await validateBinding(); try Task.checkCancellation()
        let travel: Bool
        switch operationID {
        case Operations.cancelOriginalRun.id:
            guard mode != .travel else { throw RunDisplayFailure.invalidReference };travel = false
        case Operations.cancelOriginalTravelRun.id:
            guard mode != .legacy else { throw RunDisplayFailure.invalidReference };travel = true
        default:throw RunDisplayFailure.invalidReference
        }
        guard baseURL == endpoint.url, request.method == .post,
              operationID == (travel ? Operations.cancelOriginalTravelRun.id : Operations.cancelOriginalRun.id),
              request.path == (travel ? "/v2/run-cancellations" : "/v1/run-cancellations"),
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body else {
            throw RunDisplayFailure.invalidReference
        }
        let media = request.headerFields.filter { $0.name == .contentType }
        guard media.count == 1, ["application/json", "application/json; charset=utf-8"].contains(media[0].value.lowercased()) else {
            throw RunDisplayFailure.invalidReference
        }
        let data = try await Data(collecting: body, upTo: min(endpoint.maximumRequestBytes,travel ? 65536 : 4096))
        var parser = StrictRunJSON(bytes: Array(data)); try parser.check()
        let messageID: String
        if travel { messageID = try JSONDecoder().decode(Components.Schemas.RunTravelCancellationRequest.self,from:data).message_id }
        else { messageID = try JSONDecoder().decode(Components.Schemas.RunCancellationRequest.self,from:data).message_id }
        guard !messageID.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,!messageID.utf8.contains(0),
              messageID.utf8.count <= (travel ? 16384 : 256),let path = request.path,
              let url = URL(string:path,relativeTo:endpoint.url) else { throw RunDisplayFailure.invalidReference }
        var outgoing = URLRequest(url: url.absoluteURL)
        outgoing.httpMethod = "POST"; outgoing.httpBody = data
        for field in request.headerFields { outgoing.addValue(field.value, forHTTPHeaderField: field.name.canonicalName) }
        try await validateBinding(); try Task.checkCancellation()
        if let intercepted {
            let (response, body) = try await intercepted.send(request, body: HTTPBody(data), baseURL: baseURL, operationID: operationID)
            try await validateBinding()
            guard !(300..<400).contains(response.status.code), let body else { throw RunDisplayFailure.invalidResponse }
            let result = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
            try await validateBinding(); try Task.checkCancellation()
            return (response, HTTPBody(result))
        }
        guard let session else { throw RunDisplayFailure.invalidConfiguration }
        let (bytes, response) = try await session.bytes(for: outgoing)
        guard let response = response as? HTTPURLResponse, !(300..<400).contains(response.statusCode) else {
            throw RunDisplayFailure.invalidResponse
        }
        var result = Data()
        for try await byte in bytes {
            guard result.count < endpoint.maximumResponseBytes else { throw RunDisplayFailure.invalidResponse }
            result.append(byte)
        }
        try await validateBinding(); try Task.checkCancellation()
        var output = HTTPResponse(status: .init(code: response.statusCode))
        for (key, value) in response.allHeaderFields {
            guard let name = HTTPField.Name(String(describing: key)) else { throw RunDisplayFailure.invalidResponse }
            output.headerFields.append(.init(name: name, value: String(describing: value)))
        }
        return (output, HTTPBody(result))
    }
}

private final class CancellationRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest) async -> URLRequest? { nil }
}
