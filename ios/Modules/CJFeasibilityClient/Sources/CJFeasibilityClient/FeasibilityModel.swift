import Foundation
import Observation
import CJSession
import CJMessageHTTP
import CJAPI
import OpenAPIRuntime

public typealias FeasibilityCredentials = @MainActor (FeasibilityBinding) async throws -> String?

@MainActor @Observable public final class FeasibilityModel {
    private let session: SessionLifecycle
    private let current: @MainActor () -> FeasibilityBinding?
    private let endpoint: MessageEndpoint?
    private let credentials: FeasibilityCredentials?
    private let transport: (any ClientTransport)?
    private let limits: FeasibilityLimits?
    private let owner = UUID()
    // Only state publication is observed. Ownership changes must be callback-free.
    @ObservationIgnored private var generation = UUID()
    @ObservationIgnored private var binding: FeasibilityBinding?
    @ObservationIgnored private var consumed = false
    private struct Publication {
        let generation: UUID
        let binding: FeasibilityBinding?
        let state: FeasibilityState
    }
    @ObservationIgnored private var stored: Publication?

    /// Production factory is hard closed pending root gates and accepted host activation.
    /// No network object, credentials, storage, or default endpoint is constructed.
    public init(session: SessionLifecycle, currentBinding: @escaping @MainActor () -> FeasibilityBinding?) {
        self.session = session; current = currentBinding
        endpoint = nil; credentials = nil; transport = nil; limits = nil
    }
    /// Local synthetic transport fixture only. This is not an external host activation path.
    init(session: SessionLifecycle, endpoint: MessageEndpoint, limits: FeasibilityLimits,
         credentials: @escaping FeasibilityCredentials, currentBinding: @escaping @MainActor () -> FeasibilityBinding?,
         interceptedTransport: any ClientTransport) {
        self.session = session; self.endpoint = endpoint; self.limits = limits
        self.credentials = credentials; current = currentBinding; transport = interceptedTransport
    }
    public var state: FeasibilityState {
        access(keyPath: \.state)
        guard let binding, let publication = stored,
              publication.generation == generation, publication.binding == binding else { return .unavailable }
        guard (try? check(binding, publication.generation, cancellation: false)) != nil else { return .unavailable }
        return publication.state
    }
    public func invalidate() {
        let token = UUID(); generation = token; binding = nil; consumed = false
        withMutation(keyPath: \.state) {
            // A synchronous observer may prepare a replacement before this closure.
            guard generation == token, binding == nil else { return }
            stored = .init(generation: token, binding: nil, state: .unavailable)
        }
    }
    private func publish(_ state: FeasibilityState, binding original: FeasibilityBinding,
                         token: UUID, cancellation: Bool = true) throws {
        try check(original, token, cancellation: cancellation)
        try withMutation(keyPath: \.state) {
            // Observation willSet notifies BEFORE this mutation. Recheck after that
            // synchronous callback, then commit one stamped value without callbacks.
            try check(original, token, cancellation: cancellation)
            stored = .init(generation: token, binding: original, state: state)
        }
        try check(original, token, cancellation: cancellation)
    }
    private func check(_ original: FeasibilityBinding, _ token: UUID, cancellation: Bool = true) throws {
        guard generation == token, binding == original, session.isCurrent(original.sessionOperation) else { throw FeasibilityFailure.stale }
        let observed = current()
        // Callback may synchronously reenter prepare/invalidate or replace the session.
        guard generation == token, binding == original, observed == original,
              session.isCurrent(original.sessionOperation) else { throw FeasibilityFailure.stale }
        if cancellation { try Task.checkCancellation() }
    }
    /// Capture synchronously in explicit user action BEFORE creating a Task.
    public func prepare(_ original: FeasibilityBinding) throws -> PreparedFeasibilityRead {
        let token = UUID(); generation = token; binding = original; consumed = false
        try publish(.unavailable, binding: original, token: token)
        guard let endpoint, (1...1_048_576).contains(endpoint.maximumResponseBytes),
              (1...1_048_576).contains(endpoint.maximumRequestBytes),
              transport != nil, credentials != nil, limits != nil,
              validID(original.needsID),
              (original.acceptedRevision == nil) == (original.acceptedContentSHA256 == nil),
              original.acceptedRevision.map({ $0 > 0 }) ?? true,
              original.acceptedContentSHA256.map(validHash) ?? true else { throw FeasibilityFailure.unavailable }
        try check(original, token)
        try publish(.loading, binding: original, token: token)
        return .init(owner: owner, generation: token, binding: original)
    }
    /// Exactly one explicit GET. No polling, retry, solver, mutation or private persistence.
    public func read(_ work: PreparedFeasibilityRead) async {
        let original = work.binding; let token = work.generation
        guard work.owner == owner, generation == token, !consumed else { return }
        consumed = true
        do {
            try check(original, token)
            guard let endpoint, let credentials, let transport, let limits else { throw FeasibilityFailure.unavailable }
            let bearer = try await credentials(original)
            try check(original, token)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw FeasibilityFailure.unavailable }
            let client = Client(serverURL: endpoint.url, configuration: .memory,
                transport: FeasibilityTransport(underlying: transport, endpoint: endpoint, limits: limits,
                    binding: original, bearer: bearer, validate: { [self] in try check(original, token) }))
            let output = try await client.evaluateCurrentNeedsFeasibility(query: .init(needs_id: original.needsID))
            try check(original, token)
            let observation: FeasibilityObservation
            switch output {
            case .ok(let response):
                let body = try response.body.json
                observation = .init(requestID: body.request_id, report: body.evaluation)
            case .default(let status, let response):
                let body = try response.body.json
                throw FeasibilityFailure.rejected(status, body.error.code)
            }
            try check(original, token)
            try publish(.loaded(observation), binding: original, token: token)
        } catch {
            guard generation == token else { return }
            // Cancelled work must leave loading, without clearing a replacement selection.
            do { try check(original, token, cancellation: false) }
            catch { return } // Getter withholds stale publications; never clear a replacement.
            let failure: FeasibilityState = Task.isCancelled || error is CancellationError
                ? .cancelled : .failed(error as? FeasibilityFailure ?? .exchangeFailed)
            try? publish(failure, binding: original, token: token, cancellation: false)
            // Never expose generated ClientError, authorization-bearing request or source body.
        }
    }
}
