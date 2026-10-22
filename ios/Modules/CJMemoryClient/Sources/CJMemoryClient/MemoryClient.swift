import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

public typealias MemoryEndpoint = MessageEndpoint
public typealias MemoryCredentialCallback = @MainActor (MemoryBinding) async throws -> String?

struct MemoryTransport: ClientTransport {
    let underlying: any ClientTransport
    let endpoint: MemoryEndpoint
    let bearer: String
    let writeEnabled: Bool
    let validate: @MainActor @Sendable () throws -> Void
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let paths = ["saveMemory": "/v1/memories", "listMemories": "/v1/memories", "queryMemoryReceipt": "/v1/memory-receipts", "listMemoryGroups": "/v1/memory-groups", "getMemoryItem": "/v1/memory-items"]
        guard baseURL == endpoint.url, let path = paths[operationID],
              request.path?.split(separator: "?", maxSplits: 1).first.map(String.init) == path,
              request.method == (operationID == "saveMemory" ? .post : .get),
              operationID != "saveMemory" || writeEnabled else { throw MemoryFailure.liveWriteUnavailable }
        var request = request
        request.headerFields[.authorization] = "Bearer " + bearer
        let data: Data?
        if let body { data = try await Data(collecting: body, upTo: endpoint.maximumRequestBytes) } else { data = nil }
        try await validate()
        let (response, body) = try await underlying.send(request, body: data.map(HTTPBody.init), baseURL: baseURL, operationID: operationID)
        try await validate()
        guard !(300..<400).contains(response.status.code), let body else { throw MemoryFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try await validate()
        var strict = StrictMemoryJSON(bytes: Array(bytes)); try strict.check()
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        guard traces.count == 1, let trace = traces.first?.value, UUID(uuidString: trace) != nil,
              let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let value = object["request_id"] as? String, same(value, trace) else { throw MemoryFailure.invalidResponse }
        return (response, HTTPBody(bytes))
    }
}

public struct MemoryPage: Sendable {
    public let items: [Components.Schemas.MemoryItem]
    public let next: MemoryCursor?
}
public struct MemoryCursor: Sendable {
    fileprivate let owner: UUID
    fileprivate let binding: MemoryBinding
    fileprivate let after: String
}
public enum MemorySaveResult: Sendable {
    case saved(Components.Schemas.MemoryReceipt)
    case candidate(Components.Schemas.MemoryReceipt)
    case notObserved // Still pending; explicitly not write permission.
}

