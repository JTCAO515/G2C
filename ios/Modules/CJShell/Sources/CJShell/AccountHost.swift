import Foundation
import Observation
import CJAuth
import CJSession

/// Transient material only. Never Codable, logged, placed in preferences or UI projection.
public struct EmailMaterial {
    public let address: String
    public let password: String?
}

/// One-use handoff for an exact AuthAttempt. Adapter owns any further secure handling.
@MainActor public final class AccountMaterialChannel {
    private var bound: AuthAttempt?
    private var material: EmailMaterial?
    fileprivate init() {}
    fileprivate func put(_ material: EmailMaterial, for attempt: AuthAttempt) {
        bound = attempt
        self.material = material
    }
    public func take(for attempt: AuthAttempt) -> EmailMaterial? {
        guard bound == attempt else { return nil }
        defer { clear() }
        return material
    }
    fileprivate func clear() { bound = nil; material = nil }
}

/// Presentation outcomes only; none means authenticated or invited.
public enum RestoreCheckResult: Sendable { case needsServerVerification, rejected, networkUnknown }
public enum LocalSessionStatus: Equatable {
    case notConfigured, idle, restoring, missing, needsVerification, verificationFailed, unknown, cleared
    case blocked(SessionFailure)
}

@MainActor @Observable public final class AccountHost {
    public private(set) var state: FlowState = .idle
    public private(set) var requiresReconciliation = false
    public private(set) var inputMissing = false
    public private(set) var localSessionStatus: LocalSessionStatus
    public private(set) var isRestoring = false
    public var hasSessionStore: Bool { session != nil }
    public var canRestoreSession: Bool {
        guard session != nil, !isRestoring, !isWaiting, !requiresReconciliation else { return false }
        switch localSessionStatus {
        case .blocked, .cleared, .needsVerification: return false
        default: return true
        }
    }
    public var canSubmitAccount: Bool {
        guard !isWaiting, !isRestoring, !requiresReconciliation else { return false }
        if case .blocked = localSessionStatus { return false }
        return true
    }
    @ObservationIgnored private let session: SessionLifecycle?
    @ObservationIgnored private let verifyRestored: (@MainActor (SessionMaterial, SessionOperation) async -> RestoreCheckResult)?
    public var isWaiting: Bool { if case .waiting = state { true } else { false } }
    public var canUseRestrictedBusiness: Bool { false }
    @ObservationIgnored private let shell: ShellState
    @ObservationIgnored private let flow: AuthFlow
    @ObservationIgnored private let channel: AccountMaterialChannel
    @ObservationIgnored private let adapter: any AuthSDKAdapter
    @ObservationIgnored private var task: Task<Void, Never>?

    public convenience init(shell: ShellState) {
        self.init(shell: shell) { _, _ in UnconfiguredSDKAdapter() }
    }

    /// Trusted composition seam. No configured provider, network or secure storage is shipped.
    public init(shell: ShellState, session: SessionLifecycle? = nil,
                verifyRestored: (@MainActor (SessionMaterial, SessionOperation) async -> RestoreCheckResult)? = nil,
                makeAdapter: (AccountMaterialChannel, @escaping @MainActor (AuthAttempt) -> Bool) -> any AuthSDKAdapter) {
        self.shell = shell
        self.session = session
        self.verifyRestored = verifyRestored
        if let session {
            switch session.state {
            case .blocked(let error): self.localSessionStatus = .blocked(error)
            case .cleared: self.localSessionStatus = .cleared
            case .networkUnknown:
                self.localSessionStatus = .unknown
                self.requiresReconciliation = true
            case .loadedNeedsVerification: self.localSessionStatus = .needsVerification
            case .missing: self.localSessionStatus = .missing
            case .idle, .saved: self.localSessionStatus = .idle
            }
        } else { self.localSessionStatus = .notConfigured }
        let flow = AuthFlow()
        let channel = AccountMaterialChannel()
        self.flow = flow
        self.channel = channel
        self.adapter = makeAdapter(channel, { flow.pending == $0 })
    }

    func belongs(to shell: ShellState) -> Bool { self.shell === shell }

    public func unavailableReason(for action: AuthAction) -> UnavailableReason? {
        adapter.unavailableReason(for: action)
    }

