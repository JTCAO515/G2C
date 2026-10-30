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
    func bind(_ id: String?,answerFormat: RunAnswerFormat = .plainText) throws {
        let value = AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
            conversationID: "chat-e\u{301}", messageID: id, synthetic: true,
            isCurrent: { [self] in let callback = messageCallback; messageCallback = nil; callback?(); return messageCurrent },
            invalidateResources: {}, queryOriginal: { [self] id, lease in _ = try await messageClient.query(messageID: id, lease: lease) })
        #expect(messages.bind(value))
        let config = RunContainerConfiguration(model: model, session: session, operation: operation, generation: shell.generation,
            synthetic: true,answerFormat:answerFormat, isCurrent: { [self] in let callback = admissionCallback; admissionCallback = nil; callback?(); return admission })
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
@Suite @MainActor struct RunContainerHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func wait(_ wire: RunHostWire) async {
        for _ in 0..<10000 { if await wire.held { return }; await Task.yield() }; Issue.record("Run request not held")
    }
    @Test func defaultsAndUnacceptedRecordsCannotCreateSource() async throws {
        let s = try shell(), h = RunContainerHost(shell: s), messages = AssistantMessageHost(shell: s)
        #expect(h.displayModel == nil && messages.captureAcceptedRunReceipt() == nil)
        #expect(!h.selectAcceptedMessage(from: messages))
        let f = try RunHostFixture(shell: s); try f.stage("staged"); try f.bind("staged")
        #expect(f.messages.captureAcceptedRunReceipt() == nil && !f.host.selectAcceptedMessage(from: f.messages))
        #expect(f.host.sourceUnavailable && f.model.prepareRead() == nil)
        #expect(await f.wire.calls.isEmpty)
    }
    @Test(arguments: ["queued", "running", "completed", "failed", "cancelled", "context_invalid", "unknown"])
    func canonicalMessageReceiptFeedsOnlyOriginalRead(status: String) async throws {
        let id = "m/+%e\u{301}中文", f = try RunHostFixture(shell: shell())
        try await f.accept(id); try f.bind(id)
        let origin = try #require(f.messages.captureAcceptedRunReceipt())
        #expect(!String(reflecting: origin).contains(id))
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        let before = try #require(try f.recovery.action(messageID: id, lease: f.lease)), writes = f.store.writes
        let text = status == "queued" ? "" : "Verbatim **partial** e\u{301} 中文"
        await f.wire.addSnapshot(try f.snapshot(id, status: status, text: text, highwater: status == "queued" ? 0 : 2))
        let captured = f.model.prepareRead(); await f.model.perform(captured)
        guard case .loaded(let value) = f.model.state else { Issue.record("Original run unavailable"); return }
        #expect(value.snapshot.status.rawValue == status && Data(value.snapshot.text.utf8) == Data(text.utf8))
        #expect((value.snapshot.text_state == .complete) == (status == "completed"))
        #expect(f.host.isShowingOriginal && f.store.writes == writes)
        #expect(try f.recovery.action(messageID: id, lease: f.lease) == before)
        let calls = await f.wire.calls
        #expect(calls.map(\.0) == ["queryMessageReceipt", "getRunDisplaySnapshot"] && calls.allSatisfy { $0.1 == .get })
        let items = try #require(URLComponents(string: calls.last!.2)?.queryItems)
        #expect(items.count == 1 && items.first?.name == "message_id")
        #expect(Data(try #require(items.first?.value).utf8) == Data(id.utf8))
        f.shell.selectLanguage(.chinese); #expect(f.host.displayModel === f.model)
    }
    @Test(arguments: ["malformed", "hash", "notObserved"])
    func receiptPayloadMustBeCanonicalAcceptedAndMatchOriginal(mode: String) throws {
        let f = try RunHostFixture(shell: shell()); try f.stage("A")
        _ = try f.recovery.beginSubmission(messageID: "A", lease: f.lease)
        let op = try f.recovery.beginQuery(messageID: "A", lease: f.lease)
        if mode == "notObserved" { try f.recovery.observeNotObserved(op) }
        else {
            let record = try #require(try f.recovery.action(messageID: "A", lease: f.lease))
            let bytes = mode == "malformed" ? Data("not a receipt".utf8) : try JSONEncoder().encode(f.receipt("A", hash: String(repeating: "0", count: 64)))
            try f.recovery.observeReceipt(op, messageID: "A", inputSHA256: record.inputSHA256, receipt: bytes)
        }
        try f.bind("A")
        #expect(f.messages.captureAcceptedRunReceipt() == nil && !f.host.selectAcceptedMessage(from: f.messages))
        #expect(f.model.prepareRead() == nil)
    }
    @Test func queuedASelectionAndReceiptRetirementCannotReadB() async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A"); try await f.accept("B"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages)); let oldOrigin = try #require(f.messages.captureAcceptedRunReceipt())
        let oldWork = f.model.prepareRead()
        try f.selectMessage("B")
        #expect(!oldOrigin.isCurrent()); #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.model.perform(oldWork); #expect(await f.wire.calls.count == 2)
        await f.wire.addSnapshot(try f.snapshot("B")); await f.read()
        guard case .loaded(let value) = f.model.state else { Issue.record("B not loaded"); return }
        #expect(value.snapshot.message_id == "B")
    }
    @Test(arguments: [1, 2, 3, 4]) func selectionCallbackCannotAdoptNewMessageUnderOldCapture(trigger: Int) async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A"); try await f.accept("B"); try f.bind("A")
        var checks = 0
        func replaceOnCheck() {
            checks += 1
            if checks < trigger { f.messageCallback = replaceOnCheck }
            else { try! f.selectMessage("B") }
        }
        f.messageCallback = replaceOnCheck
        #expect(!f.host.selectAcceptedMessage(from: f.messages))
        #expect(f.model.prepareRead() == nil && !f.host.sourceUnavailable)
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("B")); await f.read()
        guard case .loaded(let value) = f.model.state else { Issue.record("B not available"); return }
        #expect(value.snapshot.message_id == "B")
    }
    @Test func canonicalPrepareReentryDuringSelectIsNotClearedByOldHostReturn() async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        var checks = 0
        var newer: RunDisplayWork?
        func hook() {
            checks += 1
            if checks == 1 { f.admissionCallback = hook }
            else { newer = f.model.prepareRead() }
        }
        f.admissionCallback = hook
        #expect(!f.host.selectAcceptedMessage(from: f.messages)) // outer canonical selection was displaced
        let work = try #require(newer)
        if case .loading = f.model.state {} else { Issue.record("Old host return cleared newer prepared read") }
        #expect(!f.host.sourceUnavailable)
        await f.wire.addSnapshot(try f.snapshot("A"))
        await f.model.perform(work)
        guard case .loaded(let value) = f.model.state else { Issue.record("Newer captured work could not run"); return }
        #expect(value.snapshot.message_id == "A")
        #expect(await f.wire.calls.map(\.0) == ["queryMessageReceipt", "getRunDisplaySnapshot"])
    }
    @Test(arguments: ["lease", "session", "background"])
    func finalAdmissionCallbackCannotKeepRetiredOriginalLoaded(change: String) async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("A")); await f.read()
        guard case .loaded = f.model.state else { Issue.record("Setup not loaded"); return }
        f.messageCallback = {
            f.admissionCallback = {
                switch change {
                case "lease": f.recovery.invalidate()
                case "session": try! f.session.clear()
                default: f.host.setForeground(false)
                }
            }
        }
        let observed = f.model.state
        if case .loaded = observed { Issue.record("Final admission callback retired the source but old text remained visible") }
        #expect(await f.wire.calls.map(\.0) == ["queryMessageReceipt", "getRunDisplaySnapshot"])
    }
    @Test(arguments: [false, true])
    func finalAdmissionCallbackPreservesNewerPreparedWork(replaceSource: Bool) async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A")
        if replaceSource { try await f.accept("B") }
        try f.bind("A"); #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("A")); await f.read()
        var newer: RunDisplayWork?
        f.messageCallback = {
            f.admissionCallback = {
                if replaceSource {
                    try! f.selectMessage("B")
                    #expect(f.host.selectAcceptedMessage(from: f.messages))
                }
                newer = f.model.prepareRead()
            }
        }
        let oldObservation = f.model.state
        if case .loaded = oldObservation { Issue.record("Old observation survived newer prepared work") }
        let work = try #require(newer)
        if case .loading = f.model.state {} else { Issue.record("Old cleanup retired newer work") }
        let selectedID = replaceSource ? "B" : "A"
        await f.wire.addSnapshot(try f.snapshot(selectedID, status: "completed", highwater: 3))
        await f.model.perform(work)
        guard case .loaded(let result) = f.model.state else { Issue.record("Newer work did not remain executable"); return }
        #expect(result.snapshot.message_id == selectedID && result.snapshot.status == .completed)
    }
    @Test func lateAResultCannotOverwriteSelectedB() async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A"); try await f.accept("B"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("A")); await f.wire.hold()
        let old = f.model.prepareRead(); let task = Task { await f.model.perform(old) }; await wait(f.wire)
        try f.selectMessage("B"); #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("B", status: "completed")); await f.read()
        await f.wire.release(); await task.value
        guard case .loaded(let value) = f.model.state else { Issue.record("B overwritten"); return }
        #expect(value.snapshot.message_id == "B" && value.snapshot.status == .completed)
    }
    @Test func backgroundRetiresOldWorkAndRequiresExplicitReselection() async throws {
        let f = try RunHostFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages)); let old = f.model.prepareRead()
        f.host.setForeground(false); #expect(f.host.displayModel == nil)
        await f.model.perform(old); #expect(await f.wire.calls.count == 1)
        f.host.setForeground(true); #expect(f.model.prepareRead() == nil)
        #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("A")); await f.read()
        guard case .loaded = f.model.state else { Issue.record("Explicit resumed read failed"); return }
    }
    @Test func accountAndSessionRetirementFailClosedWithoutMutatingNewContext() async throws {
        let s = try shell(), f = try RunHostFixture(shell: s); try await f.accept("A"); try f.bind("A")
        #expect(f.host.selectAcceptedMessage(from: f.messages)); let old = f.model.prepareRead()
        s.invalidateIdentity(); #expect(f.host.displayModel == nil && f.messages.captureAcceptedRunReceipt() == nil)
        s.messageBindingBlocked = false // synthetic renewed root, not a product authority
        let b = try RunHostFixture(shell: s); try await b.accept("B"); try b.bind("B")
        #expect(b.host.selectAcceptedMessage(from: b.messages))
        await f.model.perform(old); #expect(await f.wire.calls.count == 1)
        await b.wire.addSnapshot(try b.snapshot("B")); await b.read()
        try b.session.clear(); #expect(b.host.displayModel == nil && b.model.prepareRead() == nil)
        #expect(await b.wire.calls.count == 2)
    }
    @Test func failedReadDoesNotPublishOldBodyAsFallbackOrAppend() async throws {
        let s = try shell(), f = try RunHostFixture(shell: s)
        #expect(s.apply(.init(assistantBody: "Existing unrelated answer"), for: s.generation))
        try await f.accept("A"); try f.bind("A"); #expect(f.host.selectAcceptedMessage(from: f.messages))
        await f.wire.addSnapshot(try f.snapshot("A")); await f.read()
        await f.wire.addSnapshot(try f.snapshot("A", text: "contradictory", highwater: 1)); await f.read()
        guard case .unavailable = f.model.state else { Issue.record("Old answer still published"); return }
        #expect(f.host.isShowingOriginal && s.assistantBody == "Existing unrelated answer")
        // AssistantShell hides its plain-body/old Feedback entry while original RUN mode is active.
    }
}


