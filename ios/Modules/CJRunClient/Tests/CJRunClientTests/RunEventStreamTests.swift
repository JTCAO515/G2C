import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJRunClient

private let streamTrace = "6978af59-198c-4208-b27d-14ef28493fb9"
private let originalID = "original/+%中文"
private let answer = "北京🐼e\u{301}"
private func event(_ kind: String, _ offset: Int, _ field: String, _ value: String) throws -> String {
    let data = try JSONSerialization.data(withJSONObject: [field: value], options: [.withoutEscapingSlashes])
    return "event: \(kind)\nid: \(offset)\ndata: \(String(decoding: data, as: UTF8.self))\n\n"
}
private func complete(_ text: String = answer, status: String = "completed") throws -> String {
    try event("delta", text.utf8.count, "text", text) + event("status", text.utf8.count, "status", status)
}
@MainActor private final class StreamStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor StreamTransport: ClientTransport {
    var wire: String
    var finalText = answer
    var finalStatus = "completed"
    var status = 200
    var snapshotStatus: Int?
    func snapshotFailure(_ code: Int) { snapshotStatus = code }
    var contentType = "text/event-stream; charset=utf-8"
    var trace = streamTrace
    var requests: [(String, String)] = []
    var startupFailures = 0
    func failStartup(_ count: Int) { startupFailures = count }
    var hold = false
    var continuation: AsyncThrowingStream<ArraySlice<UInt8>, Error>.Continuation?
    init(_ wire: String) { self.wire = wire }
    func configure(wire: String? = nil, finalText: String? = nil, status: Int = 200,
                   contentType: String = "text/event-stream; charset=utf-8", trace: String = streamTrace) {
        if let wire { self.wire = wire }; if let finalText { self.finalText = finalText }
        self.status = status; self.contentType = contentType; self.trace = trace
    }
    func pause() { hold = true }
    func finish(with bytes: String = "") {
        if !bytes.isEmpty { continuation?.yield(Array(bytes.utf8)[...]) }
        continuation?.finish(); continuation = nil
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && body == nil)
        #expect(request.headerFields[.authorization] == "Bearer synthetic-only")
        let offset = request.headerFields[HTTPField.Name("Last-Event-ID")!] ?? ""
        requests.append((operationID, offset))
        let parts = try #require(URLComponents(string: request.path ?? ""))
        #expect(parts.queryItems == [URLQueryItem(name: "message_id", value: originalID)])
        if operationID == "streamRunEvents", startupFailures > 0 {
            startupFailures -= 1
            return (HTTPResponse(status: .serviceUnavailable), HTTPBody(Data()))
        }
        var response = HTTPResponse(status: .init(code: operationID == "getRunDisplaySnapshot" ? (snapshotStatus ?? status) : status))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.cacheControl] = "no-store"
        if operationID == "streamRunEvents" {
            #expect(parts.path == "/v1/run-events")
            response.headerFields[.contentType] = contentType
            let (stream, continuation) = AsyncThrowingStream<ArraySlice<UInt8>, Error>.makeStream()
            // Split every byte, including inside multibyte Unicode scalars.
            for byte in wire.utf8 { continuation.yield([byte][...]) }
            if hold { self.continuation = continuation } else { continuation.finish() }
            return (response, HTTPBody(stream, length: .unknown))
        }
        #expect(operationID == "getRunDisplaySnapshot" && parts.path == "/v1/run-display")
        response.headerFields[.contentType] = "application/json"
        if snapshotStatus == 503 {
            let error: [String: Any] = ["request_id": streamTrace, "error": ["code": "RUN_UNAVAILABLE", "category": "dependency", "message_en": "Unavailable", "message_zh": "不可用", "outcome": "unknown", "recovery": "retry_safe_read"]]
            return (response, HTTPBody(try JSONSerialization.data(withJSONObject: error)))
        }
        let snapshot: [String: Any] = ["message_id": originalID, "conversation_id": "chat", "generation": "g",
            "run_id": "run", "message_sequence": 1, "event_highwater": 3, "status": finalStatus,
            "text": finalText, "text_state": finalStatus == "completed" ? "complete" : "partial"]
        let bytes = try JSONSerialization.data(withJSONObject: ["request_id": streamTrace, "snapshot": snapshot])
        return (response, HTTPBody(bytes))
    }
}
@MainActor private final class StreamFixture {
    let session = SessionLifecycle(persistence: StreamStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let transport: StreamTransport
    let model: RunDisplayModel
    var current = true
    init(_ wire: String, textLimit: Int = 4096, wireLimit: Int = 8192) throws {
        operation = try session.beginTrustedSDKSave()
        transport = StreamTransport(wire)
        model = try RunDisplayModel(endpoint: MessageEndpoint(url: URL(string: "https://synthetic.invalid")!,
            maximumRequestBytes: 2048, maximumResponseBytes: wireLimit), maximumMessageIDBytes: 256,
            maximumTextBytes: textLimit, credentials: { _ in "synthetic-only" }, transport: transport)
        let source = try RunDisplaySource(receipt: .init(message_id: originalID, conversation_id: "chat", generation: "g",
            run_id: "run", sequence: 1, input_sha256: String(repeating: "a", count: 64)), session: session,
            operation: operation, isCurrent: { [weak self] in self?.current == true })
        #expect(model.select(source))
    }
    func read() async { let work = model.prepareStream(); await model.perform(work) }
    var failure: RunDisplayFailure? { if case .unavailable(let f) = model.state { f } else { nil } }
}

@MainActor struct RunEventStreamTests {
    /// Opt-in real local HTTP/PG check; absent configuration is explicitly SKIPPED.
    /// The harness creates only disposable local identities and FakeProvider answers.
    @Test func finalSnapshot503NeverRestartsAnObservedStream() async throws {
        let f = try StreamFixture(complete()); await f.transport.snapshotFailure(503)
        await f.model.performInitialStream(f.model.prepareStream())
        #expect(await f.transport.requests.map { $0.0 } == ["streamRunEvents", "getRunDisplaySnapshot"])
        guard case .unavailable(.rejected(status: 503)) = f.model.state else { Issue.record("snapshot failure hidden"); return }
    }
    @Test func initialRunStartupRetriesOnlyOriginalGET() async throws {
        let f = try StreamFixture(complete())
        await f.transport.failStartup(1)
        await f.model.performInitialStream(f.model.prepareStream())
        guard case .loaded(let value) = f.model.state else { Issue.record("startup did not recover"); return }
        #expect(value.snapshot.text == answer)
        #expect(await f.transport.requests.map { $0.0 } == ["streamRunEvents", "streamRunEvents", "getRunDisplaySnapshot"])
    }
    @Test func initialRunStartupHasFiniteReadBudget() async throws {
        let f = try StreamFixture(complete()); await f.transport.failStartup(10)
        await f.model.performInitialStream(f.model.prepareStream())
        #expect(await f.transport.requests.count == 3)
        guard case .unavailable(.rejected(status: 503)) = f.model.state else { Issue.record("persistent failure hidden"); return }
    }
    @Test(arguments: [401, 403, 429])
    func initialRunDenialIsNotRetried(_ code: Int) async throws {
        let f = try StreamFixture(complete()); await f.transport.configure(status: code)
        await f.model.performInitialStream(f.model.prepareStream())
        #expect(await f.transport.requests.count == 1)
    }
    @Test func initialReadDelayCannotOutliveSource() async throws {
        let f = try StreamFixture(complete()); await f.transport.failStartup(10)
        let work = f.model.prepareStream()
        let task = Task { await f.model.performInitialStream(work) }
        for _ in 0..<2000 { if await f.transport.requests.count == 1 { break }; await Task.yield() }
        f.current = false
        await task.value
        #expect(await f.transport.requests.count == 1)
        #expect(f.model.streamProgress == nil)
    }