    /// Called synchronously by the submit button. Clears the caller's secret immediately.
    /// Rejects reentry/unknown rather than creating another attempt to retry a side effect.
    public func submit(_ action: AuthAction, email: String = "", password: inout String) {
        let suppliedPassword = password
        password = ""
        guard canSubmitAccount else { return }
        inputMissing = false
        if let reason = adapter.unavailableReason(for: action) {
            state = .unavailable(reason)
            return
        }
        let address = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let requiresEmail = action == .emailSignIn || action == .emailRegister || action == .emailRecovery
        let requiresPassword = action == .emailSignIn || action == .emailRegister
        guard !requiresEmail || (!address.isEmpty && (!requiresPassword || !suppliedPassword.isEmpty)) else {
            inputMissing = true
            return
        }
        // A new identity attempt cannot retain a prior account's visible data.
        if action.purpose == .signIn || action == .emailRegister {
            if session != nil {
                guard clearSession(keepAccountRoute: true), localSessionStatus == .cleared else { return }
            } else {
                let generation = shell.invalidateIdentity()
                guard shell.generation == generation else { return }
            }
            shell.memoryPath = [.account] // public account entry, never a retained private detail
        }
        guard let attempt = flow.begin(action, using: adapter) else { state = flow.state; return }
        let generation = shell.generation
        if requiresEmail {
            channel.put(EmailMaterial(address: address, password: requiresPassword ? suppliedPassword : nil), for: attempt)
        }
        state = flow.state
        let adapter = adapter
        task = Task { [weak self] in
            let event = await adapter.perform(attempt)
            guard let self else { return }
            guard self.flow.pending == attempt else { return }
            self.channel.clear()
            guard self.shell.generation == generation else {
                self.flow.invalidateIdentity()
                self.state = .idle
                self.requiresReconciliation = true
                return
            }
            _ = self.flow.accept(event, purpose: attempt.action.purpose, for: attempt)
            self.state = self.flow.state
            if event == .networkUnknown || event == .userCancelled {
                self.requiresReconciliation = true
            }
            self.task = nil
        }
    }

    /// Local dismissal is not evidence that remote effects were cancelled.
    public func cancel() {
        if isRestoring {
            let generation = fencePrivateIdentity()
            guard shell.generation == generation else { return }
            session?.noteNetworkUnknown()
            localSessionStatus = .unknown
            requiresReconciliation = true
            return
        }
        guard let attempt = flow.pending else { channel.clear(); return }
        _ = flow.cancel(attempt)
        channel.clear()
        task?.cancel()
        task = nil
        state = flow.state
        requiresReconciliation = true
    }

    /// Host lifecycle hook for account switch / authoritative identity invalidation.
    /// Keeps unresolved-operation fence; no UI reset can make unknown safe to retry.
    public func invalidateIdentity() { clearSession(keepAccountRoute: false) }

    private func fencePrivateIdentity() -> ShellGeneration {
        if flow.pending != nil || isRestoring { requiresReconciliation = true }
        flow.invalidateIdentity()
        channel.clear()
        task?.cancel()
        task = nil
        isRestoring = false
        state = .idle
        inputMissing = false
        return shell.invalidateIdentity() // last: resource callbacks may install a newer lifetime
    }

    /// Local cleanup only. Storage failure cannot reopen restore or grant access.
    public func clearLocalSession() { clearSession(keepAccountRoute: true) }

    @discardableResult private func clearSession(keepAccountRoute: Bool) -> Bool {
        let generation = fencePrivateIdentity()
        guard shell.generation == generation else { return false }
        if keepAccountRoute { shell.memoryPath = [.account] }
        guard let session else { localSessionStatus = .notConfigured; return false }
        do {
            try session.clear()
            guard shell.generation == generation else { return false }
            shell.messageBindingBlocked = false // local cleanup only; trusted binding still requires its own current identity check
            localSessionStatus = .cleared
            return true
        } catch {
            guard shell.generation == generation else { return false }
            localSessionStatus = .blocked((error as? SessionFailure) ?? .storageUnavailable)
            return false
        }
    }

    /// Explicit user action only; never invoked on init or language/view changes.
    public func restoreSession() {
        guard canRestoreSession, let session else { return }
        let generation = fencePrivateIdentity()
        guard shell.generation == generation else { return }
        shell.memoryPath = [.account]
        do {
            let operation = try session.beginUserRestore()
            guard let material = try session.load(for: operation) else {
                localSessionStatus = .missing
                return
            }
            localSessionStatus = .needsVerification
            guard let verifyRestored else { return } // bytes are dropped; no verification claim
            isRestoring = true
            localSessionStatus = .restoring
            task = Task { [weak self] in
                let result = await verifyRestored(material, operation)
                guard let self, self.isRestoring else { return }
                guard self.shell.generation == generation, session.isCurrent(operation) else {
                    self.isRestoring = false
                    self.task = nil
                    self.requiresReconciliation = true
                    session.noteNetworkUnknown()
                    self.localSessionStatus = .unknown
                    return
                }
                self.isRestoring = false
                self.task = nil
                switch result {
                case .needsServerVerification: self.localSessionStatus = .needsVerification
                case .rejected: self.localSessionStatus = .verificationFailed
                case .networkUnknown:
                    session.noteNetworkUnknown()
                    self.localSessionStatus = .unknown
                    self.requiresReconciliation = true
                }
            }
        } catch {
            localSessionStatus = .blocked((error as? SessionFailure) ?? .storageUnavailable)
        }
    }
}
