import Foundation
import CryptoKit
import Testing
import CJAPI
import CJMessageKeys
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient
@testable import CJShell

private let managementTrace = "00000000-0000-4000-8000-000000000001"
private actor ManagementHostTransport: ClientTransport {
    var replies: [Data]
    var calls: [(String, HTTPRequest.Method, String)] = []
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    let holdAt: Int?
    init(_ replies: [Data], holdFirst: Bool = false, holdAt: Int? = nil) { self.replies = replies; self.holdAt = holdAt ?? (holdFirst ? 1 : nil) }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method, request.path ?? ""))
        guard !replies.isEmpty else { throw MemoryFailure.exchangeUnknown }
        let bytes = replies.removeFirst()
        if calls.count == holdAt { held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = managementTrace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
    func release() { continuation?.resume(); continuation = nil }
}
@MainActor private final class ManagementHostFixture {
    let binding = MemoryBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: MemoryBinding?
    var callback: (() -> Void)?
    var credentials = 0
    init() { current = binding }
    func observed() -> MemoryBinding? { let old = current; let run = callback; callback = nil; run?(); return old }
    func client(_ transport: ManagementHostTransport, store: MemoryPendingStore? = nil) throws -> MemoryClient {
        MemoryClient(endpoint: try MemoryEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 100_000, maximumResponseBytes: 100_000),
            credentials: { [self] _ in credentials += 1; return "SYNTHETIC" },
            currentBinding: { [self] in observed() }, pendingStore: store, interceptedTransport: transport)
    }
    func bind(_ host: MemoryContainerHost, shell: ShellState, transport: ManagementHostTransport, store: MemoryPendingStore? = nil) throws {
        let value = MemoryContainerBinding(client: try client(transport, store: store), memory: binding,
            shellGeneration: shell.generation, pageSize: 2, synthetic: true, currentBinding: { [self] in observed() })
        #expect(host.bind(value))
    }
}
@Suite @MainActor struct MemoryManagementHostTests {
    private func setup(_ replies: [Data], holdFirst: Bool = false) throws -> (ShellState, MemoryContainerHost, ManagementHostFixture, ManagementHostTransport) {
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = MemoryContainerHost(shell: shell), fixture = ManagementHostFixture()
        let transport = ManagementHostTransport(replies, holdFirst: holdFirst)
        try fixture.bind(host, shell: shell, transport: transport)
        return (shell, host, fixture, transport)
    }
    private func json(_ fields: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: fields.merging(["request_id": managementTrace]) { a, _ in a })
    }
    private func item(_ id: String = "a", version: Int = 3, source: Int = 7) -> [String: Any] {
        ["command": ["operation_id": "synthetic-op-" + id, "item_id": id, "subject": "self", "slot": "test", "text": "synthetic only",
          "source_id": "original-source", "source_version": source, "occurred_at": "unknown", "kind": "preference", "extent": "long_term", "context_id": NSNull()],
         "version": version, "status": "active", "recorded_at": "2026-10-23T01:00:00Z"]
    }
    private func initial() throws -> [Data] {
        [try json(["groups": [["subject": "self", "status": "active", "count": 2]]]),
         try json(["items": [item(), item("b")], "next_after": "b"])]
    }
    private func select(_ host: MemoryContainerHost) async throws {
        await host.loadGroups(context: host.captureAction())
        guard case .loaded(let groups) = host.groups else { throw MemoryFailure.invalidResponse }
        #expect(host.selectGroup(try #require(groups.first), context: host.captureAction()))
        await host.loadItems(context: host.captureAction())
        #expect(host.managementSelection == nil) // list alone never mounts detail controls
        #expect(host.selectItem("a", context: host.captureAction()))
    }
    @Test func acceptedDetailProvidesBothOriginalVersions() async throws {
        let (_, host, _, transport) = try setup(initial() + [json(["item": item()])])
        try await select(host); await host.loadDetail(context: host.captureAction())
        let selection = try #require(host.managementSelection)
        #expect(selection.itemID == "a" && selection.expectedVersion == 3)
        #expect(selection.expectedSourceVersion == 7 && selection.sourceID == "original-source")
        #expect(await transport.calls.allSatisfy { $0.1 == .get })
    }
    @Test(arguments: ["null", "malformed"])
    func newReadRetiresOldSelectionEvenWhenItFails(outcome: String) async throws {
        let last = try json(["item": outcome == "null" ? NSNull() : [:]])
        let (_, host, _, _) = try setup(initial() + [json(["item": item()]), last])
        try await select(host); await host.loadDetail(context: host.captureAction())
        #expect(host.managementSelection != nil)
        let identity = host.managementIdentity
        await host.loadDetail(context: host.captureAction())
        #expect(host.managementSelection == nil && host.managementIdentity != identity)
        if outcome == "malformed" {
            if case .failed = host.detail {} else { Issue.record("Invalid read appeared successful") }
        } else {
            if case .loaded(nil) = host.detail {} else { Issue.record("Null detail was not retained") }
        }
    }
    @Test func sameVersionRefreshAndRowChangeRetireReadIdentity() async throws {
        let (_, host, _, _) = try setup(initial() + [json(["item": item()]), json(["item": item()])])
        try await select(host); await host.loadDetail(context: host.captureAction())
        let first = host.managementIdentity
        await host.loadDetail(context: host.captureAction())
        #expect(host.managementIdentity != first && host.managementSelection != nil)
        #expect(host.selectItem("b", context: host.captureAction()))
        #expect(host.managementSelection == nil)
    }
    @Test(arguments: ["account", "environment", "session", "selection"])
    func changedClientBindingCannotResurrectOldSelection(dimension: String) async throws {
        let (_, host, fixture, _) = try setup(initial() + [json(["item": item()])])
        try await select(host); await host.loadDetail(context: host.captureAction())
        let b = fixture.binding
        fixture.current = MemoryBinding(environment: dimension == "environment" ? UUID() : b.environment,
            account: dimension == "account" ? UUID() : b.account,
            generation: dimension == "session" ? UUID() : b.generation,
            selection: dimension == "selection" ? UUID() : b.selection)
        #expect(host.managementSelection == nil && !host.isConfigured)
        fixture.current = b
        #expect(host.managementSelection == nil && !host.isConfigured)
    }
    @Test func viewExitDropsLateDetailAndStaleExitCannotClearReplacement() async throws {
        let shellA = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = MemoryContainerHost(shell: shellA), fixture = ManagementHostFixture()
        let transport = ManagementHostTransport(try initial() + [json(["item": item()])], holdAt: 3)
        try fixture.bind(host, shell: shellA, transport: transport)
        try await select(host)
        let oldID = host.beginManagementPresentation()
        let action = host.captureAction()
        let work = Task { await host.loadDetail(context: action) }
        for _ in 0..<10000 { if await transport.held { break }; await Task.yield() }
        #expect(await transport.held)
        host.leaveManagementPresentation(oldID)
        #expect(host.managementSelection == nil && !host.busy)
        await transport.release(); await work.value
        #expect(host.managementSelection == nil && !host.busy)
        #expect(await transport.calls.count == 3)
        // A stale outgoing view cannot clear a later binding.
        host.invalidate()
        try fixture.bind(host, shell: shellA, transport: ManagementHostTransport([]))
        host.leaveManagementPresentation(oldID)
        #expect(host.isConfigured)
    }
    @Test func missingManagementJournalIsFailureAndClearsDetailSelection() async throws {
        let (_, host, fixture, transport) = try setup(initial() + [json(["item": item()])])
        try await select(host); await host.loadDetail(context: host.captureAction())
        host.loadManagementPending(context: host.captureAction())
        #expect(host.managementSelection == nil)
        if case .failed = host.managementPending {} else { Issue.record("Missing journal shown as empty") }
        #expect(fixture.credentials == 3)
        #expect(await transport.calls.count == 3)
    }
    @Test func publicClientRemainsClosedBeforeCredentialsOrJournalAccess() async throws {
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = MemoryContainerHost(shell: shell), fixture = ManagementHostFixture()
        let client = MemoryClient(endpoint: try MemoryEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 32768, maximumResponseBytes: 65536),
            credentials: { _ in fixture.credentials += 1; return nil }, currentBinding: { fixture.current }, pendingStore: nil,
            liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
        #expect(!client.managementAvailable)
        #expect(host.bind(MemoryContainerBinding(client: client, memory: fixture.binding, shellGeneration: shell.generation,
            pageSize: 2, synthetic: true, currentBinding: { fixture.current })))
        host.loadManagementPending(context: host.captureAction())
        if case .failed = host.managementPending {} else { Issue.record("Missing journal was hidden") }
        await #expect(throws: MemoryFailure.unconfigured) {
            try await client.queryManagement(actionID: "unsubmitted", binding: fixture.binding)
        }
        #expect(fixture.credentials == 0 && host.managementSelection == nil)
    }
    @Test func encryptedReopenExposesOnlyOriginalActionWithoutDispatch() async throws {
        // Explicitly synthetic encrypted fixture; no Keychain, POST or live credentials.
        let (_, loaded, fixture, _) = try setup(initial() + [json(["item": item()])])
        try await select(loaded); await loaded.loadDetail(context: loaded.captureAction())
        let selection = try #require(loaded.managementSelection)
        let original = try MemoryManagementPending(operation: .pause, selection: selection)
        let directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: directory) }
        let key = SymmetricKey(size: .bits256), keyID = UUID()
        let namespace = CJMessageKeys.MessageKeyNamespace(environment: fixture.binding.environment, account: fixture.binding.account, purpose: .localMemoryPendingV1)
        let store = try MemoryManagementPendingStore(directory: directory, maximumBytes: 32768, maximumRecords: 2,
            namespace: namespace, keyID: keyID) { key }
        try store.append(original, validateBinding: {})
        let reopened = try MemoryManagementPendingStore(directory: directory, maximumBytes: 32768, maximumRecords: 2,
            namespace: namespace, keyID: keyID) { key }
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString)))
        let host = MemoryContainerHost(shell: shell)
        let client = MemoryClient(endpoint: try MemoryEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 32768, maximumResponseBytes: 65536),
            credentials: { _ in Issue.record("Public recovery accessed credentials"); return nil }, currentBinding: { fixture.current }, pendingStore: nil,
            liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1), managementPendingStore: reopened)
        #expect(host.bind(MemoryContainerBinding(client: client, memory: fixture.binding, shellGeneration: shell.generation,
            pageSize: 2, synthetic: true, currentBinding: { fixture.current })))
        host.loadManagementPending(context: host.captureAction())
        guard case .loaded(let records) = host.managementPending else { throw MemoryFailure.invalidResponse }
        let record = try #require(records.first)
        #expect(record.actionID == original.actionID && record.originalUTF8 == original.originalUTF8)
        #expect(record.expectedSHA256 == original.expectedSHA256 && host.managementSelection == nil)
        #expect(!client.managementAvailable)
        await #expect(throws: MemoryFailure.unconfigured) { try await client.queryManagement(actionID: record.actionID, binding: fixture.binding) }
        #expect(try reopened.pending().first?.originalUTF8 == original.originalUTF8)
        host.leaveManagementPresentation(host.beginManagementPresentation())
        if case .unconfigured = host.managementPending {} else { Issue.record("Exit retained encrypted-record presentation") }
    }

    @Test(arguments: [false, true])
    func staleSameBindingRowExitCannotClearCurrentDetail(reappear: Bool) async throws {
        let (_, host, _, _) = try setup(initial() + [json(["item": item()]), json(["item": item("b")])])
        try await select(host)
        let exitA = host.beginManagementPresentation()
        await host.loadDetail(context: host.captureAction())
        #expect(host.managementSelection?.itemID == "a")
        #expect(host.selectItem("b", context: host.captureAction()))
        let exitB = reappear ? host.beginManagementPresentation() : nil
        await host.loadDetail(context: host.captureAction())
        let identityB = host.managementIdentity
        host.leaveManagementPresentation(exitA)
        #expect(host.isConfigured && host.managementSelection?.itemID == "b")
        #expect(host.managementIdentity == identityB)
        guard case .loaded(let current) = host.detail else { throw MemoryFailure.invalidResponse }
        #expect(current?.command.item_id == "b")
        // The actual current appearance must still synchronously clear its data.
        host.leaveManagementPresentation(exitB ?? host.beginManagementPresentation())
        #expect(host.managementSelection == nil && !host.busy)
        if case .unconfigured = host.detail {} else { Issue.record("Current exit retained detail") }
    }
    @Test func oldAppearanceOfSameRowCannotClearReopenedPresentation() async throws {
        let (_, host, _, _) = try setup(initial() + [json(["item": item()])])
        try await select(host)
        let firstAppearance = host.beginManagementPresentation()
        await host.loadDetail(context: host.captureAction())
        let reopened = host.beginManagementPresentation()
        let identity = host.managementIdentity
        host.leaveManagementPresentation(firstAppearance)
        #expect(host.managementIdentity == identity && host.managementSelection?.itemID == "a")
        host.leaveManagementPresentation(reopened)
        #expect(host.managementSelection == nil)
    }

}
