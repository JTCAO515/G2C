import Testing
import Foundation
import CryptoKit
import CJAPI
import CJMessageKeys
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJFeedbackClient

let trace = "00000000-0000-0000-0000-000000000001"
func pending(linked: Bool = false, actionID: String = "feedback-original") throws -> FeedbackPending {
    try FeedbackPending(problem: "自愿问题 e\u{301} 🌏", expectation: "期望", context: linked ? FeedbackContext(messageID: "消息e\u{301}", runID: "运行") : nil, actionID: actionID)
}
func receiptJSON(_ original: FeedbackPending, source: String? = nil, hash: String? = nil, date: String = "2026-10-22T10:00:00Z") throws -> String {
    let action = try original.action()
    let observed = source ?? (action.references.isEmpty ? "null" : """
    {"message_id":"消息e\\u0301","conversation_id":"conversation","generation":"generation","message_sequence":1,"run_id":"运行","message_input_sha256":"\(String(repeating: "b", count: 64))","run_status_at_read":"running","event_highwater_at_read":4}
    """)
    return """
    {"request_id":"\(trace)","receipt":{"action_id":"\(original.actionID)","input_sha256":"\(hash ?? original.inputSHA256)","submitted_at":"\(date)","status":"submitted","message_en":"Feedback submitted.","message_zh":"反馈已提交。","source":\(observed)}}
    """
}
let nullResponse = "{\"request_id\":\"\(trace)\",\"receipt\":null}"
struct Reply: Sendable { var text: String; var status: Int = 200 }
actor Interceptor: ClientTransport {
    struct Call: Sendable { let operation: String; let bytes: Data; let path: String?; let authorization: String? }
    var calls: [Call] = []
    let handler: @Sendable (HTTPRequest, Data, String) async throws -> Reply
    init(_ handler: @escaping @Sendable (HTTPRequest, Data, String) async throws -> Reply) { self.handler = handler }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        if let body { bytes = try await Data(collecting: body, upTo: 100_000) } else { bytes = Data() }
        calls.append(Call(operation: operationID, bytes: bytes, path: request.path, authorization: request.headerFields[.authorization]))
        let reply = try await handler(request, bytes, operationID)
        var response = HTTPResponse(status: .init(code: reply.status))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(reply.text.utf8))
    }
}
actor Gate {
    private var parked: CheckedContinuation<Void, Never>?
    private var entered = false
    private var waiter: CheckedContinuation<Void, Never>?
    func park() async {
        entered = true; waiter?.resume(); waiter = nil
        await withCheckedContinuation { parked = $0 }
    }
    func waitForEntry() async { if entered { return }; await withCheckedContinuation { waiter = $0 } }
    func release() { parked?.resume(); parked = nil }
}
@MainActor final class Harness {
    let binding = FeedbackBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: FeedbackBinding?
    var onBinding: (() -> Void)?
    let root: URL
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let endpoint = try! FeedbackEndpoint(url: URL(string: "https://feedback.invalid")!, maximumRequestBytes: 16384, maximumResponseBytes: 100_000)
    init() throws {
        root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj023-test-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        current = binding
    }
    var namespace: MessageKeyNamespace { .init(environment: binding.environment, account: binding.account, purpose: .localFeedbackPendingV1) }
    func store(key: (() throws -> SymmetricKey)? = nil) throws -> FeedbackPendingStore {
        try FeedbackPendingStore(directory: root, maximumBytes: 100_000, maximumRecords: 20, namespace: namespace, keyID: keyID, key: key ?? { [self] in self.key })
    }
    func client(_ transport: Interceptor, store: FeedbackPendingStore? = nil, credentials: FeedbackCredentialCallback? = nil) throws -> FeedbackClient {
        try FeedbackClient(endpoint: endpoint, credentials: credentials ?? { _ in "synthetic-test-token" }, currentBinding: { [self] in onBinding?(); return current },
                           pendingStore: store ?? self.store(), interceptedTransport: transport)
    }
    func clean() { try? FileManager.default.removeItem(at: root); try? FileManager.default.removeItem(at: root.appendingPathExtension("moved")) }
}
