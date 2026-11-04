import Foundation
import CJMessageHTTP
import CJSession
import CJStrictJSON
import HTTPTypes
import OpenAPIRuntime

struct MemoryHistoryOperation: Sendable {
    let owner: UUID
    let generation: UUID
    let binding: MemoryBinding
    let conversation: String
}
struct MemoryHistoryRead: Sendable {
    let settings: MemoryHistorySettings
    let owner: UUID
    let generation: UUID
    let binding: MemoryBinding
    let nonce: UUID
}

/// Only user consent routes. The App has no history-job/organizer dispatch exit.
@MainActor public final class MemoryHistoryClient {
    private let endpoint: MemoryEndpoint
    private let credentials: MemoryCredentialCallback
    private let currentBinding: @MainActor () -> MemoryBinding?
    private let currentConversation: @MainActor () -> String?
    private let session: SessionLifecycle?
    private let sessionOperation: SessionOperation?
    private let store: MemoryHistoryPendingStore
    typealias Factory = @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private let factory: Factory
    private let intercepted: Bool
    private let owner = UUID()
    private var generation = UUID()
    private var reading: [Data: UUID] = [:]
    private var availableReads: [Data: UUID] = [:]
    private var confirmed: Set<Data> = []
    private var uncertainCreation: Set<Data> = []

