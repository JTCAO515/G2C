import Foundation
import Testing
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJUsageClient
@testable import CJShell

private let usageTrace = "00000000-0000-4000-8000-000000000008"
@MainActor private struct UsageHostSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor UsageHostWire: ClientTransport {
    var replies: [Data] = []
    var calls: [(String, HTTPRequest.Method, String)] = []
    var holdNext = false
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    func add(_ data: Data) { replies.append(data) }
    func hold() { holdNext = true }
    func release() { continuation?.resume(); continuation = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && body == nil && operationID == "getUsageAttemptStatus")
        calls.append((operationID, request.method, request.path ?? ""))
        guard !replies.isEmpty else { throw UsageFailure.exchangeFailed }
        let bytes = replies.removeFirst()
        if holdNext { holdNext = false; held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = usageTrace
        response.headerFields[.contentType] = "application/json"; response.headerFields[.cacheControl] = "no-store"
        return (response, HTTPBody(bytes))
    }
}
@MainActor private final class UsageHostControl {
    var allowed = true
    var actor = Data("SYNTHETIC-ACTOR-A".utf8)
    var callback: (() -> Void)?
    var credentialHook: (() -> Void)?
    var credentials = 0
    var models: [UsageViewModel] = []
}
@MainActor private final class UsageHostFixture {
    let shell: ShellState
    let host: UsageContainerHost
    let control = UsageHostControl()
    let session = SessionLifecycle(persistence: UsageHostSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let wire = UsageHostWire()
    init(shell: ShellState) throws {
        self.shell = shell; operation = try session.beginTrustedSDKSave()
        let wire = wire, control = control
        host = UsageContainerHost(shell: shell, makeModel: { cfg, current in
            let model = UsageViewModel(session: cfg.session, endpoint: cfg.endpoint, credentials: cfg.credentials,
                currentBinding: current, interceptedTransport: wire)
            control.models.append(model); return model
        })
    }
    func configure() throws {
        let control = control
        let cfg = UsageContainerConfiguration(session: session,
            endpoint: try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 4096, maximumResponseBytes: 16384),
            credentials: { _ in control.credentials += 1; let hook = control.credentialHook; control.credentialHook = nil; hook?(); return "SYNTHETIC" },
            transport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1), generation: shell.generation,
            isCurrent: { original in
                let hook = control.callback; control.callback = nil; hook?()
                return control.allowed && original.actorIdentity == control.actor
            })
        #expect(host.configure(cfg)); host.setForeground(true)
    }
    func input(_ id: String = "attempt/+%e\u{301}", actor: Data? = nil, revision: UInt64 = 7) -> UsageBinding {
        UsageBinding(source: UsageSource(attemptID: id, operationID: "original-op", runID: "original-run"), sessionOperation: operation,
            actorIdentity: actor ?? control.actor, selectionGeneration: UUID(), revision: revision)
    }
    func response(_ id: String = "attempt/+%e\u{301}", status: String = "unknown", zero: Bool = false) throws -> Data {
        let confirmed: Any = zero ? "0" : NSNull()
        let receipt: Any = zero ? "original-receipt" : NSNull()
        return try JSONSerialization.data(withJSONObject: ["request_id": usageTrace, "attempt": [
            "attempt_id": id, "operation_id": "original-op", "run_id": "original-run", "status": status,
            "unit": "opaque-unit-not-currency", "reserved_units": String(repeating: "9", count: 70),
            "confirmed_units": confirmed, "confirmed_output": confirmed,
            "receipt_id": receipt, "cancelled": false, "exceeded": false,
            "message_en": "Synthetic usage", "message_zh": "合成用量"]])
    }
}
@Suite @MainActor struct UsageContainerHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func settle(_ predicate: () -> Bool) async {
        for _ in 0..<10000 { if predicate() { return }; await Task.yield() }; Issue.record("Read did not settle")
    }
    private func wait(_ wire: UsageHostWire) async {
        for _ in 0..<10000 { if await wire.held { return }; await Task.yield() }; Issue.record("Read not held")
    }
    @Test func noProductionSourceIsUnavailableAndNeverQueries() async throws {
        let f = try UsageHostFixture(shell: shell())
        f.host.readOriginal(); #expect(f.host.state == .unavailable && !f.host.hasOriginalSource)
        try f.configure(); f.host.readOriginal()
        #expect(f.host.state == .unavailable && !f.host.canRead)
        #expect(f.control.models.isEmpty && f.control.credentials == 0)
        f.host.setForeground(false); f.host.selectOriginal(f.input()); f.host.setForeground(true)
        #expect(!f.host.hasOriginalSource && f.host.state == .unavailable)
        #expect(await f.wire.calls.isEmpty)
    }
    @Test func originalQueryPreservesExactUnitsUnknownAndActualZero() async throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure()
        let original = f.input(); f.host.selectOriginal(original)
        #expect(f.host.selectionGeneration != original.selectionGeneration)
        await f.wire.add(try f.response()); f.host.readOriginal()
        await settle { if case .loaded = f.host.state { true } else { false } }
        guard case .loaded(let value) = f.host.state else { Issue.record("Missing original result"); return }
        #expect(value.reservedUnits == String(repeating: "9", count: 70) && value.confirmedUnits == nil && value.confirmedOutput == nil)
        #expect(value.unit == "opaque-unit-not-currency" && value.operationID == "original-op" && value.runID == "original-run")
        let path = try #require(await f.wire.calls.first?.2), query = try #require(URLComponents(string: path)?.queryItems)
        let originalID = try #require(query.first?.value)
        #expect(query.count == 1 && query[0].name == "attempt_id" && Data(originalID.utf8) == Data(original.source.attemptID.utf8))
        let generation = f.host.selectionGeneration; f.shell.selectLanguage(.chinese)
        #expect(f.host.selectionGeneration == generation)
        await f.wire.add(try f.response(status: "settled", zero: true)); f.host.readOriginal()
        await settle { if case .loaded(let state) = f.host.state { state.status == .settled } else { false } }
        guard case .loaded(let zero) = f.host.state else { return }
        #expect(zero.confirmedUnits == "0" && zero.confirmedOutput == "0" && zero.receiptID == "original-receipt")
        #expect(await f.wire.calls.count == 2)
    }
    @Test func everySelectionIncludingABAGetsNewGeneration() throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure(); let a = f.input("A"), b = f.input("B")
        f.host.selectOriginal(a); let first = f.host.selectionGeneration
        f.host.selectOriginal(b); let second = f.host.selectionGeneration
        f.host.selectOriginal(a); let third = f.host.selectionGeneration
        #expect(first != second && first != third && second != third)
        #expect(f.control.models.count == 3 && f.host.state == .unavailable)
    }
    @Test func sameBindingPrepareCallbackCannotRetireNewerRead() async throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure(); f.host.selectOriginal(f.input())
        await f.wire.add(try f.response())
        f.control.callback = { f.host.readOriginal() }
        f.host.readOriginal()
        await settle { if case .loaded = f.host.state { true } else { false } }
        #expect(await f.wire.calls.count == 1)
    }
    @Test func callbackSelectionAndActorSwitchWithholdOriginal() async throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure(); f.host.selectOriginal(f.input("A"))
        let actorB = Data("SYNTHETIC-ACTOR-B".utf8)
        f.control.callback = {
            f.control.actor = actorB; f.host.selectOriginal(f.input("B", actor: actorB))
        }
        f.host.readOriginal()
        await settle { f.control.models.count == 2 }
        #expect(await f.wire.calls.isEmpty && f.host.state == .unavailable)
        await f.wire.add(try f.response("B")); f.host.readOriginal()
        await settle { if case .loaded(let value) = f.host.state { value.attemptID == "B" } else { false } }
        #expect(await f.wire.calls.count == 1)
    }
    @Test(arguments: [false, true]) func lateReadCannotOverwriteRenewedOrBackgroundSource(background: Bool) async throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure(); f.host.selectOriginal(f.input("A"))
        await f.wire.add(try f.response("A")); await f.wire.hold(); f.host.readOriginal(); await wait(f.wire)
        if background {
            f.host.setForeground(false); #expect(!f.host.hasOriginalSource && f.host.state == .unavailable)
            f.host.setForeground(true); f.host.readOriginal(); #expect(!f.host.hasOriginalSource)
        }
        f.host.selectOriginal(f.input("B")); await f.wire.add(try f.response("B")); f.host.readOriginal()
        await settle { if case .loaded(let value) = f.host.state { value.attemptID == "B" } else { false } }
        await f.wire.release(); await Task.yield()
        guard case .loaded(let value) = f.host.state else { Issue.record("B cleared by old task"); return }
        #expect(value.attemptID == "B")
    }
    @Test func accountAndOriginalSessionInvalidationHidePrivateResults() async throws {
        let s = try shell(), f = try UsageHostFixture(shell: s); try f.configure(); f.host.selectOriginal(f.input())
        await f.wire.add(try f.response()); f.host.readOriginal()
        await settle { if case .loaded = f.host.state { true } else { false } }
        try f.session.clear(); #expect(f.host.state == .unavailable)
        s.invalidateIdentity(); #expect(!f.host.hasOriginalSource && !f.host.canRead)
        f.host.readOriginal(); #expect(await f.wire.calls.count == 1)
    }
    @Test func finalAdmissionCallbackCannotPublishOrClearNewSelection() async throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure(); f.host.selectOriginal(f.input("A"))
        await f.wire.add(try f.response("A")); f.host.readOriginal()
        await settle { if case .loaded = f.host.state { true } else { false } }
        f.control.callback = { f.host.selectOriginal(f.input("B")); f.host.readOriginal() }
        await f.wire.add(try f.response("B"))
        let old = f.host.state
        if case .loaded = old { Issue.record("Old access exposed data after source switch") }
        await settle { if case .loaded(let value) = f.host.state { value.attemptID == "B" } else { false } }
        #expect(await f.wire.calls.count == 2)
    }
    @Test func credentialsRetirementPreventsOutflow() async throws {
        let f = try UsageHostFixture(shell: shell()); try f.configure(); f.host.selectOriginal(f.input())
        f.control.credentialHook = { f.host.setForeground(false) }
        f.host.readOriginal()
        await settle { !f.host.hasOriginalSource }
        #expect(f.host.state == .unavailable); #expect(await f.wire.calls.isEmpty)
    }
}
