import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

/// Explicit DEBUG Simulator capability for the frozen original-message cancellation.
/// The shared MESSAGE NoRedirectTransport remains unchanged and rejects this write.
public final class RunCancellationTransport: ClientTransport, Sendable {
    private let endpoint: MessageEndpoint
    private let validate: @MainActor @Sendable () throws -> Void
    private let session: URLSession?
    private let intercepted: (any ClientTransport)?

    public static func development(endpoint: MessageEndpoint,
        validate: @escaping @MainActor @Sendable () throws -> Void) throws -> RunCancellationTransport {
        #if DEBUG && targetEnvironment(simulator)
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port) else { throw RunDisplayFailure.invalidConfiguration }
        return RunCancellationTransport(endpoint: endpoint, validate: validate)
        #else
        throw RunDisplayFailure.invalidConfiguration
        #endif
    }

    private init(endpoint: MessageEndpoint, validate: @escaping @MainActor @Sendable () throws -> Void) {
        self.endpoint = endpoint; self.validate = validate; intercepted = nil
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil; configuration.urlCredentialStorage = nil; configuration.urlCache = nil
        configuration.timeoutIntervalForRequest = 10; configuration.timeoutIntervalForResource = 20
        session = URLSession(configuration: configuration, delegate: CancellationRedirectBlocker(), delegateQueue: nil)
    }
    /// Non-network module-test seam, never a product composition entry.
    init(interceptedTransport: any ClientTransport, endpoint: MessageEndpoint,
         validate: @escaping @MainActor @Sendable () throws -> Void) {
        self.endpoint = endpoint; self.validate = validate
        session = nil; intercepted = interceptedTransport
    }
    deinit { session?.invalidateAndCancel() }

    public func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL,
                     operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        try await validate(); try Task.checkCancellation()
        guard baseURL == endpoint.url, request.method == .post,
              operationID == Operations.cancelOriginalRun.id, request.path == "/v1/run-cancellations",
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }), let body else {
            throw RunDisplayFailure.invalidReference
        }
        let media = request.headerFields.filter { $0.name == .contentType }
        guard media.count == 1, ["application/json", "application/json; charset=utf-8"].contains(media[0].value.lowercased()) else {
            throw RunDisplayFailure.invalidReference
        }
        let data = try await Data(collecting: body, upTo: min(endpoint.maximumRequestBytes, 4096))
        var parser = StrictRunJSON(bytes: Array(data)); try parser.check()
        let input = try JSONDecoder().decode(Components.Schemas.RunCancellationRequest.self, from: data)
        guard !input.message_id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !input.message_id.utf8.contains(0), input.message_id.utf8.count <= 256,
              let url = URL(string: "/v1/run-cancellations", relativeTo: endpoint.url) else { throw RunDisplayFailure.invalidReference }
        var outgoing = URLRequest(url: url.absoluteURL)
        outgoing.httpMethod = "POST"; outgoing.httpBody = data
        for field in request.headerFields { outgoing.addValue(field.value, forHTTPHeaderField: field.name.canonicalName) }
        try await validate(); try Task.checkCancellation()
        if let intercepted {
            let (response, body) = try await intercepted.send(request, body: HTTPBody(data), baseURL: baseURL, operationID: operationID)
            try await validate()
            guard !(300..<400).contains(response.status.code), let body else { throw RunDisplayFailure.invalidResponse }
            let result = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
            try await validate(); try Task.checkCancellation()
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
        try await validate(); try Task.checkCancellation()
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
