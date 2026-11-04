import Foundation
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

@MainActor public final class MemoryErasureEntry: Identifiable {
    public let id = UUID()
    public let itemID: String
    public let expectedVersion: Int64
    public let text: String
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: MemoryBinding
    fileprivate enum Source {
        case typed(TypedMemoryClient, TypedMemoryRead)
        case legacy(MemoryClient, MemoryManagementSelection)
    }
    fileprivate let source: Source
    fileprivate init(owner: UUID, generation: UUID, binding: MemoryBinding, source: Source, itemID: String, version: Int64, text: String) {
        self.owner = owner; self.generation = generation; self.binding = binding; self.source = source
        self.itemID = itemID; expectedVersion = version; self.text = text
    }
    fileprivate func validate() throws {
        switch source {
        case .typed(let client, let read): try client.validateRead(read, binding: binding)
        case .legacy(let client, let read): try client.validateManagementRead(read, binding: binding)
        }
    }
}
private struct ErasureScope {
    let generation: UUID
    let binding: MemoryBinding
    let entry: MemoryErasureEntry?
    let reconciliationRead: (Data, UUID)?
}
public struct MemoryErasureProgressRead: Sendable {
    public let progress: MemoryErasureProgress
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: MemoryBinding
    fileprivate let inputSHA256: String
    fileprivate let nonce: UUID
}
public struct MemoryErasureOriginal: Sendable {
    public let actionID: String
    public let itemID: String
    public let knownStopped: Bool
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: MemoryBinding
    fileprivate let pending: MemoryErasurePending
}
/// A current SDK-bound, durable observation of this original stop. The App
/// cannot manufacture it from an item ID or a displayed completion string.
@MainActor public final class MemoryErasureLocalAuthorization {
    let itemID: String
    let binding: MemoryBinding
    private let current: @MainActor () throws -> Void
    private let finalFence: @MainActor () throws -> Void
    fileprivate init(itemID: String, binding: MemoryBinding, current: @escaping @MainActor () throws -> Void,
        finalFence: @escaping @MainActor () throws -> Void) {
        self.itemID = itemID; self.binding = binding; self.current = current
        self.finalFence = finalFence
    }
    func validate() throws { try current() }
    /// No key, credentials, source/current callback or await in the final phase.
    func validateFinal() throws { try finalFence() }
}
@MainActor public final class MemoryErasureWork {
    public let original: MemoryErasureOriginal
    fileprivate let scope: ErasureScope
    fileprivate var used = false
    fileprivate init(original: MemoryErasureOriginal, scope: ErasureScope) { self.original = original; self.scope = scope }
}

