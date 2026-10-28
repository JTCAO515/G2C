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
    case accepted(account: String), rejected, expired, networkUnknown
}

public enum DevelopmentAccountState: Equatable, Sendable {
    case signedOut, checking, signedIn(String), paused, rejected, expired, networkUnknown, storageUnavailable
}

/// Local development identities only. This does not replace the production SDK host.
/// Verification and activation are supplied by the trusted DEBUG simulator root.
@MainActor @Observable public final class DevelopmentAccountHost {
    public let choices: [DevelopmentAccountChoice]
    public private(set) var state: DevelopmentAccountState = .signedOut
    @ObservationIgnored private let shell: ShellState
    @ObservationIgnored private let session: SessionLifecycle
    @ObservationIgnored private let material: (String) throws -> SessionMaterial
    @ObservationIgnored private let verify: (SessionMaterial) async -> DevelopmentSessionCheck
    @ObservationIgnored private let activate: (SessionMaterial, SessionLifecycle, SessionOperation) throws -> Void
    @ObservationIgnored private let invalidate: () -> Void
    @ObservationIgnored private var request = UUID()
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var active: (SessionMaterial, SessionOperation)?

    public init(shell: ShellState, choices: [DevelopmentAccountChoice], persistence: any SessionPersistence,
                material: @escaping (String) throws -> SessionMaterial,
                verify: @escaping (SessionMaterial) async -> DevelopmentSessionCheck,
                activate: @escaping (SessionMaterial, SessionLifecycle, SessionOperation) throws -> Void,
                invalidate: @escaping () -> Void) {
        self.shell = shell; self.choices = choices
        self.session = SessionLifecycle(persistence: persistence, restorePolicy: .userInitiatedOnly)
        self.material = material; self.verify = verify; self.activate = activate; self.invalidate = invalidate
    }

    func belongs(to shell: ShellState) -> Bool { self.shell === shell }

    /// Fence every private projection synchronously, before a callback or an await.
    private func begin() -> (UUID, ShellGeneration)? {
        let id = UUID(); request = id
        active = nil
        let old = task; task = nil; old?.cancel()
        guard request == id else { return nil }
        let generation = shell.invalidateIdentity()
        guard request == id, shell.generation == generation else { return nil }
        invalidate()
        guard request == id, shell.generation == generation else { return nil }
        shell.selectedTab = .memory
        shell.memoryPath = [.account]
        return (id, generation)
    }

    private func current(_ id: UUID, _ generation: ShellGeneration, _ operation: SessionOperation) -> Bool {
        request == id && shell.generation == generation && session.isCurrent(operation)
    }

    public func signIn(_ choiceID: String) {
        guard choices.contains(where: { $0.id == choiceID }), let (id, generation) = begin() else { return }
        do {
            // A persisted logout marker can only be replaced by this explicit new login.
            if session.state == .blocked(.restorationBlocked) {
                guard session.clearWithSettlement() == .cleared else { throw SessionFailure.storageUnavailable }
            }
            guard request == id, shell.generation == generation else { return }
            let operation = try session.beginTrustedSDKSave()
            let candidate = try material(choiceID)
            guard current(id, generation, operation) else { return }
            start(candidate, operation: operation, id: id, generation: generation, save: true)
        } catch {
            guard request == id, shell.generation == generation else { return }
            state = .storageUnavailable
        }
    }

    /// Called only by an explicit Restore button; no background/automatic Keychain restore.
    public func restore() {
        guard let (id, generation) = begin() else { return }
        do {
            let operation = try session.beginUserRestore()
            guard let candidate = try session.load(for: operation) else {
                if current(id, generation, operation) { state = .signedOut }
                return
            }
            guard current(id, generation, operation) else { return }
            start(candidate, operation: operation, id: id, generation: generation, save: false)
        } catch {
            guard request == id, shell.generation == generation else { return }
            state = error as? SessionFailure == .restorationBlocked ? .signedOut : .storageUnavailable
        }
    }

    public func signOut() {
        guard let (id, generation) = begin() else { return }
        let result = session.clearWithSettlement()
        guard request == id, shell.generation == generation else { return }
        switch result {
        case .cleared: state = .signedOut
        case .failed: state = .storageUnavailable
        case .replaced: break
        }
    }

    /// Backgrounding fences visible data; it never clears the Keychain credential.
    public func suspend() {
        guard active != nil || state == .checking else { return }
        let previous = active
        guard begin() != nil else { return }
        if let previous, session.isCurrent(previous.1) {
            active = previous
            state = .paused
        } else { state = .signedOut }
    }

    /// Revalidate only the already-active in-memory session, never load Keychain automatically.
    public func resume() {
        guard state == .paused, let previous = active, session.isCurrent(previous.1),
              let (id, generation) = begin() else { return }
        start(previous.0, operation: previous.1, id: id, generation: generation, save: false)
    }

    private func start(_ candidate: SessionMaterial, operation: SessionOperation,
                       id: UUID, generation: ShellGeneration, save: Bool) {
        state = .checking
        task = Task { [weak self] in
            guard let self else { return }
            let result = await self.verify(candidate)
            guard !Task.isCancelled, self.current(id, generation, operation) else { return }
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
            case .expired: self.state = .expired
            case .networkUnknown:
                self.session.noteNetworkUnknown()
                self.state = .networkUnknown
            }
            if self.request == id { self.task = nil }
        }
    }
}
