#if DEBUG && targetEnvironment(simulator)
import Foundation
import CJShell
import CJTripClient
import CJMessageHTTP
import CJMessageKeys
import CJSession
import CJAPI
import HTTPTypes
import OpenAPIRuntime
import Observation

@MainActor struct DevelopmentSessionLease {
    let session: SessionLifecycle
    let operation: SessionOperation
}

@MainActor private final class DevelopmentSessionPersistence: SessionPersistence {
    private var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}

@MainActor private final class DevelopmentLifetime {
    var active = true
    let session: SessionLifecycle
    let operation: SessionOperation
    let trip: TripBinding
    let shell: ShellState
    let generation: ShellGeneration
    let ownsSession: Bool
    init(configuration: DevelopmentSessionConfiguration, shell: ShellState, lease: DevelopmentSessionLease?) throws {
        self.shell = shell; generation = shell.generation
        ownsSession = lease == nil
        if let lease {
            guard lease.session.isCurrent(lease.operation) else { throw SessionFailure.staleOperation }
            session = lease.session; operation = lease.operation
        } else {
            session = SessionLifecycle(persistence: DevelopmentSessionPersistence(), restorePolicy: .userInitiatedOnly)
            operation = try session.beginTrustedSDKSave()
            try session.save(SessionMaterial(trustedSDKBytes: Data(configuration.token.utf8)), for: operation)
        }
        trip = TripBinding(environment: configuration.environmentID, account: configuration.accountID,
                           generation: UUID(), selection: UUID())
    }
    var current: TripBinding? {
        active && session.isCurrent(operation) && shell.generation == generation ? trip : nil
    }
}

/// Only this explicitly configured DEBUG simulator root grants TripLiveWrites.
/// It uses the signed app_from_environment local fixture, never a production host.
@MainActor final class DevelopmentTripHost {
    let id = UUID()
    let trips: TripContainerHost
    private let lifetime: DevelopmentLifetime
    private let keys: ScopedMessageKeyProvider

    init(configuration: DevelopmentSessionConfiguration, shell: ShellState, lease: DevelopmentSessionLease? = nil) throws {
        let endpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: 4096,
            maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
        let lifetime = try DevelopmentLifetime(configuration: configuration, shell: shell, lease: lease)
        self.lifetime = lifetime
        let namespace = MessageKeyNamespace(environment: lifetime.trip.environment, account: lifetime.trip.account,
                                             purpose: .localTripPendingV1)
        guard let applicationID = Bundle.main.bundleIdentifier else { throw TripFailure.unconfigured }
        keys = try ScopedMessageKeyProvider(namespace: namespace, applicationIdentifier: applicationID,
                                             protection: .whenUnlockedThisDeviceOnly)
        let files = FileManager.default
        let support = try files.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                    appropriateFor: nil, create: true)
        let directory = support.appendingPathComponent("G2CDevelopmentTrip", isDirectory: true)
            .appendingPathComponent(namespace.environment.uuidString, isDirectory: true)
            .appendingPathComponent(namespace.account.uuidString, isDirectory: true)
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let root = directory.resolvingSymlinksInPath()
        let existing = try keys.existing(expectedID: nil, for: keys.begin(.lookup))
        let key: MessageEncryptionKey
        if let existing { key = existing }
        else {
            guard try files.contentsOfDirectory(atPath: root.path).isEmpty else { throw TripFailure.keyUnavailable }
            key = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
        }
        let store = try TripPendingStore(directory: root, maximumBytes: 1_000_000, maximumRecords: 100,
            binding: lifetime.trip, expectedKeyID: key.id, provider: keys)
        let transport = try NoRedirectTransport(requestTimeout: 10, resourceTimeout: 20)
        let client = TripClient(endpoint: endpoint, credentials: { binding in
            guard lifetime.current == binding else { return nil }
            return configuration.token
        }, currentBinding: { lifetime.current }, session: lifetime.session, sessionOperation: lifetime.operation,
            pendingStore: store, liveTransport: transport, liveWrites: TripLiveWrites())
        trips = TripContainerHost(shell: shell)
        guard trips.bind(TripContainerBinding(client: client, trip: lifetime.trip, shellGeneration: shell.generation,
            session: lifetime.session, sessionOperation: lifetime.operation, pageSize: 20,
            proposalID: configuration.proposalID, synthetic: false, currentBinding: { lifetime.current })) else {
            throw TripFailure.staleBinding
        }
        shell.selectedTab = .trips
        // Disk restoration only selects an original action for GET reconciliation;
        // it never prepares or submits another action, even while the API is offline.
        trips.loadPending(context: trips.captureAction())
        if let original = trips.presentation?.pendingActions.first,
           trips.selectPending(original.actionID, context: trips.captureAction()) {
            shell.tripPath = [.originalAction]
        }
    }

    func invalidate() {
        lifetime.active = false
        trips.invalidate()
        keys.invalidate()
        if lifetime.ownsSession { _ = lifetime.session.clearWithSettlement() }
    }
}