/// Two erasure exits only, under an explicit local Simulator capability.
/// Actual Root/storage activation still requires the supplied complete B/C host.
@MainActor public final class MemoryErasureClient {
    private let endpoint: MemoryEndpoint
    private let credentials: MemoryCredentialCallback
    private let currentBinding: @MainActor () -> MemoryBinding?
    private let session: SessionLifecycle
    private let operation: SessionOperation
    private let store: MemoryErasurePendingStore
    private typealias Factory = @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private let factory: Factory
    private let owner = UUID()
    private var generation = UUID()
    private var uncertainCreation: Set<Data> = []
    private var preparing = false
    private var progressReads: [Data: UUID] = [:]
    private var consumedReads: [Data: UUID] = [:]
    public init(development endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
                currentBinding: @escaping @MainActor () -> MemoryBinding?, session: SessionLifecycle, sessionOperation: SessionOperation,
                pendingStore: MemoryErasurePendingStore, requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        #if DEBUG && (targetEnvironment(simulator) || G2C_M4_DEVICE_ACCEPTANCE)
        guard session.isCurrent(sessionOperation), currentBinding() != nil, session.isCurrent(sessionOperation) else { throw MemoryFailure.staleBinding }
        guard endpoint.allowsDevelopmentActivation, endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 524288,
              requestTimeout > 0, resourceTimeout > 0, requestTimeout.isFinite, resourceTimeout.isFinite else { throw MemoryFailure.unconfigured }
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.session = session; operation = sessionOperation; store = pendingStore
        factory = { validate in try NoRedirectTransport.developmentMemoryErasure(endpoint: endpoint,
            requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate) }
        #else
        throw MemoryFailure.liveWriteUnavailable
        #endif
    }
    init(endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
         currentBinding: @escaping @MainActor () -> MemoryBinding?, session: SessionLifecycle, sessionOperation: SessionOperation,
         pendingStore: MemoryErasurePendingStore, interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.session = session; operation = sessionOperation; store = pendingStore
        factory = { ErasureInterceptedTransport(underlying: interceptedTransport, validate: $0) }
    }
    public func invalidate() { generation = UUID(); progressReads = [:]; consumedReads = [:] }
    private func check(_ scope: ErasureScope) throws {
        guard generation == scope.generation, session.isCurrent(operation) else { throw MemoryFailure.staleBinding }
        let observed = currentBinding()
        guard generation == scope.generation, observed == scope.binding, session.isCurrent(operation) else { throw MemoryFailure.staleBinding }
        if let entry = scope.entry { try entry.validate() }
        guard generation == scope.generation, session.isCurrent(operation) else { throw MemoryFailure.staleBinding }
        if let (action, nonce) = scope.reconciliationRead {
            guard progressReads[action] == nonce, consumedReads[action] == nonce else { throw MemoryFailure.staleBinding }
        }
        try Task.checkCancellation()
    }
    private func begin(_ binding: MemoryBinding, entry: MemoryErasureEntry? = nil) throws -> ErasureScope {
        let scope = ErasureScope(generation: generation, binding: binding, entry: entry, reconciliationRead: nil)
        if let entry {
            guard entry.owner == owner, entry.generation == generation, entry.binding == binding else { throw MemoryFailure.staleBinding }
        }
        try check(scope); return scope
    }
    public func capture(read: TypedMemoryRead, reader: TypedMemoryClient, binding: MemoryBinding) throws -> MemoryErasureEntry {
        let scope = try begin(binding); try reader.validateRead(read, binding: binding); try check(scope)
        return .init(owner: owner, generation: scope.generation, binding: binding, source: .typed(reader, read),
            itemID: read.item.value.command.item_id, version: Int64(read.item.value.version), text: read.item.value.command.text)
    }
    public func capture(read: MemoryManagementSelection, reader: MemoryClient, binding: MemoryBinding) throws -> MemoryErasureEntry {
        let scope = try begin(binding); try reader.validateManagementRead(read, binding: binding); try check(scope)
        return .init(owner: owner, generation: scope.generation, binding: binding, source: .legacy(reader, read),
            itemID: read.itemID, version: Int64(read.expectedVersion), text: read.text)
    }
    private struct Inventory {
        let records: [MemoryErasurePending]
        let observations: [MemoryErasurePendingStore.ObservationProof]
    }
    private func inventory(_ scope: ErasureScope) throws -> Inventory {
        try check(scope); try store.validate(scope.binding)
        let records = try store.records()
        let proofs = try records.map { try store.prove($0) }
        let observations = try store.observations(for: records)
        try check(scope)
        for proof in proofs { try store.validate(proof) }
        for observation in observations { try store.validate(observation) }
        try store.validateInventory(records)
        return .init(records: records, observations: observations)
    }
    private func verify(_ original: MemoryErasurePending, scope: ErasureScope) throws {
        try check(scope); try store.validate(scope.binding)
        let proof = try store.prove(original)
        let observation = try store.observation(for: original)
        try check(scope); try store.validate(proof)
        if let observation { try store.validate(observation) }
    }
    private func wrap(_ record: MemoryErasurePending, binding: MemoryBinding, knownStopped: Bool = false) -> MemoryErasureOriginal {
        .init(actionID: record.actionID, itemID: record.itemID, knownStopped: knownStopped, owner: owner, generation: generation, binding: binding, pending: record)
    }
    public func originals(binding: MemoryBinding) throws -> [MemoryErasureOriginal] {
        let scope = try begin(binding)
        let observed = try inventory(scope)
        return observed.records.map { record in
            wrap(record, binding: binding, knownStopped: observed.observations.contains(where: { same($0.value.actionID, record.actionID) }))
        }
    }
    public func localAuthorization(for original: MemoryErasureOriginal) throws -> MemoryErasureLocalAuthorization {
        let scope = try begin(original.binding)
        guard original.owner == owner, original.generation == generation else { throw MemoryFailure.staleBinding }
        try verify(original.pending, scope: scope)
        guard let stopped = try store.observation(for: original.pending) else { throw MemoryFailure.exchangeUnknown }
        let proof = try store.prove(original.pending)
        try check(scope); try store.validate(stopped); try store.validate(proof)
        return MemoryErasureLocalAuthorization(itemID: original.itemID, binding: original.binding, current: { [self] in
            try verify(original.pending, scope: scope)
            try store.validate(stopped)
            try check(scope)
        }, finalFence: { [self] in
            guard generation == scope.generation, session.isCurrent(operation) else { throw MemoryFailure.staleBinding }
            try Task.checkCancellation()
            try store.validate(proof); try store.validate(stopped)
        })
    }
    public func prepare(entry: MemoryErasureEntry, acknowledgement: MemoryErasureRangeAcknowledgement) throws -> MemoryErasureWork {
        guard !preparing else { throw MemoryFailure.pendingRequiresQuery }
        preparing = true; defer { preparing = false }
        let scope = try begin(entry.binding, entry: entry)
        let id = Data(entry.itemID.utf8), existing = try inventory(scope).records
        guard !uncertainCreation.contains(id), !existing.contains(where: { same($0.itemID, entry.itemID) }) else { throw MemoryFailure.pendingRequiresQuery }
        let original = MemoryErasurePending(try .init(itemID: entry.itemID, expectedVersion: entry.expectedVersion, acknowledgement: acknowledgement))
        try check(scope); uncertainCreation.insert(id)
        try store.append(original, validate: { try self.check(scope) })
        try verify(original, scope: scope)
        return .init(original: wrap(original, binding: scope.binding), scope: scope)
    }
    func isCurrent(binding: MemoryBinding, entry: MemoryErasureEntry? = nil) -> Bool {
        do { _ = try begin(binding, entry: entry); return true } catch { return false }
    }
    public func perform(_ work: MemoryErasureWork) async throws -> MemoryErasureProgress {
        try check(work.scope)
        guard work.original.owner == owner, !work.used else { throw MemoryFailure.staleBinding }
        work.used = true
        return try await exchange(work.original.pending, scope: work.scope, post: true)
    }
    public func query(_ original: MemoryErasureOriginal) async throws -> MemoryErasureProgress {
        try await queryRead(original).progress
    }
    public func queryRead(_ original: MemoryErasureOriginal) async throws -> MemoryErasureProgressRead {
        let scope = try begin(original.binding)
        guard original.owner == owner, original.generation == generation else { throw MemoryFailure.staleBinding }
        let key = Data(original.actionID.utf8), nonce = UUID()
        progressReads[key] = nonce
        let progress = try await exchange(original.pending, scope: scope, post: false)
        try check(scope)
        guard progressReads[key] == nonce else { throw MemoryFailure.staleBinding }
        return .init(progress: progress, owner: owner, generation: scope.generation, binding: scope.binding,
            inputSHA256: original.pending.expectedSHA256, nonce: nonce)
    }
    /// C's explicit reconciliation POST reuses the exact original command. A
    /// successful current GET is mandatory first; absence/error cannot enable it.
    /// The service reconciles issued steps and may start untouched original steps.
    public func prepareReconciliation(_ original: MemoryErasureOriginal, after read: MemoryErasureProgressRead) throws -> MemoryErasureWork {
        guard !preparing else { throw MemoryFailure.pendingRequiresQuery }
        preparing = true; defer { preparing = false }
        let scope = try begin(original.binding), key = Data(original.actionID.utf8)
        func validateRead() throws {
            guard original.owner == owner, original.generation == generation,
                  read.owner == owner, read.generation == generation, read.binding == scope.binding,
                  same(read.progress.actionID, original.actionID), same(read.inputSHA256, original.pending.expectedSHA256),
                  read.progress.phase == .unknown || read.progress.phase == .inProgress,
                  progressReads[key] == read.nonce, consumedReads[key] != read.nonce else { throw MemoryFailure.staleBinding }
        }
        try validateRead(); try verify(original.pending, scope: scope)
        guard let observation = try store.observation(for: original.pending) else { throw MemoryFailure.storageUnavailable }
        try observation.value.check(original.pending, progress: read.progress)
        try check(scope); try validateRead(); try store.validate(observation)
        consumedReads[key] = read.nonce
        let reconciled = ErasureScope(generation: scope.generation, binding: scope.binding, entry: nil, reconciliationRead: (key, read.nonce))
        return .init(original: original, scope: reconciled)
    }
    private func exchange(_ original: MemoryErasurePending, scope: ErasureScope, post: Bool) async throws -> MemoryErasureProgress {
        try verify(original, scope: scope)
        let bearer: String?
        do { bearer = try await credentials(scope.binding) } catch { try check(scope); throw MemoryFailure.unconfigured }
        try verify(original, scope: scope)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MemoryFailure.unconfigured }
        var components = URLComponents()
        components.path = post ? "/v1/memory-erasures" : "/v1/memory-erasure-progress"
        if !post {
            components.queryItems = [.init(name: "action_id", value: original.actionID)]
            components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
        guard let path = components.string else { throw MemoryFailure.invalidInput }
        var request = HTTPRequest(method: post ? .post : .get, scheme: nil, authority: nil, path: path)
        request.headerFields[.authorization] = "Bearer " + bearer; request.headerFields[.cacheControl] = "no-store"
        if post { request.headerFields[.contentType] = "application/octet-stream" }
        let validate: @MainActor @Sendable () throws -> Void = { try self.verify(original, scope: scope) }
        do {
            try validate(); let checked = try factory(validate); try validate()
            let (response, body) = try await checked.send(request, body: post ? HTTPBody(original.originalUTF8) : nil,
                baseURL: endpoint.url, operationID: post ? "eraseMemoryV1" : "readMemoryErasureProgressV1")
            try verify(original, scope: scope)
            guard !(300..<400).contains(response.status.code), let body else { throw MemoryFailure.invalidResponse }
            let raw = try await Data(collecting: body, upTo: min(endpoint.maximumResponseBytes, 524288))
            try verify(original, scope: scope)
            let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
            let media = response.headerFields.filter { $0.name == .contentType }, caches = response.headerFields.filter { $0.name == .cacheControl }
            guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
                  media.count == 1, ["application/json", "application/json; charset=utf-8"].contains(media.first?.value.lowercased()),
                  caches.count == 1, caches.first?.value.lowercased() == "no-store" else { throw MemoryFailure.invalidResponse }
            if response.status.code != 200 { throw try erasureHTTPError(raw, trace: trace, status: response.status.code) }
            let progress = try MemoryErasureProgress(response: raw, trace: trace, original: original.action(), post: post)
            try store.record(progress, original: original, validate: { try self.check(scope) })
            try verify(original, scope: scope)
            return progress
        } catch {
            try check(scope)
            if let safe = error as? MemoryFailure { throw safe }
            if error is CancellationError { throw CancellationError() }
            throw MemoryFailure.exchangeUnknown
        }
    }
}
private func erasureHTTPError(_ bytes: Data, trace: String, status: Int) throws -> MemoryFailure {
    var parser = StrictMemoryJSON(bytes: Array(bytes))
    let root = try historyObject(parser.document(), fields: ["request_id", "error"])
    guard same(try historyString(root["request_id"], limit: 64), trace), let error = root["error"] else { throw MemoryFailure.invalidResponse }
    let fields = try historyObject(error, fields: ["code", "category", "message_en", "message_zh", "outcome", "recovery"])
    let code = try historyString(fields["code"], limit: 96)
    guard code.utf8.allSatisfy({ (65...90).contains($0) || (48...57).contains($0) || $0 == 95 }) else { throw MemoryFailure.invalidResponse }
    return status == 503 ? .exchangeUnknown : .rejected(status, code)
}
private struct ErasureInterceptedTransport: ClientTransport {
    let underlying: any ClientTransport
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = nil }
        try await validate(); try Task.checkCancellation()
        let result = try await underlying.send(request, body: bytes.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
        try await validate(); try Task.checkCancellation(); return result
    }
}
