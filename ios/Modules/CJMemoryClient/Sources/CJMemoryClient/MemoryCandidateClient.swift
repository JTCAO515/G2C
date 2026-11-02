import Foundation
import CJSession
import CJStrictJSON
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

private struct CandidateScope {
    let generation: UUID
    let binding: MemoryBinding
    let conversation: String?
}
public struct MemoryCandidateJobsRead: Sendable {
    public let page: MemoryCandidateJobPage
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: MemoryBinding
    fileprivate let series: UUID
}
public struct MemoryCandidatesRead: Sendable {
    public let page: MemoryCandidatePage
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: MemoryBinding
    fileprivate let conversation: String
    fileprivate let series: UUID
    fileprivate let nonce: UUID
}
public struct MemoryCandidateOriginal: Sendable {
    public let actionID: String
    public let candidateID: String
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let binding: MemoryBinding
    fileprivate let pending: MemoryCandidatePending
}
@MainActor public final class MemoryCandidateWork {
    fileprivate let scope: CandidateScope
    public let original: MemoryCandidateOriginal
    fileprivate var used = false
    fileprivate init(scope: CandidateScope, original: MemoryCandidateOriginal) { self.scope = scope; self.original = original }
}
public enum MemoryCandidateResult: Sendable { case recorded(MemoryCandidateReceipt), notObserved, rejected(Int, String) }

