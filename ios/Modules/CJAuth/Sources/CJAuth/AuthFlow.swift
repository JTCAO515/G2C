import Foundation

public enum AuthProvider: Sendable { case email, google, apple }
public enum AuthPurpose: Sendable { case signIn, register, verifyEmail, requestRecovery, resetPassword }
public enum AuthAction: CaseIterable, Sendable {
    case emailSignIn, emailRegister, emailVerify, emailRecovery, emailReset, googleSignIn, appleSignIn
    public var provider: AuthProvider {
        switch self { case .googleSignIn: .google; case .appleSignIn: .apple; default: .email }
    }
    public var purpose: AuthPurpose {
        switch self {
        case .emailRegister: .register
        case .emailVerify: .verifyEmail
        case .emailRecovery: .requestRecovery
        case .emailReset: .resetPassword
        default: .signIn
        }
    }
}

public enum UnavailableReason: Equatable, Sendable {
    case missingConfiguration, missingRuntimeMaterial, sdkAdapterNotInstalled, hostCapabilityRequired
}

/// Local correlation only. Never a nonce, OAuth state, credential or authorization.
public struct AuthAttempt: Equatable, Sendable {
    fileprivate let instance: UUID
    fileprivate let generation: UUID
    fileprivate let operation = UUID()
    public let action: AuthAction
    // Shared by value copies and every adapter receiving this exact attempt.
    package let sdkExecution = SDKAttemptExecution()
}

/// Process-local execution record; no credentials, persistence or global registry.
@MainActor package final class SDKAttemptExecution: Equatable, Sendable {
    package var task: Task<SDKEvent, Never>?
    package var result: SDKEvent?
    nonisolated init() {}
    nonisolated package static func == (lhs: SDKAttemptExecution, rhs: SDKAttemptExecution) -> Bool {
        lhs === rhs
    }
}

/// Events must come from an SDK-owning adapter, never parsed directly from an incoming URL.
/// Identity discovery is deliberately NOT server verification or beta eligibility.
public enum SDKEvent: Equatable, Sendable {
    case unavailable(UnavailableReason)
    case identityNeedsServerCheck, emailVerificationRequired, verificationPending, recoveryRequestAcknowledged
    case passwordUpdatedRequiresSignIn, userCancelled, networkUnknown, rejected
}

public enum FlowState: Equatable, Sendable {
    case idle, unavailable(UnavailableReason), waiting(AuthAction)
    case identityNeedsServerCheck, emailVerificationRequired, verificationPending, recoveryRequestAcknowledged
    case passwordUpdatedRequiresSignIn, cancelledLocally, networkUnknown, rejected
    case callbackPurposeMismatch
}

/// Future official SDK adapter owns secure input, credential storage, trusted callback
/// parsing/state/nonce validation and system UI. This protocol accepts no secrets or URLs.
@MainActor public protocol AuthSDKAdapter {
    func unavailableReason(for action: AuthAction) -> UnavailableReason?
    func perform(_ attempt: AuthAttempt) async -> SDKEvent
}

/// The only shipped adapter. Cannot open a browser, contact a provider or authenticate.
@MainActor public struct UnconfiguredSDKAdapter: AuthSDKAdapter {
    public init() {}
    public func unavailableReason(for action: AuthAction) -> UnavailableReason? { .missingConfiguration }
    public func perform(_ attempt: AuthAttempt) async -> SDKEvent { .rejected }
}

@MainActor public final class AuthFlow {
    private let instance = UUID()
    private var generation = UUID()
    public private(set) var pending: AuthAttempt?
    public private(set) var state: FlowState = .idle
    /// No result in this package can grant model/business access.
    public var canUseRestrictedBusiness: Bool { false }

    public init() {}

    /// Every explicit action supersedes the previous callback context. The host must
    /// separately fence private UI/cache before account changes; this owns no session.
    @discardableResult
    public func begin(_ action: AuthAction, using adapter: any AuthSDKAdapter) -> AuthAttempt? {
        pending = nil
        if let reason = adapter.unavailableReason(for: action) {
            state = .unavailable(reason)
            return nil
        }
        let attempt = AuthAttempt(instance: instance, generation: generation, action: action)
        pending = attempt
        state = .waiting(action)
        return attempt
    }

    public func run(_ action: AuthAction, using adapter: any AuthSDKAdapter) async {
        guard let attempt = begin(action, using: adapter) else { return }
        let event = await adapter.perform(attempt)
        // Re-check after await even if provider UI/task cancellation failed.
        _ = accept(event, purpose: attempt.action.purpose, for: attempt)
    }

    /// SDK/host boundary, not a raw URL handler. An adapter must validate the original
    /// callback against its operation, provider and purpose before calling this method.
    @discardableResult
    public func accept(_ event: SDKEvent, purpose: AuthPurpose, for attempt: AuthAttempt) -> Bool {
        guard pending == attempt, attempt.instance == instance, attempt.generation == generation else { return false }
        guard purpose == attempt.action.purpose, compatible(event, with: purpose) else {
            pending = nil
            state = .callbackPurposeMismatch
            return false
        }
        pending = nil // duplicate callback cannot mutate state
        switch event {
        case .unavailable(let reason): state = .unavailable(reason)
        case .identityNeedsServerCheck: state = .identityNeedsServerCheck
        case .emailVerificationRequired: state = .emailVerificationRequired
        case .verificationPending: state = .verificationPending
        case .recoveryRequestAcknowledged: state = .recoveryRequestAcknowledged
        case .passwordUpdatedRequiresSignIn: state = .passwordUpdatedRequiresSignIn
        case .userCancelled: state = .cancelledLocally
        case .networkUnknown: state = .networkUnknown
        case .rejected: state = .rejected
        }
        return true
    }

    @discardableResult
    public func cancel(_ attempt: AuthAttempt) -> Bool {
        guard pending == attempt else { return false }
        pending = nil
        state = .cancelledLocally
        return true // local only; remote operation may already have happened
    }

    /// Called on logout, account switch, new account lifetime or authoritative invalidation.
    /// Does not revoke credentials, clear host UI, delete data or cancel remote work.
    public func invalidateIdentity() {
        generation = UUID()
        pending = nil
        state = .idle
    }

    private func compatible(_ event: SDKEvent, with purpose: AuthPurpose) -> Bool {
        switch event {
        case .unavailable, .userCancelled, .networkUnknown, .rejected: true
        case .identityNeedsServerCheck: purpose == .signIn || purpose == .verifyEmail
        case .emailVerificationRequired: purpose == .signIn
        case .verificationPending: purpose == .register
        case .recoveryRequestAcknowledged: purpose == .requestRecovery
        case .passwordUpdatedRequiresSignIn: purpose == .resetPassword
        }
    }
}
