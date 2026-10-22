import Foundation
import Auth
import CJAuth

/// Non-secret deployment metadata must be explicitly provided. No URL/key defaults.
public struct SupabaseAdapterConfiguration: Sendable {
    public let authURL: URL?
    public let publicKey: String?
    public let emailRedirect: URL?
    public let googleClientID: String?
    public let appleClientID: String?

    public init(authURL: URL? = nil, publicKey: String? = nil, emailRedirect: URL? = nil,
                googleClientID: String? = nil, appleClientID: String? = nil) {
        self.authURL = authURL; self.publicKey = publicKey; self.emailRedirect = emailRedirect
        self.googleClientID = googleClientID; self.appleClientID = appleClientID
    }
}

/// Transient host input, never logged or persisted here. Native input must be produced
/// by the real platform flow for this exact attempt; arbitrary URL strings are not accepted.
public enum SDKMaterial: Sendable {
    case email(attempt: AuthAttempt, address: String, password: String?)
    case native(attempt: AuthAttempt, provider: AuthProvider, clientID: String,
                idToken: String, nonce: String, accessToken: String?)
}

/// Injected fetch is mandatory for local transport tests. Default never touches URLSession.
public typealias AuthFetch = @Sendable (URLRequest) async throws -> (Data, URLResponse)

@MainActor public final class SupabaseSDKAdapter: AuthSDKAdapter {
    private let configuration: SupabaseAdapterConfiguration
    private let fetch: AuthFetch
    private let material: @MainActor (AuthAttempt) async -> SDKMaterial?
    private let isCurrent: @MainActor (AuthAttempt) -> Bool
    private let onSessionForSecureStorage: (@MainActor (Session, AuthAttempt) -> Void)?

    public init(configuration: SupabaseAdapterConfiguration,
                fetch: @escaping AuthFetch = { _ in throw URLError(.notConnectedToInternet) },
                isCurrent: @escaping @MainActor (AuthAttempt) -> Bool,
                onSessionForSecureStorage: (@MainActor (Session, AuthAttempt) -> Void)? = nil,
                material: @escaping @MainActor (AuthAttempt) async -> SDKMaterial?) {
        self.configuration = configuration; self.fetch = fetch
        self.isCurrent = isCurrent; self.material = material
        self.onSessionForSecureStorage = onSessionForSecureStorage
    }

    public func unavailableReason(for action: AuthAction) -> UnavailableReason? {
        guard let url = configuration.authURL, validEndpoint(url),
              let key = configuration.publicKey, !key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              key.hasPrefix("sb_publishable_"), key.count > "sb_publishable_".count else { return .missingConfiguration }
        switch action {
        case .emailRegister, .emailRecovery:
            guard let redirect = configuration.emailRedirect, validEndpoint(redirect) else { return .missingConfiguration }
        case .googleSignIn:
            guard nonempty(configuration.googleClientID) else { return .missingConfiguration }
        case .appleSignIn:
            guard nonempty(configuration.appleClientID) else { return .missingConfiguration }
        case .emailVerify, .emailReset:
            // A trusted recovery/verification callback and secure credential lifecycle
            // are not supplied yet. Never exchange arbitrary URL/code or update a user.
            return .hostCapabilityRequired
        case .emailSignIn: break
        }
        return nil
    }

    public func perform(_ attempt: AuthAttempt) async -> SDKEvent {
        guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
        let execution = attempt.sdkExecution
        if let result = execution.result { return result }
        let task: Task<SDKEvent, Never>
        if let running = execution.task {
            task = running
        } else {
            task = Task { await self.performOnce(attempt) }
            // Publish before the first await: reentrancy cannot start another dispatch.
            execution.task = task
        }
        let result = await task.value
        execution.result = result
        execution.task = nil
        guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
        return result
    }