    public init(development endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
                currentBinding: @escaping @MainActor () -> MemoryBinding?, currentConversation: @escaping @MainActor () -> String?,
                session: SessionLifecycle, sessionOperation: SessionOperation, pendingStore: MemoryHistoryPendingStore,
                requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        #if DEBUG && (targetEnvironment(simulator) || G2C_M4_DEVICE_ACCEPTANCE)
        guard session.isCurrent(sessionOperation), currentBinding() != nil, session.isCurrent(sessionOperation) else { throw MemoryFailure.staleBinding }
        guard endpoint.allowsDevelopmentActivation, endpoint.maximumRequestBytes <= 32768, endpoint.maximumResponseBytes <= 65536,
              requestTimeout > 0, resourceTimeout > 0, requestTimeout.isFinite, resourceTimeout.isFinite else { throw MemoryFailure.unconfigured }
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.currentConversation = currentConversation; self.session = session; self.sessionOperation = sessionOperation
        store = pendingStore; intercepted = false
        factory = { validate in try NoRedirectTransport.developmentMemoryHistory(endpoint: endpoint,
            requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate) }
        #else
        throw MemoryFailure.liveWriteUnavailable
        #endif
    }
    /// Non-network module tests only. Ordinary/Release code cannot supply a raw transport.
    init(endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
         currentBinding: @escaping @MainActor () -> MemoryBinding?, currentConversation: @escaping @MainActor () -> String?,
         pendingStore: MemoryHistoryPendingStore, interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.currentConversation = currentConversation; store = pendingStore
        factory = { validate in HistoryInterceptedTransport(underlying: interceptedTransport, validate: validate) }
        session = nil; sessionOperation = nil; intercepted = true
    }
    public func invalidate() { generation = UUID(); reading = [:]; availableReads = [:] }
    private var sessionCurrent: Bool {
        if let session, let sessionOperation { return session.isCurrent(sessionOperation) }
        return intercepted && session == nil && sessionOperation == nil
    }
    func owns(_ op: MemoryHistoryOperation) -> Bool {
        guard op.owner == owner, op.generation == generation else { return false }
        let observedBinding = currentBinding(), observedConversation = currentConversation()
        return op.owner == owner && op.generation == generation && observedBinding == op.binding
            && observedConversation.map { same($0, op.conversation) } == true && sessionCurrent
    }
    func check(_ op: MemoryHistoryOperation) throws {
        guard owns(op) else { throw MemoryFailure.staleBinding }
        try Task.checkCancellation()
    }
    func begin(binding: MemoryBinding, conversation: String) throws -> MemoryHistoryOperation {
        guard !conversation.contains("\0"), !conversation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              conversation.utf8.count <= 256 else { throw MemoryFailure.invalidInput }
        let op = MemoryHistoryOperation(owner: owner, generation: generation, binding: binding, conversation: conversation)
        try check(op); return op
    }
    private func verify(_ original: MemoryHistoryPending, _ op: MemoryHistoryOperation) throws {
        try store.validate(op.binding)
        let proof = try store.prove(original)
        try check(op)
        try store.validate(proof) // no key/current-source callback after this proof
    }
    private struct Inventory {
        let records: [MemoryHistoryPending]
        let declines: [Data: MemoryHistoryPendingStore.Decline]
    }
    private func inventory(_ op: MemoryHistoryOperation) throws -> Inventory {
        try check(op); try store.validate(op.binding)
        let records = try store.records()
        var declines: [Data: MemoryHistoryPendingStore.Decline] = [:]
        for record in records where !confirmed.contains(Data(record.actionID.utf8)) {
            if let decline = try store.rejection(for: record) { declines[Data(record.actionID.utf8)] = decline }
        }
        let proofs = try records.map { try store.prove($0) }
        try check(op)
        for proof in proofs { try store.validate(proof) }
        for decline in declines.values { try store.validate(decline) }
        try store.validateInventory(records)
        return Inventory(records: records, declines: declines)
    }
    func pending(_ op: MemoryHistoryOperation) throws -> [MemoryHistoryPending] {
        try inventory(op).records.filter { same($0.conversationID, op.conversation) }
    }
    struct PendingInfo {
        let records: [MemoryHistoryPending]
        let unresolved: Set<Data>
    }
    func pendingInfo(_ op: MemoryHistoryOperation) throws -> PendingInfo {
        let value = try inventory(op)
        let records = value.records.filter { same($0.conversationID, op.conversation) }
        let unresolved = Set(records.filter { !confirmed.contains(Data($0.actionID.utf8)) && value.declines[Data($0.actionID.utf8)] == nil }.map { Data($0.actionID.utf8) })
        return PendingInfo(records: records, unresolved: unresolved)
    }
    func read(_ op: MemoryHistoryOperation) async throws -> MemoryHistoryRead {
        try check(op)
        let key = Data(op.conversation.utf8), nonce = UUID(); reading[key] = nonce
        let response = try await exchange(op, route: .settings, value: op.conversation)
        let settings = try MemoryHistorySettings(response.requireResult())
        guard same(settings.conversationID, op.conversation) else { throw MemoryFailure.invalidResponse }
        try check(op)
        guard reading[key] == nonce else { throw MemoryFailure.staleBinding }
        availableReads[key] = nonce
        return MemoryHistoryRead(settings: settings, owner: owner, generation: generation, binding: op.binding, nonce: nonce)
    }
    func prepare(change: MemoryHistoryChange, read: MemoryHistoryRead, operation op: MemoryHistoryOperation) throws -> MemoryHistoryPending {
        try check(op)
        let key = Data(op.conversation.utf8)
        guard read.owner == owner, read.generation == generation, read.binding == op.binding,
              same(read.settings.conversationID, op.conversation), availableReads[key] == read.nonce else { throw MemoryFailure.staleBinding }
        let original = try MemoryHistoryPending(change: change, settings: read.settings)
        try check(op)
        guard read.generation == generation, availableReads[key] == read.nonce else { throw MemoryFailure.staleBinding }
        availableReads[key] = nil // a fresh review is required after any attempted change
        return original
    }
    func submit(_ original: MemoryHistoryPending, operation op: MemoryHistoryOperation) async throws -> MemoryHistoryResult {
        try original.validate(); try check(op)
        guard same(original.conversationID, op.conversation) else { throw MemoryFailure.staleBinding }
        let existing = try inventory(op), key = Data(op.conversation.utf8)
        guard !uncertainCreation.contains(key), !existing.records.contains(where: { same($0.actionID, original.actionID) }),
              existing.records.filter({ same($0.conversationID, op.conversation) }).allSatisfy({ confirmed.contains(Data($0.actionID.utf8)) || existing.declines[Data($0.actionID.utf8)] != nil }) else { throw MemoryFailure.pendingRequiresQuery }
        uncertainCreation.insert(key) // before encryption/key/store callbacks; failed append does not grant a second ID
        try store.append(original) { try self.check(op) }
        try verify(original, op)
        let response = try await exchange(op, route: .change, value: nil, original: original)
        if response.status == 200 { return try settle(response.requireResult(), original: original, operation: op) }
        let error = try response.error()
        if [400,401,403,409].contains(response.status), error.outcome == "failed", error.recovery == "do_not_retry" {
            try store.recordRejection(original, status: response.status, code: error.code) { try self.check(op) }
            let checked = try inventory(op)
            guard checked.declines[Data(original.actionID.utf8)] != nil else { throw MemoryFailure.storageUnavailable }
            uncertainCreation.remove(key)
            throw MemoryFailure.rejected(response.status, error.code)
        }
        throw MemoryFailure.exchangeUnknown
    }
    func query(_ original: MemoryHistoryPending, operation op: MemoryHistoryOperation) async throws -> MemoryHistoryResult {
        try check(op)
        guard same(original.conversationID, op.conversation) else { throw MemoryFailure.staleBinding }
        try verify(original, op)
        let response = try await exchange(op, route: .receipt, value: original.actionID, original: original)
        let result = try response.requireResult()
        if case .null = result {
            let checked = try inventory(op)
            if let decline = checked.declines[Data(original.actionID.utf8)] {
                return .rejected(decline.record.status, decline.record.code)
            }
            return .notObserved // null never authorizes resubmission or a replacement ID
        }
        return try settle(result, original: original, operation: op)
    }
    private func settle(_ value: StrictJSONValue, original: MemoryHistoryPending, operation op: MemoryHistoryOperation) throws -> MemoryHistoryResult {
        let receipt = try MemoryHistoryReceipt(value, original: original)
        let checked = try inventory(op)
        guard checked.declines[Data(original.actionID.utf8)] == nil else { throw MemoryFailure.invalidResponse }
        try verify(original, op)
        confirmed.insert(Data(original.actionID.utf8)); uncertainCreation.remove(Data(op.conversation.utf8))
        return .recorded(receipt)
    }