@MainActor public final class MemoryClient {
    private let endpoint: MemoryEndpoint
    private let credentials: MemoryCredentialCallback
    private let current: @MainActor () -> MemoryBinding?
    private let transport: any ClientTransport
    private let store: MemoryPendingStore?
    private let writeEnabled: Bool
    private let owner = UUID()
    private var generation = UUID()
    private var confirmed: Set<Data> = []
    public init(endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
                currentBinding: @escaping @MainActor () -> MemoryBinding?, pendingStore: MemoryPendingStore?,
                liveReadTransport: NoRedirectTransport) {
        self.endpoint = endpoint; self.credentials = credentials; current = currentBinding
        store = pendingStore; transport = liveReadTransport; writeEnabled = false
    }
    /// Internal capability: tests can intercept POST, public consumers cannot enable live writes.
    init(endpoint: MemoryEndpoint, credentials: @escaping MemoryCredentialCallback,
         currentBinding: @escaping @MainActor () -> MemoryBinding?, pendingStore: MemoryPendingStore?,
         interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint; self.credentials = credentials; current = currentBinding
        store = pendingStore; transport = interceptedTransport; writeEnabled = true
    }
    private func check(_ binding: MemoryBinding, _ token: UUID) throws {
        guard generation == token else { throw MemoryFailure.staleBinding }
        let observed = current()
        guard generation == token, observed == binding else { throw MemoryFailure.staleBinding }
        try Task.checkCancellation()
    }
    private func begin(_ binding: MemoryBinding) throws -> UUID {
        let token = UUID(); generation = token
        try check(binding, token)
        return token
    }
    public func invalidate() { generation = UUID(); confirmed.removeAll() }
    private func api(_ binding: MemoryBinding, _ token: UUID, original: MemoryPending? = nil) async throws -> Client {
        try check(binding, token)
        let bearer: String?
        do { bearer = try await credentials(binding) }
        catch { try check(binding, token); throw MemoryFailure.unconfigured }
        try check(binding, token)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MemoryFailure.unconfigured }
        return Client(serverURL: endpoint.url, configuration: .memory,
                      transport: MemoryTransport(underlying: transport, endpoint: endpoint, bearer: bearer, writeEnabled: writeEnabled,
                        validate: { [self] in
                            try check(binding, token)
                            if let original {
                                guard let store else { throw MemoryFailure.unconfigured }
                                try store.requireOriginal(original)
                                try check(binding, token)
                                try store.validateDirectory()
                            }
                        }))
    }
    private func exchange<T>(_ binding: MemoryBinding, _ token: UUID, _ action: () async throws -> T) async throws -> T {
        do { let value = try await action(); try check(binding, token); return value }
        catch { try check(binding, token); throw MemoryFailure.exchangeUnknown }
    }
    public func pending(binding: MemoryBinding) throws -> [MemoryPending] {
        let token = try begin(binding)
        guard let store else { throw MemoryFailure.unconfigured }
        try store.validate(binding)
        let records = try store.pending(); try check(binding, token)
        return records
    }
    public func save(_ command: Components.Schemas.MemoryManualSaveCommand, binding: MemoryBinding) async throws -> MemorySaveResult {
        let token = try begin(binding)
        guard writeEnabled else { throw MemoryFailure.liveWriteUnavailable }
        guard let store else { throw MemoryFailure.unconfigured }
        try store.validate(binding)
        guard try store.pending().allSatisfy({ confirmed.contains(Data($0.operationID.utf8)) }) else { throw MemoryFailure.pendingRequiresQuery }
        try check(binding, token)
        let record = try MemoryPending(command)
        guard record.originalUTF8.count <= endpoint.maximumRequestBytes else { throw MemoryFailure.invalidInput }
        // Durable immutable original bytes precede even the async credential lookup.
        try store.append(record) { try check(binding, token) }; try check(binding, token)
        let client = try await api(binding, token, original: record)
        let response = try await exchange(binding, token) { try await client.saveMemory(body: .binary(HTTPBody(record.originalUTF8))) }
        switch response {
        case .ok(let value): return try settle(value.body.json.receipt, record: record, binding: binding, token: token)
        case .default(let status, let value): throw MemoryFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func query(operationID: String, binding: MemoryBinding) async throws -> MemorySaveResult {
        let token = try begin(binding)
        guard let store else { throw MemoryFailure.unconfigured }
        try store.validate(binding)
        guard let record = try store.pending().first(where: { same($0.operationID, operationID) }) else { throw MemoryFailure.invalidInput }
        try check(binding, token)
        let client = try await api(binding, token)
        let response = try await exchange(binding, token) { try await client.queryMemoryReceipt(query: .init(operation_id: record.operationID)) }
        switch response {
        case .ok(let value):
            switch try value.body.json.receipt {
            case .MemoryReceipt(let receipt): return try settle(receipt, record: record, binding: binding, token: token)
            case .case2(let null): guard null.value == nil else { throw MemoryFailure.invalidResponse }; return .notObserved
            }
        case .default(let status, let value): throw MemoryFailure.rejected(status, try value.body.json.error.code)
        }
    }
    private func settle(_ receipt: Components.Schemas.MemoryReceipt, record: MemoryPending, binding: MemoryBinding, token: UUID) throws -> MemorySaveResult {
        try check(binding, token)
        guard same(receipt.operation_id, record.operationID), same(receipt.item_id, record.itemID),
              same(receipt.input_sha256, record.expectedSHA256), receipt.version == 1,
              (!record.inference || receipt.status == .candidate) else { throw MemoryFailure.invalidResponse }
        confirmed.insert(Data(record.operationID.utf8))
        return receipt.status == .candidate ? .candidate(receipt) : .saved(receipt)
    }
    public func groups(binding: MemoryBinding) async throws -> [Components.Schemas.MemoryGroup] {
        let token = try begin(binding); let client = try await api(binding, token)
        let response = try await exchange(binding, token) { try await client.listMemoryGroups() }
        switch response {
        case .ok(let value):
            let groups = try value.body.json.groups
            var seen = Set<Data>()
            for group in groups {
                let identity = try JSONEncoder().encode([group.subject, group.status.rawValue])
                guard !group.subject.isEmpty, group.count > 0, seen.insert(identity).inserted else { throw MemoryFailure.invalidResponse }
            }
            return groups
        case .default(let status, let value): throw MemoryFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func list(limit: Int, after: MemoryCursor? = nil, binding: MemoryBinding) async throws -> MemoryPage {
        let token = try begin(binding)
        guard (1...100).contains(limit) else { throw MemoryFailure.invalidInput }
        if let after { guard after.owner == owner, after.binding == binding else { throw MemoryFailure.staleBinding } }
        let client = try await api(binding, token)
        let response = try await exchange(binding, token) { try await client.listMemories(query: .init(limit: limit, after: after?.after)) }
        switch response {
        case .ok(let value):
            let body = try value.body.json
            guard body.items.count <= limit else { throw MemoryFailure.invalidResponse }
            var previous = after?.after ?? ""
            for item in body.items {
                try validateItem(item)
                guard previous.utf8.lexicographicallyPrecedes(item.command.item_id.utf8) else { throw MemoryFailure.invalidResponse }
                previous = item.command.item_id
            }
            let next: MemoryCursor?
            switch body.next_after {
            case .case1(let text):
                guard let last = body.items.last, same(text, last.command.item_id) else { throw MemoryFailure.invalidResponse }
                next = MemoryCursor(owner: owner, binding: binding, after: text)
            case .case2(let null):
                guard null.value == nil, body.items.isEmpty else { throw MemoryFailure.invalidResponse }; next = nil
            }
            return MemoryPage(items: body.items, next: next)
        case .default(let status, let value): throw MemoryFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func detail(itemID: String, binding: MemoryBinding) async throws -> Components.Schemas.MemoryItem? {
        let token = try begin(binding)
        guard memoryText(itemID) else { throw MemoryFailure.invalidInput }
        let client = try await api(binding, token)
        let response = try await exchange(binding, token) { try await client.getMemoryItem(query: .init(item_id: itemID)) }
        switch response {
        case .ok(let value):
            switch try value.body.json.item {
            case .MemoryItem(let item):
                try validateItem(item)
                guard same(item.command.item_id, itemID) else { throw MemoryFailure.invalidResponse }; return item
            case .case2(let null): guard null.value == nil else { throw MemoryFailure.invalidResponse }; return nil
            }
        case .default(let status, let value): throw MemoryFailure.rejected(status, try value.body.json.error.code)
        }
    }
    private func validateItem(_ item: Components.Schemas.MemoryItem) throws {
        let c = item.command
        guard memoryText(c.item_id), memoryText(c.operation_id),
              !c.source_id.isEmpty, c.source_version > 0, item.version > 0,
              !c.subject.isEmpty, !c.slot.isEmpty, !c.text.isEmpty else { throw MemoryFailure.invalidResponse }
        switch c.context_id {
        case .case1(let id): guard c.extent == .current, !id.isEmpty else { throw MemoryFailure.invalidResponse }
        case .case2(let null): guard c.extent == .long_term, null.value == nil else { throw MemoryFailure.invalidResponse }
        }
    }
}
