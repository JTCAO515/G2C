import Foundation
import Observation
import CJSession

/// Non-secret choices supplied only by the DEBUG simulator composition root.
public struct DevelopmentAccountChoice: Identifiable, Equatable, Sendable {
    public let id: String
    public let label: String
    public init(id: String, label: String) { self.id = id; self.label = label }
}

public enum DevelopmentSessionCheck: Equatable, Sendable {
    case accepted(account: String), rejected, serverRejected, expired, networkUnknown
}

public enum DemoAccountExchangeFailure: Error {
    case rejected, expired, unavailable
}

public enum DevelopmentAccountState: Equatable, Sendable {
    case signedOut, checking, signedIn(String), paused, rejected, expired, networkUnknown, storageUnavailable
}

/// Local development identities only. This does not replace the production SDK host.
/// Verification and activation are supplied by the trusted DEBUG simulator root.
@MainActor @Observable public final class DevelopmentAccountHost {
    public let choices: [DevelopmentAccountChoice]
    public let demoMode: Bool
    public private(set) var state: DevelopmentAccountState = .signedOut
    @ObservationIgnored private let shell: ShellState
    @ObservationIgnored private let session: SessionLifecycle
    @ObservationIgnored private let material: (String) throws -> SessionMaterial
    @ObservationIgnored private let verify: (SessionMaterial) async -> DevelopmentSessionCheck
    @ObservationIgnored private let refresh: ((SessionMaterial) async throws -> SessionMaterial?)?
    @ObservationIgnored private let activate: (SessionMaterial, SessionLifecycle, SessionOperation) throws -> Void
    @ObservationIgnored private let invalidate: () -> Void
    @ObservationIgnored private let clearOffline: (() throws -> Void)?
    @ObservationIgnored private let serverRejected: ((SessionMaterial) throws -> Void)?
    @ObservationIgnored private let identityWillChange: (() -> Void)?
    @ObservationIgnored private let rejectedContext: ((SessionMaterial, SessionLifecycle, SessionOperation) async throws -> Void)?
    @ObservationIgnored private var request = UUID()
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var active: (SessionMaterial, SessionOperation)?
    @ObservationIgnored private var resuming: (material: SessionMaterial, operation: SessionOperation, generation: ShellGeneration, save: Bool)?

    /// A foreground check is still the same sign-in, not a new login attempt.
    public var isResuming: Bool { state == .paused || resuming?.generation == shell.generation }

    public init(shell: ShellState, choices: [DevelopmentAccountChoice], persistence: any SessionPersistence, demoMode: Bool = false,
                material: @escaping (String) throws -> SessionMaterial,
                verify: @escaping (SessionMaterial) async -> DevelopmentSessionCheck,
                refresh: ((SessionMaterial) async throws -> SessionMaterial?)? = nil,
                activate: @escaping (SessionMaterial, SessionLifecycle, SessionOperation) throws -> Void,
                invalidate: @escaping () -> Void,
                clearOffline: (() throws -> Void)? = nil,
                serverRejected: ((SessionMaterial) throws -> Void)? = nil,
                identityWillChange: (() -> Void)? = nil,
                rejectedContext: ((SessionMaterial, SessionLifecycle, SessionOperation) async throws -> Void)? = nil) {
        self.shell = shell; self.choices = choices; self.demoMode = demoMode
        self.session = SessionLifecycle(persistence: persistence, restorePolicy: .userInitiatedOnly)
        self.material = material; self.verify = verify; self.activate = activate; self.invalidate = invalidate
        self.refresh = refresh
        self.clearOffline = clearOffline; self.serverRejected = serverRejected; self.identityWillChange = identityWillChange; self.rejectedContext = rejectedContext
    }

    func belongs(to shell: ShellState) -> Bool { self.shell === shell }

    /// Fence every private projection synchronously, before a callback or an await.
    private func begin(cancelTask: Bool = true, cleanup: Bool = false) -> (UUID, ShellGeneration)? {
        let id = UUID(); request = id
        active = nil
        resuming = nil
        let old = task; task = nil; if cancelTask { old?.cancel() }
        guard request == id else { return nil }
        let generation = cleanup ? shell.retireBusinessForCleanup() : shell.invalidateIdentity()
        guard request == id, shell.generation == generation else { return nil }
        invalidate()
        guard request == id, shell.generation == generation else { return nil }
        shell.selectedTab = .memory
        if !cleanup { shell.memoryPath = [.account] }
        return (id, generation)
    }

    private func current(_ id: UUID, _ generation: ShellGeneration, _ operation: SessionOperation) -> Bool {
        request == id && shell.generation == generation && session.isCurrent(operation)
    }