extension RunContainerHostTests {
    @Test func explicitPlaceFormatProjectsOnlyTheProtectedOriginalAndRetiresOnAdmissionLoss() async throws {
        let f = try RunHostFixture(shell:shell());try await f.accept("A");try f.bind("A",answerFormat:.placeToolV1)
        #expect(f.host.selectAcceptedMessage(from:f.messages))
        let text = "{\"version\":\"TOOL-answer.1\",\"data_origin\":\"synthetic\",\"text_zh\":\"合成说明\",\"text_en\":\"Synthetic explanation\"}\n"
        await f.wire.addSnapshot(try f.snapshot("A",status:"completed",text:text))
        await f.model.perform(f.model.prepareRead())
        guard case .loaded(let value) = f.host.placeProjection else { Issue.record("place projection missing");return }
        #expect(value.answer?.english == "Synthetic explanation" && value.outputs.isEmpty)
        f.shell.selectLanguage(.chinese)
        guard case .loaded(let same) = f.host.placeProjection else { Issue.record("language replaced original source");return }
        #expect(same.originalUTF8 == value.originalUTF8)
        f.admission = false
        guard case .unavailable = f.host.placeProjection else { Issue.record("retired admission exposed place data");return }
        #expect(f.host.answerFormat == nil)
    }
    @Test func malformedPlacePayloadIsUnavailableInsteadOfPlainTextFallback() async throws {
        let f = try RunHostFixture(shell:shell());try await f.accept("A");try f.bind("A",answerFormat:.placeToolV1)
        #expect(f.host.selectAcceptedMessage(from:f.messages))
        await f.wire.addSnapshot(try f.snapshot("A",status:"completed",text:"{\"version\":\"TOOL-answer.9\"}\n"))
        await f.model.perform(f.model.prepareRead())
        guard case .loaded = f.model.state,case .unavailable = f.host.placeProjection else { Issue.record("unknown place payload accepted");return }
    }
    @Test func reentrantSelectionRetirementCannotReturnPreviousPlaceProjection() async throws {
        let f = try RunHostFixture(shell:shell());try await f.accept("A");try await f.accept("B");try f.bind("A",answerFormat:.placeToolV1)
        #expect(f.host.selectAcceptedMessage(from:f.messages))
        await f.wire.addSnapshot(try f.snapshot("A",status:"completed",text:"{\"version\":\"TOOL-answer.1\",\"data_origin\":\"synthetic\",\"text_zh\":\"A原文\",\"text_en\":\"A original\"}\n"))
        await f.model.perform(f.model.prepareRead())
        f.admissionCallback = { do { try f.selectMessage("B") } catch { Issue.record(error) } }
        guard case .unavailable = f.host.placeProjection else { Issue.record("A projection survived B selection");return }
    }
}