    private func performOnce(_ attempt: AuthAttempt) async -> SDKEvent {
        if let reason = unavailableReason(for: attempt.action) { return .unavailable(reason) }
        guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
        let supplied = await material(attempt)
        guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
        guard let supplied else { return .unavailable(.missingRuntimeMaterial) }
        guard let url = configuration.authURL, let key = configuration.publicKey else {
            return .unavailable(.missingConfiguration)
        }
        // Client/storage are private to this attempt: an SDK late success cannot replace
        // another attempt's session or write keychain. No auto refresh/restore/logger.
        let storage = AttemptStorage()
        let gate = SingleRequestGate()
        let transport = fetch
        let current = isCurrent
        defer { storage.clear() }
        let client = AuthClient(configuration: .init(
            url: url, headers: ["apikey": key, "Authorization": "Bearer \(key)"],
            flowType: .pkce, localStorage: storage,
            fetch: { request in
                guard await current(attempt) else { throw CancellationError() }
                try await gate.claim() // suppress SDK automatic POST retries after unknown ACK
                guard await current(attempt), !Task.isCancelled else { throw CancellationError() }
                return try await transport(request)
            }, autoRefreshToken: false, emitLocalSessionAsInitialSession: false
        ))
        do {
            let outcome: SDKEvent
            var verifiedSession: Session?
            switch (attempt.action, supplied) {
            case (.emailSignIn, .email(let bound, let address, let password)):
                guard bound == attempt, nonempty(address), let password, nonempty(password) else { return .unavailable(.missingRuntimeMaterial) }
                verifiedSession = try await client.signIn(email: address, password: password)
                outcome = .identityNeedsServerCheck
            case (.emailRegister, .email(let bound, let address, let password)):
                guard bound == attempt, nonempty(address), let password, nonempty(password) else { return .unavailable(.missingRuntimeMaterial) }
                _ = try await client.signUp(email: address, password: password, redirectTo: configuration.emailRedirect)
                outcome = .verificationPending
            case (.emailRecovery, .email(let bound, let address, _)):
                guard bound == attempt, nonempty(address) else { return .unavailable(.missingRuntimeMaterial) }
                try await client.resetPasswordForEmail(address, redirectTo: configuration.emailRedirect)
                outcome = .recoveryRequestAcknowledged
            case (.googleSignIn, .native(let bound, let provider, let clientID, let token, let nonce, let access)),
                 (.appleSignIn, .native(let bound, let provider, let clientID, let token, let nonce, let access)):
                let expected = attempt.action == .googleSignIn ? configuration.googleClientID : configuration.appleClientID
                guard bound == attempt, provider == attempt.action.provider, clientID == expected,
                      nonempty(token), nonempty(nonce) else { return .unavailable(.missingRuntimeMaterial) }
                verifiedSession = try await client.signInWithIdToken(credentials: .init(
                    provider: attempt.action == .googleSignIn ? .google : .apple,
                    idToken: token, accessToken: access, nonce: nonce))
                outcome = .identityNeedsServerCheck
            default: return .unavailable(.missingRuntimeMaterial)
            }
            guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
            if let verifiedSession { onSessionForSecureStorage?(verifiedSession, attempt) }
            guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
            return outcome // SDK session callback is not a principal/invitation or persistence receipt
        } catch is CancellationError {
            return .userCancelled
        } catch let error as AuthError {
            guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
            if case .api(_, let code, _, _) = error, code == .emailNotConfirmed,
               attempt.action.purpose == .signIn { return .emailVerificationRequired }
            if case .api(_, _, _, let response) = error,
               (400..<500).contains(response.statusCode) { return .rejected }
            return .networkUnknown // failed decoding/5xx cannot establish a write outcome
        } catch {
            guard isCurrent(attempt), !Task.isCancelled else { return .userCancelled }
            return .networkUnknown // no raw errors/response bodies escape into UI/logs
        }
    }

    private func nonempty(_ value: String?) -> Bool {
        guard let value else { return false }
        return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    private func validEndpoint(_ url: URL) -> Bool {
        url.scheme == "https" && nonempty(url.host) && url.user == nil && url.password == nil
            && url.query == nil && url.fragment == nil
    }
}

/// Short-lived SDK storage only; every access is lock-protected. Never shared between attempts.
private final class AttemptStorage: AuthLocalStorage, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: Data] = [:]
    func store(key: String, value: Data) { lock.withLock { values[key] = value } }
    func retrieve(key: String) -> Data? { lock.withLock { values[key] } }
    func remove(key: String) { _ = lock.withLock { values.removeValue(forKey: key) } }
    func clear() { lock.withLock { values.removeAll() } }
}


private actor SingleRequestGate {
    private var used = false
    enum Failure: Error { case repeatRequestBlocked }
    func claim() throws {
        guard !used else { throw Failure.repeatRequestBlocked }
        used = true
    }
}
