import Foundation
import CryptoKit
import CJAPI
import CJMessageKeys
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
import Testing
@testable import CJNeedsClient

let trace = "00000000-0000-0000-0000-000000000001"
func original(_ id: String = "manual-1", version: Int = 0, text: String = "日期未定。 Dates undecided. e\u{301}") throws -> NeedsPending {
    try .init(command: .init(action_id: id, needs_id: "visit:local-1", expected_version: version,
                            source: .init(kind: .manual, text: text), changes: .init(party_size: .NeedsPartySizeObservationKnown(.init(state: .known, value: 3)))))
}
func event() -> NeedsSchema.NeedsEvent {
    .init(date: .NeedsUnknownObservation(.init(state: .unknown)), time: .NeedsUnknownObservation(.init(state: .unknown)),
          timezone: .NeedsUnknownObservation(.init(state: .unknown)), place: .NeedsUnknownObservation(.init(state: .unknown)))
}
func fields(_ action: NeedsPending) throws -> NeedsSchema.NeedsFields {
    try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: encoded(action.command.changes))
}
func receipt(_ action: NeedsPending) -> NeedsSchema.NeedsReceipt {
    .init(action_id: action.actionID, needs_id: action.needsID, version: action.command.expected_version + 1, operation: .manual_patch)
}
func revision(_ action: NeedsPending) throws -> NeedsSchema.NeedsRevision {
    let f = try fields(action)
    return .init(needs_id: action.needsID, version: action.command.expected_version + 1, action_id: action.actionID,
                 source_kind: .user_provided, original_input_utf8_base64: action.originalUTF8.base64EncodedString(),
                 content_utf8_base64: try encoded(f).base64EncodedString(), fields: f)
}
func snapshot(_ action: NeedsPending) throws -> NeedsSchema.NeedsSnapshot {
    .init(needs_id: action.needsID, version: action.command.expected_version + 1, source_kind: .user_provided,
          content_utf8_base64: try encoded(fields(action)).base64EncodedString(), fields: try fields(action))
}
func response<T: Encodable>(_ key: String, _ value: T) throws -> String {
    "{\"request_id\":\"\(trace)\",\"\(key)\":\(String(decoding: try encoded(value), as: UTF8.self))}"
}
func nullResponse(_ key: String) -> String { "{\"request_id\":\"\(trace)\",\"\(key)\":null}" }
struct Reply: Sendable {
    let text: String
    let status: Int
    init(_ text: String, status: Int = 200) { self.text = text; self.status = status }
}
actor Interceptor: ClientTransport {
    struct Call: Sendable { let operation: String; let bytes: Data; let path: String? }
    var calls: [Call] = []
    let handler: @Sendable (HTTPRequest, Data, String) async throws -> Reply
    init(_ handler: @escaping @Sendable (HTTPRequest, Data, String) async throws -> Reply) { self.handler = handler }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        if let body { bytes = try await Data(collecting: body, upTo: 524_288) } else { bytes = Data() }
        calls.append(.init(operation: operationID, bytes: bytes, path: request.path))
        let reply = try await handler(request, bytes, operationID)
        var response = HTTPResponse(status: .init(code: reply.status))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(reply.text.utf8))
    }
}
func successfulTransport(_ action: NeedsPending) -> Interceptor {
    Interceptor { _, _, operation in
        switch operation {
        case "actOnNeeds", "queryNeedsAction": Reply(try response("receipt", receipt(action)))
        case "getNeedsRevision": Reply(try response("revision", revision(action)))
        case "getNeeds": Reply(try response("needs", snapshot(action)))
        default: throw NeedsFailure.invalidInput
        }
    }
}
actor Gate {
    private var parked: CheckedContinuation<Void, Never>?
    private var entered = false
    private var waiter: CheckedContinuation<Void, Never>?
    func park() async { entered = true; waiter?.resume(); waiter = nil; await withCheckedContinuation { parked = $0 } }
    func waitForEntry() async { if entered { return }; await withCheckedContinuation { waiter = $0 } }
    func release() { parked?.resume(); parked = nil; entered = false }
}
@MainActor final class Harness {
    let binding = NeedsBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: NeedsBinding?
    let root: URL
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let endpoint = try! NeedsEndpoint(url: URL(string: "https://needs.invalid")!, maximumRequestBytes: 131_072, maximumResponseBytes: 1_048_576)
    init() throws {
        root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj013-test-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        current = binding
    }
    var namespace: MessageKeyNamespace { .init(environment: binding.environment, account: binding.account, purpose: .localNeedsPendingV1) }
    func store(key: (() throws -> SymmetricKey)? = nil, keyID: UUID? = nil, namespace: MessageKeyNamespace? = nil) throws -> NeedsPendingStore {
        try .init(directory: root, maximumBytes: 524_288, maximumRecords: 20, namespace: namespace ?? self.namespace, keyID: keyID ?? self.keyID,
                  key: key ?? { [self] in self.key })
    }
    func client(_ transport: Interceptor, store: NeedsPendingStore? = nil, credentials: NeedsCredentialCallback? = nil,
                bindingCallback: (@MainActor () -> NeedsBinding?)? = nil) throws -> NeedsClient {
        try NeedsClient(endpoint: endpoint, credentials: credentials ?? { _ in "synthetic-test-token" },
                        currentBinding: bindingCallback ?? { [self] in current }, pendingStore: store ?? self.store(), interceptedTransport: transport)
    }
    func clean() { try? FileManager.default.removeItem(at: root) }
}
