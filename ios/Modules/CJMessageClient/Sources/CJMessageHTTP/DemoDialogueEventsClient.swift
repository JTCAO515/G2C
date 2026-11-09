import Foundation
import CJMessageClient
import HTTPTypes
import OpenAPIRuntime

public enum DemoDialogueEventsFailure: Error {
    case resyncRequired
}

/// Reads the original dialogue's event feed in the same current account lease.
@MainActor public final class DemoDialogueEventsClient {
    private let recovery: MessageRecovery
    private let scope: StorageScope
    private let endpoint: MessageEndpoint
    private let credentials: any MessageCredentialsProvider
    private let transport: NoRedirectTransport
    private let validateSession: @MainActor @Sendable () throws -> Void

    public convenience init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
                            credentials: any MessageCredentialsProvider,
                            validateSession: @escaping @MainActor @Sendable () throws -> Void) throws {
        let transport = try NoRedirectTransport.demoDialogueMessages(
            endpoint: endpoint, requestTimeout: 30, resourceTimeout: 150, validate: validateSession)
        self.init(recovery: recovery, scope: scope, endpoint: endpoint, credentials: credentials,
                  transport: transport, validateSession: validateSession)
    }

    init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
         credentials: any MessageCredentialsProvider, transport: NoRedirectTransport,
         validateSession: @escaping @MainActor @Sendable () throws -> Void) {
        self.recovery = recovery
        self.scope = scope
        self.endpoint = endpoint
        self.credentials = credentials
        self.transport = transport
        self.validateSession = validateSession
    }

    /// The caller supplies a message ID bound to its verified message or action
    /// receipt. Complete, original-bound frames are validated by the consumer.
    public func read(messageID: String, after cursor: String?, lease: Lease,
                     consume: @MainActor (Data) throws -> Void) async throws {
        try check(lease)
        if let cursor, !DemoDialogueRoute.validEventCursor(cursor) { throw MessageHTTPFailure.invalidConfiguration }
        let bearer = try await credentials.bearer(for: scope, lease: lease)
        try check(lease)
        guard let bearer else { throw MessageHTTPFailure.credentialsUnavailable }
        var parts = URLComponents()
        parts.path = DemoDialogueRoute.eventsPath
        parts.queryItems = [URLQueryItem(name: "message_id", value: messageID)]
        parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let path = parts.string else { throw MessageHTTPFailure.invalidConfiguration }
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
        request.headerFields[.authorization] = "Bearer " + bearer
        request.headerFields[.accept] = "text/event-stream"
        if let cursor { request.headerFields[HTTPField.Name("Last-Event-ID")!] = cursor }
        let (response, body) = try await transport.send(request, body: nil, baseURL: endpoint.url, operationID: DemoDialogueRoute.eventStream)
        try check(lease)
        let media = response.headerFields.filter { $0.name == .contentType }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        guard let body, media.count == 1, let contentType = media.first?.value.split(separator: ";").first?.lowercased(),
              traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil
        else { throw MessageHTTPFailure.invalidResponse }
        if response.status.code == 409 && contentType == "application/json" {
            let bytes = try await Data(collecting: body, upTo: min(endpoint.maximumResponseBytes, 4096))
            try check(lease)
            try validateUnambiguousJSON(bytes)
            guard let root = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  root["request_id"] as? String == trace,
                  let error = root["error"] as? [String: Any],
                  error["code"] as? String == "RESYNC_REQUIRED",
                  error["outcome"] as? String == "failed", error["recovery"] as? String == "retry_safe_read"
            else { throw MessageHTTPFailure.invalidResponse }
            throw DemoDialogueEventsFailure.resyncRequired
        }
        let controls = response.headerFields.filter { $0.name == .cacheControl }
        guard response.status.code == 200, contentType == "text/event-stream",
              controls.count == 1, controls.first?.value.lowercased() == "no-store"
        else { throw MessageHTTPFailure.invalidResponse }
        var remaining = endpoint.maximumResponseBytes
        for try await bytes in body {
            try check(lease)
            guard bytes.count <= remaining else { throw MessageHTTPFailure.invalidResponse }
            remaining -= bytes.count
            try consume(Data(bytes))
        }
        try check(lease)
    }

    private func check(_ lease: Lease) throws {
        try recovery.validateScope(scope, lease: lease)
        try validateSession()
        try Task.checkCancellation()
    }
}
