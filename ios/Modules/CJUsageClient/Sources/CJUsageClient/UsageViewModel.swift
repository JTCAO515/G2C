import Foundation
import Observation
import CJSession
import CJMessageHTTP
import CJAPI
import OpenAPIRuntime

public typealias UsageCredentialCallback = @MainActor (UsageBinding) async throws -> String?

@MainActor @Observable public final class UsageViewModel {
    private let session: SessionLifecycle
    private let endpoint: MessageEndpoint?
    private let credentials: UsageCredentialCallback?
    private let current: @MainActor () -> UsageBinding?
    private let transport: (any ClientTransport)?
    private let owner = UUID()
    private var generation = UUID()
    private var binding: UsageBinding?
    private var consumed = false
    private var stored: UsageState = .unavailable

    /// No endpoint, credential or transport default. Construct live transport explicitly.
    public init(session: SessionLifecycle, endpoint: MessageEndpoint? = nil,
                credentials: UsageCredentialCallback? = nil,
                currentBinding: @escaping @MainActor () -> UsageBinding?,
                liveReadTransport: NoRedirectTransport? = nil) {
        self.session = session; self.endpoint = endpoint; self.credentials = credentials
        current = currentBinding; transport = liveReadTransport
    }
    /// In-process tests only; unavailable to external hosts.
    init(session: SessionLifecycle, endpoint: MessageEndpoint, credentials: @escaping UsageCredentialCallback,
         currentBinding: @escaping @MainActor () -> UsageBinding?, interceptedTransport: any ClientTransport) {
        self.session = session; self.endpoint = endpoint; self.credentials = credentials
        current = currentBinding; transport = interceptedTransport
    }
    public var state: UsageState {
        guard let binding else { return .unavailable }
        let token = generation
        guard (try? check(binding, token)) != nil else { return .unavailable }
        return stored
    }
    /// Host calls synchronously on selection/session invalidation. Never cancels remotely.
    public func invalidate() {
        generation = UUID(); binding = nil; consumed = false; stored = .unavailable
    }
    private func check(_ original: UsageBinding, _ token: UUID) throws {
        guard generation == token, binding == original, session.isCurrent(original.sessionOperation) else { throw UsageFailure.stale }
        let observed = current()
        // Recheck all local ownership AFTER the trusted callback, which may reenter.
        guard generation == token, binding == original, observed == original,
              session.isCurrent(original.sessionOperation) else { throw UsageFailure.stale }
        try Task.checkCancellation()
    }
    /// Called synchronously from the user action, before creating any Task.
    /// The independent generation is installed BEFORE callbacks, even at equal revision.
    public func prepare(_ original: UsageBinding) throws -> PreparedUsageRead {
        let token = UUID(); generation = token; binding = original; consumed = false; stored = .unavailable
        try check(original, token)
        guard endpoint != nil, credentials != nil, transport != nil,
              !original.actorIdentity.isEmpty, validID(original.source.attemptID),
              original.source.operationID.map(validID) ?? true,
              original.source.runID.map(validID) ?? true else { throw UsageFailure.unavailable }
        try check(original, token)
        stored = .loading
        return PreparedUsageRead(owner: owner, generation: token, binding: original)
    }
    /// Exactly one GET per preparation; explicit user action only, no automatic retry/poll.
    public func read(_ prepared: PreparedUsageRead) async {
        let original = prepared.binding; let token = prepared.generation
        guard prepared.owner == owner, generation == token, !consumed else { return }
        consumed = true
        do {
            try check(original, token)
            guard let endpoint, let credentials, let transport else { throw UsageFailure.unavailable }
            let bearer: String?
            do { bearer = try await credentials(original) }
            catch { try check(original, token); throw UsageFailure.unavailable }
            try check(original, token)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw UsageFailure.unavailable }
            let client = Client(serverURL: endpoint.url, configuration: .memory,
                transport: UsageTransport(underlying: transport, endpoint: endpoint, bearer: bearer,
                    validate: { [self] in try check(original, token) }))
            let output = try await client.getUsageAttemptStatus(query: .init(attempt_id: original.source.attemptID))
            try check(original, token)
            let result: UsageSnapshot
            switch output {
            case .ok(let response): result = try snapshot(response.body.json, source: original.source)
            case .default(let status, let response):
                _ = try response.body.json
                throw UsageFailure.rejected(status)
            }
            // Final callback and ownership check immediately precede publication.
            try check(original, token)
            stored = .loaded(result)
        } catch {
            // Stale/cancelled work cannot clear or fail a newer read.
            guard generation == token else { return }
            do { try check(original, token) }
            catch { if generation == token { stored = .unavailable }; return }
            stored = .failed(error as? UsageFailure ?? .exchangeFailed)
        }
    }
}
func validID(_ text: String) -> Bool { !text.isEmpty && text.unicodeScalars.count <= 200 && text.utf8.count <= 800 }
