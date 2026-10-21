import Foundation
import Observation
import CJAuth

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

@MainActor @Observable public final class AccountHost {
    public private(set) var state: FlowState = .idle
    public private(set) var requiresReconciliation = false
    public private(set) var inputMissing = false
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
    public init(shell: ShellState,
                makeAdapter: (AccountMaterialChannel, @escaping @MainActor (AuthAttempt) -> Bool) -> any AuthSDKAdapter) {
        self.shell = shell
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
        guard !isWaiting, !requiresReconciliation else { return }
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
        guard let attempt = flow.begin(action, using: adapter) else { state = flow.state; return }
        // A new identity attempt cannot retain a prior account's visible data.
        if action.purpose == .signIn || action == .emailRegister {
            shell.invalidateIdentity()
            shell.memoryPath = [.account] // public account entry, never a retained private detail
        }
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
    public func invalidateIdentity() {
        if flow.pending != nil { requiresReconciliation = true }
        flow.invalidateIdentity()
        shell.invalidateIdentity()
        channel.clear()
        task?.cancel()
        task = nil
        state = .idle
        inputMissing = false
    }
}
