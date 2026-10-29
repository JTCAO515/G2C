import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
import CJMessageHTTP
@testable import CJShell

@MainActor private final class SendStore: SecureMessageStorage {
    var value: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { value = snapshot }
}
@MainActor private final class SendCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
private actor SendServer: ClientTransport {
    var sequence = 0
    var posted: [Data] = []
    var losePost = false
    var rejectPost = false
    func rejectNextPost() { rejectPost = true }
    var postHook: (@Sendable () async -> Void)?
    func loseNextPost() { losePost = true }
    func beforePostReply(_ hook: @escaping @Sendable () async -> Void) { postHook = hook }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let trace = UUID().uuidString
        let value: [String: Any]
        if request.method == .get {
            value = ["request_id": trace, "receipt": NSNull(), "head": ["conversation_id": "chat", "generation": "g1", "last_sequence": sequence]]
        } else {
            let bytes = try await Data(collecting: body!, upTo: 10000)
            posted.append(bytes)
            if losePost { losePost = false; throw URLError(.networkConnectionLost) }
            if rejectPost {
                rejectPost = false
                var response = HTTPResponse(status: .serviceUnavailable)
                response.headerFields[.contentType] = "application/json"
                response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
                let error: [String: Any] = ["request_id": trace, "error": ["code": "MESSAGE_OUTCOME_UNKNOWN", "category": "dependency", "message_en": "Unknown", "message_zh": "未知", "outcome": "unknown", "recovery": "reconcile_original"]]
                return (response, HTTPBody(try JSONSerialization.data(withJSONObject: error)))
            }
            sequence += 1
            let original = try JSONSerialization.jsonObject(with: bytes) as! [String: Any]
            value = ["request_id": trace, "receipt": ["conversation_id": "chat", "message_id": original["message_id"]!, "generation": "g1", "sequence": sequence, "run_id": "run1", "input_sha256": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()]]
            if let postHook { self.postHook = nil; await postHook() }
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response, HTTPBody(try JSONSerialization.data(withJSONObject: value)))
    }
}

