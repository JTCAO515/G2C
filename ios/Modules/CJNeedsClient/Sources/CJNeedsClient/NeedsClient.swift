import Foundation
import CJAPI
import CJMessageHTTP
import CJSession
import OpenAPIRuntime
import HTTPTypes

public typealias NeedsEndpoint = MessageEndpoint
public typealias NeedsCredentialCallback = @MainActor (NeedsBinding) async throws -> String?

/// One selected operation per client. Public construction cannot enable POST.
@MainActor public final class NeedsClient {
    private let endpoint: NeedsEndpoint
    private let credentials: NeedsCredentialCallback
    private let currentBinding: @MainActor () -> NeedsBinding?
    private let transport: any ClientTransport
    private let session: SessionLifecycle?
    private let sessionOperation: SessionOperation?
    private let testWrites: Bool
    private let store: NeedsPendingStore?
    private let owner = UUID()
    private var generation = UUID()
    private var started: UUID?
    private var confirmed: [Data: String] = [:]
    public let acceptsUserActions: Bool

    public init(endpoint: NeedsEndpoint, credentials: @escaping NeedsCredentialCallback,
                currentBinding: @escaping @MainActor () -> NeedsBinding?, session: SessionLifecycle,
                sessionOperation: SessionOperation, pendingStore: NeedsPendingStore? = nil,
                liveReadTransport: NoRedirectTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.session = session; self.sessionOperation = sessionOperation; store = pendingStore
        transport = liveReadTransport; testWrites = false; acceptsUserActions = false
    }
    /// Internal synthetic transport seam. Never exported as production write permission.
    init(endpoint: NeedsEndpoint, credentials: @escaping NeedsCredentialCallback,
         currentBinding: @escaping @MainActor () -> NeedsBinding?, pendingStore: NeedsPendingStore?,
         interceptedTransport: any ClientTransport, manualWritesAvailable: Bool = false) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        session = nil; sessionOperation = nil; store = pendingStore
        transport = interceptedTransport; testWrites = true; acceptsUserActions = manualWritesAvailable
    }
    #if DEBUG && targetEnvironment(simulator)
    /// Explicit CJ-LOCAL-NEEDS@1 manual-v1 capability. Ordinary and Release
    /// construction retains its read-only path and original session fences.
    public init(localEndpoint endpoint: NeedsEndpoint, credentials: @escaping NeedsCredentialCallback,
                currentBinding: @escaping @MainActor () -> NeedsBinding?, session: SessionLifecycle,
                sessionOperation: SessionOperation, pendingStore: NeedsPendingStore,
                localTransport: NoRedirectTransport) throws {
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1",
              let port = endpoint.url.port, (1...65535).contains(port),
              endpoint.maximumRequestBytes <= 131072, endpoint.maximumResponseBytes <= 1048576 else {
            throw NeedsFailure.unconfigured
        }
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        self.session = session; self.sessionOperation = sessionOperation; store = pendingStore
        transport = localTransport; testWrites = true; acceptsUserActions = true
    }
    #endif
    public func invalidate() { generation = UUID(); started = nil; confirmed.removeAll() }
    func retireWork() { generation = UUID(); started = nil }
    private var sessionIsCurrent: Bool {
        if let session, let sessionOperation { return session.isCurrent(sessionOperation) }
        return testWrites && session == nil && sessionOperation == nil
    }
    func owns(_ work: NeedsWork) -> Bool {
        guard work.owner == owner, generation == work.generation else { return false }
        let observed = currentBinding()
        return work.owner == owner && generation == work.generation && observed == work.binding && sessionIsCurrent
    }
    private func check(_ work: NeedsWork) throws {
        guard owns(work) else { throw NeedsFailure.staleBinding }
        try Task.checkCancellation()
    }
    private func prepare(_ kind: NeedsWork.Kind, binding: NeedsBinding) -> NeedsWork {
        generation = UUID(); started = nil
        return NeedsWork(owner: owner, generation: generation, binding: binding, kind: kind)
    }
    public func prepareDetail(id: String, binding: NeedsBinding) -> NeedsWork { prepare(.detail(id), binding: binding) }
    public func prepareRevision(id: String, version: Int, binding: NeedsBinding) -> NeedsWork { prepare(.revision(id, version), binding: binding) }
    public func prepareQuery(actionID: String, binding: NeedsBinding) -> NeedsWork { prepare(.query(actionID), binding: binding) }
    public func prepareReplay(actionID: String, binding: NeedsBinding) -> NeedsWork { prepare(.replay(actionID), binding: binding) }
    public func prepareManualAction(_ original: NeedsPending, binding: NeedsBinding) -> NeedsWork { prepare(.submit(original), binding: binding) }

    public func pending(binding: NeedsBinding) throws -> [NeedsPending] {
        let work = NeedsWork(owner: owner, generation: generation, binding: binding, kind: .query(""))
        try check(work)
        guard let store else { throw NeedsFailure.unconfigured }
        try store.validate(binding)
        let records = try store.pending(); try check(work)
        let proofs = try records.map { try store.requireOriginal($0) }
        try check(work)
        for proof in proofs { try store.validateDurability(proof) }
        // An empty result has no ciphertext proofs; it still needs the final directory fence.
        try store.validateDirectory()
        return records
    }
    /// Read-only admission for an explicit *new* manual action. A null/failed
    /// GET cannot settle an old POST. Only exact history or durable failed-POST
    /// evidence qualifies, with all resources checked after the last callback.
    public func requiresOriginalReconciliation(binding: NeedsBinding) throws -> Bool {
        let work = NeedsWork(owner: owner, generation: generation, binding: binding, kind: .query(""))
        try check(work)
        guard let store else { throw NeedsFailure.unconfigured }
        try store.validate(binding)
        let records = try store.pending()
        var originals: [NeedsPendingStore.Durability] = []
        var rejections: [NeedsPendingStore.RejectionProof] = []
        for original in records {
            originals.append(try store.requireOriginal(original))
            if confirmed[Data(original.actionID.utf8)] != digest(original.originalUTF8) {
                guard acceptsUserActions, let proof = try store.rejectionProof(for: original) else {
                    try check(work)
                    return true
                }
                rejections.append(proof)
            }
        }
        try check(work)
        try store.validateInventory(records.map(\.actionID))
        for proof in originals { try store.validateDurability(proof) }
        for proof in rejections { try proof.validateDurability() }
        return false
    }
    private func api(_ work: NeedsWork, original: NeedsPending? = nil, prerequisites: [NeedsPending]? = nil) async throws -> Client {
        try check(work)
        let bearer: String?
        do { bearer = try await credentials(work.binding) }
        catch { try check(work); throw NeedsFailure.unconfigured }
        try check(work)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw NeedsFailure.unconfigured }
        return Client(serverURL: endpoint.url, configuration: .memory,
                      transport: NeedsTransport(underlying: transport, endpoint: endpoint, bearer: bearer, testWrites: testWrites) { [self] in
            try check(work)
            if let original {
                guard let store else { throw NeedsFailure.unconfigured }
                var originals = [try store.requireOriginal(original)]
                var rejections: [NeedsPendingStore.RejectionProof] = []
                if let prerequisites {
                    for prior in prerequisites {
                        originals.append(try store.requireOriginal(prior))
                        if confirmed[Data(prior.actionID.utf8)] != digest(prior.originalUTF8) {
                            guard let proof = try store.rejectionProof(for: prior) else { throw NeedsFailure.pendingRequiresQuery }
                            rejections.append(proof)
                        }
                    }
                }
                try check(work)
                // All key/binding callbacks have finished. The entire prefix,
                // originals and rejection ciphertexts must still be durable.
                if let prerequisites { try store.validateInventory(prerequisites.map(\.actionID) + [original.actionID]) }
                for proof in originals { try store.validateDurability(proof) }
                for proof in rejections { try proof.validateDurability() }
            }
        })
    }
    private func exchange<T>(_ work: NeedsWork, _ action: () async throws -> T) async throws -> T {
        do { let result = try await action(); try check(work); return result }
        catch { try check(work); throw NeedsFailure.exchangeUnknown } // Never leak ClientError's bearer/body.
    }
    public func perform(_ work: NeedsWork) async throws -> NeedsResult {
        try check(work)
        guard started != work.generation else { throw NeedsFailure.staleBinding }
        started = work.generation
        switch work.kind {
        case .detail(let id):
            guard needsID(id) else { throw NeedsFailure.invalidInput }
            let client = try await api(work)
            let output = try await exchange(work) { try await client.getNeeds(query: .init(needs_id: id)) }
            switch output {
            case .ok(let response):
                switch try response.body.json.needs {
                case .NeedsSnapshot(let value):
                    try validateSnapshot(value)
                    guard same(value.needs_id, id) else { throw NeedsFailure.invalidResponse }
                    return .detail(value)
                case .case2(let null): guard null.value == nil else { throw NeedsFailure.invalidResponse }; return .detail(nil)
                }
            case .default(let status, let response): throw NeedsFailure.rejected(status, try response.body.json.error.code)
            }
        case .revision(let id, let version): return .revision(try await revision(id, version, work))
        case .query(let id):
            guard needsID(id), let store else { throw NeedsFailure.invalidInput }
            try store.validate(work.binding)
            guard let original = try store.pending().first(where: { same($0.actionID, id) }) else { throw NeedsFailure.invalidInput }
            try check(work)
            let rejected = acceptsUserActions ? try store.rejectionProof(for: original) : nil
            try check(work)
            let client = try await api(work, original: original)
            let output = try await exchange(work) { try await client.queryNeedsAction(query: .init(action_id: original.actionID)) }
            switch output {
            case .ok(let response):
                switch try response.body.json.receipt {
                case .NeedsReceipt(let receipt):
                    guard rejected == nil else { throw NeedsFailure.invalidResponse }
                    return try await settle(receipt, original, work)
                case .case2(let null):
                    guard null.value == nil else { throw NeedsFailure.invalidResponse }
                    if let rejected {
                        // The proof was read before credential/transport callbacks.
                        // It must still be the same durable evidence at settlement.
                        try check(work)
                        try rejected.validateDurability()
                        return .rejectedOriginal(original, rejected.record.status, rejected.record.response.error.code)
                    }
                    return .notObserved
                }
            case .default(let status, let response): throw NeedsFailure.rejected(status, try response.body.json.error.code)
            }
        case .submit(let original):
            guard testWrites else { throw NeedsFailure.liveWriteUnavailable }
            guard let store else { throw NeedsFailure.unconfigured }
            try store.validate(work.binding); try original.validate()
            guard original.originalUTF8.count <= endpoint.maximumRequestBytes else { throw NeedsFailure.invalidInput }
            let existing = try store.pending(); try check(work)
            guard !existing.contains(where: { same($0.actionID, original.actionID) }),
                  try existing.allSatisfy({ prior in
                      if confirmed[Data(prior.actionID.utf8)] == digest(prior.originalUTF8) { return true }
                      return try acceptsUserActions && store.rejection(for: prior) != nil
                  }) else { throw NeedsFailure.pendingRequiresQuery }
            try store.append(original) { try self.check(work) }
            try check(work)
            let client = try await api(work, original: original, prerequisites: acceptsUserActions ? existing : nil)
            let output = try await exchange(work) { try await client.actOnNeeds(body: .binary(HTTPBody(original.originalUTF8))) }
            switch output {
            case .ok(let response): return try await settle(response.body.json.receipt, original, work)
            case .default(let status, let response):
                let body = try response.body.json
                if acceptsUserActions, body.error.outcome == .failed, body.error.recovery == .do_not_retry,
                   (status == 400 && body.error.code == "INVALID_INPUT") || (status == 409 && body.error.code == "NEEDS_CONFLICT") {
                    try store.recordRejection(original, status: status, response: body) { try self.check(work) }
                    try check(work)
                    return .rejectedOriginal(original, status, body.error.code)
                }
                if acceptsUserActions { throw NeedsFailure.exchangeUnknown }
                throw NeedsFailure.rejected(status, body.error.code)
            }
        case .replay(let id):
            guard acceptsUserActions, let store else { throw NeedsFailure.liveWriteUnavailable }
            try store.validate(work.binding)
            guard let original = try store.pending().first(where: { same($0.actionID, id) }),
                  confirmed[Data(id.utf8)] == digest(original.originalUTF8) else { throw NeedsFailure.pendingRequiresQuery }
            try check(work)
            confirmed.removeValue(forKey: Data(id.utf8)) // Unknown replay returns to query-only.
            let client = try await api(work, original: original)
            let output = try await exchange(work) { try await client.actOnNeeds(body: .binary(HTTPBody(original.originalUTF8))) }
            switch output {
            case .ok(let response): return try await settle(response.body.json.receipt, original, work)
            case .default: throw NeedsFailure.exchangeUnknown
            }
        }
    }
    private func revision(_ id: String, _ version: Int, _ work: NeedsWork, original: NeedsPending? = nil) async throws -> NeedsSchema.NeedsRevision? {
        guard needsID(id), version > 0 else { throw NeedsFailure.invalidInput }
        let client = try await api(work, original: original)
        let output = try await exchange(work) { try await client.getNeedsRevision(query: .init(needs_id: id, version: version)) }
        switch output {
        case .ok(let response):
            switch try response.body.json.revision {
            case .NeedsRevision(let value):
                try validateRevision(value)
                guard same(value.needs_id, id), value.version == version else { throw NeedsFailure.invalidResponse }
                return value
            case .case2(let null): guard null.value == nil else { throw NeedsFailure.invalidResponse }; return nil
            }
        case .default(let status, let response): throw NeedsFailure.rejected(status, try response.body.json.error.code)
        }
    }
    private func settle(_ receipt: NeedsSchema.NeedsReceipt, _ original: NeedsPending, _ work: NeedsWork) async throws -> NeedsResult {
        guard same(receipt.action_id, original.actionID), same(receipt.needs_id, original.needsID),
              receipt.version > 0, original.command.expected_version < Int.max,
              receipt.version == original.command.expected_version + 1 else { throw NeedsFailure.invalidResponse }
        guard let revision = try await revision(receipt.needs_id, receipt.version, work, original: original) else { return .notObserved }
        guard same(revision.action_id, original.actionID),
              Data(base64Encoded: revision.original_input_utf8_base64) == original.originalUTF8 else { throw NeedsFailure.invalidResponse }
        guard let store else { throw NeedsFailure.unconfigured }
        let proof = try store.requireOriginal(original); try check(work); try store.validateDurability(proof)
        confirmed[Data(original.actionID.utf8)] = digest(original.originalUTF8)
        return .confirmed(receipt, revision)
    }
}

