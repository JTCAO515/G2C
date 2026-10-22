import Foundation
import CryptoKit
import Testing
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJNeedsClient
@testable import CJShell

private let needsTrace = "00000000-0000-4000-8000-000000000001"
private actor NeedsHostTransport: ClientTransport {
    var replies: [Data]
    var calls: [(String, HTTPRequest.Method, String)] = []
    let holdFirst: Bool
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    init(_ replies: [Data], holdFirst: Bool = false) { self.replies = replies; self.holdFirst = holdFirst }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method, request.path ?? ""))
        guard !replies.isEmpty else { throw NeedsFailure.exchangeUnknown }
        let bytes = replies.removeFirst()
        if holdFirst && calls.count == 1 { held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = needsTrace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
    func release() { continuation?.resume(); continuation = nil }
}
@MainActor private struct NeedsHostSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class NeedsHostFixture {
    let binding = NeedsBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    let session = SessionLifecycle(persistence: NeedsHostSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    var current: NeedsBinding?
    var callback: (() -> Void)?
    var credentials = 0
    init() throws { operation = try session.beginTrustedSDKSave(); current = binding }
    func observed() -> NeedsBinding? { let old = current; let run = callback; callback = nil; run?(); return old }
    func bind(_ host: NeedsContainerHost, shell: ShellState, transport: NeedsHostTransport, id: String = "needs-A", store: NeedsPendingStore? = nil) throws {
        let client = NeedsClient(endpoint: try NeedsEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 131_072, maximumResponseBytes: 1_048_576),
            credentials: { [self] _ in credentials += 1; return "SYNTHETIC" }, currentBinding: { [self] in observed() },
            pendingStore: store, interceptedTransport: transport)
        let value = NeedsContainerBinding(client: client, needs: binding, selectedNeedsID: id, shellGeneration: shell.generation,
            session: session, sessionOperation: operation, synthetic: true, currentBinding: { [self] in observed() })
        #expect(host.bind(value))
    }
}
@Suite @MainActor struct IndependentNeedsEditReentryTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func response<T: Encodable>(_ key: String, _ value: T) throws -> Data {
        Data(("{\"request_id\":\"" + needsTrace + "\",\"" + key + "\":" + String(decoding: try JSONEncoder().encode(value), as: UTF8.self) + "}").utf8)
    }
    private func null(_ key: String) -> Data { Data("{\"request_id\":\"\(needsTrace)\",\"\(key)\":null}".utf8) }
    private func fields() throws -> NeedsSchema.NeedsFields {
        try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: Data(#"{"budget_total":{"state":"unknown"},"budget_paid":{"state":"known","value":"12.3400"},"party_size":{"state":"missing"},"pace":{"state":"uncertain","note":"unsure / 未定"}}"#.utf8))
    }
    private func snapshot(_ id: String = "needs-A", version: Int = 2) throws -> NeedsSchema.NeedsSnapshot {
        let fields = try fields()
        return .init(needs_id: id, version: version, source_kind: .user_provided,
                     content_utf8_base64: try JSONEncoder().encode(fields).base64EncodedString(), fields: fields)
    }
    private func original(_ id: String = "actionA", needsID: String = "needs-A") throws -> NeedsPending {
        try NeedsPending(command: .init(action_id: id, needs_id: needsID, expected_version: 1,
            source: .init(kind: .manual, text: "Original e\u{301}; dates undecided / 日期未定"),
            changes: .init(budget_total: .NeedsUnknownObservation(.init(state: .unknown)))))
    }
    private func receipt(_ action: NeedsPending) -> NeedsSchema.NeedsReceipt {
        .init(action_id: action.actionID, needs_id: action.needsID, version: action.command.expected_version + 1, operation: .manual_patch)
    }
    private func revision(_ action: NeedsPending) throws -> NeedsSchema.NeedsRevision {
        let fields = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: JSONEncoder().encode(action.command.changes))
        return .init(needs_id: action.needsID, version: action.command.expected_version + 1, action_id: action.actionID, source_kind: .user_provided,
            original_input_utf8_base64: action.originalUTF8.base64EncodedString(), content_utf8_base64: try JSONEncoder().encode(fields).base64EncodedString(), fields: fields)
    }
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]); return url
    }
    private func store(_ f: NeedsHostFixture, directory: URL, key: @escaping () throws -> SymmetricKey) throws -> NeedsPendingStore {
        try NeedsPendingStore(directory: directory, maximumBytes: 524_288, maximumRecords: 20,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localNeedsPendingV1), keyID: UUID(), key: key)
    }
    private func wait(_ t: NeedsHostTransport) async {
        for _ in 0..<10000 { if await t.held { return }; await Task.yield() }; Issue.record("No held request")
    }
    @Test func oldEditCannotOverwriteNewerSameEditorCallbackEdit() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture()
        let t = NeedsHostTransport([try response("needs", snapshot())])
        try f.bind(h, shell: s, transport: t)
        await h.perform(h.prepareDetail(context: h.captureAction()))
        let model = try #require(h.presentation)
        var old = try #require(model.draft)
        var newer = old
        old.sourceText = "older draft"; old.set(.pace, .init(state: .known, value: "old pace"))
        newer.sourceText = "newer draft"; newer.set(.pace, .init(state: .known, value: "new pace"))
        let context = try #require(h.captureAction()); var nestedAccepted = false
        f.callback = { nestedAccepted = h.updateDraft(newer, context: h.captureAction()) }
        let oldAccepted = h.updateDraft(old, context: context)
        #expect(nestedAccepted)
        #expect(!oldAccepted, "Old update retained ownership after a newer editor write in current-binding callback")
        #expect(model.draft?.sourceText == "newer draft" && model.draft?.observations[.pace]?.value == "new pace",
            "Older local correction overwrote the newer same-editor value")
    }
}
