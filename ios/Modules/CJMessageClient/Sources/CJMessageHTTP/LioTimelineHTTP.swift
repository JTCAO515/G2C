import CJMessageClient
import Foundation
import HTTPTypes
import Network
import OpenAPIRuntime

/// Uses the signed Beta endpoint and the existing account-bound credential provider.
@MainActor
public final class LioTimelineHTTP {
    public enum Acceptance: Sendable {
        case accepted(conversationID: String)
        case notSent, dailyLimit
    }

    private let scope: StorageScope
    private let lease: Lease
    private let credentials: any MessageCredentialsProvider
    private let transport: NoRedirectTransport
    private let connectivity: LioConnectivity?

    public convenience init(endpoint: MessageEndpoint, scope: StorageScope, lease: Lease,
                            credentials: any MessageCredentialsProvider,
                            validate: @escaping @MainActor @Sendable () throws -> Void) throws {
        let transport = try NoRedirectTransport.lioTimeline(endpoint: endpoint, validate: validate)
        self.init(scope: scope, lease: lease, credentials: credentials, transport: transport, monitorNetwork: true)
    }

    init(scope: StorageScope, lease: Lease, credentials: any MessageCredentialsProvider,
         transport: NoRedirectTransport, monitorNetwork: Bool = false) {
        self.scope = scope
        self.lease = lease
        self.credentials = credentials
        self.transport = transport
        connectivity = monitorNetwork ? LioConnectivity() : nil
    }

    public func submit(_ original: LioTimelineWire.Send) async throws -> Acceptance {
        let token = try await bearer()
        if connectivity?.offline == true { return .notSent }
        let (response, body) = try await transport.sendLio(original, bearer: token)
        let bytes = try await json(response, body, limit: 65_536)
        if response.status.code == 429 {
            try validateUnambiguousJSON(bytes)
            guard try JSONDecoder().decode(Failure.self, from: bytes).failure == "quota" else {
                throw MessageHTTPFailure.invalidResponse
            }
            return .dailyLimit
        }
        guard response.status.code == 200 else { throw MessageHTTPFailure.exchangeUnknown }
        return .accepted(conversationID: try original.confirm(bytes))
    }

    public func timeline(conversationID: String? = nil, before: String? = nil,
                         version: LioTimelineWire.Version = .v1) async throws -> LioTimelineWire.Page {
        let token = try await bearer()
        let (response, body) = try await transport.readLio(conversationID: conversationID, before: before, bearer: token, version: version)
        guard response.status.code == 200 else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await json(response, body, limit: 4_500_000)
        let page = try LioTimelineWire.decodePage(bytes, for: conversationID, version: version)
        if let before, page.messages.contains(where: { $0.id.utf8.elementsEqual(before.utf8) }) {
            throw MessageHTTPFailure.invalidResponse
        }
        return page
    }

    func tripHistory(before: String?) async throws -> LioTripHistoryWire.Page {
        let token = try await bearer()
        let (response, body) = try await transport.readLioTrip(before: before, bearer: token)
        guard response.status.code == 200 else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await json(response, body, limit: 4_500_000)
        return try LioTripHistoryWire.decodePage(bytes, before: before)
    }

    func submitUndo(_ undo: LioTripHistoryWire.Undo) async throws -> LioTripHistoryClient.SubmissionResult {
        let token = try await bearer()
        let (response, body) = try await transport.sendLioUndo(undo, bearer: token)
        let bytes = try await json(response, body, limit: 65_536)
        switch response.status.code {
        case 200:
            guard try undo.committed(bytes) else { throw MessageHTTPFailure.exchangeUnknown }
            return .committed(bytes)
        case 409:
            try validateUnambiguousJSON(bytes)
            guard try JSONDecoder().decode(Failure.self, from: bytes).failure == "unavailable" else {
                throw MessageHTTPFailure.exchangeUnknown
            }
            return .conflict(bytes)
        default:
            throw MessageHTTPFailure.exchangeUnknown
        }
    }

    func readUndo(_ undo: LioTripHistoryWire.Undo) async throws -> Data? {
        let token = try await bearer()
        let (response, body) = try await transport.readLioUndo(undo, bearer: token)
        guard response.status.code == 200 else { throw MessageHTTPFailure.exchangeUnknown }
        let bytes = try await json(response, body, limit: 65_536)
        return try undo.committed(bytes) ? bytes : nil
    }

    func submitMemoryChoice(_ action: LioMemoryWire.Action) async throws -> LioMemoryActionsClient.SubmissionResult {
        let token = try await bearer()
        let (response, body) = try await transport.sendLioMemoryChoice(action, bearer: token)
        let bytes = try await json(response, body, limit: 65_536)
        switch response.status.code {
        case 200: return .receipt(bytes)
        case 409:
            try validateUnambiguousJSON(bytes)
            guard try JSONDecoder().decode(Failure.self, from: bytes).failure == "unavailable" else {
                throw MessageHTTPFailure.exchangeUnknown
            }
            return .conflict(bytes)
        default:
            throw MessageHTTPFailure.exchangeUnknown
        }
    }

    func readMemoryChoice(_ action: LioMemoryWire.Action) async throws -> Data {
        let token = try await bearer()
        let (response, body) = try await transport.readLioMemoryChoice(action, bearer: token)
        guard response.status.code == 200 else { throw MessageHTTPFailure.exchangeUnknown }
        return try await json(response, body, limit: 65_536)
    }

    private func bearer() async throws -> String {
        guard let token = try await credentials.bearer(for: scope, lease: lease),
              !token.isEmpty, !token.contains(","), !token.contains(where: \.isWhitespace) else {
            throw MessageHTTPFailure.credentialsUnavailable
        }
        return token
    }

    private func json(_ response: HTTPResponse, _ body: HTTPBody?, limit: Int) async throws -> Data {
        guard response.headerFields[.contentType]?.split(separator: ";").first?.lowercased() == "application/json",
              let body else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: limit)
        try Task.checkCancellation()
        return bytes
    }

    private struct Failure: Decodable { let failure: String }
}


/// A known absence of a network path before a POST permits an explicit resend.
/// Errors returned after invoking the transport remain uncertain.
@MainActor
private final class LioConnectivity {
    private let monitor = NWPathMonitor()
    private(set) var offline = false

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let offline = path.status == .unsatisfied
            Task { @MainActor in self?.offline = offline }
        }
        monitor.start(queue: DispatchQueue(label: "g2c.lio.connectivity"))
    }

    deinit { monitor.cancel() }
}
