import Foundation
import CJMessageClient
import CJAPI
import OpenAPIRuntime
import OpenAPIURLSession
import HTTPTypes

public enum MessageHTTPFailure: Error { case invalidConfiguration, credentialsUnavailable, invalidResponse, redirectRejected, queryGeneratedFieldMissing, exchangeUnknown }

public struct MessageEndpoint: Sendable {
    public let url: URL
    public let maximumRequestBytes: Int
    public let maximumResponseBytes: Int
    public init(url: URL, maximumRequestBytes: Int, maximumResponseBytes: Int, allowLoopbackHTTP: Bool = false) throws {
        let local = allowLoopbackHTTP && url.scheme == "http" && url.host == "127.0.0.1" && url.port != nil
        guard url.scheme == "https" || local, url.host != nil, url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, ["", "/"].contains(url.path), maximumRequestBytes > 0, maximumResponseBytes > 0 else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        self.url = url; self.maximumRequestBytes = maximumRequestBytes; self.maximumResponseBytes = maximumResponseBytes
    }
}

@MainActor public protocol MessageCredentialsProvider: AnyObject {
    /// Trusted host provides only current credentials. No default or token persistence.
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String?
}

/// Injectable transport must not follow redirects. Live networking is explicitly created
/// via NoRedirectTransport, never defaulted. Tests inject an in-process interceptor only.
struct CheckedTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MessageEndpoint
    let bearer: String
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint.url,
              (operationID == "receiveMessage" && request.method == .post && request.path == "/v1/messages") ||
              (operationID == "queryMessageReceipt" && request.method == .get && request.path?.hasPrefix("/v1/message-receipts?") == true) else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        let (response, body) = try await underlying.send(request, body: body, baseURL: baseURL, operationID: operationID)
        guard !(300..<400).contains(response.status.code) else { throw MessageHTTPFailure.redirectRejected }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        guard traces.count == 1, let header = traces.first?.value, UUID(uuidString: header) != nil,
              let body else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        var parser = StrictJSON(bytes: Array(bytes)); try parser.check()
        guard let json = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let trace = json["request_id"] as? String, trace == header else { throw MessageHTTPFailure.invalidResponse }
        return (response, HTTPBody(bytes))
    }
}

public final class NoRedirectTransport: ClientTransport, Sendable {
    private let session: URLSession
    private let transport: URLSessionTransport
    public init(requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        guard requestTimeout > 0, resourceTimeout > 0 else { throw MessageHTTPFailure.invalidConfiguration }
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil; config.urlCache = nil; config.urlCredentialStorage = nil
        config.timeoutIntervalForRequest = requestTimeout; config.timeoutIntervalForResource = resourceTimeout
        let session = URLSession(configuration: config, delegate: RedirectBlocker(), delegateQueue: nil)
        self.session = session; transport = URLSessionTransport(configuration: .init(session: session))
    }
    deinit { session.invalidateAndCancel() }
    public func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        try await transport.send(request, body: body, baseURL: baseURL, operationID: operationID)
    }
}
private final class RedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest) async -> URLRequest? { nil }
}

public enum MessageHTTPOutcome: Sendable {
    case accepted
    case rejected(status: Int, error: Components.Schemas.ErrorResponse)
}

@MainActor public final class MessageHTTPClient {
    private let recovery: MessageRecovery
    private let scope: StorageScope
    private let endpoint: MessageEndpoint
    private let credentials: any MessageCredentialsProvider
    private let transport: any ClientTransport
    public init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
                credentials: any MessageCredentialsProvider, transport: any ClientTransport) {
        self.recovery = recovery; self.scope = scope; self.endpoint = endpoint
        self.credentials = credentials; self.transport = transport
    }
    private func client(_ lease: Lease) async throws -> Client {
        try recovery.validateScope(scope, lease: lease)
        let value = try await credentials.bearer(for: scope, lease: lease)
        try recovery.validateScope(scope, lease: lease)
        guard let value, !value.isEmpty, value.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MessageHTTPFailure.credentialsUnavailable }
        return Client(serverURL: endpoint.url, transport: CheckedTransport(underlying: transport, endpoint: endpoint, bearer: value))
    }
    public func submit(messageID: String, lease: Lease) async throws -> MessageHTTPOutcome {
        let client = try await client(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease),
              record.originalUTF8.count <= endpoint.maximumRequestBytes else { throw RecoveryError.invalidInput }
        var original = StrictJSON(bytes: Array(record.originalUTF8)); try original.check()
        guard let envelope = try JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any],
              let originalID = envelope["message_id"] as? String, Data(originalID.utf8) == Data(messageID.utf8),
              let conversationID = envelope["conversation_id"] as? String, !conversationID.isEmpty else {
            throw RecoveryError.invalidInput
        }
        let submission = try recovery.beginSubmission(messageID: messageID, lease: lease)
        let output: Operations.receiveMessage.Output
        do { output = try await client.receiveMessage(.init(body: .binary(HTTPBody(submission.originalUTF8)))) }
        catch {
            try recovery.observeUnknown(submission.operation)
            // Generated ClientError may carry an Authorization-bearing request; do not
            // expose it through this public boundary or turn it into a retry instruction.
            throw MessageHTTPFailure.exchangeUnknown
        }
        switch output {
        case .ok(let response):
            let body = try response.body.json
            let receipt = body.receipt
            guard Data(receipt.conversation_id.utf8) == Data(conversationID.utf8), !receipt.generation.isEmpty, !receipt.run_id.isEmpty,
                  receipt.sequence > 0 else {
                try recovery.observeUnknown(submission.operation); throw MessageHTTPFailure.invalidResponse
            }
            try recovery.observeReceipt(submission.operation, messageID: receipt.message_id,
                                        inputSHA256: receipt.input_sha256, receipt: JSONEncoder().encode(receipt))
            return .accepted
        case .default(let status, let response):
            try recovery.observeUnknown(submission.operation)
            return .rejected(status: status, error: try response.body.json)
        }
    }
    public func query(messageID: String, lease: Lease) async throws {
        try recovery.validateScope(scope, lease: lease)
        // d886677's generated MessageReceiptQueryResponse omits receipt entirely.
        // Never parse a substitute wire model or turn that absence into notObserved.
        throw MessageHTTPFailure.queryGeneratedFieldMissing
    }
}
