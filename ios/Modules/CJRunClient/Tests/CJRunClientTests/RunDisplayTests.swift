import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJRunClient

private let trace = "7ac6d943-3772-4aa2-aea7-aed4c819a6f5"
private let messageID = "m/+%e\u{301}中文"
private let sensitive = "正文 PRIVATE_SENTINEL e\u{301} 中文 🐼"
@MainActor private final class Store: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor Interceptor: ClientTransport {
    var bytes: Data
    var status = 200
    var traceHeader: String? = trace
    var cache: String? = "no-store"
    var count = 0
    var paths: [String] = []
    var hold = false
    var continuation: CheckedContinuation<Void, Never>?
    var hook: (@MainActor @Sendable () -> Void)?
    init(_ bytes: Data) { self.bytes = bytes }
    func configure(bytes: Data? = nil, status: Int = 200, traceHeader: String? = trace, cache: String? = "no-store") {
        if let bytes { self.bytes = bytes }; self.status = status; self.traceHeader = traceHeader; self.cache = cache
    }
    func pause() { hold = true }
    func release() { hold = false; continuation?.resume(); continuation = nil }
    func setHook(_ hook: @escaping @MainActor @Sendable () -> Void) { self.hook = hook }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && operationID == "getRunDisplaySnapshot" && body == nil)
        #expect(request.headerFields[.authorization] == "Bearer synthetic-only")
        count += 1; paths.append(request.path ?? "")
        if hold { await withCheckedContinuation { continuation = $0 } }
        if let hook { await hook() }
        var response = HTTPResponse(status: .init(code: status))
        if let traceHeader { response.headerFields[HTTPField.Name("X-Request-ID")!] = traceHeader }
        if let cache { response.headerFields[.cacheControl] = cache }
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
}
private func receipt(_ id: String = messageID) -> Components.Schemas.MessageReceipt {
    .init(message_id: id, conversation_id: "chat-e\u{301}", generation: "generation", run_id: "run", sequence: 41, input_sha256: String(repeating: "a", count: 64))
}
private func snapshot(status: String = "running", text: String = sensitive, highwater: Int = 2) -> [String: Any] {
    ["conversation_id": "chat-e\u{301}", "generation": "generation", "message_id": messageID, "run_id": "run",
     "message_sequence": 41, "status": status, "event_highwater": highwater, "text": text,
     "text_state": status == "completed" ? "complete" : "partial"]
}
private func encoded(_ value: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: ["request_id": trace, "snapshot": value])
}
@MainActor private final class Fixture {
    let session = SessionLifecycle(persistence: Store(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let transport: Interceptor
    var source: RunDisplaySource!
    var model: RunDisplayModel!
    var current = true
    var callback: (() -> Void)?
    var credentialCallback: (() async -> Void)?
    init(bytes: Data? = nil, maxText: Int = 4096, maxBody: Int = 8192, maxID: Int = 512) throws {
        operation = try session.beginTrustedSDKSave()
        transport = Interceptor(try bytes ?? encoded(snapshot()))
        source = try RunDisplaySource(receipt: receipt(), session: session, operation: operation, isCurrent: { [weak self] in
            guard let self else { return false }; self.callback?(); return self.current
        })
        model = try RunDisplayModel(endpoint: MessageEndpoint(url: URL(string: "https://synthetic.invalid")!, maximumRequestBytes: 2048, maximumResponseBytes: maxBody), maximumMessageIDBytes: maxID, maximumTextBytes: maxText, credentials: { [weak self] op in
            guard let self else { return nil }; #expect(op == self.operation)
            await self.credentialCallback?(); return "synthetic-only"
        }, transport: transport)
        _ = model.select(source)
    }
    func read() async { let work = model.prepareRead(); await model.perform(work) }
    func loaded() -> RunDisplayValue? { if case .loaded(let value) = model.state { value } else { nil } }
    func unavailable() -> Bool { if case .unavailable = model.state { true } else { false } }
}

@MainActor struct RunDisplayTests {
    @Test(arguments: ["queued", "running", "completed", "failed", "cancelled", "context_invalid", "unknown"])
    func sevenStates(_ status: String) async throws {
        let text = status == "queued" ? "" : sensitive
        let f = try Fixture(bytes: encoded(snapshot(status: status, text: text, highwater: status == "queued" ? 0 : 3)))
        await f.read()
        let value = try #require(f.loaded())
        #expect(value.snapshot.status.rawValue == status)
        #expect(exact(value.snapshot.text, text))
        #expect((value.snapshot.text_state == .complete) == (status == "completed"))
        #expect(value.snapshot.message_sequence == 41 && value.snapshot.event_highwater != 41)
        #expect(value.requestID == trace)
        #expect(!f.model.state.label(.english).isEmpty && !f.model.state.label(.chinese).isEmpty)
        #expect(!String(reflecting: value).contains("PRIVATE_SENTINEL"))
        #expect(!String(reflecting: f.model.state).contains("PRIVATE_SENTINEL"))
        let paths = await f.transport.paths
        let items = try #require(URLComponents(string: paths[0])?.queryItems)
        #expect(items.count == 1 && items[0].name == "message_id")
        #expect(exact(items[0].value!, messageID))
    }
    @Test(arguments: ["conversation_id", "generation", "message_id", "run_id", "message_sequence"])
    func referenceMismatch(_ field: String) async throws {
        var value = snapshot(); value[field] = field == "message_sequence" ? 42 : "foreign"
        let f = try Fixture(bytes: encoded(value)); await f.read(); #expect(f.unavailable())
    }
    @Test func normalizedIDIsNotOriginal() async throws {
        var value = snapshot(); value["message_id"] = messageID.precomposedStringWithCanonicalMapping
        let f = try Fixture(bytes: encoded(value)); await f.read(); #expect(f.unavailable())
    }
    @Test(arguments: ["missing", "missingSnapshot", "null", "extra", "unknownStatus", "completePartial", "negative", "bool", "queuedText", "duplicate", "invalidJSON"])
    func malformed(_ kind: String) async throws {
        var value = snapshot(); var bytes: Data
        switch kind {
        case "missing": value.removeValue(forKey: "generation")
        case "extra": value["scope"] = "private"
        case "unknownStatus": value["status"] = "invented"
        case "completePartial": value["text_state"] = "complete"
        case "negative": value["event_highwater"] = -1
        case "bool": value["message_sequence"] = true
        case "queuedText": value["status"] = "queued"
        default: break
        }
        bytes = try encoded(value)
        if kind == "null" { bytes = Data("{\"request_id\":\"\(trace)\",\"snapshot\":null}".utf8) }
        if kind == "missingSnapshot" { bytes = Data("{\"request_id\":\"\(trace)\"}".utf8) }
        if kind == "invalidJSON" { bytes = Data("{invalid".utf8) }
        if kind == "duplicate" { bytes = Data("{\"request_id\":\"\(trace)\",\"request_id\":\"\(trace)\",\"snapshot\":null}".utf8) }
        let f = try Fixture(bytes: bytes); await f.read(); #expect(f.unavailable())
    }
    @Test(arguments: ["noTrace", "wrongTrace", "noCache", "cacheable", "redirect"])
    func headers(_ kind: String) async throws {
        let f = try Fixture()
        await f.transport.configure(status: kind == "redirect" ? 302 : 200,
            traceHeader: kind == "noTrace" ? nil : (kind == "wrongTrace" ? UUID().uuidString : trace),
            cache: kind == "noCache" ? nil : (kind == "cacheable" ? "public" : "no-store"))
        await f.read(); #expect(f.unavailable()); #expect(await f.transport.count == 1)
    }
    @Test(arguments: [401, 413, 503, 429])
    func rejectionDoesNotCreateAnswer(_ status: Int) async throws {
        let f = try Fixture()
        let error = try JSONEncoder().encode(Components.Schemas.ErrorResponse(request_id: trace,
            error: .init(code: "unavailable", category: "dependency", message_en: "Unavailable", message_zh: "不可用",
                         outcome: .unknown, recovery: .retry_safe_read)))
        await f.transport.configure(bytes: error, status: status)
        await f.read(); #expect(f.unavailable()); #expect(await f.transport.count == 1)
        if case .unavailable(.rejected(let actual)) = f.model.state { #expect(actual == status) }
        else { Issue.record("Expected explicit HTTP rejection") }
    }
    @Test func explicitByteLimits() async throws {
        let f = try Fixture(maxText: sensitive.utf8.count - 1); await f.read(); #expect(f.unavailable())
        let bounded = try Fixture(maxBody: 40); await bounded.read(); #expect(bounded.unavailable())
        let id = try Fixture(maxID: messageID.utf8.count - 1); await id.read(); #expect(await id.transport.count == 0)
    }
    @Test func duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse() async throws {
        let f = try Fixture(); let work = f.model.prepareRead()
        #expect(f.model.prepareRead() == nil)
        await f.model.perform(work); await f.model.perform(work); #expect(await f.transport.count == 1)
        await f.read(); #expect(await f.transport.count == 2)
        #expect(exact(try #require(f.loaded()).snapshot.text, sensitive))
    }
    @Test(arguments: ["lower", "sameConflict", "prefixConflict", "terminalRevive"])
    func inconsistentSnapshots(_ kind: String) async throws {
        let f = try Fixture(bytes: encoded(snapshot(status: kind == "terminalRevive" ? "completed" : "running")))
        await f.read(); #expect(f.loaded() != nil)
        let next = snapshot(text: kind == "prefixConflict" || kind == "sameConflict" ? "different" : sensitive,
                            highwater: kind == "lower" ? 1 : (kind == "sameConflict" ? 2 : 3))
        await f.transport.configure(bytes: try encoded(next)); await f.read(); #expect(f.unavailable())
    }
    @Test func increasingSnapshotReplacesRatherThanAppends() async throws {
        let f = try Fixture(); await f.read()
        await f.transport.configure(bytes: try encoded(snapshot(status: "completed", text: sensitive + " end", highwater: 4)))
        await f.read(); #expect(exact(try #require(f.loaded()).snapshot.text, sensitive + " end"))
    }
    @Test(arguments: ["selection", "background", "session", "source"])
    func queuedWorkRetiresBeforeGET(_ change: String) async throws {
        let f = try Fixture(); let work = f.model.prepareRead()
        switch change {
        case "selection": _ = f.model.select(f.source)
        case "background": f.model.invalidate()
        case "session": _ = try f.session.beginTrustedSDKSave()
        default: f.current = false
        }
        await f.model.perform(work); #expect(await f.transport.count == 0); #expect(f.loaded() == nil)
    }
    @Test func credentialAwaitCannotRedirectOldRead() async throws {
        let f = try Fixture()
        f.credentialCallback = { _ = f.model.select(f.source) }
        await f.read(); #expect(await f.transport.count == 0)
        if case .ready = f.model.state {} else { Issue.record("New selection was changed") }
    }
    @Test func reentrantPrepareAndSelectionAreFenced() async throws {
        let f = try Fixture(); var nested: RunDisplayWork?
        f.callback = { f.callback = nil; nested = f.model.prepareRead() }
        let outer = f.model.prepareRead(); #expect(outer == nil); #expect(nested != nil)
        await f.model.perform(nested); #expect(await f.transport.count == 1)
        f.callback = { f.callback = nil; _ = f.model.select(f.source) }
        #expect(f.model.prepareRead() == nil)
        if case .ready = f.model.state {} else { Issue.record("Reentrant selection must survive") }
    }
    @Test func lateResponseCannotClearNewSelection() async throws {
        let f = try Fixture()
        await f.transport.setHook { _ = f.model.select(f.source) }
        await f.read()
        if case .ready = f.model.state {} else { Issue.record("Late response changed new selection") }
        #expect(f.loaded() == nil)
    }
    @Test func cancellationIsUnknownWithoutRetry() async throws {
        let f = try Fixture(); await f.transport.pause()
        let work = f.model.prepareRead(); let task = Task { await f.model.perform(work) }
        while await f.transport.count == 0 { await Task.yield() }
        task.cancel(); await f.transport.release(); await task.value
        if case .unavailable(.cancelled) = f.model.state {} else { Issue.record("Cancellation not explicit") }
        #expect(await f.transport.count == 1)
    }
    @Test func lazyAndEagerSourceInvalidationDoNotExposeText() async throws {
        let f = try Fixture(); await f.read(); #expect(f.loaded() != nil)
        f.current = false; #expect(f.loaded() == nil); #expect(f.unavailable())
        f.current = true; _ = f.model.select(f.source); await f.read(); f.model.invalidate()
        if case .unselected = f.model.state {} else { Issue.record("Background retained display") }
    }
    @Test(arguments: ["background", "session", "source"])
    func responseCallbackInvalidation(_ change: String) async throws {
        let f = try Fixture()
        await f.transport.setHook {
            switch change {
            case "background": f.model.invalidate()
            case "session": _ = try? f.session.beginTrustedSDKSave()
            default: f.current = false
            }
        }
        await f.read(); #expect(f.loaded() == nil); #expect(await f.transport.count == 1)
    }
    @Test func retiredWorkCannotReadAnotherMessageOrAnotherModel() async throws {
        let f = try Fixture(); let work = f.model.prepareRead()
        let other = try RunDisplaySource(receipt: receipt("another-message"), session: f.session, operation: f.operation, isCurrent: { true })
        #expect(f.model.select(other)); await f.model.perform(work)
        let g = try Fixture(); await g.model.perform(work)
        #expect(await f.transport.count == 0); #expect(await g.transport.count == 0)
        if case .ready = f.model.state {} else { Issue.record("Old work affected another message") }
    }
    @Test func sessionClearHidesAlreadyLoadedText() async throws {
        let f = try Fixture(); await f.read(); #expect(f.loaded() != nil)
        try f.session.clear(); #expect(f.loaded() == nil); #expect(f.unavailable())
    }

}
