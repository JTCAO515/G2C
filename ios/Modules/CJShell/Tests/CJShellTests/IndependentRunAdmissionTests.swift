import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageClient
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJRunClient
@testable import CJShell

private let runTrace = "00000000-0000-4000-8000-000000000001"
@MainActor private final class RunMessageStore: SecureMessageStorage {
    var saved: Snapshot?
    var writes = 0
    func load(scope: StorageScope) throws -> Snapshot? { saved }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { saved = snapshot; writes += 1 }
}
@MainActor private struct RunSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class RunMessageCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "SYNTHETIC" }
}
private actor RunHostWire: ClientTransport {
    var receipts: [Data] = []
    var snapshots: [Data] = []
    var calls: [(String, HTTPRequest.Method, String)] = []
    var holdNextRun = false
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    func addReceipt(_ bytes: Data) { receipts.append(bytes) }
    func addSnapshot(_ bytes: Data) { snapshots.append(bytes) }
    func hold() { holdNextRun = true }
    func release() { continuation?.resume(); continuation = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method, request.path ?? ""))
        #expect(request.method == .get && body == nil)
        let bytes: Data
        if operationID == "queryMessageReceipt", !receipts.isEmpty { bytes = receipts.removeFirst() }
        else if operationID == "getRunDisplaySnapshot", !snapshots.isEmpty {
            bytes = snapshots.removeFirst()
            if holdNextRun { holdNextRun = false; held = true; await withCheckedContinuation { continuation = $0 } }
        } else { throw RunDisplayFailure.unavailable }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = runTrace
        response.headerFields[.cacheControl] = "no-store"
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
}
@MainActor private final class RunHostFixture {
    let shell: ShellState
    let messages: AssistantMessageHost
    let host: RunContainerHost
    let store = RunMessageStore()
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let wire = RunHostWire()
    let session = SessionLifecycle(persistence: RunSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let messageClient: MessageHTTPClient
    let model: RunDisplayModel
    var messageCurrent = true
    var admission = true
    var messageCallback: (() -> Void)?
    var admissionCallback: (() -> Void)?
    init(shell: ShellState) throws {
        self.shell = shell
        messages = AssistantMessageHost(shell: shell); host = RunContainerHost(shell: shell)
        recovery = MessageRecovery(storage: store)
        scope = try StorageScope(environment: UUID().uuidString, account: "synthetic")
        lease = try recovery.activate(scope)
        operation = try session.beginTrustedSDKSave()
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 4096, maximumResponseBytes: 16384)
        messageClient = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint, credentials: RunMessageCredentials(), interceptedTestTransport: wire)
        let operation = operation
        model = try RunDisplayModel(endpoint: endpoint, maximumMessageIDBytes: 1024, maximumTextBytes: 8192,
            credentials: { captured in #expect(captured == operation); return "SYNTHETIC" }, transport: wire)
    }
    func receipt(_ id: String, hash: String) -> Components.Schemas.MessageReceipt {
        .init(message_id: id, conversation_id: "chat-e\u{301}", generation: "generation", run_id: "run-" + id, sequence: 7, input_sha256: hash)
    }
    func stage(_ id: String) throws {
        let bytes = try JSONSerialization.data(withJSONObject: ["message_id": id, "conversation_id": "chat-e\u{301}", "text": "Synthetic user input"], options: [.sortedKeys])
        try recovery.stage(messageID: id, originalUTF8: bytes, lease: lease)
    }
    func accept(_ id: String) async throws {
        try stage(id)
        _ = try recovery.beginSubmission(messageID: id, lease: lease) // synthetic unknown dispatch; no POST
        let action = try #require(try recovery.action(messageID: id, lease: lease))
        let value = receipt(id, hash: action.inputSHA256)
        let json = "{\"request_id\":\"\(runTrace)\",\"receipt\":\(String(decoding: try JSONEncoder().encode(value), as: UTF8.self))}"
        await wire.addReceipt(Data(json.utf8))
        guard case .accepted = try await messageClient.query(messageID: id, lease: lease) else { Issue.record("Canonical MESSAGE query not accepted"); return }
    }
    func bind(_ id: String?) throws {
        let value = AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
            conversationID: "chat-e\u{301}", messageID: id, synthetic: true,
            isCurrent: { [self] in let callback = messageCallback; messageCallback = nil; callback?(); return messageCurrent },
            invalidateResources: {}, queryOriginal: { [self] id, lease in _ = try await messageClient.query(messageID: id, lease: lease) })
        #expect(messages.bind(value))
        let config = RunContainerConfiguration(model: model, session: session, operation: operation, generation: shell.generation,
            synthetic: true, isCurrent: { [self] in let callback = admissionCallback; admissionCallback = nil; callback?(); return admission })
        #expect(host.configure(config))
        host.setForeground(true)
    }
    func selectMessage(_ id: String) throws {
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        let item = try #require(projection.actions.first { Data($0.messageID.utf8) == Data(id.utf8) })
        #expect(messages.selectAction(item, from: projection))
    }
    func snapshot(_ id: String, status: String = "running", text: String = "Verbatim **partial** e\u{301} 中文", highwater: Int = 2) throws -> Data {
        try JSONSerialization.data(withJSONObject: ["request_id": runTrace, "snapshot": [
            "message_id": id, "conversation_id": "chat-e\u{301}", "generation": "generation", "run_id": "run-" + id,
            "message_sequence": 7, "event_highwater": highwater, "status": status, "text": text,
            "text_state": status == "completed" ? "complete" : "partial"]])
    }
    func read() async { let work = model.prepareRead(); await model.perform(work) }
}

@Suite @MainActor struct IndependentRunAdmissionTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    @Test func loadedAccessMustRecheckAdmissionAfterMessageCallback() async throws {
        let f = try RunHostFixture(shell: shell())
        try await f.accept("A"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("A")); await f.read()
        guard case .loaded = f.model.state else { Issue.record("Fixture must load canonical original first"); return }
        f.messageCallback = { f.admission = false }
        let observed = f.model.state
        #expect(!f.admission)
        if case .loaded = observed { Issue.record("Loaded private text escaped after MESSAGE callback revoked current host admission") }
    }
    @Test func lastMessageCallbackCannotDispatchAfterAdmissionIsFalse() async throws {
        let f = try RunHostFixture(shell: shell())
        try await f.accept("A"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        let work = try #require(f.model.prepareRead())
        await f.wire.addSnapshot(try f.snapshot("A"))
        var calls = 0
        func revokeOnLastValidation() {
            calls += 1
            if calls < 4 { f.messageCallback = revokeOnLastValidation }
            else { f.admission = false }
        }
        f.messageCallback = revokeOnLastValidation
        await f.model.perform(work)
        #expect(calls == 4 && !f.admission)
        let operations = await f.wire.calls.map(\.0)
        #expect(operations == ["queryMessageReceipt"], "RUN GET dispatched after its last MESSAGE callback made current admission false")
    }
}
