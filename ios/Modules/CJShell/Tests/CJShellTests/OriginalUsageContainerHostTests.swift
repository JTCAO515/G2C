import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageClient
@testable import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJUsageClient
@testable import CJShell

private let officialTrace = "00000000-0000-4000-8000-000000000033"
@MainActor private final class OfficialMessageStorage: SecureMessageStorage {
    var saved: Snapshot?
    var writes = 0
    func load(scope: StorageScope) throws -> Snapshot? { saved }
    func save(_ value: Snapshot, scope: StorageScope) throws { saved = value; writes += 1 }
}
@MainActor private struct OfficialSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class OfficialMessageCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "SYNTHETIC" }
}
private actor OfficialUsageWire: ClientTransport {
    struct Reply: Sendable { let bytes: Data; let status: Int }
    var replies: [String: [Reply]] = [:]
    var calls: [(String, HTTPRequest.Method, String)] = []
    var holdAssociation = false
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    func add(_ operation: String, bytes: Data, status: Int = 200) { replies[operation, default: []].append(.init(bytes: bytes, status: status)) }
    func hold() { holdAssociation = true }
    func release() { continuation?.resume(); continuation = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && body == nil)
        calls.append((operationID, request.method, request.path ?? ""))
        guard let reply = replies[operationID]?.first else { throw UsageFailure.exchangeFailed }
        replies[operationID]?.removeFirst()
        if operationID == "getOriginalUsageAssociation", holdAssociation {
            holdAssociation = false; held = true; await withCheckedContinuation { continuation = $0 }
        }
        var response = HTTPResponse(status: .init(code: reply.status))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = officialTrace
        response.headerFields[.contentType] = "application/json"; response.headerFields[.cacheControl] = "no-store"
        return (response, HTTPBody(reply.bytes))
    }
}
@MainActor private final class OfficialUsageControl {
    var allowed = true
    let actor = Data("SYNTHETIC-VERIFIED-ACTOR".utf8)
    var callback: (() -> Void)?
    var messageCallback: (() -> Void)?
}
@MainActor private final class OfficialUsageFixture {
    let shell: ShellState
    let messages: AssistantMessageHost
    let host: OriginalUsageContainerHost
    let storage = OfficialMessageStorage()
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let session = SessionLifecycle(persistence: OfficialSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let wire = OfficialUsageWire()
    let control = OfficialUsageControl()
    let endpoint: MessageEndpoint
    let client: MessageHTTPClient
    init(shell: ShellState) throws {
        self.shell = shell; messages = AssistantMessageHost(shell: shell)
        recovery = MessageRecovery(storage: storage)
        scope = try StorageScope(environment: UUID().uuidString, account: "synthetic")
        lease = try recovery.activate(scope); operation = try session.beginTrustedSDKSave()
        endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 4096, maximumResponseBytes: 16384)
        client = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint, credentials: OfficialMessageCredentials(), interceptedTestTransport: wire)
        let wire = wire
        host = OriginalUsageContainerHost(shell: shell, makeModel: { cfg, input, current in
            OriginalUsageViewModel(session: cfg.session, recovery: input.recovery, scope: input.scope, endpoint: cfg.endpoint,
                credentials: cfg.credentials, currentBinding: current,
                interceptedTransport: try! NoRedirectTransport(interceptedTransport: wire, previewEndpoint: nil, validatePreview: nil))
        })
    }
    func json(_ key: String, _ fields: Any) throws -> Data { try JSONSerialization.data(withJSONObject: ["request_id": officialTrace, key: fields]) }
    func accept(_ id: String, runID: String? = nil) async throws {
        let raw = try JSONSerialization.data(withJSONObject: ["message_id": id, "conversation_id": "chat-e\u{301}", "text": "Synthetic accepted original"])
        try recovery.stage(messageID: id, originalUTF8: raw, lease: lease)
        _ = try recovery.beginSubmission(messageID: id, lease: lease)
        let record = try #require(try recovery.action(messageID: id, lease: lease))
        let receipt: [String: Any] = ["message_id": id, "conversation_id": "chat-e\u{301}", "generation": "generation-e\u{301}", "run_id": runID ?? "run-" + id, "sequence": 7, "input_sha256": record.inputSHA256]
        await wire.add("queryMessageReceipt", bytes: try json("receipt", receipt))
        guard case .accepted = try await client.query(messageID: id, lease: lease) else { Issue.record("Actual MESSAGE query not accepted"); return }
    }
    func bind(_ id: String?) throws {
        let control = control
        let value = AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
            conversationID: "chat-e\u{301}", messageID: id, synthetic: true,
            isCurrent: { let callback = control.messageCallback; control.messageCallback = nil; callback?(); return true }, invalidateResources: {})
        #expect(messages.bind(value))
        let cfg = try OriginalUsageContainerConfiguration(session: session, operation: operation, actorIdentity: control.actor, revision: 9,
            endpoint: endpoint, credentials: { _ in "SYNTHETIC" }, transport: NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1), generation: shell.generation,
            isCurrent: { value in
                let callback = control.callback; control.callback = nil; callback?()
                return control.allowed && value.actorIdentity == control.actor
            })
        #expect(host.configure(cfg)); host.setForeground(true)
    }
    func select(_ id: String) throws {
        let list = try recovery.localProjection(scope: scope, lease: lease)
        let value = try #require(list.actions.first { Data($0.messageID.utf8) == Data(id.utf8) })
        #expect(messages.selectAction(value, from: list))
    }
    func association(_ id: String) throws -> Data {
        try json("association", ["message_id": id, "conversation_id": "chat-e\u{301}", "generation": "generation-e\u{301}", "run_id": "run-" + id,
            "message_sequence": 7, "operation_id": "operation-" + id, "attempt_id": "attempt-" + id])
    }
    func status(_ id: String) throws -> Data {
        try json("attempt", ["attempt_id": "attempt-" + id, "operation_id": "operation-" + id, "run_id": "run-" + id, "status": "unknown",
            "unit": "opaque-unit", "reserved_units": String(repeating: "9", count: 70), "confirmed_units": NSNull(), "confirmed_output": NSNull(),
            "receipt_id": NSNull(), "cancelled": false, "exceeded": false, "message_en": "Synthetic", "message_zh": "合成"])
    }
}
@Suite @MainActor struct OriginalUsageContainerHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func settle(_ predicate: () -> Bool) async {
        for _ in 0..<20000 { if predicate() { return }; await Task.yield() }; Issue.record("Original read did not settle")
    }
    private func wait(_ wire: OfficialUsageWire) async {
        for _ in 0..<10000 { if await wire.held { return }; await Task.yield() }; Issue.record("Association not held")
    }
    @Test func absentOrStagedMessageCannotQueryOrCreateAttempt() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try f.bind(nil)
        f.host.resolveCurrentMessage(from: f.messages); f.host.readResolvedStatus()
        #expect(f.host.state == .unavailable && !f.host.canReadStatus)
        #expect(await f.wire.calls.isEmpty)
        let raw = Data("{\"message_id\":\"staged\",\"conversation_id\":\"chat-é\",\"text\":\"Synthetic\"}".utf8)
        try f.recovery.stage(messageID: "staged", originalUTF8: raw, lease: f.lease)
        try f.select("staged"); f.host.resolveCurrentMessage(from: f.messages)
        #expect(f.host.state == .unavailable); #expect(await f.wire.calls.isEmpty)
    }
    @Test func actualAcceptedMessageResolvesThenRequiresSecondExplicitAction() async throws {
        let id = "message/+%e\u{301}", f = try OfficialUsageFixture(shell: shell())
        try await f.accept(id); try f.bind(id)
        let input = try #require(f.messages.captureAcceptedUsageInput())
        #expect(!String(reflecting: input).contains(id))
        let before = f.storage.writes
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association(id))
        f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        guard case .sourceReady(let source) = f.host.state else { return }
        #expect(Data(source.attemptID.utf8) == Data(("attempt-" + id).utf8))
        #expect(await f.wire.calls.map(\.0) == ["queryMessageReceipt", "getOriginalUsageAssociation"])
        #expect(f.storage.writes == before)
        await f.wire.add("getUsageAttemptStatus", bytes: try f.status(id)); f.host.readResolvedStatus()
        await settle { if case .loaded = f.host.state { true } else { false } }
        guard case .loaded(let value) = f.host.state else { return }
        #expect(value.reservedUnits == String(repeating: "9", count: 70) && value.confirmedUnits == nil)
        #expect(value.attemptID == source.attemptID && value.runID == source.runID && value.operationID == source.operationID)
        let calls = await f.wire.calls
        #expect(calls.map(\.0) == ["queryMessageReceipt", "getOriginalUsageAssociation", "getUsageAttemptStatus"])
        let query = try #require(URLComponents(string: calls.last!.2)?.queryItems), attempt = try #require(query.first?.value)
        #expect(query.count == 1 && query[0].name == "attempt_id" && Data(attempt.utf8) == Data(source.attemptID.utf8))
        #expect(f.storage.writes == before)
    }
    @Test func legalLongMessageIDIsNotTreatedAsAttemptID() async throws {
        let id = String(repeating: "m", count: 201), f = try OfficialUsageFixture(shell: shell())
        try await f.accept(id, runID: "run-original"); try f.bind(id)
        let association: [String: Any] = ["message_id": id, "conversation_id": "chat-e\u{301}", "generation": "generation-e\u{301}",
            "run_id": "run-original", "message_sequence": 7, "attempt_id": "attempt-original", "operation_id": "operation-original"]
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.json("association", association))
        f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        guard case .sourceReady(let source) = f.host.state else { return }
        #expect(source.messageID == id && source.attemptID == "attempt-original")
        #expect(await f.wire.calls.map(\.0) == ["queryMessageReceipt", "getOriginalUsageAssociation"])
    }
    @Test(arguments: ["503", "foreign", "null"])
    func unavailableAssociationNeverTriggersStatus(mode: String) async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        let data: Data
        if mode == "503" { data = try f.json("error", ["code":"ORIGINAL_USAGE_UNAVAILABLE","category":"dependency","outcome":"unknown","recovery":"retry_safe_read","message_en":"Unavailable","message_zh":"不可用"]) }
        else if mode == "foreign" { data = try f.association("B") }
        else { data = try f.json("association", NSNull()) }
        await f.wire.add("getOriginalUsageAssociation", bytes: data, status: mode == "503" ? 503 : 200)
        f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .failed = f.host.state { true } else { false } }
        #expect(!f.host.canReadStatus); f.host.readResolvedStatus()
        #expect(await f.wire.calls.map(\.0) == ["queryMessageReceipt", "getOriginalUsageAssociation"])
    }
    @Test func messageSelectionABAInvalidatesClosedSourceBetweenActions() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try await f.accept("B"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A")); f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }; let old = f.host.selectionGeneration
        try f.select("B"); try f.select("A"); f.host.readResolvedStatus()
        #expect(f.host.state == .unavailable && !f.host.canReadStatus)
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A")); f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        #expect(f.host.selectionGeneration != old)
        #expect(await f.wire.calls.filter { $0.0 == "getUsageAttemptStatus" }.isEmpty)
    }
    @Test func equalRevisionResolveReentryPreservesNewerWork() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A"))
        f.control.callback = { f.host.resolveCurrentMessage(from: f.messages) }
        f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        #expect(await f.wire.calls.filter { $0.0 == "getOriginalUsageAssociation" }.count == 1)
    }
    @Test func equalRevisionStatusReentryPreservesOnlyNewerRead() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A")); f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        await f.wire.add("getUsageAttemptStatus", bytes: try f.status("A"))
        f.control.callback = { f.host.readResolvedStatus() }; f.host.readResolvedStatus()
        await settle { if case .loaded = f.host.state { true } else { false } }
        #expect(await f.wire.calls.filter { $0.0 == "getUsageAttemptStatus" }.count == 1)
    }
    @Test func lateAssociationAndOldErrorCannotPublishOverNewMessage() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try await f.accept("B"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A")); await f.wire.hold(); f.host.resolveCurrentMessage(from: f.messages)
        await wait(f.wire); try f.select("B")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("B")); f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady(let source) = f.host.state { source.messageID == "B" } else { false } }
        await f.wire.release(); await Task.yield()
        guard case .sourceReady(let source) = f.host.state else { Issue.record("New source cleared"); return }
        #expect(source.messageID == "B")
    }
    @Test func backgroundAndReceiptRetirementWithholdBothActions() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A")); f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        f.host.setForeground(false); f.host.setForeground(true); f.host.readResolvedStatus()
        #expect(f.host.state == .unavailable && !f.host.canReadStatus)
        f.recovery.invalidate(); f.host.resolveCurrentMessage(from: f.messages)
        #expect(f.host.state == .unavailable)
        #expect(await f.wire.calls.count == 2)
    }
    @Test func finalMessageCallbackRevokingAdmissionHidesSource() async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A")); f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        f.control.messageCallback = { f.control.allowed = false }
        #expect(f.host.state == .unavailable)
        f.host.readResolvedStatus(); #expect(await f.wire.calls.count == 2)
    }
    @Test(arguments: [false, true])
    func identityOrOriginalSessionRetirementBlocksBothActions(sessionOnly: Bool) async throws {
        let f = try OfficialUsageFixture(shell: shell()); try await f.accept("A"); try f.bind("A")
        await f.wire.add("getOriginalUsageAssociation", bytes: try f.association("A"))
        f.host.resolveCurrentMessage(from: f.messages)
        await settle { if case .sourceReady = f.host.state { true } else { false } }
        if sessionOnly { try f.session.clear() } else { f.shell.invalidateIdentity() }
        f.host.setForeground(true); f.host.readResolvedStatus(); f.host.resolveCurrentMessage(from: f.messages)
        #expect(f.host.state == .unavailable && !f.host.canResolve && !f.host.canReadStatus)
        #expect(await f.wire.calls.map(\.0) == ["queryMessageReceipt", "getOriginalUsageAssociation"])
    }
}
