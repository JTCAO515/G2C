import Foundation
import Observation
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime

@MainActor @Observable public final class CleanupViewModel {
    private let session: SessionLifecycle
    private let environment: UUID
    private let endpoint: MessageEndpoint?
    private let maximumSteps: Int
    private let credentials: CleanupCredentialCallback?
    private let current: @MainActor () -> CleanupBinding?
    private let transport: (any ClientTransport)?
    private let owner = UUID()
    private var generation = UUID()
    private var binding: CleanupBinding?
    private var consumed = false
    private var stored: CleanupState = .unavailable

    /// No production factory or network defaults. Trusted host supplies current ALLOWED
    /// credentials and existing operation provenance. Without either, leave unavailable.
    public init(session: SessionLifecycle, environment: UUID, maximumSteps: Int,
                endpoint: MessageEndpoint? = nil, credentials: CleanupCredentialCallback? = nil,
                currentBinding: @escaping @MainActor () -> CleanupBinding?,
                liveReadTransport: NoRedirectTransport? = nil) {
        self.session = session; self.environment = environment; self.maximumSteps = maximumSteps
        self.endpoint = endpoint; self.credentials = credentials
        current = currentBinding; transport = liveReadTransport
    }
    /// Internal in-process test seam, never a public transport bypass.
    init(session: SessionLifecycle, environment: UUID, maximumSteps: Int = 128,
         endpoint: MessageEndpoint, credentials: @escaping CleanupCredentialCallback,
         currentBinding: @escaping @MainActor () -> CleanupBinding?, interceptedTransport: any ClientTransport) {
        self.session = session; self.environment = environment; self.maximumSteps = maximumSteps
        self.endpoint = endpoint; self.credentials = credentials
        current = currentBinding; transport = interceptedTransport
    }
    public var state: CleanupState {
        guard let binding else { return .unavailable }
        let token = generation
        guard (try? check(binding, token)) != nil else {
            if generation == token { invalidate() }
            return .unavailable
        }
        return stored
    }
    /// Synchronous local fence for logout, account/environment/operation switch, dismiss
    /// or user cancellation. Does not cancel the server's original cleanup operation.
    public func invalidate() {
        generation = UUID(); binding = nil; consumed = false; stored = .unavailable
    }
    private func check(_ original: CleanupBinding, _ token: UUID) throws {
        guard generation == token, binding == original, original.environment == environment,
              session.isCurrent(original.sessionOperation) else { throw CleanupFailure.stale }
        let observed = current()
        // Callback can reenter/switch even when returning its old captured binding.
        guard generation == token, binding == original, observed == original,
              session.isCurrent(original.sessionOperation) else { throw CleanupFailure.stale }
        try Task.checkCancellation()
    }
    /// Capture synchronously at the explicit user tap, before scheduling a Task.
    public func prepare(_ original: CleanupBinding) throws -> PreparedCleanupRead {
        let token = UUID(); generation = token; binding = original; consumed = false; stored = .unavailable
        try check(original, token)
        guard let endpoint, (1...65536).contains(endpoint.maximumResponseBytes),
              (1...128).contains(maximumSteps), credentials != nil, transport != nil,
              !original.actorIdentity.isEmpty,
              cleanupIdentifier(original.originalOperationID, maximum: 160) else { throw CleanupFailure.unavailable }
        try check(original, token)
        stored = .loading
        return PreparedCleanupRead(owner: owner, generation: token, binding: original)
    }
    /// One GET per preparation. No background polling, retries, create or recovery.
    public func read(_ prepared: PreparedCleanupRead) async {
        let original = prepared.binding; let token = prepared.generation
        guard prepared.owner == owner, generation == token, !consumed else { return }
        consumed = true
        do {
            try check(original, token)
            guard let endpoint, let credentials, let transport else { throw CleanupFailure.unavailable }
            let bearer: String?
            do { bearer = try await credentials(original) }
            catch { try check(original, token); throw CleanupFailure.unavailable }
            try check(original, token)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else {
                throw CleanupFailure.unavailable
            }
            let client = Client(serverURL: endpoint.url, configuration: .memory,
                transport: CleanupTransport(underlying: transport, endpoint: endpoint, bearer: bearer,
                    originalOperationID: original.originalOperationID, maximumSteps: maximumSteps,
                    validate: { [self] in try check(original, token) }))
            let output = try await client.getCurrentAccountCleanupProgress(query: .init(operation_id: original.originalOperationID))
            try check(original, token)
            let result: CleanupProgress
            switch output {
            case .ok(let response): result = try response.body.json.progress
            case .default(let status, let response):
                _ = try response.body.json
                throw status == 503 ? CleanupFailure.unavailable : .rejected(status)
            }
            try validateProgress(result, operationID: original.originalOperationID, maximumSteps: maximumSteps)
            try check(original, token)
            stored = .loaded(result)
        } catch {
            guard generation == token else { return }
            do { try check(original, token) }
            catch { if generation == token { invalidate() }; return }
            // OpenAPI runtime wraps transport failures. Retain only our safe typed
            // classification; never retain/log ClientError (it can contain bearer).
            let failure = error as? CleanupFailure
                ?? (error as? ClientError)?.underlyingError as? CleanupFailure
                ?? .exchangeUnknown
            stored = .failed(failure)
        }
    }
}
