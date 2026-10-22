import Foundation
import Observation
import CJAuth
import CJSession
import CJAuthSupabase
import Auth

/// Trusted SDK/service verification process, injected by the composition root, never the UI.
/// verifiedUserID must be published only by this process after authoritative verification,
/// not decoded JWT/cache/user input. generation changes when that verification flow changes.
@MainActor public protocol AccountSessionVerification: AnyObject {
    var generation: UUID { get }
    var verifiedUserID: UUID? { get }
    func verifyInitialSession(_ candidate: Session, attempt: AuthAttempt) async -> SDKSessionCheck
    func revalidateSession(_ candidate: Session, reason: SessionRevalidationReason) async -> SDKSessionCheck
}

/// Transient material only. Never Codable, logged, placed in preferences or UI projection.
public struct EmailMaterial {
    public let address: String
    public let password: String?
}

/// One-use handoff for an exact AuthAttempt. Adapter owns any further secure handling.
@MainActor public final class AccountMaterialChannel {
    private var bound: AuthAttempt?
    private var material: EmailMaterial?
    fileprivate var sdkSessionHandler: (@MainActor (Session, AuthAttempt) -> Void)?
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
    /// Trusted SDK completion channel only; this does not publish identity or save by itself.
    public func receiveSDKSession(_ value: Session, for attempt: AuthAttempt) {
        sdkSessionHandler?(value, attempt)
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
    public private(set) var sessionBridgeResult: SessionBridgeResult = .unavailable
    public private(set) var committedSessionOperation: SessionOperation?
    private struct SDKSaveContext {
        let attempt: AuthAttempt
        let operation: SessionOperation
        let generation: ShellGeneration
        let verificationGeneration: UUID
        let expectedUserBefore: UUID
        var candidate: Session?
    }
    @ObservationIgnored private var sdkSave: SDKSaveContext?
    @ObservationIgnored private var restoreOperation: SessionOperation?
    @ObservationIgnored private var sdkEmailOnly = false
    @ObservationIgnored private let sessionVerification: (any AccountSessionVerification)?
    public private(set) var localSessionStatus: LocalSessionStatus
    public private(set) var isRestoring = false
    public var hasSessionStore: Bool { session != nil }
    public var canRestoreSession: Bool {
        guard session != nil, !isRestoring, !isWaiting, !requiresReconciliation else { return false }
        if let sessionVerification, sessionVerification.verifiedUserID == nil { return false }
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
                sessionVerification: (any AccountSessionVerification)? = nil,
                makeAdapter: (AccountMaterialChannel, @escaping @MainActor (AuthAttempt) -> Bool) -> any AuthSDKAdapter) {
        self.shell = shell
        self.session = session
        self.verifyRestored = verifyRestored
        self.sessionVerification = sessionVerification
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
        channel.sdkSessionHandler = { [weak self] value, attempt in self?.receiveSDKSession(value, for: attempt) }
    }

    /// Explicit SDK composition; missing config/offline default fetch never creates a live login.
    public convenience init(shell: ShellState, session: SessionLifecycle,
        sdkConfiguration: SupabaseAdapterConfiguration = .init(), verification: any AccountSessionVerification,
        fetch: @escaping AuthFetch = { _ in throw URLError(.notConnectedToInternet) }) {
        self.init(shell: shell, session: session, sessionVerification: verification) { channel, current in
            SupabaseSDKAdapter(configuration: sdkConfiguration, fetch: fetch, isCurrent: current,
                onSessionForSecureStorage: { value, attempt in channel.receiveSDKSession(value, for: attempt) },
                material: { attempt in
                    guard let value = channel.take(for: attempt) else { return nil }
                    return .email(attempt: attempt, address: value.address, password: value.password)
                })
        }
        sdkEmailOnly = true // this convenience composition provides email material only
    }

    func belongs(to shell: ShellState) -> Bool { self.shell === shell }

    public func unavailableReason(for action: AuthAction) -> UnavailableReason? {
        if sdkEmailOnly, action.provider != .email { return .hostCapabilityRequired }
        if let verification = sessionVerification, verification.verifiedUserID == nil { return .hostCapabilityRequired }
        return adapter.unavailableReason(for: action)
    }

    /// Called synchronously by the submit button. Clears the caller's secret immediately.
    /// Rejects reentry/unknown rather than creating another attempt to retry a side effect.
    public func submit(_ action: AuthAction, email: String = "", password: inout String) {
        let suppliedPassword = password
        password = ""
        guard canSubmitAccount else { return }
        inputMissing = false
        if let reason = unavailableReason(for: action) {
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
        if let verification = sessionVerification, let session, action.purpose == .signIn {
            let verificationGeneration = verification.generation
            guard let expected = verification.verifiedUserID else {
                _ = flow.cancel(attempt); state = .unavailable(.hostCapabilityRequired); return
            }
            guard flow.pending == attempt, shell.generation == generation else { return }
            do {
                let operation = try session.beginTrustedSDKSave() // before SDK work, never from a late callback
                sdkSave = SDKSaveContext(attempt: attempt, operation: operation, generation: generation,
                    verificationGeneration: verificationGeneration, expectedUserBefore: expected)
                sessionBridgeResult = .unavailable
            } catch {
                _ = flow.cancel(attempt); state = flow.state
                localSessionStatus = .blocked((error as? SessionFailure) ?? .storageUnavailable)
                return
            }
        }
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
                self.sdkSave = nil; self.channel.clear(); self.task = nil
                self.sessionBridgeResult = .stale; self.localSessionStatus = .unknown
                self.state = .idle
                self.requiresReconciliation = true
                return
            }
            if event == .identityNeedsServerCheck, self.sessionVerification != nil {
                await self.verifyAndStoreInitialSession(for: attempt)
                guard self.flow.pending == attempt, self.shell.generation == generation else { return }
            }
            if self.sessionVerification != nil, event == .networkUnknown || event == .userCancelled,
               let original = self.sdkSave, self.initialIsCurrent(original) {
                self.session?.noteNetworkUnknown()
                self.sessionBridgeResult = .networkUnknown
                self.localSessionStatus = .unknown
            }
            self.sdkSave = nil
            var publication = event
            if event == .identityNeedsServerCheck, self.sessionVerification != nil {
                switch self.sessionBridgeResult {
                case .networkUnknown, .stale: publication = .networkUnknown
                case .identityInvalid, .identityMismatch, .malformedMaterial: publication = .rejected
                case .unavailable: publication = .unavailable(.hostCapabilityRequired)
                default: break
                }
            }
            _ = self.flow.accept(publication, purpose: attempt.action.purpose, for: attempt)
            self.state = self.flow.state
            if publication == .networkUnknown || publication == .userCancelled {
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
        sdkSave = nil
        channel.clear()
        let pending = task; task = nil
        state = flow.state
        requiresReconciliation = true
        pending?.cancel() // no old-lifetime mutation after cancellation callbacks
    }

    /// Host lifecycle hook for account switch / authoritative identity invalidation.
    /// Keeps unresolved-operation fence; no UI reset can make unknown safe to retry.
    public func invalidateIdentity() { clearSession(keepAccountRoute: false) }

    private func fencePrivateIdentity() -> ShellGeneration {
        if flow.pending != nil || isRestoring { requiresReconciliation = true }
        flow.invalidateIdentity()
        sdkSave = nil; restoreOperation = nil; committedSessionOperation = nil; sessionBridgeResult = .unavailable
        channel.clear()
        let pending = task; task = nil
        isRestoring = false
        state = .idle
        inputMissing = false
        let generation = shell.invalidateIdentity()
        pending?.cancel() // original task only; caller rechecks this generation after all callbacks
        return generation
    }

    /// Local cleanup only. Storage failure cannot reopen restore or grant access.
    public func clearLocalSession() { clearSession(keepAccountRoute: true) }

    @discardableResult private func clearSession(keepAccountRoute: Bool) -> Bool {
        let generation = fencePrivateIdentity()
        guard shell.generation == generation else { return false }
        if keepAccountRoute { shell.memoryPath = [.account] }
        guard let session else { localSessionStatus = .notConfigured; return false }
        let verificationGeneration = sessionVerification?.generation
        let verifiedUserID = sessionVerification?.verifiedUserID
        func canSettleOriginalClear() -> Bool {
            let sameVerification = sessionVerification?.generation == verificationGeneration
                && sessionVerification?.verifiedUserID == verifiedUserID
            guard shell.generation == generation else { return false }
            guard sameVerification else {
                // clear retires its operation normally. Only the trusted verification
                // lifetime changed here; discard A's result without adopting or clearing B.
                sessionBridgeResult = .stale; localSessionStatus = .idle
                return false
            }
            return true
        }
        guard canSettleOriginalClear() else { return false }
        let settlement = session.clearWithSettlement()
        guard canSettleOriginalClear() else { return false }
        switch settlement {
        case .cleared:
            shell.messageBindingBlocked = false // local cleanup only; trusted binding still requires its own current identity check
            localSessionStatus = .cleared
            return true
        case .failed(let failure):
            localSessionStatus = .blocked(failure)
            return false
        case .replaced:
            // Canonical settlement, including same-tuple or failed replacements.
            // Retire only this clear's UI result; do not inspect/adopt/clear B.
            sessionBridgeResult = .stale; localSessionStatus = .idle
            return false
        }
    }

    /// Explicit user action only; never invoked on init or language/view changes.
    public func restoreSession() {
        guard canRestoreSession, let session else { return }
        let generation = fencePrivateIdentity()
        guard shell.generation == generation else { return }
        shell.memoryPath = [.account]
        let verificationGeneration = sessionVerification?.generation
        let verifiedUserID = sessionVerification?.verifiedUserID
        guard shell.generation == generation else { return }
        var requestedOperation: SessionOperation?
        do {
            let operation = try session.beginUserRestore()
            requestedOperation = operation; restoreOperation = operation
            let material = try session.load(for: operation)
            let sameVerification = sessionVerification?.generation == verificationGeneration
                && sessionVerification?.verifiedUserID == verifiedUserID
            guard shell.generation == generation, restoreOperation == operation else { return }
            guard sameVerification, session.isCurrent(operation) else {
                retireDisplacedLoad(operation, generation: generation)
                return
            }
            guard let material else { localSessionStatus = .missing; return }
            localSessionStatus = .needsVerification
            if let verification = sessionVerification {
                restoreViaSDKBridge(material, operation: operation, generation: generation, verification: verification)
                return
            }
            guard let verifyRestored else { return } // bytes are dropped; no verification claim
            isRestoring = true
            localSessionStatus = .restoring
            task = Task { [weak self] in
                let result = await verifyRestored(material, operation)
                guard let self, self.isRestoring, self.restoreOperation == operation else { return }
                guard self.shell.generation == generation, session.isCurrent(operation) else {
                    self.isRestoring = false
                    self.task = nil
                    self.requiresReconciliation = true
                    if session.isCurrent(operation) { session.noteNetworkUnknown() }
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
            let sameVerification = sessionVerification?.generation == verificationGeneration
                && sessionVerification?.verifiedUserID == verifiedUserID
            guard shell.generation == generation, requestedOperation == nil || restoreOperation == requestedOperation else { return }
            if let operation = requestedOperation, !session.ownsOperation(operation) || !sameVerification {
                retireDisplacedLoad(operation, generation: generation)
                return
            }
            localSessionStatus = .blocked((error as? SessionFailure) ?? .storageUnavailable)
        }
    }
    private func retireDisplacedLoad(_ operation: SessionOperation, generation: ShellGeneration) {
        guard shell.generation == generation, restoreOperation == operation else { return }
        restoreOperation = nil; isRestoring = false; task = nil
        sessionBridgeResult = .stale; localSessionStatus = .idle
        // A read was displaced before SDK verification. Do not inspect/adopt/clear the replacement,
        // publish its error, or manufacture an unknown remote operation/permission.
    }
    private func initialUIIsCurrent(_ context: SDKSaveContext) -> Bool {
        guard let verification = sessionVerification,
              verification.generation == context.verificationGeneration,
              verification.verifiedUserID == context.expectedUserBefore else { return false }
        return flow.pending == context.attempt && shell.generation == context.generation
            && sdkSave?.operation == context.operation
    }
    private func initialIsCurrent(_ context: SDKSaveContext) -> Bool {
        initialUIIsCurrent(context) && session?.isCurrent(context.operation) == true
    }
    private func receiveSDKSession(_ value: Session, for attempt: AuthAttempt) {
        guard var context = sdkSave, context.attempt == attempt, context.candidate == nil,
              initialIsCurrent(context) else { return }
        context.candidate = value
        guard initialIsCurrent(context) else { return }
        sdkSave = context // private transient SDK value; never enters UI projection/logging
    }
    private func verifyAndStoreInitialSession(for attempt: AuthAttempt) async {
        guard let context = sdkSave, context.attempt == attempt,
              let verification = sessionVerification, let session else {
            if flow.pending == attempt { sessionBridgeResult = .unavailable; localSessionStatus = .verificationFailed }
            return
        }
        guard initialIsCurrent(context) else {
            settleStaleInitialIfOwned(context)
            return
        }
        guard let candidate = context.candidate else {
            sessionBridgeResult = .unavailable; localSessionStatus = .verificationFailed
            return
        }
        let checked = await verification.verifyInitialSession(candidate, attempt: attempt)
        guard initialIsCurrent(context), !Task.isCancelled else {
            settleStaleInitialIfOwned(context)
            return
        }
        switch checked {
        case .unknown:
            session.noteNetworkUnknown(); sessionBridgeResult = .networkUnknown
            localSessionStatus = .unknown; requiresReconciliation = true
        case .invalid:
            // This initial attempt already explicitly cleared its old slot before dispatch.
            // Rejection of a new candidate does not delete any unrelated/replacement session.
            sessionBridgeResult = .identityInvalid; localSessionStatus = .verificationFailed
        case .verified(let verified):
            let result = SupabaseSessionBridge.saveTrustedSDKSession(verified, lifecycle: session,
                operation: context.operation, expectedUserID: context.expectedUserBefore,
                uiIsCurrent: { [weak self] in self?.initialUIIsCurrent(context) == true })
            // Bridge already checked the trusted verifier; avoid invoking external getters again
            // between its terminal result and publication of the same owned UI operation.
            guard flow.pending == context.attempt, sdkSave?.operation == context.operation,
                  shell.generation == context.generation else { settleStaleInitialIfOwned(context); return }
            if result == .stored, !session.isCurrent(context.operation) { settleStaleInitialIfOwned(context); return }
            sessionBridgeResult = result
            switch result {
            case .stored:
                guard session.isCurrent(context.operation) else { return }
                committedSessionOperation = context.operation
                localSessionStatus = .needsVerification // CJ server/invitation grant remains separate
            case .storageFailure(let error): localSessionStatus = .blocked(error)
            case .networkUnknown, .stale: localSessionStatus = .unknown; requiresReconciliation = true
            default: localSessionStatus = .verificationFailed
            }
        }
    }

    private func settleStaleInitialIfOwned(_ context: SDKSaveContext) {
        guard flow.pending == context.attempt, sdkSave?.operation == context.operation else { return }
        _ = flow.accept(.networkUnknown, purpose: context.attempt.action.purpose, for: context.attempt)
        state = flow.state; sessionBridgeResult = .stale; localSessionStatus = .unknown
        requiresReconciliation = true; sdkSave = nil; channel.clear(); task = nil
        // Do not touch persistence: it may already belong to a replacement operation.
    }

    private func ownsRestore(_ operation: SessionOperation, generation: ShellGeneration,
                             verification: any AccountSessionVerification, verifierGeneration: UUID, userID: UUID) -> Bool {
        guard verification.generation == verifierGeneration, verification.verifiedUserID == userID else { return false }
        return isRestoring && restoreOperation == operation && shell.generation == generation
    }
    private func restoreViaSDKBridge(_ material: SessionMaterial, operation: SessionOperation,
                                    generation: ShellGeneration, verification: any AccountSessionVerification) {
        guard let session, let userID = verification.verifiedUserID else { sessionBridgeResult = .unavailable; return }
        let verifierGeneration = verification.generation
        guard shell.generation == generation, restoreOperation == operation, session.isCurrent(operation) else { return }
        isRestoring = true; localSessionStatus = .restoring; sessionBridgeResult = .unavailable
        let bridge = SupabaseSessionBridge(lifecycle: session, operation: operation, expectedUserID: userID,
            uiIsCurrent: { [weak self] in
                self?.ownsRestore(operation, generation: generation, verification: verification,
                    verifierGeneration: verifierGeneration, userID: userID) == true
            }, verify: { value, reason in await verification.revalidateSession(value, reason: reason) })
        task = Task { [weak self] in
            let result = await bridge.revalidate(material, reason: .explicitRestore)
            guard let self, self.isRestoring, self.restoreOperation == operation else { return }
            guard self.ownsRestore(operation, generation: generation, verification: verification,
                    verifierGeneration: verifierGeneration, userID: userID), session.isCurrent(operation), !Task.isCancelled else {
                self.isRestoring = false; self.task = nil; self.requiresReconciliation = true
                self.sessionBridgeResult = .stale; self.localSessionStatus = .unknown
                return
            }
            // Original restore operation MUST still be current at this point.
            let committed: SessionBridgeResult
            switch result {
            case .readyToSave: committed = bridge.persistVerified()
            case .identityInvalid: committed = bridge.clearAuthoritativelyInvalid()
            default: committed = result
            }
            // No external verifier callback after commit: preserve the bridge's checked terminal ownership.
            guard self.isRestoring, self.restoreOperation == operation, self.shell.generation == generation else { return }
            if committed == .stored {
                guard let adopted = bridge.committedOperation, session.isCurrent(adopted) else {
                    self.sessionBridgeResult = .stale; self.localSessionStatus = .unknown
                    self.requiresReconciliation = true; self.isRestoring = false; self.task = nil
                    return
                }
            }
            self.sessionBridgeResult = committed
            switch committed {
            case .stored:
                guard let adopted = bridge.committedOperation, session.isCurrent(adopted) else { return }
                self.committedSessionOperation = adopted
                self.restoreOperation = adopted
                self.localSessionStatus = .needsVerification
                self.state = .identityNeedsServerCheck // not a CJ principal/invitation grant
            case .invalidated:
                self.committedSessionOperation = nil
                self.localSessionStatus = .cleared; self.state = .rejected
            case .networkUnknown, .stale, .operationConflict:
                self.localSessionStatus = .unknown; self.requiresReconciliation = true
            case .storageFailure(let error): self.localSessionStatus = .blocked(error)
            case .unavailable: self.localSessionStatus = .needsVerification
            default: self.localSessionStatus = .verificationFailed
            }
            self.isRestoring = false; self.task = nil
        }
    }

}
