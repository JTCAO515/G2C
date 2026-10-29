import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJRunClient

@MainActor private final class CancelStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor CancelWire: ClientTransport {
    var posts = 0
    var code = 200
    var foreign = false
    var stopped = false
    var terminal = "cancelled"
    var hook: (@MainActor @Sendable () -> Void)?
    func configure(code: Int = 200, foreign: Bool = false, terminal: String = "cancelled") {
        self.code = code; self.foreign = foreign; self.terminal = terminal
    }
    func onPost(_ hook: @escaping @MainActor @Sendable () -> Void) { self.hook = hook }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let trace = UUID().uuidString
        #expect(request.headerFields[.authorization] == "Bearer synthetic-only")
        let value: [String: Any]
        var status = 200
        if request.method == .post {
            #expect(request.path == "/v1/run-cancellations" && operationID == "cancelOriginalRun")
            let raw = try await Data(collecting: #require(body), upTo: 4096)
            let input = try JSONDecoder().decode(Components.Schemas.RunCancellationRequest.self, from: raw)
            #expect(input.message_id == "original" && input.version == .RUN_hyphen_cancel_period_1)
            posts += 1; stopped = code == 200 || code == 503; status = code
            if let hook { await hook() }
            value = ["request_id": trace, "message_id": foreign ? "foreign" : "original", "run_id": "run",
                     "status": terminal, "event_highwater": 3]
        } else {
            #expect(operationID == "getRunDisplaySnapshot")
            let state = stopped ? terminal : "running"
            value = ["request_id": trace, "snapshot": ["message_id": "original", "conversation_id": "chat",
                "generation": "g", "run_id": "run", "message_sequence": 1, "event_highwater": stopped ? 3 : 2,
                "status": state, "text": "received / 已收到", "text_state": state == "completed" ? "complete" : "partial"]]
        }
        var response = HTTPResponse(status: .init(code: status))
        response.headerFields[.contentType] = "application/json"
        response.headerFields[.cacheControl] = "no-store"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response, HTTPBody(try JSONSerialization.data(withJSONObject: value)))
    }
}
@MainActor private final class CancelChecks {
    var count = 0
    var hook: (() -> Void)?
    func fire() { count += 1; hook?() }
}
@MainActor private final class CancelFixture {
    let session = SessionLifecycle(persistence: CancelStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let wire = CancelWire()
    let model: RunDisplayModel
    let source: RunDisplaySource
    let checks = CancelChecks()
    init(enabled: Bool = true, bound: Bool = false) throws {
        operation = try session.beginTrustedSDKSave()
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!, maximumRequestBytes: 4096, maximumResponseBytes: 10000)
        let checks = checks
        let cancellation: (any ClientTransport)?
        if !enabled { cancellation = nil }
        else if bound { cancellation = RunCancellationTransport(interceptedTransport: wire, endpoint: endpoint, validate: { checks.fire() }) }
        else { cancellation = wire }
        model = try RunDisplayModel(endpoint: endpoint, maximumMessageIDBytes: 256, maximumTextBytes: 10000,
            credentials: { _ in "synthetic-only" }, transport: wire, cancellationTransport: cancellation)
        let receipt = Components.Schemas.MessageReceipt(message_id: "original", conversation_id: "chat", generation: "g", run_id: "run", sequence: 1, input_sha256: String(repeating: "a", count: 64))
        source = try RunDisplaySource(receipt: receipt, session: session, operation: operation, isCurrent: { true })
        #expect(model.select(source))
    }
    func read() async { await model.perform(model.prepareRead()) }
}
@MainActor private final class CancelLifetime {
    var active = true
    func validate() throws { if !active { throw RunDisplayFailure.staleContext } }
}
@Suite @MainActor struct RunCancellationTests {
    @Test func cancellationTransportAdmitsOnlyExactOriginalCancellation() async throws {
        let wire = CancelWire(), lifetime = CancelLifetime()
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!, maximumRequestBytes: 4096, maximumResponseBytes: 10000)
        let transport = RunCancellationTransport(interceptedTransport: wire, endpoint: endpoint, validate: { try lifetime.validate() })
        let raw = try JSONEncoder().encode(Components.Schemas.RunCancellationRequest(version: .RUN_hyphen_cancel_period_1, message_id: "original"))
        var request = HTTPRequest(method: .post, scheme: nil, authority: nil, path: "/v1/run-cancellations")
        request.headerFields[.contentType] = "application/json"
        request.headerFields[.authorization] = "Bearer synthetic-only"
        for (method, path, operation) in [(HTTPRequest.Method.put, "/v1/run-cancellations", "cancelOriginalRun"),
            (.post, "/v1/messages", "receiveMessage"), (.post, "/v1/run-cancellations?scope=foreign", "cancelOriginalRun"),
            (.post, "/v1/run-cancellations", "arbitraryWrite")] {
            var wrong = request; wrong.method = method; wrong.path = path
            await #expect(throws: (any Error).self) { try await transport.sendBound(wrong, body: HTTPBody(raw), baseURL: endpoint.url, operationID: operation, validateOriginal: {}) }
        }
        for bytes in [Data("{}".utf8), Data(String(decoding: raw, as: UTF8.self).replacingOccurrences(of: "RUN-cancel.1", with: "other").utf8), Data(repeating: 32, count: 4097)] {
            await #expect(throws: (any Error).self) { try await transport.sendBound(request, body: HTTPBody(bytes), baseURL: endpoint.url, operationID: "cancelOriginalRun", validateOriginal: {}) }
        }
        var foreign = request; foreign.authority = "foreign.invalid"
        await #expect(throws: (any Error).self) { try await transport.sendBound(foreign, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "cancelOriginalRun", validateOriginal: {}) }
        await #expect(throws: (any Error).self) { try await transport.send(request, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "cancelOriginalRun") }
        #expect(await wire.posts == 0)
        _ = try await transport.sendBound(request, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "cancelOriginalRun", validateOriginal: {})
        lifetime.active = false
        await #expect(throws: (any Error).self) { try await transport.sendBound(request, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "cancelOriginalRun", validateOriginal: {}) }
        #expect(await wire.posts == 1)
    }
    @Test(arguments: [false, true])
    func operationRetirementDuringTransportValidationPreventsPost(_ reselect: Bool) async throws {
        let f = try CancelFixture(bound: true); await f.read()
        f.checks.hook = {
            if f.checks.count == 2 {
                if reselect { _ = f.model.select(f.source) } else { f.model.invalidate() }
            }
        }
        await f.model.performCancellation(f.model.prepareCancellation())
        #expect(await f.wire.posts == 0)
        #expect(!f.model.canCancel)
    }
    @Test func boundedModelCancellationHasAValidOutflow() async throws {
        let f = try CancelFixture(bound: true); await f.read()
        await f.model.performCancellation(f.model.prepareCancellation())
        #expect(await f.wire.posts == 1)
        guard case .loaded(let value) = f.model.state else { Issue.record("valid stop failed"); return }
        #expect(value.snapshot.status == .cancelled)
    }
    @Test func onlyConfirmedSnapshotShowsCancelledAndRetainsText() async throws {
        let f = try CancelFixture(); await f.read()
        let work = try #require(f.model.prepareCancellation())
        #expect(f.model.cancellationState == .stopping && !f.model.canCancel)
        #expect(f.model.streamProgress?.text == "received / 已收到")
        await f.model.performCancellation(work)
        guard case .loaded(let value) = f.model.state else { Issue.record("canonical snapshot missing"); return }
        #expect(value.snapshot.status == .cancelled && value.snapshot.text == "received / 已收到")
        #expect(f.model.streamProgress == nil && !f.model.canCancel)
        await f.model.performCancellation(work)
        #expect(await f.wire.posts == 1)
    }
    @Test func uncertainStopKeepsPartialAndRequiresOriginalRead() async throws {
        let f = try CancelFixture(); await f.read(); await f.wire.configure(code: 503)
        await f.model.performCancellation(f.model.prepareCancellation())
        #expect(f.model.cancellationState == .unknown && !f.model.canCancel)
        #expect(f.model.streamProgress?.text == "received / 已收到")
        await f.read()
        guard case .loaded(let value) = f.model.state else { Issue.record("reconcile original failed"); return }
        #expect(value.snapshot.status == .cancelled)
        #expect(await f.wire.posts == 1)
    }
    @Test(arguments: ["denied", "foreign", "revoked"])
    func rejectionAndChangedSessionNeverPublishCancelled(_ kind: String) async throws {
        let f = try CancelFixture(); await f.read()
        if kind == "denied" { await f.wire.configure(code: 403) }
        if kind == "foreign" { await f.wire.configure(foreign: true) }
        if kind == "revoked" { await f.wire.onPost { _ = f.session.clearWithSettlement() } }
        await f.model.performCancellation(f.model.prepareCancellation())
        if case .loaded = f.model.state { Issue.record("invalid cancellation published") }
        #expect(f.model.streamProgress == nil)
    }
    @Test func reselectionCannotSkipOriginalReadAfterUnknownStop() async throws {
        let f = try CancelFixture(); await f.read(); await f.wire.configure(code: 503)
        await f.model.performCancellation(f.model.prepareCancellation())
        #expect(f.model.cancellationState == .unknown)
        #expect(f.model.select(f.source))
        #expect(!f.model.canCancel && f.model.prepareCancellation() == nil)
        await f.read()
        #expect(!f.model.canCancel)
        #expect(await f.wire.posts == 1)
    }
    @Test func priorTerminalIsNotRelabelledAsCancelled() async throws {
        let f = try CancelFixture(); await f.read(); await f.wire.configure(terminal: "completed")
        await f.model.performCancellation(f.model.prepareCancellation())
        guard case .loaded(let value) = f.model.state else { Issue.record("terminal snapshot missing"); return }
        #expect(value.snapshot.status == .completed && !f.model.canCancel)
    }
    @Test func readonlyCompositionAndNonSimulatorFactoryStayClosed() throws {
        let f = try CancelFixture(enabled: false)
        #expect(!f.model.canCancel && f.model.prepareCancellation() == nil)
        #if !DEBUG || !targetEnvironment(simulator)
        let endpoint = try MessageEndpoint(url: URL(string: "http://127.0.0.1:12345")!, maximumRequestBytes: 4096, maximumResponseBytes: 10000, allowLoopbackHTTP: true)
        #expect(throws: (any Error).self) { try RunCancellationTransport.development(endpoint: endpoint, validate: {}) }
        #endif
    }
}
