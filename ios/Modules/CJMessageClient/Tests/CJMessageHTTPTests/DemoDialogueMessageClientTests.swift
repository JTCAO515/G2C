import CryptoKit
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class DialogueFixtureStorage: SecureMessageStorage {
    private var snapshots: [String: Snapshot] = [:]
    func load(scope: StorageScope) throws -> Snapshot? { snapshots[scope.account] }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { snapshots[scope.account] = snapshot }
}

@MainActor private final class DialogueFixtureCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "fixture-only" }
}

private actor DialogueReceiptFixture: ClientTransport {
    enum Reply: Sendable { case lost, response(Int, Data) }
    struct Call: Sendable {
        let method: HTTPRequest.Method
        let path: String?
        let body: Data?
    }

    let trace: String
    private var replies: [Reply]
    private(set) var calls: [Call] = []

    init(trace: String, replies: [Reply]) {
        self.trace = trace
        self.replies = replies
    }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 16_384) }
        else { bytes = nil }
        calls.append(.init(method: request.method, path: request.path, body: bytes))
        guard !replies.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        switch replies.removeFirst() {
        case .lost: throw URLError(.networkConnectionLost)
        case .response(let status, let payload):
            var response = HTTPResponse(status: .init(code: status))
            response.headerFields[.contentType] = "application/json"
            response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
            return (response, HTTPBody(payload))
        }
    }
}

@MainActor struct DemoDialogueMessageClientTests {
    private let requestID = "11111111-1111-4111-8111-111111111111"
    private let messageID = "a+b"
    private let conversationID = "demo-dialogue-0123456789abcdef0123456789abcdef"

    private func original(_ id: String = "a+b") -> Data {
        Data(#"{"version":"DEMO-dialogue-message.1","message_id":"\#(id)","text":"  原文 🧳  ","locale":"zh"}"#.utf8)
    }

    private func response(_ receipt: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: [
            "version": "DEMO-dialogue-receipt.1", "request_id": requestID, "receipt": receipt
        ])
    }

    private func accepted(_ raw: Data, digest: String? = nil) throws -> Data {
        try response([
            "message_id": messageID, "conversation_id": conversationID, "run_id": "run",
            "input_sha256": digest ?? SHA256.hash(data: raw).map { String(format: "%02x", $0) }.joined()
        ])
    }

    private func fixture(recovery: MessageRecovery, scope: StorageScope, responder: DialogueReceiptFixture) throws -> DemoDialogueMessageClient {
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://api-beta.go2china.space")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        return DemoDialogueMessageClient(recovery: recovery, scope: scope, endpoint: endpoint,
            credentials: DialogueFixtureCredentials(),
            transport: NoRedirectTransport(interceptedTransport: responder, demoDialogueEndpoint: endpoint, validateDemoDialogue: {}))
    }

    @Test func lostWriteRemainsQueryOnlyAfterReopenAndNullRead() async throws {
        let store = DialogueFixtureStorage(), scope = try StorageScope(environment: UUID().uuidString, account: "one")
        let first = MessageRecovery(storage: store), lease = try first.activate(scope), raw = original()
        let responder = DialogueReceiptFixture(trace: requestID, replies: [
            .lost, .response(200, try response(NSNull())), .response(200, try accepted(raw))
        ])
        let sending = try fixture(recovery: first, scope: scope, responder: responder)
        guard case .unknown = try await sending.submit(originalUTF8: raw, lease: lease) else {
            Issue.record("The lost POST must remain unresolved"); return
        }
        first.invalidate()
        let reopened = MessageRecovery(storage: store), restoredLease = try reopened.activate(scope)
        let reading = try fixture(recovery: reopened, scope: scope, responder: responder)
        #expect(try reading.unresolvedMessages(lease: restoredLease).map(\.messageID) == [messageID])
        #expect(try reopened.action(messageID: messageID, lease: restoredLease)?.originalUTF8 == raw)
        guard case .notObserved = try await reading.reconcile(messageID: messageID, lease: restoredLease) else {
            Issue.record("A null GET must not prove a failed write"); return
        }
        await #expect(throws: RecoveryError.queryOnly) {
            _ = try await reading.submit(originalUTF8: original("different"), lease: restoredLease)
        }
        guard case .accepted(let receipt) = try await reading.reconcile(messageID: messageID, lease: restoredLease) else {
            Issue.record("Expected the matching original receipt"); return
        }
        #expect(receipt.conversationID == conversationID)
        #expect(try reading.unresolvedMessages(lease: restoredLease).isEmpty)
        let calls = await responder.calls
        #expect(calls.map(\.method) == [.post, .get, .get])
        #expect(calls.first?.body == raw)
        #expect(calls.dropFirst().allSatisfy { $0.body == nil && $0.path == "/v1/demo-dialogue/messages?message_id=a%2Bb" })
    }

    @Test func wrongDigestAndOtherOwnerDoNotSettleTheOriginal() async throws {
        let store = DialogueFixtureStorage(), scope = try StorageScope(environment: UUID().uuidString, account: "one")
        let first = MessageRecovery(storage: store), lease = try first.activate(scope), raw = original()
        let responder = DialogueReceiptFixture(trace: requestID, replies: [
            .lost, .response(200, try accepted(raw, digest: String(repeating: "f", count: 64)))
        ])
        let client = try fixture(recovery: first, scope: scope, responder: responder)
        _ = try await client.submit(originalUTF8: raw, lease: lease)
        let otherScope = try StorageScope(environment: scope.environment, account: "two")
        let other = MessageRecovery(storage: store), otherLease = try other.activate(otherScope)
        let foreign = try fixture(recovery: other, scope: otherScope, responder: responder)
        await #expect(throws: RecoveryError.queryOnly) { _ = try await foreign.reconcile(messageID: messageID, lease: otherLease) }
        guard case .unknown = try await client.reconcile(messageID: messageID, lease: lease) else {
            Issue.record("A mismatched digest must keep the original unresolved"); return
        }
        #expect(try client.unresolvedMessages(lease: lease).map(\.messageID) == [messageID])
        #expect(await responder.calls.count == 2)
    }
}