    public func signIn(_ choiceID: String) {
        guard choices.contains(where: { $0.id == choiceID }) else { return }
        identityWillChange?()
        guard let (id, generation) = begin() else { return }
        do {
            guard let operation = try prepareExplicitSignIn(id, generation) else { return }
            let candidate = try material(choiceID)
            guard current(id, generation, operation) else { return }
            start(candidate, operation: operation, id: id, generation: generation, save: true)
        } catch {
            guard request == id, shell.generation == generation else { return }
            state = .storageUnavailable
        }
    }

    private func prepareExplicitSignIn(_ id: UUID, _ generation: ShellGeneration) throws -> SessionOperation? {
        if let clearOffline {
            var cacheFailure: (any Error)?
            do { try clearOffline() } catch { cacheFailure = error }
            guard request == id, shell.generation == generation else { return nil }
            let result = session.clearWithSettlement()
            guard request == id, shell.generation == generation else { return nil }
            guard result == .cleared else { throw SessionFailure.storageUnavailable }
            if let cacheFailure { throw cacheFailure }
        }
        // A persisted logout marker can only be replaced by this explicit new login.
        if session.state == .blocked(.restorationBlocked) {
            guard session.clearWithSettlement() == .cleared else { throw SessionFailure.storageUnavailable }
        }
        guard request == id, shell.generation == generation else { return nil }
        return try session.beginTrustedSDKSave()
    }

    /// A signed Beta obtains candidate bytes from the fixed-origin invite
    /// exchange. A late exchange cannot save or activate after identity changes.
    public func signIn(exchanging exchange: @escaping @MainActor () async throws -> SessionMaterial) {
        guard demoMode else { return }
        identityWillChange?()
        guard let (id, generation) = begin() else { return }
        let operation: SessionOperation
        do {
            guard let prepared = try prepareExplicitSignIn(id, generation) else { return }
            operation = prepared
        } catch {
            if request == id, shell.generation == generation { state = .storageUnavailable }
            return
        }
        state = .checking
        task = Task { [weak self] in
            guard let self else { return }
            do {
                let candidate = try await exchange()
                guard !Task.isCancelled, self.current(id, generation, operation) else { return }
                self.start(candidate, operation: operation, id: id, generation: generation, save: true)
            } catch {
                guard !Task.isCancelled, self.current(id, generation, operation) else { return }
                switch error as? DemoAccountExchangeFailure {
                case .rejected: self.state = .rejected
                case .expired: self.state = .expired
                default: self.state = .networkUnknown
                }
                self.task = nil
            }
        }
    }

    /// Recheck the current material without changing its generation on success.
    /// A late denial for a replaced session cannot sign out the new owner.
    public func recheckDemoSession() async {
        guard demoMode, let (candidate, operation) = active else { return }
        let id = request, generation = shell.generation
        guard current(id, generation, operation) else { return }
        let result = await verify(candidate)
        guard !Task.isCancelled, current(id, generation, operation) else { return }
        _ = settleDemoDenial(result)
    }

    private func settleDemoDenial(_ result: DevelopmentSessionCheck) -> Bool {
        guard demoMode else { return false }
        let denial: DevelopmentAccountState
        switch result {
        case .expired: denial = .expired
        case .rejected, .serverRejected: denial = .rejected
        case .accepted, .networkUnknown: return false
        }
        signOut()
        if state == .signedOut { state = denial }
        return true
    }

    /// Called only by an explicit Restore button; no background/automatic Keychain restore.
    public func restore() {
        identityWillChange?()
        guard let (id, generation) = begin() else { return }
        do {
            let operation = try session.beginUserRestore()
            guard let candidate = try session.load(for: operation) else {
                if current(id, generation, operation) { state = .signedOut }
                return
            }
            guard current(id, generation, operation) else { return }
            if demoMode { resuming = (candidate, operation, generation, false) }
            start(candidate, operation: operation, id: id, generation: generation, save: false)
        } catch {
            guard request == id, shell.generation == generation else { return }
            state = error as? SessionFailure == .restorationBlocked ? .signedOut : .storageUnavailable
        }
    }

    public func signOut() {
        identityWillChange?()
        guard let (id, generation) = begin() else { return }
        var cacheFailed = false
        if let clearOffline { do { try clearOffline() } catch { cacheFailed = true } }
        guard request == id, shell.generation == generation else { return }
        let result = session.clearWithSettlement()
        guard request == id, shell.generation == generation else { return }
        switch result {
        case .cleared: state = cacheFailed ? .storageUnavailable : .signedOut
        case .failed: state = .storageUnavailable
        case .replaced: break
        }
    }