struct NeedsTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: NeedsEndpoint
    let bearer: String
    let testWrites: Bool
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let paths = ["getNeeds": "/v1/needs", "getNeedsRevision": "/v1/needs-revisions",
                     "queryNeedsAction": "/v1/needs-action-receipts", "actOnNeeds": "/v1/needs-actions"]
        guard baseURL == endpoint.url, let path = paths[operationID],
              request.path?.split(separator: "?", maxSplits: 1).first.map(String.init) == path,
              request.method == (operationID == "actOnNeeds" ? .post : .get),
              operationID != "actOnNeeds" || testWrites else { throw NeedsFailure.liveWriteUnavailable }
        var request = request; request.headerFields[.authorization] = "Bearer " + bearer
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: endpoint.maximumRequestBytes) } else { bytes = nil }
        try await validate()
        let (response, responseBody) = try await underlying.send(request, body: bytes.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let responseBody else { throw NeedsFailure.invalidResponse }
        let data = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
        try await validate()
        _ = try validateUnambiguousJSON(data)
        guard response.headerFields[.contentType]?.split(separator: ";", maxSplits: 1).first?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "application/json",
              let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let trace = root["request_id"] as? String, UUID(uuidString: trace) != nil,
              let header = response.headerFields[HTTPField.Name("X-Request-ID")!], same(trace, header) else { throw NeedsFailure.invalidResponse }
        // Formal parsing stays in the official generated Client. No parallel wire/parser.
        return (response, HTTPBody(data))
    }
}
