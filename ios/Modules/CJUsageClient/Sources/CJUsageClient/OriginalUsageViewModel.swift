import Foundation
import Observation
import CJAPI
import CJSession
import CJMessageClient
import CJMessageHTTP
import OpenAPIRuntime

/// Official original-association source path. The old explicit-host UsageViewModel
/// remains a compatibility path and cannot construct this model's closed source.
@MainActor @Observable public final class OriginalUsageViewModel {
    private let session: SessionLifecycle
    private let recovery: MessageRecovery
    private let scope: StorageScope
    private let endpoint: MessageEndpoint?
    private let credentials: OriginalUsageCredentialCallback?
    private let current: @MainActor () -> OriginalUsageBinding?
    private let transport: (any ClientTransport)?
    private let owner = UUID()
    private var generation = UUID()
    private var binding: OriginalUsageBinding?
    private var consumed = false
    private var resolved: ResolvedUsageSource?
    private var stored: OriginalUsageState = .unavailable

    public init(session: SessionLifecycle, recovery: MessageRecovery, scope: StorageScope,
                endpoint: MessageEndpoint? = nil, credentials: OriginalUsageCredentialCallback? = nil,
                currentBinding: @escaping @MainActor () -> OriginalUsageBinding?, liveReadTransport: NoRedirectTransport? = nil) {
        self.session = session; self.recovery = recovery; self.scope = scope
        self.endpoint = endpoint; self.credentials = credentials; current = currentBinding; transport = liveReadTransport
    }
    init(session: SessionLifecycle, recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
         credentials: @escaping OriginalUsageCredentialCallback, currentBinding: @escaping @MainActor () -> OriginalUsageBinding?,
         interceptedTransport: any ClientTransport) {
        self.session = session; self.recovery = recovery; self.scope = scope
        self.endpoint = endpoint; self.credentials = credentials; current = currentBinding; transport = interceptedTransport
    }
    /// Read-only capture: never stage, query, mark accepted, mutate storage or mint IDs.
    public func captureAcceptedMessage(_ original: ActionRecord, lease: Lease) throws -> AcceptedUsageMessage {
        guard let endpoint, original.phase == .accepted, let bytes = original.receipt,
              bytes.count <= endpoint.maximumResponseBytes, original.originalUTF8.count <= endpoint.maximumRequestBytes else { throw UsageFailure.unavailable }
        try recovery.validateScope(scope, lease: lease)
        guard try recovery.action(messageID: original.messageID, lease: lease) == original else { throw UsageFailure.stale }
        var json = StrictUsageJSON(bytes: Array(bytes)); try json.check()
        let receipt = try JSONDecoder().decode(Components.Schemas.MessageReceipt.self, from: bytes)
        var command = StrictUsageJSON(bytes: Array(original.originalUTF8)); try command.check()
        // MESSAGE refs are nonempty with configured byte budgets. The original
        // stored RUN usage command separately retains its 200-scalar run ID limit.
        guard let envelope = try JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any],
              let message = envelope["message_id"] as? String, let conversation = envelope["conversation_id"] as? String,
              equalBytes(message, original.messageID), equalBytes(receipt.message_id, original.messageID),
              equalBytes(conversation, receipt.conversation_id), equalBytes(receipt.input_sha256, original.inputSHA256),
              [receipt.message_id, receipt.conversation_id, receipt.generation].allSatisfy({ !$0.isEmpty }),
              validID(receipt.run_id),
              receipt.sequence > 0 else { throw UsageFailure.invalidResponse }
        return AcceptedUsageMessage(owner: owner, id: UUID(), record: original, lease: lease, receipt: receipt)
    }
    public var state: OriginalUsageState {
        guard let binding else { return .unavailable }
        guard (try? check(binding, generation)) != nil else { return .unavailable }
        return stored
    }
    public func invalidate() {
        generation = UUID(); binding = nil; resolved = nil; consumed = false; stored = .unavailable
    }
    private func check(_ original: OriginalUsageBinding, _ token: UUID) throws {
        guard generation == token, binding == original, original.acceptedMessage.owner == owner,
              session.isCurrent(original.sessionOperation) else { throw UsageFailure.stale }
        let observed = current()
        guard generation == token, binding == original, observed == original,
              session.isCurrent(original.sessionOperation) else { throw UsageFailure.stale }
        let message = original.acceptedMessage
        try recovery.validateScope(scope, lease: message.lease)
        guard try recovery.action(messageID: message.messageID, lease: message.lease) == message.record else { throw UsageFailure.stale }
        try Task.checkCancellation()
    }
    /// Explicit user action 1. Capture original binding BEFORE scheduling a Task.
    public func prepareAssociation(_ original: OriginalUsageBinding) throws -> PreparedOriginalUsageRead {
        let token = UUID(); generation = token; binding = original; consumed = false; resolved = nil; stored = .unavailable
        try check(original, token)
        guard endpoint != nil, credentials != nil, transport != nil, !original.actorIdentity.isEmpty else { throw UsageFailure.unavailable }
        try check(original, token); stored = .loading
        return PreparedOriginalUsageRead(owner: owner, generation: token, binding: original, source: nil)
    }
    /// Explicit user action 2, after inspecting sourceReady. No automatic status GET.
    public func prepareStatus(_ source: ResolvedUsageSource) throws -> PreparedOriginalUsageRead {
        guard source.owner == owner, resolved == source else { throw UsageFailure.stale }
        let original = source.binding; let token = UUID()
        generation = token; binding = original; consumed = false; stored = .unavailable
        try check(original, token)
        guard resolved == source else { throw UsageFailure.stale }
        stored = .loading
        return PreparedOriginalUsageRead(owner: owner, generation: token, binding: original, source: source)
    }
    public func read(_ prepared: PreparedOriginalUsageRead) async {
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
                    association: prepared.source == nil, validate: { [self] in try check(original, token) }))
            if let source = prepared.source {
                guard resolved == source else { throw UsageFailure.stale }
                let output = try await client.getUsageAttemptStatus(query: .init(attempt_id: source.attemptID))
                try check(original, token)
                let result: UsageSnapshot
                switch output {
                case .ok(let response): result = try snapshot(response.body.json,
                    source: UsageSource(attemptID: source.attemptID, operationID: source.operationID, runID: source.runID))
                case .default(let status, let response): _ = try response.body.json; throw status == 503 ? UsageFailure.unavailable : .rejected(status)
                }
                try check(original, token)
                guard resolved == source else { throw UsageFailure.stale }
                stored = .loaded(result)
            } else {
                let output = try await client.getOriginalUsageAssociation(query: .init(message_id: original.acceptedMessage.messageID))
                try check(original, token)
                let association: Components.Schemas.OriginalUsageAssociation; let requestID: String
                switch output {
                case .ok(let response): let body = try response.body.json; association = body.association; requestID = body.request_id
                case .default(let status, let response): _ = try response.body.json; throw status == 503 ? UsageFailure.unavailable : .rejected(status)
                }
                let receipt = original.acceptedMessage.receipt
                guard equalBytes(association.message_id, receipt.message_id), equalBytes(association.conversation_id, receipt.conversation_id),
                      equalBytes(association.generation, receipt.generation), equalBytes(association.run_id, receipt.run_id),
                      association.message_sequence == receipt.sequence else { throw UsageFailure.invalidResponse }
                let source = ResolvedUsageSource(owner: owner, id: UUID(), binding: original, association: association, requestID: requestID)
                try check(original, token)
                resolved = source; stored = .sourceReady(source)
            }
        } catch {
            guard generation == token else { return }
            do { try check(original, token) }
            catch { if generation == token { stored = .unavailable }; return }
            stored = .failed(error as? UsageFailure ?? .exchangeFailed)
        }
    }
}
private func equalBytes(_ a: String, _ b: String) -> Bool { Data(a.utf8) == Data(b.utf8) }