    /// Original account-cleanup exit: retire in-memory SDK material as well as
    /// its canonical secure slot. Does not clear another workflow's evidence.
    public func clearForAccountCleanup() throws {
        guard let (id, generation) = begin(cancelTask: false, cleanup: true) else { throw SessionFailure.staleOperation }
        let result = session.clearWithSettlement()
        guard request == id, shell.generation == generation else { throw SessionFailure.staleOperation }
        guard result == .cleared else { state = .storageUnavailable; throw SessionFailure.storageUnavailable }
        state = .signedOut
    }

    /// Backgrounding fences visible data; it never clears the Keychain credential.
    public func suspend() {
        guard active != nil || state == .checking || isResuming else { return }
        let previous = active.map { ($0.0, $0.1, false) } ?? resuming.flatMap { candidate in
            candidate.generation == shell.generation ? (candidate.material, candidate.operation, candidate.save) : nil
        }
        guard begin() != nil else { return }
        if let previous, session.isCurrent(previous.1) {
            resuming = (previous.0, previous.1, shell.generation, previous.2)
            state = .paused
        } else { state = .signedOut }
    }

    /// Revalidate only the already-active in-memory session, never load Keychain automatically.
    public func resume() {
        guard state == .paused || (state == .networkUnknown && isResuming) else { return }
        let previous = active.map { ($0.0, $0.1, false) } ?? resuming.map { ($0.material, $0.operation, $0.save) }
        guard let previous, session.isCurrent(previous.1), let (id, generation) = begin() else { return }
        resuming = (previous.0, previous.1, generation, previous.2)
        guard demoMode, !previous.2, let refresh else {
            start(previous.0, operation: previous.1, id: id, generation: generation, save: previous.2)
            return
        }
        state = .checking
        task = Task { [weak self] in
            guard let self else { return }
            do {
                let renewed = try await refresh(previous.0)
                guard !Task.isCancelled, self.current(id, generation, previous.1) else { return }
                if let renewed {
                    let operation = try self.session.beginTrustedSDKSave()
                    self.resuming = (renewed, operation, generation, true)
                    self.start(renewed, operation: operation, id: id, generation: generation, save: true)
                } else {
                    self.start(previous.0, operation: previous.1, id: id, generation: generation, save: false)
                }
            } catch {
                guard !Task.isCancelled, self.current(id, generation, previous.1) else { return }
                switch error as? DemoAccountExchangeFailure {
                case .expired: _ = self.settleDemoDenial(.expired)
                case .rejected: _ = self.settleDemoDenial(.serverRejected)
                default:
                    // A failed renewal is not sign-out. The unchanged credential
                    // still requires ordinary server verification before use.
                    self.start(previous.0, operation: previous.1, id: id, generation: generation, save: false)
                }
            }
        }
    }

    private func start(_ candidate: SessionMaterial, operation: SessionOperation,
                       id: UUID, generation: ShellGeneration, save: Bool) {
        state = .checking
        task = Task { [weak self] in
            guard let self else { return }
            let result = await self.verify(candidate)
            guard !Task.isCancelled, self.current(id, generation, operation) else { return }
            if self.settleDemoDenial(result) { return }
            switch result {
            case .accepted(let account):
                do {
                    if save { try self.session.save(candidate, for: operation) }
                    guard self.current(id, generation, operation) else { return }
                    // Retire only this verified identity's local cleanup fence.
                    // Each domain still requires its own current session/binding.
                    self.shell.messageBindingBlocked = false
                    try self.activate(candidate, self.session, operation)
                    guard self.current(id, generation, operation) else { return }
                    self.active = (candidate, operation)
                    self.state = .signedIn(account)
                } catch {
                    guard self.request == id, self.shell.generation == generation,
                          self.session.ownsOperation(operation) else { return }
                    self.shell.messageBindingBlocked = true
                    self.invalidate()
                    guard self.request == id, self.shell.generation == generation else { return }
                    self.state = .storageUnavailable
                }
            case .rejected: self.state = .rejected
            case .serverRejected:
                do {
                    try self.serverRejected?(candidate)
                    try await self.rejectedContext?(candidate, self.session, operation)
                    guard self.current(id, generation, operation) else { return }
                    self.state = .rejected
                } catch {
                    guard self.current(id, generation, operation) else { return }
                    self.state = .storageUnavailable
                }
            case .expired: self.state = .expired
            case .networkUnknown:
                self.session.noteNetworkUnknown()
                self.state = .networkUnknown
            }
            if self.request == id {
                self.task = nil
                if result != .networkUnknown { self.resuming = nil }
            }
        }
    }
}