    @Test(.enabled(if: ProcessInfo.processInfo.environment["CJ_RUN_STREAM_TEST_URL"] != nil))
    func liveLoopback() async throws {
        let env = ProcessInfo.processInfo.environment
        let url = try #require(env["CJ_RUN_STREAM_TEST_URL"].flatMap(URL.init(string:)))
        #expect(url.scheme == "http" && url.host == "127.0.0.1")
        let bearer = try #require(env["CJ_RUN_STREAM_TEST_TOKEN"])
        let foreign = try #require(env["CJ_RUN_STREAM_TEST_FOREIGN_TOKEN"])
        let cases = try JSONDecoder().decode([LiveCase].self,
            from: Data(try #require(env["CJ_RUN_STREAM_TEST_CASES"]).utf8))
        for item in cases {
            for (credential, allowed) in [(bearer, true), (foreign, false)] {
                let session = SessionLifecycle(persistence: StreamStore(), restorePolicy: .userInitiatedOnly)
                let operation = try session.beginTrustedSDKSave()
                let source = try RunDisplaySource(receipt: item.receipt, session: session, operation: operation, isCurrent: { true })
                let transport = try NoRedirectTransport(requestTimeout: 10, resourceTimeout: 20)
                let model = try RunDisplayModel(endpoint: MessageEndpoint(url: url, maximumRequestBytes: 4096,
                    maximumResponseBytes: 400000, allowLoopbackHTTP: true), maximumMessageIDBytes: 256,
                    maximumTextBytes: 200000, credentials: { _ in credential }, liveReadTransport: transport)
                #expect(model.select(source))
                let work = model.prepareStream(); await model.perform(work)
                if allowed {
                    guard case .loaded(let value) = model.state else { Issue.record("local stream not loaded"); continue }
                    #expect(value.snapshot.text == item.text && value.snapshot.status == .completed)
                } else {
                    guard case .unavailable(.rejected(status: 503)) = model.state else {
                        Issue.record("foreign original message was not withheld"); continue
                    }
                    #expect(model.streamProgress == nil)
                }
            }
        }
    }
    @Test func unicodeFragmentsAndCanonicalFinalSnapshot() async throws {
        let f = try StreamFixture(complete())
        let work = f.model.prepareStream(); await f.model.perform(work); await f.model.perform(work)
        guard case .loaded(let value) = f.model.state else { Issue.record("not loaded"); return }
        #expect(value.snapshot.text == answer && value.snapshot.event_highwater == 3)
        #expect(f.model.streamProgress == nil)
        let requests = await f.transport.requests
        #expect(requests.map(\.0) == ["streamRunEvents", "getRunDisplaySnapshot"])
        #expect(requests[0].1 == "0")
    }
    @Test func disconnectRetainsPartialAndExplicitResumeUsesBytes() async throws {
        let first = "北京"
        let f = try StreamFixture(event("delta", first.utf8.count, "text", first))
        await f.read()
        #expect(f.failure == .unavailable && f.model.streamProgress?.text == first)
        #expect(await f.transport.requests.count == 1) // no automatic reconnect or snapshot success
        let remainder = "🐼e\u{301}"
        await f.transport.configure(wire: try event("delta", answer.utf8.count, "text", remainder)
            + event("status", answer.utf8.count, "status", "completed"))
        await f.read()
        guard case .loaded(let value) = f.model.state else { Issue.record("resume not loaded"); return }
        #expect(value.snapshot.text == answer)
        let requests = await f.transport.requests
        #expect(requests[1].1 == String(first.utf8.count))
    }
    @Test func terminalMustMatchProtectedSnapshot() async throws {
        let f = try StreamFixture(complete())
        await f.transport.configure(finalText: "different")
        await f.read()
        #expect(f.failure == .inconsistentSnapshot)
        #expect(f.model.streamProgress == nil)
    }
    @Test func serverWithdrawalHidesPreviouslyReceivedText() async throws {
        let f = try StreamFixture(event("delta", answer.utf8.count, "text", answer))
        await f.read()
        #expect(f.model.streamProgress?.text == answer)
        await f.transport.configure(wire: try event("status", answer.utf8.count, "status", "unavailable"))
        await f.read()
        #expect(f.failure == .rejected(status: 503) && f.model.streamProgress == nil)
        #expect(await f.transport.requests.count == 2)
    }
    @Test(arguments: [301, 401, 409, 503]) func rejectedReadsNeverRetry(_ status: Int) async throws {
        let f = try StreamFixture(complete()); await f.transport.configure(status: status)
        await f.read(); #expect(f.failure == .rejected(status: status))
        #expect(await f.transport.requests.count == 1)
    }
    @Test(arguments: ["media", "trace"]) func invalidHeaders(_ kind: String) async throws {
        let f = try StreamFixture(complete())
        await f.transport.configure(contentType: kind == "media" ? "application/json" : "text/event-stream",
                                    trace: kind == "trace" ? "invalid" : streamTrace)
        await f.read(); #expect(f.failure == .invalidResponse)
    }
    @Test func invalidationDuringStreamWithholdsLateContent() async throws {
        let f = try StreamFixture(event("delta", answer.utf8.count, "text", answer))
        await f.transport.pause()
        let work = f.model.prepareStream()
        let task = Task { await f.model.perform(work) }
        for _ in 0..<1000 { if f.model.streamProgress != nil { break }; await Task.yield() }
        #expect(f.model.streamProgress?.text == answer)
        f.current = false; f.model.invalidate()
        await f.transport.finish(with: try event("status", answer.utf8.count, "status", "completed"))
        await task.value
        #expect(f.model.streamProgress == nil)
        if case .unselected = f.model.state {} else { Issue.record("late content returned") }
        #expect(await f.transport.requests.count == 1)
    }
    @Test func cancelledReadIsUnknownNotCompleted() async throws {
        let f = try StreamFixture(event("delta", answer.utf8.count, "text", answer))
        await f.transport.pause()
        let work = f.model.prepareStream(); let task = Task { await f.model.perform(work) }
        for _ in 0..<1000 { if f.model.streamProgress != nil { break }; await Task.yield() }
        task.cancel(); await f.transport.finish(); await task.value
        #expect(f.failure == .cancelled)
    }
    @Test(arguments: ["offset", "duplicate", "unknown", "truncated", "afterTerminal", "textLimit", "wireLimit", "invalidUTF8"])
    func malformedStreamsFailClosed(_ kind: String) throws {
        var parser = try RunEventParser(text: "", maximumTextBytes: kind == "textLimit" ? 1 : 4096,
                                        maximumWireBytes: kind == "wireLimit" ? 1 : 8192)
        var wire = try complete()
        switch kind {
        case "offset": wire = try event("delta", 1, "text", answer)
        case "duplicate": wire = "event: delta\nid: 1\ndata: {\"text\":\"a\",\"text\":\"b\"}\n\n"
        case "unknown": wire = try event("status", 0, "status", "invented")
        case "truncated": wire.removeLast()
        case "afterTerminal": wire += try event("delta", answer.utf8.count + 1, "text", "x")
        case "invalidUTF8":
            #expect(throws: (any Error).self) { _ = try parser.append([255, 10][...]) }; return
        default: break
        }
        #expect(throws: (any Error).self) { _ = try parser.append(Array(wire.utf8)[...]); try parser.finish() }
    }
    @Test func crlfAndTerminalUnknownArePreserved() throws {
        var parser = try RunEventParser(text: "", maximumTextBytes: 4096, maximumWireBytes: 8192)
        let wire = try complete(status: "unknown").replacingOccurrences(of: "\n", with: "\r\n")
        _ = try parser.append(Array(wire.utf8)[...]); try parser.finish()
        #expect(parser.progress.status == "unknown")
        #expect(!String(reflecting: parser.progress).contains(answer))
    }
}

private struct LiveCase: Decodable {
    let receipt: Components.Schemas.MessageReceipt
    let text: String
}
