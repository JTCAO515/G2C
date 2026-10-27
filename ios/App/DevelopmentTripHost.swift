#if DEBUG && targetEnvironment(simulator)
import Foundation
import CJShell
import CJTripClient
import CJMessageHTTP
import CJMessageKeys
import CJSession

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
    init(configuration: DevelopmentSessionConfiguration, shell: ShellState) throws {
        self.shell = shell; generation = shell.generation
        session = SessionLifecycle(persistence: DevelopmentSessionPersistence(), restorePolicy: .userInitiatedOnly)
        operation = try session.beginTrustedSDKSave()
        try session.save(SessionMaterial(trustedSDKBytes: Data(configuration.token.utf8)), for: operation)
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

    init(configuration: DevelopmentSessionConfiguration, shell: ShellState) throws {
        let endpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: 4096,
            maximumResponseBytes: 1_000_000, allowLoopbackHTTP: true)
        let lifetime = try DevelopmentLifetime(configuration: configuration, shell: shell)
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
        _ = lifetime.session.clearWithSettlement() // memory only; not a Keychain session
    }
}
#endif
