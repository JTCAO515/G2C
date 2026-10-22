import Testing
import Foundation
import CryptoKit
import CJAPI
import CJMessageKeys
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJTripClient

let trace = "00000000-0000-0000-0000-000000000001"
struct ActionFixture: Decodable {
    let producer: String
    let proposal: Components.Schemas.TripProposalSnapshot
    let accept_raw: String
    let reject_raw: String
}
func fixture() throws -> ActionFixture {
    let url = try #require(Bundle.module.url(forResource: "action", withExtension: "json", subdirectory: "Fixtures"))
    return try JSONDecoder().decode(ActionFixture.self, from: Data(contentsOf: url))
}
func pending(_ kind: TripActionKind = .accept) throws -> TripPending {
    try TripPending(actionID: kind == .accept ? "accept1" : "reject1", kind: kind, proposal: fixture().proposal,
                    confirmationReference: kind == .accept ? "server-held-accept-proof" : "server-held-reject-proof")
}
func json<T: Encodable>(_ value: T) throws -> String { String(decoding: try JSONEncoder().encode(value), as: UTF8.self) }
func response<T: Encodable>(_ key: String, _ value: T) throws -> String { "{\"request_id\":\"\(trace)\",\"\(key)\":\(try json(value))}" }
func actionReceipt(_ original: TripPending, version: Int? = nil) -> Components.Schemas.TripActionReceipt {
    .init(action_id: original.actionID, kind: original.kind, proposal_id: original.proposal.proposal_id,
          candidate_hash: original.proposal.candidate_hash, trip_id: original.proposal.trip_id,
          committed_version: original.kind == .accept ? .case1(version ?? 1) : .case2(nil))
}
func record(_ id: String = "trip1", version: Int = 1) throws -> Components.Schemas.TripRecord {
    let p = try fixture().proposal
    return .init(trip_id: id, version: version, content_utf8_base64: p.content_utf8_base64, document: p.document)
}
actor Interceptor: ClientTransport {
    struct Call: Sendable { let operation: String; let bytes: Data; let path: String? }
    var calls: [Call] = []
    let handler: @Sendable (HTTPRequest, Data, String) async throws -> String
    init(_ handler: @escaping @Sendable (HTTPRequest, Data, String) async throws -> String) { self.handler = handler }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        if let body { bytes = try await Data(collecting: body, upTo: 100_000) } else { bytes = Data() }
        calls.append(Call(operation: operationID, bytes: bytes, path: request.path))
        let text = try await handler(request, bytes, operationID)
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(text.utf8))
    }
}
actor Gate {
    private var parked: CheckedContinuation<Void, Never>?
    private var entered = false
    private var entryWaiter: CheckedContinuation<Void, Never>?
    func park() async {
        entered = true; entryWaiter?.resume(); entryWaiter = nil
        await withCheckedContinuation { parked = $0 }
    }
    func waitForEntry() async {
        if entered { return }; await withCheckedContinuation { entryWaiter = $0 }
    }
    func release() { parked?.resume(); parked = nil; entered = false }
}
@MainActor final class Harness {
    let binding = TripBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: TripBinding?
    let root: URL
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let endpoint = try! TripEndpoint(url: URL(string: "https://trip.invalid")!, maximumRequestBytes: 100_000, maximumResponseBytes: 100_000)
    init() throws {
        root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj015-test-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        current = binding
    }
    var namespace: MessageKeyNamespace { .init(environment: binding.environment, account: binding.account, purpose: .localTripPendingV1) }
    func store(key: (() throws -> SymmetricKey)? = nil) throws -> TripPendingStore {
        try TripPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 20, namespace: namespace, keyID: keyID,
                             key: key ?? { [self] in self.key })
    }
    func client(_ transport: Interceptor, store: TripPendingStore? = nil, credentials: TripCredentialCallback? = nil) throws -> TripClient {
        try TripClient(endpoint: endpoint, credentials: credentials ?? { _ in "synthetic-test-token" }, currentBinding: { [self] in current },
                       pendingStore: store ?? self.store(), interceptedTransport: transport)
    }
    func clean() { try? FileManager.default.removeItem(at: root) }
}

@MainActor struct SyntheticSessionPersistence: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws { }
    func clearAndBlock() throws { }
}
