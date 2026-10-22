import Foundation
import CryptoKit
import Testing
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient
@testable import CJShell

private let memoryTrace = "00000000-0000-4000-8000-000000000001"
private actor MemoryHostTransport: ClientTransport {
    var replies: [Data]
    var calls: [(String, HTTPRequest.Method, String)] = []
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    let holdFirst: Bool
    init(_ replies: [Data], holdFirst: Bool = false) { self.replies = replies; self.holdFirst = holdFirst }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method, request.path ?? ""))
        guard !replies.isEmpty else { throw MemoryFailure.exchangeUnknown }
        let bytes = replies.removeFirst()
        if holdFirst && calls.count == 1 { held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = memoryTrace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
    func release() { continuation?.resume(); continuation = nil }
}
@MainActor private final class MemoryHostFixture {
    let binding = MemoryBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: MemoryBinding?
    var callback: (() -> Void)?
    var credentials = 0
    init() { current = binding }
    func observed() -> MemoryBinding? { let old = current; let run = callback; callback = nil; run?(); return old }
    func client(_ transport: MemoryHostTransport, store: MemoryPendingStore? = nil) throws -> MemoryClient {
        MemoryClient(endpoint: try MemoryEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 100_000, maximumResponseBytes: 100_000),
            credentials: { [self] _ in credentials += 1; return "SYNTHETIC" },
            currentBinding: { [self] in observed() }, pendingStore: store, interceptedTransport: transport)
    }
    func bind(_ host: MemoryContainerHost, shell: ShellState, transport: MemoryHostTransport, store: MemoryPendingStore? = nil) throws {
        let value = MemoryContainerBinding(client: try client(transport, store: store), memory: binding,
            shellGeneration: shell.generation, pageSize: 2, synthetic: true, currentBinding: { [self] in observed() })
        #expect(host.bind(value))
    }
}
@Suite @MainActor struct MemoryContainerHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func json(_ fields: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: fields.merging(["request_id": memoryTrace]) { a, _ in a })
    }
    private func item(_ id: String, subject: String = "self", status: String = "active") -> [String: Any] {
        ["command": ["operation_id": "synthetic-op-" + id, "item_id": id, "subject": subject, "slot": "test", "text": "synthetic " + id,
          "source_id": "synthetic-source", "source_version": 1, "occurred_at": "date unknown", "kind": "preference", "extent": "long_term", "context_id": NSNull()],
         "version": 1, "status": status, "recorded_at": "2026-10-22T01:00:00Z"]
    }
    private func rows<T>(_ state: MemoryLoad<[T]>) throws -> [T] {
        guard case .loaded(let rows) = state else { throw MemoryFailure.invalidResponse }; return rows
    }
    private func wait(_ transport: MemoryHostTransport) async {
        for _ in 0..<10000 { if await transport.held { return }; await Task.yield() }
        Issue.record("Intercepted request did not reach hold")
    }
    private func command(_ operation: String = "synthetic-original", inference: Bool = false) -> Components.Schemas.MemoryManualSaveCommand {
        .init(operation_id: operation, item_id: "synthetic-item", subject: "self", slot: "test", text: "synthetic only",
              occurred_at: "unknown", kind: inference ? .inference : .preference, extent: .long_term, context_id: .case2(nil))
    }
    @Test func defaultDoesNotLoadOrWrite() async throws {
        let host = MemoryContainerHost(shell: try shell())
        await host.loadGroups(context: host.captureAction())
        #expect(!host.isConfigured && !host.canSubmitManual && host.manualBinding == nil)
        if case .unconfigured = host.groups {} else { Issue.record("Default is not unavailable") }
        await #expect(throws: MemoryFailure.liveWriteUnavailable) { try await host.submitManual(command(), context: nil) }
    }
    @Test func actualGroupsGlobalPagesAndDetailPreserveBytesAndStatus() async throws {
        let composed = "é", decomposed = "e\u{301}"
        let transport = MemoryHostTransport([
            try json(["groups": [["subject": composed, "status": "candidate", "count": 1]]]),
            try json(["items": [item("a", subject: decomposed, status: "candidate")], "next_after": "a"]),
            try json(["items": [item("b", subject: composed, status: "candidate")], "next_after": "b"]),
            try json(["items": [], "next_after": NSNull()]),
            try json(["item": item("b", subject: composed, status: "candidate")])])
        let shell = try shell(), host = MemoryContainerHost(shell: shell), f = MemoryHostFixture()
        try f.bind(host, shell: shell, transport: transport)
        #expect(await transport.calls.isEmpty)
        await host.loadGroups(context: host.captureAction())
        let group = try #require(rows(host.groups).first)
        #expect(host.selectGroup(group, context: host.captureAction()))
        await host.loadItems(context: host.captureAction())
        #expect(try rows(host.items).isEmpty && host.hasMore)
        await host.loadItems(context: host.captureAction(), more: true)
        #expect(try rows(host.items).map(\.command.item_id) == ["b"])
        await host.loadItems(context: host.captureAction(), more: true)
        #expect(!host.hasMore)
        #expect(try rows(host.items).count == 1)
        #expect(!host.selectItem("a", context: host.captureAction()))
        #expect(host.selectItem("b", context: host.captureAction()))
        await host.loadDetail(context: host.captureAction())
        guard case .loaded(let detail) = host.detail else { Issue.record("Missing actual detail"); return }
        #expect(detail?.status == .candidate && detail?.command.source_id == "synthetic-source")
        #expect(detail?.command.source_version == 1 && detail?.command.occurred_at == "date unknown")
        #expect(await transport.calls.allSatisfy { $0.1 == .get })
    }
    @Test func emptyAndFailureRemainDifferent() async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), f = MemoryHostFixture()
        let t = MemoryHostTransport([try json(["groups": []]), Data("{}".utf8)])
        try f.bind(h, shell: s, transport: t)
        await h.loadGroups(context: h.captureAction()); #expect(try rows(h.groups).isEmpty)
        await h.loadGroups(context: h.captureAction())
        if case .failed = h.groups {} else { Issue.record("Failure was not explicit") }
    }
    @Test func queuedOldActionCannotRetargetReplacementBinding() async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), a = MemoryHostFixture(), b = MemoryHostFixture()
        let ta = MemoryHostTransport([]), tb = MemoryHostTransport([try json(["groups": []])])
        try a.bind(h, shell: s, transport: ta); let old = h.captureAction()
        h.invalidate(); try b.bind(h, shell: s, transport: tb)
        await h.loadGroups(context: old)
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.isEmpty)
        await h.loadGroups(context: h.captureAction()); #expect(await tb.calls.count == 1)
    }
    @Test(arguments: [false, true]) func lateResponseCannotReviveAfterIdentityOrBackground(background: Bool) async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), a = MemoryHostFixture(), b = MemoryHostFixture()
        let ta = MemoryHostTransport([try json(["groups": [["subject": "old", "status": "active", "count": 1]]])], holdFirst: true)
        try a.bind(h, shell: s, transport: ta)
        let action = h.captureAction(); let old = Task { await h.loadGroups(context: action) }
        await wait(ta)
        let generation = s.generation; s.selectLanguage(.chinese)
        #expect(s.generation == generation && h.busy)
        if background { h.suspendForBackground() } else { s.invalidateIdentity() }
        #expect(!h.isConfigured && !h.busy && h.manualBinding == nil)
        // Explicit trusted-root setup in this synthetic test only; no automatic foreground binding.
        s.messageBindingBlocked = false
        let tb = MemoryHostTransport([try json(["groups": [["subject": "new", "status": "active", "count": 1]]])])
        try b.bind(h, shell: s, transport: tb)
        await h.loadGroups(context: h.captureAction())
        await ta.release(); await old.value
        #expect(try rows(h.groups).map(\.subject) == ["new"])
        #expect(!h.busy && h.manualBinding == b.binding)
    }
    @Test func reentrantBindingCallbackCannotClearOrUseB() async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), a = MemoryHostFixture(), b = MemoryHostFixture()
        let ta = MemoryHostTransport([]), tb = MemoryHostTransport([])
        try a.bind(h, shell: s, transport: ta)
        a.callback = { h.invalidate(); try! b.bind(h, shell: s, transport: tb) }
        let action = h.captureAction()
        #expect(action == nil && h.manualBinding == b.binding)
        await h.loadGroups(context: action)
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.isEmpty)
    }
    @Test func missingStoreCannotBecomeEmptyRecoveryOrSend() async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), f = MemoryHostFixture(), t = MemoryHostTransport([])
        try f.bind(h, shell: s, transport: t)
        h.loadPending(context: h.captureAction())
        if case .failed = h.pending {} else { Issue.record("Missing store appeared usable") }
        await h.queryOriginal("foreign", context: h.captureAction())
        await #expect(throws: MemoryFailure.liveWriteUnavailable) { try await h.submitManual(command(), context: h.captureAction()) }
        #expect(f.credentials == 0); #expect(await t.calls.isEmpty)
    }
    @Test func missingExistingKeyFailsRecoveryWithoutCredentialOrFallback() async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), f = MemoryHostFixture()
        let directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: directory) }
        let key = SymmetricKey(size: .bits256)
        var available = true
        let store = try MemoryPendingStore(directory: directory, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localMemoryPendingV1), keyID: UUID()) {
                guard available else { throw MemoryFailure.keyUnavailable }; return key
            }
        try store.append(MemoryPending(command()))
        available = false
        let t = MemoryHostTransport([])
        try f.bind(h, shell: s, transport: t, store: store)
        h.loadPending(context: h.captureAction())
        if case .failed = h.pending {} else { Issue.record("Missing original key appeared recoverable") }
        await h.queryOriginal("synthetic-original", context: h.captureAction())
        #expect(f.credentials == 0); #expect(await t.calls.isEmpty)
    }
    @Test(arguments: ["null", "candidate", "active", "malformed"])
    func originalQueryUsesStoredBytesAndNeverResends(outcome: String) async throws {
        let s = try shell(), h = MemoryContainerHost(shell: s), f = MemoryHostFixture()
        let directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: directory) }
        let key = SymmetricKey(size: .bits256)
        let store = try MemoryPendingStore(directory: directory, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localMemoryPendingV1), keyID: UUID()) { key }
        let record = try MemoryPending(command("original-é", inference: outcome == "candidate"))
        try store.append(record)
        let receipt: Any = outcome == "null" ? NSNull() : outcome == "malformed" ? [:] : ["operation_id": record.operationID, "item_id": record.itemID,
            "version": 1, "status": outcome, "input_sha256": record.expectedSHA256] as [String: Any]
        let t = MemoryHostTransport([try json(["receipt": receipt])])
        try f.bind(h, shell: s, transport: t, store: store)
        h.loadPending(context: h.captureAction())
        #expect(try rows(h.pending).first?.originalUTF8 == record.originalUTF8)
        await h.queryOriginal("original-e\u{301}", context: h.captureAction())
        #expect(await t.calls.isEmpty)
        await h.queryOriginal(record.operationID, context: h.captureAction())
        #expect(h.queriedOperationID == record.operationID)
        switch (outcome, h.saveState) {
        case ("null", .notObserved), ("candidate", .candidate), ("active", .saved), ("malformed", .unknown): break
        default: Issue.record("Incorrect receipt presentation")
        }
        #expect(await t.calls.map(\.0) == ["queryMemoryReceipt"])
        #expect(await t.calls.allSatisfy { $0.1 == .get })
        #expect(try store.pending().first?.originalUTF8 == record.originalUTF8)
        #expect(!h.canSubmitManual)
    }
}
