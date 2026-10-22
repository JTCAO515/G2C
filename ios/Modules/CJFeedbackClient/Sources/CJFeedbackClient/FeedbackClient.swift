import Foundation
import CJAPI
import CJMessageHTTP
import CJSession
import OpenAPIRuntime

/// Capture synchronously before creating a Task. Bound to this client and original host lifetime.
public struct FeedbackOperation: Sendable {
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: FeedbackBinding
}

@MainActor public final class FeedbackClient {
    let endpoint: FeedbackEndpoint
    let credentials: FeedbackCredentialCallback
    let currentBinding: @MainActor () -> FeedbackBinding?
    let transport: any ClientTransport
    let store: FeedbackPendingStore?
    private let session: SessionLifecycle?
    private let sessionOperation: SessionOperation?
    let testWrites: Bool
    private let owner = UUID()
    private var generation = UUID()
    private var confirmed = Set<Data>()
    private var uncertainCreation = false

    public init(endpoint: FeedbackEndpoint, credentials: @escaping FeedbackCredentialCallback,
                currentBinding: @escaping @MainActor () -> FeedbackBinding?, session: SessionLifecycle,
                sessionOperation: SessionOperation, pendingStore: FeedbackPendingStore?, liveReadTransport: NoRedirectTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.session = session; self.sessionOperation = sessionOperation; store = pendingStore
        transport = liveReadTransport; testWrites = false
    }
    /// Test-only intercepted transport; never a public write activation switch.
    init(endpoint: FeedbackEndpoint, credentials: @escaping FeedbackCredentialCallback,
         currentBinding: @escaping @MainActor () -> FeedbackBinding?, pendingStore: FeedbackPendingStore?, interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        store = pendingStore; transport = interceptedTransport; session = nil; sessionOperation = nil; testWrites = true
    }
    public var acceptsSubmissions: Bool { testWrites && store != nil }
    // Confirmed originals remain tied to this immutable store namespace; cancellation is not unconfirmation.
    public func invalidate() { generation = UUID() }
    private var sessionIsCurrent: Bool {
        if let session, let sessionOperation { return session.isCurrent(sessionOperation) }
        return testWrites && session == nil && sessionOperation == nil
    }
    func owns(_ operation: FeedbackOperation) -> Bool {
        guard operation.owner == owner, operation.generation == generation else { return false }
        let binding = currentBinding()
        return operation.owner == owner && operation.generation == generation && binding == operation.binding && sessionIsCurrent
    }
    func check(_ operation: FeedbackOperation) throws {
        guard owns(operation) else { throw FeedbackFailure.staleBinding }
        try Task.checkCancellation()
    }
    public func begin(binding: FeedbackBinding) throws -> FeedbackOperation {
        let operation = FeedbackOperation(owner: owner, generation: generation, binding: binding)
        try check(operation); return operation
    }
    func requireStore(_ operation: FeedbackOperation) throws -> FeedbackPendingStore {
        try check(operation)
        guard let store else { throw FeedbackFailure.unconfigured }
        try store.validate(operation.binding); return store
    }
    /// All external resources return before the final callback-free durability check.
    func verify(_ original: FeedbackPending, operation: FeedbackOperation, allowCancelled: Bool = false) throws {
        guard let store else { throw FeedbackFailure.unconfigured }
        try store.validate(operation.binding)
        let proof = try store.requireOriginal(original)
        if allowCancelled { guard owns(operation) else { throw FeedbackFailure.staleBinding } }
        else { try check(operation) }
        try store.validateDurability(proof)
    }
    public func pending(operation: FeedbackOperation) throws -> [FeedbackPending] {
        let store = try requireStore(operation)
        let records = try store.pending(); try check(operation)
        // Verify the entire original set after callbacks, not just directory identity.
        let proofs = try records.map { try store.requireOriginal($0) }
        try check(operation)
        for proof in proofs { try store.validateDurability(proof) }
        try store.validateInventory(records)
        return records
    }
    func api(_ original: FeedbackPending, _ operation: FeedbackOperation) async throws -> Client {
        try check(operation)
        let bearer: String?
        do { bearer = try await credentials(operation.binding) }
        catch { try check(operation); throw FeedbackFailure.unconfigured }
        try check(operation)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw FeedbackFailure.unconfigured }
        return Client(serverURL: endpoint.url, configuration: .memory,
                      transport: FeedbackTransport(underlying: transport, endpoint: endpoint, bearer: bearer, testWrites: testWrites,
                        validate: { [self] in try verify(original, operation: operation) }))
    }
    func exchange<T>(_ operation: FeedbackOperation, _ work: () async throws -> T) async throws -> T {
        do { let result = try await work(); try check(operation); return result }
        catch {
            try check(operation)
            // Never propagate ClientError, credential, provider, URL, body or private exception text.
            throw FeedbackFailure.exchangeUnknown
        }
    }
    public func submit(_ original: FeedbackPending, operation: FeedbackOperation) async throws -> FeedbackResult {
        let store = try requireStore(operation)
        guard testWrites else { throw FeedbackFailure.liveWriteUnavailable }
        try original.validate()
        guard original.originalUTF8.count <= endpoint.maximumRequestBytes else { throw FeedbackFailure.invalidInput }
        let existing = try pending(operation: operation)
        guard !uncertainCreation, !existing.contains(where: { same($0.actionID, original.actionID) }),
              existing.allSatisfy({ confirmed.contains(Data($0.actionID.utf8)) }) else { throw FeedbackFailure.pendingRequiresQuery }
        // Set BEFORE any key/store callback: failed/unknown append never grants another attempt.
        uncertainCreation = true
        try store.append(original) { try self.check(operation) }
        try check(operation)
        let api = try await api(original, operation)
        let result = try await exchange(operation) { try await api.submitFeedback(body: .binary(HTTPBody(original.originalUTF8))) }
        switch result {
        case .ok(let value): return try settle(value.body.json.receipt, original: original, operation: operation)
        case .default(let status, _): throw FeedbackFailure.rejected(status)
        }
    }
    public func queryOriginal(actionID: String, operation: FeedbackOperation) async throws -> FeedbackResult {
        guard let original = try pending(operation: operation).first(where: { same($0.actionID, actionID) }) else { throw FeedbackFailure.invalidInput }
        let api = try await api(original, operation)
        let output = try await exchange(operation) { try await api.queryFeedbackAction(query: .init(action_id: original.actionID)) }
        switch output {
        case .ok(let value):
            switch try value.body.json.receipt {
            case .FeedbackReceipt(let receipt): return try settle(receipt, original: original, operation: operation)
            case .case2(let null):
                guard null.value == nil else { throw FeedbackFailure.invalidResponse }
                try verify(original, operation: operation); return .notObserved
            }
        case .default(let status, _): throw FeedbackFailure.rejected(status)
        }
    }
    private func settle(_ receipt: Components.Schemas.FeedbackReceipt, original: FeedbackPending, operation: FeedbackOperation) throws -> FeedbackResult {
        try validateReceipt(receipt, original: original)
        try verify(original, operation: operation)
        confirmed.insert(Data(original.actionID.utf8)); uncertainCreation = false
        return .submitted(receipt)
    }
}
