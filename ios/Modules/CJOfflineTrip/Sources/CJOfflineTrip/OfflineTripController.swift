import Foundation
import Observation
import CJTripClient
import CJSession
import CJMessageKeys

public struct OfflineTripRead: Sendable {
    public let namespace: OfflineNamespace
    public let version: Int64
    public let syncedAt: Int64
    public let deadline: Int64
    public let responseHash: String
    public let content: OfflineTripContent
}
public enum OfflineTripState: Sendable {
    case idle, missing, expired, untrustedTime, unavailable, storageFailure
    case readable(OfflineTripRead)
}
public enum OfflineSyncState: Sendable, Equatable { case idle, synchronizing, saved, failed, unknown }

/// Sealed evidence of storage provisioned while staging an accepted formal source.
/// This is not a read/cleanup grant and contains no key or SDK credential.
public struct OfflineTripStorageProvision: Sendable {
    public let namespace: OfflineNamespace
    public let keyID: UUID
    fileprivate let anchor: OfflineAnchor
    fileprivate let token: UUID
}

/// Protected metadata is an offline-read grant for one already-synced response,
/// never an AUTH session, ordinary API permission or a cleanup operation receipt.
struct OfflineAnchor: Codable, Equatable, Sendable {
    let namespace: OfflineNamespace
    let keyID: UUID
    let version: Int64
    let responseHash: String
    let sessionHash: String
    let syncedAt: Int64
    let deadline: Int64
    let boot: UUID
    let uptimeAtSync: Double
    var lastWall: Int64
    var readAllowed: Bool
}

@MainActor private final class UsedOfflineSource {
    weak var source: AnyObject?
    init(_ source: AnyObject) { self.source = source }
}

@MainActor private final class OfflineReadSession: SessionPersistence {
    var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}

/// Network-free reader. Only sealed TripClient source handles can write a cache.
/// The App's explicit read may inspect protected local material, but cannot restore
/// ordinary business permission. Logout/switch clears the grant before file removal.
@Observable @MainActor public final class OfflineTripController {
    @ObservationIgnored private var stateValue: (UUID, OfflineTripState)?
    @ObservationIgnored private var syncValue: (UUID, OfflineSyncState)?
    public private(set) var state: OfflineTripState {
        get {
            access(keyPath: \.state)
            guard !blocked, !clearing else { return .unavailable }
            guard let value = stateValue else { return .idle }
            return value.0 == generation ? value.1 : .unavailable
        }
        set {
            stateValue = (generation, newValue)
            withMutation(keyPath: \.state) {} // Publish after installation; callbacks cannot overwrite a replacement.
        }
    }
    public private(set) var syncState: OfflineSyncState {
        get { access(keyPath: \.syncState); guard let value = syncValue, value.0 == generation else { return .idle }; return value.1 }
        set { syncValue = (generation, newValue); withMutation(keyPath: \.syncState) {} }
    }
    private let environment: UUID
    private let root: URL
    private let anchors: any SessionPersistence
    private let sdkMaterial: () throws -> SessionMaterial?
    private let makeKeys: (MessageKeyNamespace) throws -> ScopedMessageKeyProvider
    private let clock: () -> OfflineClock?
    private let policy: OfflinePolicy?
    private let makeStore: (URL) throws -> AtomicSnapshotStore
    @ObservationIgnored private var generation = UUID()
    @ObservationIgnored private var inFlight = false
    @ObservationIgnored private var blocked = false
    @ObservationIgnored private var identityRejection: (@MainActor (SessionMaterial) async throws -> Void)?
    @ObservationIgnored private var storageProvision: (@MainActor (OfflineTripStorageProvision) -> Void)?
    @ObservationIgnored private var clearing = false
    private var stores: [UUID: AtomicSnapshotStore] = [:]
    private var providers: [UUID: ScopedMessageKeyProvider] = [:]
    private var displayed: OfflineSnapshot?
    private var displayedAnchor: OfflineAnchor?
    private var readSession: SessionLifecycle?
    private struct SynchronizationIdentity {
        let account: UUID
        let materialHash: String
        let session: SessionLifecycle
        let operation: SessionOperation
    }
    @ObservationIgnored private var synchronizationIdentity: SynchronizationIdentity?
    /// Only the trusted App root calls this after its actual signed identity check.
    /// It grants no cached read and does not write or renew the Keychain anchor.
    public func bindSynchronizationIdentity(material: SessionMaterial, account: UUID,
                                             session: SessionLifecycle, operation: SessionOperation) throws {
        guard session.isCurrent(operation), !inFlight, !clearing else { throw OfflineFailure.unavailable }
        synchronizationIdentity = .init(account: account, materialHash: materialHash(material), session: session, operation: operation)
    }
    private var usedSources: [UsedOfflineSource] = []
    private func claim(_ source: AnyObject) throws {
        usedSources.removeAll { $0.source == nil }
        guard !inFlight, !clearing, !usedSources.contains(where: { $0.source === source }) else {
            throw OfflineFailure.unavailable
        }
        usedSources.append(UsedOfflineSource(source))
    }

