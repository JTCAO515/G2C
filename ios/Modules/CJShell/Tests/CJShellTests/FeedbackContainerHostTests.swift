import Foundation
import CryptoKit
import Testing
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJFeedbackClient
@testable import CJShell

private let feedbackTrace = "00000000-0000-4000-8000-000000000001"
private actor FeedbackHostTransport: ClientTransport {
    var replies: [Data]
    var calls: [(String, HTTPRequest.Method)] = []
    let holdFirst: Bool
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    init(_ replies: [Data], holdFirst: Bool = false) { self.replies = replies; self.holdFirst = holdFirst }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method))
        guard !replies.isEmpty else { throw FeedbackFailure.exchangeUnknown }
        let bytes = replies.removeFirst()
        if holdFirst && calls.count == 1 { held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = feedbackTrace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
    func release() { continuation?.resume(); continuation = nil }
}
@MainActor private struct FeedbackHostSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class FeedbackHostFixture {
    let feedback = FeedbackBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    let session = SessionLifecycle(persistence: FeedbackHostSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    var current: FeedbackBinding?
    var callback: (() -> Void)?
    var credentials = 0
    init() throws { operation = try session.beginTrustedSDKSave(); current = feedback }
    func observed() -> FeedbackBinding? { let old = current; let run = callback; callback = nil; run?(); return old }
    func client(_ transport: FeedbackHostTransport, store: FeedbackPendingStore? = nil) throws -> FeedbackClient {
        FeedbackClient(endpoint: try FeedbackEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 16384, maximumResponseBytes: 100_000),
            credentials: { [self] _ in credentials += 1; return "SYNTHETIC" }, currentBinding: { [self] in observed() },
            pendingStore: store, interceptedTransport: transport)
    }
    func binding(shell: ShellState, client: FeedbackClient, context: FeedbackContext? = nil, revision: UUID? = nil) -> FeedbackContainerBinding {
        FeedbackContainerBinding(client: client, feedback: feedback, shellGeneration: shell.generation, session: session,
            sessionOperation: operation, context: context, answerRevision: revision, synthetic: true, currentBinding: { [self] in observed() })
    }
}
@Suite @MainActor struct FeedbackContainerHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]); return url
    }
    private func store(_ f: FeedbackHostFixture, directory: URL, key: @escaping () throws -> SymmetricKey) throws -> FeedbackPendingStore {
        try FeedbackPendingStore(directory: directory, maximumBytes: 100_000, maximumRecords: 20,
            namespace: .init(environment: f.feedback.environment, account: f.feedback.account, purpose: .localFeedbackPendingV1), keyID: UUID(), key: key)
    }
    private func pending(linked: Bool = false, id: String = "original-feedback") throws -> FeedbackPending {
        try FeedbackPending(problem: "Voluntary problem / 自愿问题", expectation: "Expected / 期望",
            context: linked ? FeedbackContext(messageID: "message-e\u{301}", runID: "run-A") : nil, actionID: id)
    }
    private func receipt(_ original: FeedbackPending, wrongHash: Bool = false) throws -> Data {
        let action = try original.action()
        let source: Any = action.references.isEmpty ? NSNull() : [
            "message_id": "message-e\u{301}", "run_id": "run-A", "conversation_id": "synthetic-conversation", "generation": "synthetic-generation",
            "message_sequence": 1, "message_input_sha256": String(repeating: "b", count: 64), "run_status_at_read": "running", "event_highwater_at_read": 4]
        return try JSONSerialization.data(withJSONObject: ["request_id": feedbackTrace, "receipt": [
            "action_id": original.actionID, "input_sha256": wrongHash ? String(repeating: "0", count: 64) : original.inputSHA256,
            "submitted_at": "2026-10-22T10:00:00Z", "status": "submitted", "message_en": "Feedback submitted.", "message_zh": "反馈已提交。", "source": source]])
    }
    private func wait(_ t: FeedbackHostTransport) async {
        for _ in 0..<10000 { if await t.held { return }; await Task.yield() }; Issue.record("Request did not reach hold")
    }
    @Test(arguments: ["answer-problem", "answer-expectation", "answer-association", "general-problem", "general-expectation"])
    func acceptedEditorCallbackRetiresOldPreparationThroughHost(scenario: String) async throws {
        let s = try shell(), f = try FeedbackHostFixture(), t = FeedbackHostTransport([]), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), store = try store(f, directory: dir) { key }
        let answer = scenario.hasPrefix("answer-")
        #expect(s.apply(.init(assistantBody: "Synthetic answer; do not copy"), for: s.generation))
        let host = FeedbackContainerHost(shell: s, surface: answer ? .answer : .general)
        let context = answer ? try FeedbackContext(messageID: "message-e\u{301}", runID: "run-A") : nil
        #expect(host.bind(f.binding(shell: s, client: try f.client(t, store: store), context: context,
                                   revision: answer ? s.assistantContentRevision : nil)))
        let entry = host.captureEntry(), model = try #require(host.presentation(for: entry))
        model.edit(problem: "Original problem", expectation: "Original expectation")
        if answer { model.associateContext(true) }
        f.callback = {
            if scenario.hasSuffix("-problem") { model.edit(problem: "New problem", expectation: model.expectation) }
            else if scenario.hasSuffix("-expectation") { model.edit(problem: model.problem, expectation: "New expectation") }
            else { model.associateContext(false) }
        }
        let stale = model.prepareSubmit()
        #expect(stale == nil, "Accepted callback edit must retire old frozen preparation")
        #expect(model.original == nil, "No stale original may be presented beside the new draft")
        guard stale == nil else { return } // do not dispatch the known-bad original in the before run
        let expectedProblem = scenario.hasSuffix("-problem") ? "New problem" : "Original problem"
        let expectedExpectation = scenario.hasSuffix("-expectation") ? "New expectation" : "Original expectation"
        let expectedAssociation = answer && !scenario.hasSuffix("-association")
        #expect(model.problem == expectedProblem && model.expectation == expectedExpectation && model.includeContext == expectedAssociation)
        #expect(model.canEdit && host.presentation(for: entry) === model)
        #expect(try store.pending().isEmpty); #expect(await t.calls.isEmpty)
        // A new explicit preparation is allowed only because the rejected one never persisted/dispatched.
        let next = try #require(model.prepareSubmit()), frozen = try #require(model.original)
        let action = try frozen.action()
        #expect(action.problem == expectedProblem && action.expectation == expectedExpectation)
        #expect(action.references.isEmpty == !expectedAssociation)
        model.edit(problem: "Late edit", expectation: "Late expectation"); model.associateContext(!expectedAssociation)
        #expect(model.original?.originalUTF8 == frozen.originalUTF8 && model.problem == action.problem && model.expectation == action.expectation)
        host.invalidate(); await model.perform(next)
        #expect(try store.pending().isEmpty); #expect(await t.calls.isEmpty)
    }
    @Test func defaultsUnavailableAndPublicClientCannotSubmit() throws {
        let s = try shell(), host = FeedbackContainerHost(shell: s, surface: .general), f = try FeedbackHostFixture()
        #expect(host.captureEntry() == nil && host.presentation(for: nil) == nil)
        let client = FeedbackClient(endpoint: try FeedbackEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 16384, maximumResponseBytes: 100_000),
            credentials: { _ in Issue.record("Credential requested"); return nil }, currentBinding: { f.feedback }, session: f.session,
            sessionOperation: f.operation, pendingStore: nil, liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
        #expect(host.bind(f.binding(shell: s, client: client)))
        let model = try #require(host.presentation(for: host.captureEntry()))
        model.edit(problem: "Voluntary", expectation: "")
        #expect(!model.submissionAvailable && model.prepareSubmit() == nil && model.original == nil)
    }
    @Test func answerAndGeneralStartEmptyWithExplicitOptInOnly() throws {
        let s = try shell(), f = try FeedbackHostFixture(), t = FeedbackHostTransport([])
        #expect(s.apply(.init(assistantBody: "SYNTHETIC TRANSCRIPT MUST NOT PREFILL"), for: s.generation))
        let answer = FeedbackContainerHost(shell: s, surface: .answer), general = FeedbackContainerHost(shell: s, surface: .general)
        let context = try FeedbackContext(messageID: "message-e\u{301}", runID: "run-A")
        let answerClient = try f.client(t), generalClient = try f.client(t)
        #expect(!general.bind(f.binding(shell: s, client: generalClient, context: context)))
        #expect(!answer.bind(f.binding(shell: s, client: answerClient, context: context, revision: UUID())))
        #expect(answer.bind(f.binding(shell: s, client: answerClient, context: context, revision: s.assistantContentRevision)))
        #expect(!general.bind(f.binding(shell: s, client: answerClient))) // no cross-surface invalidation through a shared client
        #expect(general.bind(f.binding(shell: s, client: generalClient)))
        let am = try #require(answer.presentation(for: answer.captureEntry())), gm = try #require(general.presentation(for: general.captureEntry()))
        #expect(am.problem.isEmpty && am.expectation.isEmpty && !am.includeContext)
        #expect(gm.problem.isEmpty && gm.context == nil && !gm.includeContext)
        am.associateContext(true); gm.associateContext(true)
        #expect(am.includeContext && !gm.includeContext)
        #expect(Data(try #require(am.context).messageID.utf8) == Data(context.messageID.utf8))
        #expect(am.context?.runID == "run-A")
        am.edit(problem: "Chosen text", expectation: "Chosen expectation")
        s.selectLanguage(.chinese)
        #expect(am.problem == "Chosen text" && gm.problem.isEmpty)
    }
    @Test func newAnswerRetiresQueuedSourceWithoutClearingGeneralDraft() async throws {
        let s = try shell(), f = try FeedbackHostFixture(), t = FeedbackHostTransport([]), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), store = try store(f, directory: dir) { key }
        #expect(s.apply(.init(assistantBody: "A"), for: s.generation))
        let answer = FeedbackContainerHost(shell: s, surface: .answer), general = FeedbackContainerHost(shell: s, surface: .general)
        #expect(answer.bind(f.binding(shell: s, client: try f.client(t, store: store), context: try FeedbackContext(messageID: "message-A"), revision: s.assistantContentRevision)))
        #expect(general.bind(f.binding(shell: s, client: try f.client(t))))
        let oldEntry = answer.captureEntry(), old = try #require(answer.presentation(for: oldEntry))
        let gm = try #require(general.presentation(for: general.captureEntry()))
        old.edit(problem: "Voluntary A", expectation: ""); old.associateContext(true)
        gm.edit(problem: "General draft", expectation: "")
        let work = try #require(old.prepareSubmit()) // internal intercepted capability only; never dispatched
        #expect(s.apply(.init(assistantBody: "B"), for: s.generation))
        #expect(answer.presentation(for: oldEntry) == nil && old.problem.isEmpty && old.context == nil)
        #expect(gm.problem == "General draft" && gm.context == nil)
        #expect(answer.bind(f.binding(shell: s, client: try f.client(t), context: try FeedbackContext(messageID: "message-B"), revision: s.assistantContentRevision)))
        await old.perform(work)
        let newer = try #require(answer.presentation(for: answer.captureEntry()))
        #expect(answer.presentation(for: oldEntry) == nil && newer.context?.messageID == "message-B" && newer.problem.isEmpty)
        #expect(await t.calls.isEmpty); #expect(try store.pending().isEmpty)
    }
    @Test func sourceChangeDuringBindingCallbackRejectsOldEntry() throws {
        let s = try shell(), f = try FeedbackHostFixture(), t = FeedbackHostTransport([])
        #expect(s.apply(.init(assistantBody: "A"), for: s.generation))
        let host = FeedbackContainerHost(shell: s, surface: .answer)
        let value = f.binding(shell: s, client: try f.client(t), context: try FeedbackContext(messageID: "message-A"), revision: s.assistantContentRevision)
        f.callback = { _ = s.apply(.init(assistantBody: "B"), for: s.generation) }
        #expect(!host.bind(value) && host.captureEntry() == nil)
    }
    @Test func answerChangeInsidePrepareCallbackCannotFreezeOldAssociation() async throws {
        let s = try shell(), f = try FeedbackHostFixture(), t = FeedbackHostTransport([]), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), store = try store(f, directory: dir) { key }
        #expect(s.apply(.init(assistantBody: "A"), for: s.generation))
        let host = FeedbackContainerHost(shell: s, surface: .answer)
        #expect(host.bind(f.binding(shell: s, client: try f.client(t, store: store), context: try FeedbackContext(messageID: "message-A"), revision: s.assistantContentRevision)))
        let entry = host.captureEntry(), model = try #require(host.presentation(for: entry))
        model.edit(problem: "Only voluntary text", expectation: ""); model.associateContext(true)
        f.callback = { _ = s.apply(.init(assistantBody: "B"), for: s.generation) }
        #expect(model.prepareSubmit() == nil)
        #expect(host.presentation(for: entry) == nil && model.original == nil && model.problem.isEmpty)
        #expect(try store.pending().isEmpty); #expect(await t.calls.isEmpty)
    }
    @Test(arguments: [false, true]) func originalRecoveryIsExplicitAndSubmittedOnly(linked: Bool) async throws {
        let s = try shell(), f = try FeedbackHostFixture(), host = FeedbackContainerHost(shell: s, surface: .general), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), store = try store(f, directory: dir) { key }, original = try pending(linked: linked)
        try store.append(original)
        let t = FeedbackHostTransport([try receipt(original)])
        #expect(host.bind(f.binding(shell: s, client: try f.client(t, store: store))))
        let model = try #require(host.presentation(for: host.captureEntry()))
        #expect(model.context == nil && model.problem.isEmpty)
        let reload = try #require(model.prepareReload()); await model.perform(reload)
        model.selectPending(actionID: original.actionID)
        #expect(model.original?.originalUTF8 == original.originalUTF8 && !model.canEdit)
        let query = try #require(model.prepareQuery()); await model.perform(query)
        #expect(model.state == .submitted && model.receipt?.status == .submitted)
        #expect(model.receipt?.input_sha256 == original.inputSHA256 && model.context == nil)
        if linked {
            guard case .FeedbackSourceObservation(let source) = model.receipt?.source else { Issue.record("Missing original source"); return }
            #expect(source.run_status_at_read == .running && source.event_highwater_at_read == 4)
        } else {
            guard case .case2 = model.receipt?.source else { Issue.record("General feedback acquired source"); return }
        }
        #expect(try store.pending().first?.originalUTF8 == original.originalUTF8)
        #expect(await t.calls.allSatisfy { $0.1 == .get }); #expect(await t.calls.count == 1)
    }
    @Test(arguments: ["null", "wrong-hash", "cancel"])
    func uncertainQueryRetainsOriginalWithoutResend(mode: String) async throws {
        let s = try shell(), f = try FeedbackHostFixture(), host = FeedbackContainerHost(shell: s, surface: .general), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), store = try store(f, directory: dir) { key }, original = try pending()
        try store.append(original)
        let bytes = mode == "wrong-hash" ? try receipt(original, wrongHash: true) : Data("{\"request_id\":\"\(feedbackTrace)\",\"receipt\":null}".utf8)
        let t = FeedbackHostTransport([bytes], holdFirst: mode == "cancel")
        #expect(host.bind(f.binding(shell: s, client: try f.client(t, store: store))))
        let model = try #require(host.presentation(for: host.captureEntry()))
        await model.perform(try #require(model.prepareReload())); model.selectPending(actionID: original.actionID)
        let query = try #require(model.prepareQuery()), task = Task { await model.perform(query) }
        if mode == "cancel" { await wait(t); task.cancel(); await t.release() }; await task.value
        #expect([FeedbackState.unknown, .recoveryUnavailable].contains(model.state) && !model.state.isBusy && model.receipt == nil)
        #expect(model.original?.originalUTF8 == original.originalUTF8 && model.prepareSubmit() == nil)
        #expect(try store.pending().first?.originalUTF8 == original.originalUTF8)
        #expect(await t.calls.count == 1)
    }
    @Test(arguments: [false, true]) func accountOrBackgroundLateQueryCannotReachNewSurface(background: Bool) async throws {
        let s = try shell(), a = try FeedbackHostFixture(), b = try FeedbackHostFixture(), host = FeedbackContainerHost(shell: s, surface: .general), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), store = try store(a, directory: dir) { key }, original = try pending()
        try store.append(original)
        let ta = FeedbackHostTransport([try receipt(original)], holdFirst: true)
        #expect(host.bind(a.binding(shell: s, client: try a.client(ta, store: store))))
        let oldEntry = host.captureEntry(), old = try #require(host.presentation(for: oldEntry))
        await old.perform(try #require(old.prepareReload())); old.selectPending(actionID: original.actionID)
        let work = try #require(old.prepareQuery()), task = Task { await old.perform(work) }; await wait(ta)
        if background { host.suspendForBackground() } else { s.invalidateIdentity() }
        #expect(old.problem.isEmpty && old.original == nil && host.presentation(for: oldEntry) == nil)
        s.messageBindingBlocked = false // explicit synthetic root renewal only
        let tb = FeedbackHostTransport([])
        #expect(host.bind(b.binding(shell: s, client: try b.client(tb))))
        let newer = try #require(host.presentation(for: host.captureEntry())); newer.edit(problem: "B private", expectation: "")
        await ta.release(); await task.value
        #expect(newer.problem == "B private" && newer.receipt == nil && host.presentation(for: oldEntry) == nil)
        #expect(try store.pending().first?.originalUTF8 == original.originalUTF8); #expect(await tb.calls.isEmpty)
    }
    @Test func missingStoreOrKeyIsRecoveryUnavailable() async throws {
        let s = try shell(), f = try FeedbackHostFixture(), host = FeedbackContainerHost(shell: s, surface: .general), t = FeedbackHostTransport([])
        #expect(host.bind(f.binding(shell: s, client: try f.client(t))))
        let first = try #require(host.presentation(for: host.captureEntry()))
        await first.perform(try #require(first.prepareReload())); #expect(first.state == .recoveryUnavailable)
        host.invalidate()
        let dir = try directory(); defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256); var available = true
        let store = try store(f, directory: dir) { guard available else { throw FeedbackFailure.keyUnavailable }; return key }
        try store.append(pending()); available = false
        #expect(host.bind(f.binding(shell: s, client: try f.client(t, store: store))))
        let second = try #require(host.presentation(for: host.captureEntry()))
        await second.perform(try #require(second.prepareReload())); #expect(second.state == .recoveryUnavailable)
        #expect(f.credentials == 0); #expect(await t.calls.isEmpty)
    }
}