/// Protected producer discovery and explicit review. No organizer/model/consent
/// dispatch is exposed. Canonical live activation is connected in the App seam;
/// raw transport construction remains module-internal for independent tests.
@MainActor public final class MemoryCandidateClient {
    typealias Factory = @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private let endpoint: MemoryEndpoint
    private let credentials: MemoryCredentialCallback
    private let currentBinding: @MainActor () -> MemoryBinding?
    private let currentConversation: @MainActor () -> String?
    private let session: SessionLifecycle
    private let sessionOperation: SessionOperation
    private let store: MemoryCandidatePendingStore
    private let factory: Factory
    private let owner = UUID()
    private var generation = UUID()
    private struct Discovery { let series: UUID; var request: UUID; var next: String? }
    private var discovery: [Data: Discovery] = [:]
    private var candidateReads: [MemoryCandidateJob: UUID] = [:]
    private var settled: Set<Data> = []
    private var uncertainCreation: Set<Data> = []
    public init(development endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
                currentBinding: @escaping @MainActor () -> MemoryBinding?, currentConversation: @escaping @MainActor () -> String?,
                session: SessionLifecycle, sessionOperation: SessionOperation, pendingStore: MemoryCandidatePendingStore,
                requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        #if DEBUG && targetEnvironment(simulator)
        guard session.isCurrent(sessionOperation), currentBinding() != nil, session.isCurrent(sessionOperation) else { throw MemoryFailure.staleBinding }
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1", let port = endpoint.url.port,
              (1...65535).contains(port), endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 524288,
              requestTimeout > 0, resourceTimeout > 0, requestTimeout.isFinite, resourceTimeout.isFinite else { throw MemoryFailure.unconfigured }
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.currentConversation = currentConversation; self.session = session; self.sessionOperation = sessionOperation; store = pendingStore
        factory = { validate in try NoRedirectTransport.developmentMemoryCandidates(endpoint: endpoint,
            requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate) }
        #else
        throw MemoryFailure.liveWriteUnavailable
        #endif
    }
    init(endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
         currentBinding: @escaping @MainActor () -> MemoryBinding?, currentConversation: @escaping @MainActor () -> String?,
         session: SessionLifecycle, sessionOperation: SessionOperation, pendingStore: MemoryCandidatePendingStore,
         interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.currentConversation = currentConversation; self.session = session; self.sessionOperation = sessionOperation; store = pendingStore
        factory = { CandidateInterceptedTransport(underlying: interceptedTransport, validate: $0) }
    }
    public func invalidate() { generation = UUID(); discovery = [:]; candidateReads = [:] }
    func retireReads() { discovery = [:]; candidateReads = [:] }
    func isCurrent(binding: MemoryBinding, conversation: String?) -> Bool {
        do { _ = try begin(binding, conversation: conversation); return true } catch { return false }
    }
    private func begin(_ binding: MemoryBinding, conversation: String? = nil) throws -> CandidateScope {
        if let conversation {
            guard !conversation.contains("\0"), !conversation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  conversation.utf8.count <= 256 else { throw MemoryFailure.invalidInput }
        }
        let scope = CandidateScope(generation: generation, binding: binding, conversation: conversation)
        try check(scope); return scope
    }
    private func check(_ scope: CandidateScope) throws {
        guard scope.generation == generation, session.isCurrent(sessionOperation) else { throw MemoryFailure.staleBinding }
        let binding = currentBinding()
        let conversation = scope.conversation == nil ? nil : currentConversation()
        guard scope.generation == generation, binding == scope.binding, session.isCurrent(sessionOperation),
              scope.conversation == nil || conversation.map({ same($0, scope.conversation!) }) == true else { throw MemoryFailure.staleBinding }
        try Task.checkCancellation()
    }
    public func discover(binding: MemoryBinding, conversation: String, after previous: MemoryCandidateJobsRead? = nil) async throws -> MemoryCandidateJobsRead {
        let scope = try begin(binding, conversation: conversation), key = Data(conversation.utf8)
        let series: UUID, cursor: String
        if let previous {
            guard previous.owner == owner, previous.generation == generation, previous.binding == binding,
                  same(previous.page.conversationID, conversation), let next = previous.page.nextAfterJobID,
                  let state = discovery[key], state.series == previous.series, state.next.map({ same($0, next) }) == true else { throw MemoryFailure.staleBinding }
            series = previous.series; cursor = next
        } else { series = UUID(); cursor = "" }
        let request = UUID(); discovery[key] = .init(series: series, request: request, next: nil)
        let response = try await exchange(scope, path: "/v5/memory-candidate-jobs", operation: "readMemoryCandidateJobsV1",
            query: [.init(name: "conversation_id", value: conversation), .init(name: "after_job_id", value: cursor)])
        let page = try MemoryCandidateJobPage(response: response.requireSuccess(), trace: response.trace, conversationID: conversation)
        try check(scope)
        guard discovery[key]?.request == request else { throw MemoryFailure.staleBinding }
        if let next = page.nextAfterJobID { guard !same(next, cursor) else { throw MemoryFailure.invalidResponse } }
        discovery[key]?.next = page.nextAfterJobID
        return .init(page: page, owner: owner, generation: generation, binding: binding, series: series)
    }
    public func candidates(from source: MemoryCandidateJobsRead, producer: MemoryCandidateJob) async throws -> MemoryCandidatesRead {
        let scope = try begin(source.binding, conversation: source.page.conversationID)
        guard source.owner == owner, source.generation == generation,
              discovery[Data(source.page.conversationID.utf8)]?.series == source.series,
              source.page.jobs.contains(producer) else { throw MemoryFailure.staleBinding }
        let nonce = UUID(); candidateReads[producer] = nonce
        let response = try await exchange(scope, path: "/v3/memory-candidates", operation: "readMemoryCandidatesV1",
            query: [.init(name: "job_id", value: producer.jobID), .init(name: "attempt_id", value: producer.attemptID)])
        let page = try MemoryCandidatePage(response: response.requireSuccess(), trace: response.trace, producer: producer)
        try check(scope)
        guard candidateReads[producer] == nonce,
              discovery[Data(source.page.conversationID.utf8)]?.series == source.series else { throw MemoryFailure.staleBinding }
        return .init(page: page, owner: owner, generation: generation, binding: scope.binding,
            conversation: source.page.conversationID, series: source.series, nonce: nonce)
    }
    private struct Inventory { let records: [MemoryCandidatePending]; let declines: [Data: MemoryCandidatePendingStore.Decline] }
    private func inventory(_ scope: CandidateScope) throws -> Inventory {
        try check(scope); try store.validate(scope.binding)
        let records = try store.records()
        var declines: [Data: MemoryCandidatePendingStore.Decline] = [:]
        let proofs = try records.map { try store.prove($0) }
        for record in records {
            if let decline = try store.rejection(for: record) { declines[Data(record.actionID.utf8)] = decline }
        }
        try check(scope)
        for proof in proofs { try store.validate(proof) }
        for decline in declines.values { try store.validate(decline) }
        try store.validateInventory(records)
        return .init(records: records, declines: declines)
    }
    private func verify(_ original: MemoryCandidatePending, scope: CandidateScope) throws {
        try check(scope); try store.validate(scope.binding)
        let proof = try store.prove(original)
        try check(scope); try store.validate(proof)
    }
    public func originals(binding: MemoryBinding) throws -> [MemoryCandidateOriginal] {
        let scope = try begin(binding)
        return try inventory(scope).records.map { wrap($0, binding) }
    }
    private func wrap(_ pending: MemoryCandidatePending, _ binding: MemoryBinding) -> MemoryCandidateOriginal {
        .init(actionID: pending.actionID, candidateID: pending.candidateID, owner: owner,
            generation: generation, binding: binding, pending: pending)
    }
    public func prepareReview(read: MemoryCandidatesRead, candidateID: String, review: MemoryCandidateReview) throws -> MemoryCandidateWork {
        let scope = try begin(read.binding, conversation: read.conversation)
        guard read.owner == owner, read.generation == generation,
              discovery[Data(read.conversation.utf8)]?.series == read.series,
              candidateReads[read.page.producer] == read.nonce else { throw MemoryFailure.staleBinding }
        let existing = try inventory(scope), id = Data(candidateID.utf8)
        guard !uncertainCreation.contains(id), existing.records.filter({ same($0.candidateID, candidateID) }).allSatisfy({
            settled.contains(Data($0.actionID.utf8)) || existing.declines[Data($0.actionID.utf8)] != nil
        }) else { throw MemoryFailure.pendingRequiresQuery }
        let pending = try MemoryCandidatePending(MemoryCandidateAction(page: read.page, candidateID: candidateID, review: review))
        try check(scope)
        guard read.generation == generation, candidateReads[read.page.producer] == read.nonce,
              discovery[Data(read.conversation.utf8)]?.series == read.series else { throw MemoryFailure.staleBinding }
        candidateReads = [:]; uncertainCreation.insert(id)
        try store.append(pending) { try self.check(scope) }
        try verify(pending, scope: scope)
        return MemoryCandidateWork(scope: scope, original: wrap(pending, scope.binding))
    }
    public func perform(_ work: MemoryCandidateWork) async throws -> MemoryCandidateResult {
        try check(work.scope)
        guard work.original.owner == owner, !work.used else { throw MemoryFailure.staleBinding }
        work.used = true
        let original = work.original.pending
        try verify(original, scope: work.scope)
        let response = try await exchange(work.scope, path: "/v3/memory-candidate-actions", operation: "applyMemoryCandidateActionV1", original: original, post: true)
        if response.status == 200 { return try settle(response, original: original, scope: work.scope, allowMissing: false) }
        let error = try response.error()
        if [400,401,403,409].contains(response.status), error.outcome == "failed", error.recovery == "do_not_retry" {
            try store.recordRejection(original, status: response.status, code: error.code) { try self.check(work.scope) }
            let checked = try inventory(work.scope)
            guard checked.declines[Data(original.actionID.utf8)] != nil else { throw MemoryFailure.storageUnavailable }
            uncertainCreation.remove(Data(original.candidateID.utf8)); throw MemoryFailure.rejected(response.status, error.code)
        }
        throw MemoryFailure.exchangeUnknown
    }
    public func query(_ original: MemoryCandidateOriginal) async throws -> MemoryCandidateResult {
        let scope = try begin(original.binding)
        guard original.owner == owner, original.generation == generation else { throw MemoryFailure.staleBinding }
        try verify(original.pending, scope: scope)
        let response = try await exchange(scope, path: "/v3/memory-candidate-receipts", operation: "queryMemoryCandidateReceiptV1",
            query: [.init(name: "action_id", value: original.actionID)], original: original.pending)
        return try settle(response, original: original.pending, scope: scope, allowMissing: true)
    }
    private func settle(_ response: CandidateHTTPResult, original: MemoryCandidatePending, scope: CandidateScope, allowMissing: Bool) throws -> MemoryCandidateResult {
        let value = try candidateEnvelope(response.requireSuccess(), trace: response.trace, version: "MEMORY-CANDIDATE-response@1")
        if case .null = value {
            guard allowMissing else { throw MemoryFailure.invalidResponse }
            let checked = try inventory(scope)
            if let decline = checked.declines[Data(original.actionID.utf8)] { return .rejected(decline.record.status, decline.record.code) }
            return .notObserved
        }
        let receipt = try MemoryCandidateReceipt(value, original: original.action())
        let checked = try inventory(scope)
        guard checked.declines[Data(original.actionID.utf8)] == nil else { throw MemoryFailure.invalidResponse }
        try verify(original, scope: scope)
        settled.insert(Data(original.actionID.utf8)); uncertainCreation.remove(Data(original.candidateID.utf8))
        return .recorded(receipt)
    }
    private func exchange(_ scope: CandidateScope, path: String, operation: String, query: [URLQueryItem] = [], original: MemoryCandidatePending? = nil, post: Bool = false) async throws -> CandidateHTTPResult {
        try check(scope)
        let bearer: String?
        do { bearer = try await credentials(scope.binding) } catch { try check(scope); throw MemoryFailure.unconfigured }
        try check(scope)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MemoryFailure.unconfigured }
        var components = URLComponents(); components.path = path
        if !query.isEmpty {
            components.queryItems = query
            // Python's canonical query parser treats a literal plus as a space.
            // Keep the original opaque IDs exact through that boundary.
            components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
        guard let target = components.string else { throw MemoryFailure.invalidInput }
        var request = HTTPRequest(method: post ? .post : .get, scheme: nil, authority: nil, path: target)
        request.headerFields[.authorization] = "Bearer " + bearer; request.headerFields[.cacheControl] = "no-store"
        if post { request.headerFields[.contentType] = "application/octet-stream" }
        let validate: @MainActor @Sendable () throws -> Void = { [self] in
            if let original { try verify(original, scope: scope) } else { try check(scope) }
        }
        do {
            try validate(); let transport = try factory(validate); try validate()
            let (response, body) = try await transport.send(request, body: post ? original.map { HTTPBody($0.originalUTF8) } : nil, baseURL: endpoint.url, operationID: operation)
            try validate()
            guard !(300..<400).contains(response.status.code), let body else { throw MemoryFailure.invalidResponse }
            let raw = try await Data(collecting: body, upTo: min(endpoint.maximumResponseBytes, 524288)); try validate()
            let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
            let caches = response.headerFields.filter { $0.name == .cacheControl }, media = response.headerFields.filter { $0.name == .contentType }
            guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
                  caches.count == 1, caches.first?.value.lowercased() == "no-store", media.count == 1,
                  ["application/json", "application/json; charset=utf-8"].contains(media.first?.value.lowercased()) else { throw MemoryFailure.invalidResponse }
            return .init(status: response.status.code, raw: raw, trace: trace)
        } catch {
            try check(scope)
            if let safe = error as? MemoryFailure { throw safe }
            if error is CancellationError { throw CancellationError() }
            throw MemoryFailure.exchangeUnknown
        }
    }
}
private struct CandidateHTTPResult {
    let status: Int
    let raw: Data
    let trace: String
    func requireSuccess() throws -> Data {
        guard status == 200 else {
            let failure = try error()
            if status == 503 { throw MemoryFailure.exchangeUnknown }
            throw MemoryFailure.rejected(status, failure.code)
        }
        return raw
    }
    func error() throws -> (code: String, outcome: String, recovery: String) {
        var parser = StrictMemoryJSON(bytes: Array(raw))
        let root = try historyObject(parser.document(), fields: ["request_id", "error"])
        guard same(try historyString(root["request_id"], limit: 64), trace), let value = root["error"] else { throw MemoryFailure.invalidResponse }
        let fields = try historyObject(value, fields: ["code", "category", "message_en", "message_zh", "outcome", "recovery"])
        let code = try historyString(fields["code"], limit: 96)
        guard code.utf8.allSatisfy({ (65...90).contains($0) || (48...57).contains($0) || $0 == 95 }) else { throw MemoryFailure.invalidResponse }
        return (code, try historyString(fields["outcome"], limit: 32), try historyString(fields["recovery"], limit: 64))
    }
}
private struct CandidateInterceptedTransport: ClientTransport {
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