/// Explicit DEBUG simulator account root; its volatile tokens are never UI state or preferences.
@MainActor @Observable final class DevelopmentAccountRoot {
    var trip: DevelopmentTripHost?
    private let shell: ShellState
    private let endpoint: URL
    private let proposalID: String?
    private let tokens: [String: String]
    private let persistence: KeychainSessionStore
    @ObservationIgnored lazy var accounts: DevelopmentAccountHost = {
        DevelopmentAccountHost(shell: shell,
            choices: tokens.keys.sorted().map { .init(id: $0, label: $0) }, persistence: persistence,
            material: { [weak self] choice in
                guard let token = self?.tokens[choice] else { throw SessionFailure.invalidConfiguration }
                return try SessionMaterial(trustedSDKBytes: Data(token.utf8))
            }, verify: { [weak self] material in
                guard let self else { return .networkUnknown }
                return await self.verify(material)
            }, activate: { [weak self] material, session, operation in
                guard let self, let configuration = self.configuration(material) else { throw SessionFailure.invalidConfiguration }
                self.trip = try DevelopmentTripHost(configuration: configuration, shell: self.shell,
                    lease: DevelopmentSessionLease(session: session, operation: operation))
                self.shell.selectedTab = .memory
                self.shell.memoryPath = [.account]
            }, invalidate: { [weak self] in self?.trip?.invalidate(); self?.trip = nil })
    }()

    init(environment: [String: String], shell: ShellState) throws {
        guard environment["G2C_DEV_ACCOUNT_MODE"] == "1",
              let endpoint = DevelopmentSessionConfiguration.readEndpoint(environment),
              let raw = (environment["G2C_DEV_ACCOUNTS"] ?? "{}").data(using: .utf8), raw.count <= 131072,
              let tokens = try JSONSerialization.jsonObject(with: raw) as? [String: String], tokens.count <= 8,
              tokens.keys.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              let applicationID = Bundle.main.bundleIdentifier else { throw SessionFailure.invalidConfiguration }
        self.shell = shell; self.endpoint = endpoint; self.tokens = tokens
        proposalID = environment["G2C_DEV_PROPOSAL_ID"]
        let scope = try KeychainSessionScope(namespace: SessionNamespace(
            environment: DevelopmentSessionConfiguration.environmentNamespace(endpoint), slot: "M1.Development.Active"),
            applicationIdentifier: applicationID)
        persistence = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly)
    }

    private func configuration(_ material: SessionMaterial) -> DevelopmentSessionConfiguration? {
        material.withBytes { bytes in
            guard let token = String(data: bytes, encoding: .utf8) else { return nil }
            var environment = ["G2C_DEV_API_BASE_URL": endpoint.absoluteString, "G2C_DEV_TOKEN": token]
            if let proposalID { environment["G2C_DEV_PROPOSAL_ID"] = proposalID }
            return DevelopmentSessionConfiguration.read(environment)
        }
    }

    private func verify(_ material: SessionMaterial) async -> DevelopmentSessionCheck {
        guard let configuration = configuration(material) else { return .rejected }
        // Untrusted token metadata can deny an expired attempt, never authorize one.
        if let expiry = configuration.expiresAt, expiry <= Date().timeIntervalSince1970 { return .expired }
        do {
            let transport = try DevelopmentVerificationTransport(endpoint: endpoint, token: configuration.token)
            let client = Client(serverURL: endpoint, transport: transport)
            let result = try await client.queryMessageReceipt(.init(query: .init(message_id: "session-" + UUID().uuidString)))
            try Task.checkCancellation()
            switch result {
            case .ok(let response):
                let body = try response.body.json
                guard UUID(uuidString: body.request_id) != nil,
                      body.request_id == response.headers.X_hyphen_Request_hyphen_ID else { return .networkUnknown }
                return .accepted(account: configuration.subject)
            case .default(let status, _): return status == 401 || status == 403 ? .rejected : .networkUnknown
            }
        } catch { return .networkUnknown }
    }
}

private struct DevelopmentVerificationTransport: ClientTransport {
    let endpoint: URL
    private let token: String
    private let transport: NoRedirectTransport
    init(endpoint: URL, token: String) throws {
        self.endpoint = endpoint; self.token = token
        transport = try NoRedirectTransport(requestTimeout: 5, resourceTimeout: 10)
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard baseURL == endpoint, request.method == .get, request.scheme == nil, request.authority == nil,
              operationID == Operations.queryMessageReceipt.id,
              request.path?.hasPrefix("/v1/message-receipts?") == true, body == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }) else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        var request = request; request.headerFields[.authorization] = "Bearer " + token
        try Task.checkCancellation()
        let (response, body) = try await transport.send(request, body: nil, baseURL: baseURL, operationID: operationID)
        guard !(300..<400).contains(response.status.code), let body else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: 16384)
        try Task.checkCancellation()
        return (response, HTTPBody(bytes))
    }
}
#endif