@Suite @MainActor struct AssistantMessageSendTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "message-send-" + UUID().uuidString)))
    }
    private func wait(_ predicate: () -> Bool) async {
        for _ in 0..<2000 { if predicate() { return }; await Task.yield() }
        #expect(predicate())
    }
    private func bind(shell: ShellState, state: MessageRecovery, scope: StorageScope, lease: Lease, server: SendServer) throws -> AssistantMessageHost {
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 10000, maximumResponseBytes: 10000)
        let client = MessageHTTPClient(recovery: state, scope: scope, endpoint: endpoint, credentials: SendCredentials(), interceptedTestTransport: server)
        let host = AssistantMessageHost(shell: shell)
        #expect(host.bind(.init(recovery: state, scope: scope, lease: lease, generation: shell.generation,
                               synthetic: true, isCurrent: { true }, invalidateResources: {}, sendClient: client)))
        return host
    }
    @Test func unavailableResponseKeepsOriginalUnknownAndQueryOnly() async throws {
        let shell = try shell(), recovery = MessageRecovery(storage: SendStore())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try recovery.activate(scope), server = SendServer()
        let host = try bind(shell: shell, state: recovery, scope: scope, lease: lease, server: server)
        #expect(host.selectConversationForSending("chat")); await wait { !host.isBusy }
        shell.draft = "original"; await server.rejectNextPost()
        host.sendNew(); await wait { !host.isBusy }
        #expect(host.activity == .unknown)
        #expect(host.visibleRecord?.phase == .queryRequired)
        #expect(host.canQuery && !host.canResubmit && !host.canSend)
        #expect(shell.draft == "original")
        #expect(await server.posted.count == 1)
    }
    @Test func oversizedInputIsNotReportedAsAnUnknownSubmittedAction() async throws {
        let shell = try shell(), recovery = MessageRecovery(storage: SendStore())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try recovery.activate(scope), server = SendServer()
        let host = try bind(shell: shell, state: recovery, scope: scope, lease: lease, server: server)
        #expect(host.selectConversationForSending("chat")); await wait { !host.isBusy }
        shell.draft = String(repeating: "x", count: 10001)
        host.sendNew()
        #expect(host.activity == .inputRejected && host.visibleRecord == nil)
        #expect(await server.posted.isEmpty)
        #expect(shell.draft.count == 10001)
        shell.draft = "shorter"; host.sendNew(); await wait { host.activity == .ready }
        #expect(host.visibleRecord?.phase == .accepted)
    }
    @Test func laterEditorRevisionSurvivesReceiptAndIsStored() async throws {
        let store = SendStore(), shell = try shell()
        let recovery = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try recovery.activate(scope), server = SendServer()
        let host = try bind(shell: shell, state: recovery, scope: scope, lease: lease, server: server)
        #expect(host.selectConversationForSending("chat")); await wait { !host.isBusy }
        shell.draft = "first"; host.saveDraft()
        await server.beforePostReply { await MainActor.run { shell.draft = "later edit" } }
        host.sendNew(); await wait { host.activity == .ready }
        #expect(host.visibleRecord?.phase == .accepted)
        #expect(shell.draft == "later edit")
        #expect(try recovery.draft(conversationID: "chat", lease: lease) == Data("later edit".utf8))
    }

    @Test func restoredUnknownNeedsFreshQueryConfirmationAndMatchingContext() async throws {
        let store = SendStore(), shell = try shell()
        let recovery = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try recovery.activate(scope), server = SendServer()
        let host = try bind(shell: shell, state: recovery, scope: scope, lease: lease, server: server)
        #expect(host.selectConversationForSending("chat")); await wait { !host.isBusy }
        shell.draft = "original"; host.saveDraft(); await server.loseNextPost()
        host.sendNew(); await wait { host.activity == .unknown }
        let original = try #require(host.visibleRecord)
        #expect(!host.canSend && !host.canResubmit && host.canQuery)
        host.queryOriginal(); await wait { host.activity == .ready }
        let stale = try #require(host.captureResubmission())
        #expect(!stale.requiresConfirmation)
        host.invalidate()
        let reopened = MessageRecovery(storage: store), newShell = try self.shell()
        let newLease = try reopened.activate(scope)
        let next = try bind(shell: newShell, state: reopened, scope: scope, lease: newLease, server: server)
        #expect(next.selectConversationForSending("chat")); await wait { !next.isBusy }
        #expect(!next.canSend && !next.canResubmit)
        next.queryOriginal(); await wait { next.activity == .ready }
        let context = try #require(next.captureResubmission())
        #expect(context.requiresConfirmation)
        next.resubmitOriginal(stale, confirmed: true)
        next.resubmitOriginal(context, confirmed: false)
        #expect(await server.posted.count == 1)
        next.resubmitOriginal(context, confirmed: true)
        await wait { next.activity == .ready }
        #expect(next.visibleRecord?.phase == .accepted)
        #expect(next.visibleRecord?.originalUTF8 == original.originalUTF8)
        #expect(await server.posted == [original.originalUTF8, original.originalUTF8])
    }
    @Test func sendKeepsLanguageIdentityIntentAndRestoresUnsentDraft() async throws {
        let store = SendStore()
        let recovery = MessageRecovery(storage: store)
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try recovery.activate(scope), server = SendServer()
        let shell = try shell(), host = try bind(shell: shell, state: recovery, scope: scope, lease: lease, server: server)
        #expect(!host.canSend)
        #expect(host.selectConversationForSending("chat"))
        await wait { !host.isBusy }
        shell.draft = "北京三日 / three days"; host.saveDraft()
        host.creationIntent = .considerTrip
        #expect(host.canSend)
        let generation = shell.generation
        host.sendNew()
        let original = try #require(host.visibleRecord)
        shell.selectLanguage(.chinese)
        await wait { host.activity == .ready }
        #expect(host.visibleRecord?.phase == .accepted)
        #expect(host.visibleRecord?.messageID == original.messageID)
        #expect(shell.generation == generation && shell.draft.isEmpty)
        let data = try #require(await server.posted.first)
        let input = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(input["trip_id"] is NSNull)
        #expect(input["creation_intent"] as? String == "consider_trip")
        #expect(input["conversation_id"] as? String == "chat")
        #expect(input["version"] as? String == "MESSAGE-send.1")
        host.sendNew()
        #expect(await server.posted.count == 1)
        shell.draft = "未发送草稿 / unsent"; host.saveDraft(); host.invalidate()
        let reopened = MessageRecovery(storage: store), reopenedShell = try self.shell()
        let reopenedLease = try reopened.activate(scope)
        let next = try bind(shell: reopenedShell, state: reopened, scope: scope, lease: reopenedLease, server: server)
        #expect(next.selectConversationForSending("chat"))
        await wait { !next.isBusy }
        #expect(reopenedShell.draft == "未发送草稿 / unsent")
        #expect(await server.posted.count == 1)
    }
}