    private func exchange(_ op: MemoryHistoryOperation, route: HistoryRoute, value: String?, original: MemoryHistoryPending? = nil) async throws -> HistoryHTTPResult {
        try check(op)
        let bearer: String?
        do { bearer = try await credentials(op.binding) }
        catch { try check(op); throw MemoryFailure.unconfigured }
        try check(op)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MemoryFailure.unconfigured }
        var components = URLComponents(); components.path = route.path
        if let value, let field = route.query { components.queryItems = [.init(name: field, value: value)] }
        guard let path = components.string else { throw MemoryFailure.invalidInput }
        var request = HTTPRequest(method: route == .change ? .post : .get, scheme: nil, authority: nil, path: path)
        request.headerFields[.authorization] = "Bearer " + bearer
        if route == .change { request.headerFields[.contentType] = "application/octet-stream" }
        let bytes = original.map { route == .change ? $0.originalUTF8 : nil } ?? nil
        do {
            if let original { try verify(original, op) } else { try check(op) }
            let transport = try factory { [self] in
                if let original { try verify(original, op) } else { try check(op) }
            }
            let (response, body) = try await transport.send(request, body: bytes.map(HTTPBody.init), baseURL: endpoint.url, operationID: route.operation)
            if let original { try verify(original, op) } else { try check(op) }
            guard !(300..<400).contains(response.status.code), let body else { throw MemoryFailure.invalidResponse }
            let raw = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
            if let original { try verify(original, op) } else { try check(op) }
            let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
            guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
                  response.headerFields[.cacheControl]?.lowercased().split(separator: ",").map({ $0.trimmingCharacters(in: .whitespaces) }).contains("no-store") == true else { throw MemoryFailure.invalidResponse }
            return HistoryHTTPResult(status: response.status.code, raw: raw, trace: trace)
        } catch {
            try check(op)
            throw MemoryFailure.exchangeUnknown // never leak a transport/credential/private response exception
        }
    }
}

private enum HistoryRoute {
    case settings, change, receipt
    var path: String {
        switch self { case .settings: "/v3/memory-history-settings"; case .change: "/v3/memory-history-actions"; case .receipt: "/v3/memory-history-receipts" }
    }
    var query: String? { switch self { case .settings: "conversation_id"; case .receipt: "action_id"; case .change: nil } }
    var operation: String {
        switch self { case .settings: "readMemoryHistorySettingsV1"; case .change: "applyMemoryHistoryActionV1"; case .receipt: "queryMemoryHistoryReceiptV1" }
    }
}
private struct HistoryHTTPResult {
    let status: Int
    let raw: Data
    let trace: String
    func requireResult() throws -> StrictJSONValue {
        guard status == 200 else { throw MemoryFailure.rejected(status, try error().code) }
        return try historyEnvelope(raw, trace: trace)
    }
    func error() throws -> (code: String, recovery: String, outcome: String) {
        var parser = StrictMemoryJSON(bytes: Array(raw))
        let object = try historyObject(parser.document(), fields: ["request_id", "error"])
        guard same(try historyString(object["request_id"], limit: 64), trace),
              case .object(let error) = object["error"] else { throw MemoryFailure.invalidResponse }
        guard Set(error.keys) == ["code", "category", "outcome", "message_en", "message_zh", "recovery"] else { throw MemoryFailure.invalidResponse }
        let code = try historyString(error["code"], limit: 96)
        guard code.utf8.allSatisfy({ (65...90).contains($0) || (48...57).contains($0) || $0 == 95 }) else { throw MemoryFailure.invalidResponse }
        return (code, try historyString(error["recovery"], limit: 64), try historyString(error["outcome"], limit: 32))
    }
}

/// Internal non-network seam mirrors the canonical live exit's last validator.
private struct HistoryInterceptedTransport: ClientTransport {
    let underlying: any ClientTransport
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 32768) } else { bytes = nil }
        try await validate(); try Task.checkCancellation()
        let value = try await underlying.send(request, body: bytes.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
        try await validate(); try Task.checkCancellation()
        return value
    }
}
