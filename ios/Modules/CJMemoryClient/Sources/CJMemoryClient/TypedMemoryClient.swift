import Foundation
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime

/// Explicit compatible consumer for the additive typed host. V1 remains a
/// separate client/journal; a failed V2 operation never falls back to V1.
@MainActor public final class TypedMemoryClient {
    private let endpoint: MemoryEndpoint
    private let credentials: MemoryCredentialCallback
    private let current: @MainActor () -> MemoryBinding?
    private let transport: any ClientTransport
    private let store: TypedMemoryPendingStore
    private var generation = UUID()
    private var confirmed: Set<Data> = []
    #if DEBUG && targetEnvironment(simulator)
    public convenience init(localEndpoint: MemoryEndpoint,credentials: @escaping MemoryCredentialCallback,
        currentBinding: @escaping @MainActor () -> MemoryBinding?,pendingStore: TypedMemoryPendingStore,
        localTransport: NoRedirectTransport) throws {
        guard localEndpoint.url.scheme == "http",localEndpoint.url.host == "127.0.0.1",
              let port = localEndpoint.url.port,(1...65535).contains(port),localEndpoint.maximumRequestBytes <= 32768,
              localEndpoint.maximumResponseBytes <= 1_000_000 else { throw MemoryFailure.unconfigured }
        self.init(endpoint:localEndpoint,credentials:credentials,currentBinding:currentBinding,pendingStore:pendingStore,interceptedTransport:localTransport)
    }
    #endif
    init(endpoint: MemoryEndpoint,credentials: @escaping MemoryCredentialCallback,
        currentBinding: @escaping @MainActor () -> MemoryBinding?,pendingStore: TypedMemoryPendingStore,
        interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint;self.credentials = credentials;current = currentBinding;store = pendingStore;transport = interceptedTransport
    }
    private func check(_ binding: MemoryBinding,_ token: UUID) throws {
        guard generation == token else { throw MemoryFailure.staleBinding }
        let observed = current()
        guard generation == token,observed == binding else { throw MemoryFailure.staleBinding }
    }
    private func begin(_ binding: MemoryBinding) throws -> UUID {
        let token = generation;try check(binding,token);return token
    }
    public func invalidate() { generation = UUID();confirmed.removeAll() }
    private func api(_ binding: MemoryBinding,_ token: UUID,original: TypedMemoryPending? = nil) async throws -> Client {
        try check(binding,token)
        let bearer: String?
        do { bearer = try await credentials(binding) }
        catch { try check(binding,token);throw MemoryFailure.exchangeUnknown }
        try check(binding,token)
        guard let bearer,!bearer.isEmpty,bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw MemoryFailure.unconfigured }
        return Client(serverURL:endpoint.url,configuration:.memory,transport:MemoryTransport(wire:.v2,underlying:transport,
            endpoint:endpoint,bearer:bearer,writeEnabled:true,managementEnabled:false,validate:{ [self] in
                try check(binding,token)
                if let original { try store.requireOriginal(original);try check(binding,token) }
                try store.validateDirectory()
            }))
    }
    private func exchange<Value>(_ binding: MemoryBinding,_ token: UUID,_ action: () async throws -> Value) async throws -> Value {
        do { let value = try await action();try check(binding,token);return value }
        catch { try check(binding,token);throw MemoryFailure.exchangeUnknown }
    }
    public func pending(binding: MemoryBinding) throws -> [TypedMemoryCommand] {
        let token = try begin(binding);try store.validate(binding)
        let result = try store.pending();try check(binding,token);return result
    }
    public func save(_ command: TypedMemoryCommand,binding: MemoryBinding) async throws -> MemorySaveResult {
        let token = try begin(binding);try store.validate(binding)
        guard try store.records().allSatisfy({ record in
            if confirmed.contains(Data(record.operationID.utf8)) { return true }
            return try store.rejection(for:record) != nil
        }) else { throw MemoryFailure.pendingRequiresQuery }
        try check(binding,token)
        let record = TypedMemoryPending(command)
        guard record.originalUTF8.count <= endpoint.maximumRequestBytes else { throw MemoryFailure.invalidInput }
        try store.append(record) { try check(binding,token) };try check(binding,token)
        let api = try await api(binding,token,original:record)
        let output = try await exchange(binding,token) { try await api.saveTypedMemory(body:.binary(HTTPBody(record.originalUTF8))) }
        switch output {
        case .ok(let value):return try settle(value.body.json.receipt,record:record,binding:binding,token:token)
        case .default(let status,let value):
            let error = try value.body.json.error
            guard error.outcome == .failed else { throw MemoryFailure.exchangeUnknown }
            try store.recordRejection(record,status:status,code:error.code) { try check(binding,token) }
            try check(binding,token);throw MemoryFailure.rejected(status,error.code)
        }
    }
    public func query(operationID: String,binding: MemoryBinding) async throws -> MemorySaveResult {
        let token = try begin(binding);try store.validate(binding)
        guard let record = try store.records().first(where:{ same($0.operationID,operationID) }) else { throw MemoryFailure.invalidInput }
        let rejection = try store.rejection(for:record);try check(binding,token)
        let api = try await api(binding,token,original:record)
        let output = try await exchange(binding,token) { try await api.getTypedMemoryReceipt(query:.init(operation_id:operationID)) }
        switch output {
        case .ok(let value):
            switch try value.body.json.receipt {
            case .MemoryReceipt(let receipt):
                guard rejection == nil else { throw MemoryFailure.invalidResponse }
                return try settle(receipt,record:record,binding:binding,token:token)
            case .CJExplicitJSONNull:
                if let rejection { return .rejected(rejection.status,rejection.code) }
                return .notObserved
            }
        case .default:throw MemoryFailure.exchangeUnknown
        }
    }
    private func settle(_ receipt: Components.Schemas.MemoryReceipt,record: TypedMemoryPending,binding: MemoryBinding,token: UUID) throws -> MemorySaveResult {
        try check(binding,token)
        guard same(receipt.operation_id,record.operationID),same(receipt.item_id,record.itemID),
              same(receipt.input_sha256,record.expectedSHA256),receipt.version == 1,
              !record.inference || receipt.status == .candidate else { throw MemoryFailure.invalidResponse }
        confirmed.insert(Data(record.operationID.utf8))
        return receipt.status == .candidate ? .candidate(receipt) : .saved(receipt)
    }
}