    init(environment: UUID, root: URL, anchors: any SessionPersistence,
         sdkMaterial: @escaping () throws -> SessionMaterial?,
         makeKeys: @escaping (MessageKeyNamespace) throws -> ScopedMessageKeyProvider,
         clock: @escaping () -> OfflineClock?, policy: OfflinePolicy?,
         makeStore: @escaping (URL) throws -> AtomicSnapshotStore = { try AtomicSnapshotStore(existingPrivateDirectory: $0) }) {
        self.environment = environment; self.root = root; self.anchors = anchors
        self.sdkMaterial = sdkMaterial; self.makeKeys = makeKeys; self.clock = clock; self.policy = policy; self.makeStore = makeStore
    }
    private func check(_ token: UUID) throws {
        guard generation == token, !blocked else { throw OfflineFailure.unavailable }
    }
    private func materialHash(_ material: SessionMaterial) -> String { material.withBytes(digest) }
    private func requireCurrentMaterial(_ expected: String, token: UUID) throws {
        let current = try sdkMaterial()
        try check(token)
        guard let current, materialHash(current) == expected else { throw OfflineFailure.unavailable }
    }
    private func loadAnchor() throws -> OfflineAnchor? {
        let value: SessionMaterial?
        do { value = try anchors.load() }
        catch SessionFailure.restorationBlocked { return nil }
        guard let value else { return nil }
        return try value.withBytes { bytes in
            guard bytes.count <= 8192 else { throw OfflineFailure.invalidSnapshot }
            var strict = StrictSnapshotJSON(bytes: Array(bytes)); try strict.check()
            let result = try JSONDecoder().decode(OfflineAnchor.self, from: bytes)
            guard result.namespace.backend == environment, validID(result.namespace.trip), result.version > 0,
                  result.syncedAt > 0, result.deadline > result.syncedAt,
                  result.lastWall >= result.syncedAt, result.uptimeAtSync.isFinite, result.uptimeAtSync >= 0,
                  result.responseHash.count == 64, result.sessionHash.count == 64,
                  try SnapshotCodec.encoder().encode(result) == bytes else { throw OfflineFailure.invalidSnapshot }
            return result
        }
    }
    private func saveAnchor(_ value: OfflineAnchor, token: UUID) throws {
        try check(token)
        let bytes = try SnapshotCodec.encoder().encode(value)
        try anchors.save(SessionMaterial(trustedSDKBytes: bytes))
        if generation != token {
            // This controller is the single anchor writer. A reentrant local clear
            // must stay durable even if an injected storage callback completed late.
            try anchors.clearAndBlock()
            throw OfflineFailure.unavailable
        }
        try check(token)
        let observed = try anchors.load()?.withBytes { $0 }
        try check(token)
        guard observed == bytes else { throw OfflineFailure.writeUnknown }
    }
    private func saveDeniedAnchor(_ value: OfflineAnchor, token: UUID) throws {
        guard !value.readAllowed, generation == token else { throw OfflineFailure.unavailable }
        let bytes = try SnapshotCodec.encoder().encode(value)
        try anchors.save(SessionMaterial(trustedSDKBytes: bytes))
        guard generation == token, try anchors.load()?.withBytes({ $0 }) == bytes else { throw OfflineFailure.writeUnknown }
    }
    private func store(_ account: UUID, create: Bool) throws -> AtomicSnapshotStore {
        if let existing = stores[account] { return existing }
        let directory = root.appendingPathComponent(account.uuidString, isDirectory: true)
        if create {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700])
            #if os(iOS)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: directory.path)
            #endif
        }
        let value = try makeStore(directory)
        stores[account] = value
        return value
    }
    private func keys(_ namespace: OfflineNamespace) throws -> ScopedMessageKeyProvider {
        if let value = providers[namespace.account] { return value }
        let value = try makeKeys(.init(environment: environment, account: namespace.account, purpose: .localOfflineTripSnapshotV1))
        providers[namespace.account] = value
        return value
    }
    private func sync(namespace: OfflineNamespace, session: SessionLifecycle, operation: SessionOperation,
                      capture: (AtomicSnapshotStore, ScopedMessageKeyProvider, UUID, OfflineSyncMetadata) throws -> AcceptedDetailSnapshotCache) throws {
        guard !inFlight, !clearing, session.isCurrent(operation), namespace.backend == environment, let policy,
              let identity = synchronizationIdentity, identity.account == namespace.account,
              identity.session === session, identity.operation == operation else {
            throw OfflineFailure.unavailable
        }
        inFlight = true; defer { inFlight = false }
        blocked = false
        let token = generation
        guard let material = try sdkMaterial(), let now = clock(), let wall = now.trustedWallSeconds else {
            throw OfflineFailure.unavailable
        }
        try check(token)
        guard materialHash(material) == identity.materialHash else { throw OfflineFailure.unavailable }
        // A wall clock below the old lastWall does not block this sync: the fresh
        // authenticated GET re-anchors syncedAt/deadline/boot/lastWall, and the
        // version check below still rejects an older server snapshot.
        let previous = try loadAnchor(); try check(token)
        let store = try store(namespace.account, create: true), provider = try keys(namespace)
        try check(token); try store.requireNoPendingWrite()
        let key: MessageEncryptionKey
        if let existing = try provider.existing(expectedID: nil, for: provider.begin(.lookup)) { key = existing }
        else {
            guard try store.read() == nil, previous?.namespace.account != namespace.account else {
                throw OfflineFailure.keyUnavailable
            }
            key = try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create))
        }
        try check(token)
        guard session.isCurrent(operation) else { throw OfflineFailure.unavailable }
        let sync = OfflineSyncMetadata(syncedAt: wall, deadline: try policy.deadline(syncedAt: wall), boot: now.boot, uptime: now.uptime)
        let original = try capture(store, provider, key.id, sync)
        if let previous, previous.namespace == namespace {
            guard original.snapshot.version >= previous.version else { throw OfflineFailure.rollback }
        }
        var anchor = OfflineAnchor(namespace: namespace, keyID: key.id, version: original.snapshot.version,
            responseHash: original.snapshot.metadata.responseHash, sessionHash: materialHash(material), syncedAt: wall,
            deadline: sync.deadline, boot: now.boot, uptimeAtSync: now.uptime, lastWall: wall, readAllowed: false)
        displayed = nil; displayedAnchor = nil; state = .unavailable
        try saveAnchor(anchor, token: token) // retain the exact denied target before any file commit
        storageProvision?(.init(namespace: anchor.namespace, keyID: anchor.keyID, anchor: anchor, token: token))
        try check(token)
        guard session.isCurrent(operation) else { throw OfflineFailure.unavailable }
        _ = try original.writeOnce()
        try check(token)
        guard session.isCurrent(operation) else { throw OfflineFailure.unavailable }
        try requireCurrentMaterial(identity.materialHash, token: token)
        anchor.readAllowed = true
        try saveAnchor(anchor, token: token)
        try requireCurrentMaterial(identity.materialHash, token: token)
        try check(token)
        storageProvision?(.init(namespace: anchor.namespace, keyID: anchor.keyID, anchor: anchor, token: token))
        try check(token); syncState = .saved
        // The next explicit local read revalidates the persisted pair before exposing text.
        displayed = nil; displayedAnchor = nil; state = .idle
        try check(token)
        guard session.isCurrent(operation) else { throw OfflineFailure.unavailable }
    }
    public func synchronize(client: TripClient, source: AcceptedTripDetailSnapshot,
                            session: SessionLifecycle, operation: SessionOperation) throws {
        let token = generation
        do {
            try claim(source)
            let namespace = try client.withCurrentDetailSnapshot(source) { _, record, _, binding in
                try OfflineNamespace(account: binding.account, backend: binding.environment, trip: record.trip_id)
            }
            try sync(namespace: namespace, session: session, operation: operation) { store, keys, id, sync in
                try AcceptedDetailSnapshotCache(client: client, accepted: source, store: store, provider: keys,
                    session: session, sessionOperation: operation, expectedKeyID: id, sync: sync)
            }
        } catch {
            if generation == token { syncState = error as? OfflineFailure == .writeUnknown ? .unknown : .failed }
            throw error
        }
    }
    public func synchronize(client: TripClient, source: AcceptedStructuredTripSnapshot,
                            session: SessionLifecycle, operation: SessionOperation) throws {
        let token = generation
        do {
            try claim(source)
            let namespace = try client.withCurrentStructuredSnapshot(source) { _, record, _, binding in
                try OfflineNamespace(account: binding.account, backend: binding.environment, trip: record.tripID)
            }
            try sync(namespace: namespace, session: session, operation: operation) { store, keys, id, sync in
                try AcceptedDetailSnapshotCache(client: client, accepted: source, store: store, provider: keys,
                    session: session, sessionOperation: operation, expectedKeyID: id, sync: sync)
            }
        } catch {
            if generation == token { syncState = error as? OfflineFailure == .writeUnknown ? .unknown : .failed }
            throw error
        }
    }
    public func readCached() {
        guard !inFlight, !clearing else { return }
        inFlight = true; defer { inFlight = false }
        displayed = nil; displayedAnchor = nil; state = .unavailable
        let token = generation
        do {
            try check(token)
            guard policy != nil else { return }
            guard let anchor = try loadAnchor() else { try check(token); state = .missing; return }
            guard anchor.readAllowed, let material = try sdkMaterial(), materialHash(material) == anchor.sessionHash else {
                throw OfflineFailure.unavailable
            }
            try check(token)
            guard let now = clock(), now.boot == anchor.boot else { state = .untrustedTime; return }
            let local = SessionLifecycle(persistence: OfflineReadSession(), restorePolicy: .userInitiatedOnly)
            let operation = try local.beginTrustedSDKSave(); try local.save(material, for: operation)
            readSession = local
            let access = try CanonicalSnapshotAccess(store: store(anchor.namespace.account, create: false),
                provider: keys(anchor.namespace), session: local, sessionOperation: operation,
                namespace: anchor.namespace, expectedKeyID: anchor.keyID, sourceToken: token,
                currentSource: { [weak self] in self?.generation })
            guard let snapshot = try access.read(minimumVersion: anchor.version),
                  snapshot.metadata.responseHash == anchor.responseHash, snapshot.syncedAt == anchor.syncedAt,
                  snapshot.metadata.deadline == anchor.deadline else { throw OfflineFailure.invalidSnapshot }
            try check(token)
            switch OfflineValidityEvaluator.evaluate(snapshot, active: anchor.namespace, policy: policy,
                clock: now, lastTrustedWall: anchor.lastWall, minimumVersion: anchor.version, sessionAllowsOffline: true) {
            case .readable:
                var updated = anchor; updated.lastWall = now.trustedWallSeconds!
                try requireCurrentMaterial(anchor.sessionHash, token: token)
                try saveAnchor(updated, token: token)
                try requireCurrentMaterial(anchor.sessionHash, token: token)
                displayed = snapshot; displayedAnchor = updated; publish(snapshot, anchor: updated)
            case .stale: state = .expired
            case .unavailable: state = .untrustedTime
            }
        } catch {
            guard token == generation else { return }
            state = error as? OfflineFailure == .unavailable ? .unavailable : .storageFailure
        }
    }
    private func publish(_ snapshot: OfflineSnapshot, anchor: OfflineAnchor) {
        state = .readable(.init(namespace: anchor.namespace, version: snapshot.version, syncedAt: snapshot.syncedAt,
            deadline: anchor.deadline, responseHash: anchor.responseHash, content: snapshot.content))
    }
    /// Timer checks only the clock; it performs no network or file write and cannot renew a grant.
    public func checkDisplayedTime() {
        guard let snapshot = displayed, var anchor = displayedAnchor else { return }
        guard !blocked, let now = clock(), now.boot == anchor.boot else { hide(); state = .untrustedTime; return }
        switch OfflineValidityEvaluator.evaluate(snapshot, active: anchor.namespace, policy: policy, clock: now,
            lastTrustedWall: anchor.lastWall, minimumVersion: anchor.version, sessionAllowsOffline: true) {
        case .readable:
            anchor.lastWall = now.trustedWallSeconds!; displayedAnchor = anchor
        case .stale: hide(); state = .expired
        case .unavailable: hide(); state = .untrustedTime
        }
    }
    public func hide() { displayed = nil; displayedAnchor = nil; state = .idle }
    public func clearLocally() throws {
        guard !clearing else { throw OfflineFailure.unavailable }
        clearing = true; defer { clearing = false }
        synchronizationIdentity = nil
        generation = UUID(); blocked = true; hide(); syncState = .idle
        _ = readSession?.clearWithSettlement(); readSession = nil
        let token = generation
        let loaded = Result { try loadAnchor() }
        switch loaded {
        case .success(var original?):
            original.readAllowed = false
            try saveDeniedAnchor(original, token: token)
            // Retain the exact target in the denied anchor if physical cleanup fails.
            try store(original.namespace.account, create: false).clearLocalEntry()
            guard generation == token else { throw OfflineFailure.unavailable }
            try anchors.clearAndBlock()
        case .success(nil): try anchors.clearAndBlock()
        case .failure(let error): try anchors.clearAndBlock(); throw error
        }
    }
    /// Exact account guard for the native device hook. Never clear an anchor
    /// which now belongs to a different account; caller holds the original scope.
    public func clearDeviceAccount(account: UUID) throws {
        if let anchor = try loadAnchor() {
            guard anchor.namespace.backend == environment, anchor.namespace.account == account else { throw OfflineFailure.wrongNamespace }
        }
        let unanchored = try loadAnchor() == nil
        try clearLocally()
        // An interrupted sync may leave an exact owned file without a grant.
        // Reuse the cached store so its unresolved-write guard still applies.
        if unanchored { try store(account, create: false).clearLocalEntry() }
    }
    public func verifyDeviceAnchorCleared() throws {
        guard try loadAnchor() == nil else { throw OfflineFailure.unavailable }
    }
    /// Reuses this controller's existing store, preserving its original pending
    /// write guard. No fresh store can bypass an unresolved original write.
    public func clearDeviceTemporaryWrites(account: UUID) throws {
        if let anchor = try loadAnchor() {
            guard anchor.namespace.backend == environment, anchor.namespace.account == account else { throw OfflineFailure.wrongNamespace }
        }
        try store(account, create: false).clearLocalTemporaryWrites()
    }
    public func prepareSynchronization() { syncState = .synchronizing }
    public func noteSyncReadFailure() { syncState = .failed }
    public func bindStorageProvision(_ handler: @escaping @MainActor (OfflineTripStorageProvision) -> Void) {
        storageProvision = handler
    }
    public func bindDeviceIdentityRejection(_ handler: @escaping @MainActor (SessionMaterial) async throws -> Void) {
        identityRejection = handler
    }
    public func currentIdentityRejected() async throws {
        let token = generation
        guard let material = try sdkMaterial() else { return }
        guard generation == token else { throw OfflineFailure.unavailable }
        if let identityRejection {
            try denyRejectedIdentity(material: material)
            try await identityRejection(material)
        } else { try self.identityRejected(material: material) }
    }
    public func captureStorageProvision() throws -> OfflineTripStorageProvision {
        let token = generation
        try check(token)
        guard syncState == .saved, let anchor = try loadAnchor(), anchor.readAllowed else { throw OfflineFailure.unavailable }
        try requireCurrentMaterial(anchor.sessionHash, token: token)
        return .init(namespace: anchor.namespace, keyID: anchor.keyID, anchor: anchor, token: token)
    }
    public func validateStorageProvision(_ provision: OfflineTripStorageProvision) throws {
        try check(provision.token)
        guard try loadAnchor() == provision.anchor else { throw OfflineFailure.unavailable }
        try requireCurrentMaterial(provision.anchor.sessionHash, token: provision.token)
    }
    /// Immediate read fence for the DEVICE@3 original-call flow. Physical erasure
    /// follows its durable native intent; no missing/foreign grant is adopted.
    public func denyRejectedIdentity(material: SessionMaterial) throws {
        let previous = generation
        guard var original = try loadAnchor(), original.sessionHash == materialHash(material) else { return }
        guard generation == previous else { throw OfflineFailure.unavailable }
        let token = UUID(); generation = token; blocked = true
        hide()
        guard generation == token else { throw OfflineFailure.unavailable }
        synchronizationIdentity = nil
        let originalSession = readSession; readSession = nil
        _ = originalSession?.clearWithSettlement()
        guard generation == token else { throw OfflineFailure.unavailable }
        original.readAllowed = false
        try saveDeniedAnchor(original, token: token)
    }
    /// Only an explicitly verified HTTP identity rejection may invoke this path.
    public func identityRejected(material: SessionMaterial) throws {
        guard let original = try loadAnchor(), original.sessionHash == materialHash(material) else { return }
        try clearLocally()
    }
}
