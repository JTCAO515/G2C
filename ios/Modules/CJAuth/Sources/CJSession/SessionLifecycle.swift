import Foundation

public enum SessionFailure: Error, Equatable, Sendable {
    case invalidConfiguration, emptyMaterial, staleOperation, restorationBlocked
    case automaticRestoreUnavailable, malformedRecord, storageUnavailable
    case keychain(Int32)
}

/// Host must allocate a new environment UUID for G2C. No default/legacy namespace.
public struct SessionNamespace: Equatable, Sendable {
    public let environment: UUID
    public let slot: String
    public init(environment: UUID, slot: String) throws {
        guard !slot.isEmpty, slot.utf8.count <= 128,
              slot.utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0)
                  || (97...122).contains($0) || [45, 46, 95].contains($0) }) else {
            throw SessionFailure.invalidConfiguration
        }
        self.environment = environment; self.slot = slot
    }
    public var service: String { "G2C.CJAuth.session.\(environment.uuidString)" }
}

/// Only SDK-owning trusted host may construct this with session bytes. Not a password input.
/// Deliberately not Codable/Equatable and redacted under String(reflecting:) and Mirror.
public struct SessionMaterial: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    private let data: Data
    public init(trustedSDKBytes: Data) throws {
        guard !trustedSDKBytes.isEmpty else { throw SessionFailure.emptyMaterial }
        data = trustedSDKBytes
    }
    public func withBytes<T>(_ body: (Data) throws -> T) rethrows -> T { try body(data) }
    public var description: String { "<redacted session material>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

@MainActor public protocol SessionPersistence {
    func load() throws -> SessionMaterial?
    func save(_ material: SessionMaterial) throws
    /// Replace credential bytes with a persistent non-secret block marker.
    func clearAndBlock() throws
}

public enum SessionRestorePolicy: Sendable { case userInitiatedOnly }
public enum SessionState: Equatable, Sendable {
    case idle, missing, loadedNeedsVerification, saved, cleared, networkUnknown
    case blocked(SessionFailure)
}
public struct SessionOperation: Equatable, Sendable {
    fileprivate enum Purpose: Sendable { case load, save }
    fileprivate let instance: UUID
    fileprivate let generation: UUID
    fileprivate let id = UUID()
    fileprivate let purpose: Purpose
    package let sdkBridgeClaim = SessionBridgeClaim()
}

/// Original-operation ownership shared across value copies; no credentials or global registry.
@MainActor package final class SessionBridgeClaim: Equatable, Sendable {
    private var owner: UUID?
    nonisolated init() {}
    package func claim(_ candidate: UUID) -> Bool {
        if let owner { return owner == candidate }
        owner = candidate; return true
    }
    nonisolated package static func == (lhs: SessionBridgeClaim, rhs: SessionBridgeClaim) -> Bool { lhs === rhs }
}

/// One lifecycle/writer per namespace. MainActor sync persistence has no await reentrancy.
@MainActor public final class SessionLifecycle {
    public static let interfaceVersion = "CJ-SESSION-STORE@0.1.0-rc.1"
    private let persistence: any SessionPersistence
    private let instance = UUID()
    private var generation = UUID()
    private var current: SessionOperation?
    private var consumed = false
    private var blocked = false
    public private(set) var state: SessionState = .idle
    public var canUseRestrictedBusiness: Bool { false }

    public init(persistence: any SessionPersistence, restorePolicy: SessionRestorePolicy) {
        self.persistence = persistence
        // The only currently implemented policy is explicitly requested restoration.
    }
    public func restoreAutomatically() throws -> SessionMaterial? {
        throw SessionFailure.automaticRestoreUnavailable
    }
    public func beginUserRestore() throws -> SessionOperation { try begin(.load) }
    public func beginTrustedSDKSave() throws -> SessionOperation { try begin(.save) }
    private func begin(_ purpose: SessionOperation.Purpose) throws -> SessionOperation {
        guard !blocked else { throw SessionFailure.restorationBlocked }
        let op = SessionOperation(instance: instance, generation: generation, purpose: purpose)
        current = op; consumed = false
        return op
    }
    package var identityGeneration: UUID { generation }
    public func isCurrent(_ operation: SessionOperation) -> Bool {
        !blocked && ownsOperation(operation)
    }
    /// Read-only ownership for this lifecycle instance and generation, even when blocked.
    /// Does not imply usability, credential validity, namespace authority or business permission.
    public func ownsOperation(_ operation: SessionOperation) -> Bool {
        current == operation && operation.instance == instance && operation.generation == generation
    }
    private func consume(_ operation: SessionOperation, purpose: SessionOperation.Purpose) throws {
        guard isCurrent(operation), !consumed, operation.purpose == purpose else { throw SessionFailure.staleOperation }
        consumed = true
    }
    public func load(for operation: SessionOperation) throws -> SessionMaterial? {
        try consume(operation, purpose: .load)
        do {
            let material = try persistence.load()
            guard isCurrent(operation) else { throw SessionFailure.staleOperation }
            state = material == nil ? .missing : .loadedNeedsVerification
            return material
        } catch {
            guard ownsOperation(operation) else { throw SessionFailure.staleOperation }
            throw block(error)
        }
    }
    public func save(_ material: SessionMaterial, for operation: SessionOperation) throws {
        try consume(operation, purpose: .save)
        do {
            try persistence.save(material)
            guard isCurrent(operation) else { throw SessionFailure.staleOperation }
            state = .saved
        } catch {
            guard ownsOperation(operation) else { throw SessionFailure.staleOperation }
            throw block(error)
        }
    }
    /// Logout/account switch/authoritative invalidation: fence first, then clear storage.
    /// A new trusted SDK save is allowed only after clearAndBlock succeeds.
    public func clear() throws {
        generation = UUID(); current = nil; consumed = true; blocked = true
        let clearingGeneration = generation
        do {
            try persistence.clearAndBlock()
            guard generation == clearingGeneration, current == nil else { throw SessionFailure.staleOperation }
            blocked = false; state = .cleared
        } catch {
            guard generation == clearingGeneration, current == nil else { throw SessionFailure.staleOperation }
            throw block(error)
        }
    }
    /// Network uncertainty is not logout and does not touch the store or generation.
    public func noteNetworkUnknown() { if !blocked { state = .networkUnknown } }
    private func block(_ error: Error) -> SessionFailure {
        let failure = error as? SessionFailure ?? .storageUnavailable
        blocked = true; state = .blocked(failure)
        return failure
    }
}
