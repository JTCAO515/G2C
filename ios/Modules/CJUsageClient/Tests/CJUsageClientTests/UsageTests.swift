import Foundation
import Testing
import CJSession
@testable import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJUsageClient

@MainActor final class MemorySession: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
struct Intercept: ClientTransport {
    let action: @MainActor @Sendable (HTTPRequest, HTTPBody?, URL, String) async throws -> (HTTPResponse, HTTPBody?)
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        try await action(request, body, baseURL, operationID)
    }
}
@MainActor final class Harness {
    let session = SessionLifecycle(persistence: MemorySession(), restorePolicy: .userInitiatedOnly)
    let endpoint = try! MessageEndpoint(url: URL(string: "https://synthetic.invalid")!, maximumRequestBytes: 4096, maximumResponseBytes: 16384)
    var selected: UsageBinding!
    var requests: [HTTPRequest] = []
    var credentialHook: (() async throws -> String?)?
    var currentHook: (() -> Void)?
    var responseHook: (() async throws -> Void)?
    var wire: [String: Any] = [:]
    var delayedBody: HTTPBody?
    var raw: Data?
    var responseStatus: HTTPResponse.Status = .ok
    var trace = "0237bca3-5300-41e7-9945-a46c2b774725"
    var contentType = "application/json"
    var cache = "no-store"
    lazy var model: UsageViewModel = makeModel()
    func makeModel() -> UsageViewModel {
        UsageViewModel(session: session, endpoint: endpoint,
        credentials: { [self] _ in if let credentialHook { return try await credentialHook() }; return "synthetic-not-a-credential" },
        currentBinding: { [self] in currentHook?(); return selected },
        interceptedTransport: Intercept { [self] request, body, url, operation in
            #expect(body == nil && url == endpoint.url && operation == "getUsageAttemptStatus")
            requests.append(request)
            try await responseHook?()
            var response = HTTPResponse(status: responseStatus)
            response.headerFields[.contentType] = contentType
            response.headerFields[.cacheControl] = cache
            response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
            if let delayedBody { return (response, delayedBody) }
            return (response, HTTPBody(try raw ?? JSONSerialization.data(withJSONObject: ["request_id": trace, "attempt": wire])))
        })
    }
    init(attempt: String = "original/+%e\u{301}", status: String = "unknown") throws {
        selected = UsageBinding(source: UsageSource(attemptID: attempt, operationID: "original-op", runID: "original-run"),
            sessionOperation: try session.beginTrustedSDKSave(), actorIdentity: Data("actor-A".utf8), selectionGeneration: UUID(), revision: 1)
        wire = ["attempt_id": attempt, "operation_id": "original-op", "run_id": "original-run", "status": status,
            "unit": "opaque-unit", "reserved_units": "999999999999999999999999999999999999999999999999999999",
            "confirmed_units": NSNull(), "confirmed_output": NSNull(), "receipt_id": NSNull(),
            "cancelled": false, "exceeded": false, "message_en": "Synthetic", "message_zh": "合成"]
        if status == "released" { wire["cancelled"] = true }
        if status == "settled" { wire["confirmed_units"] = "0"; wire["confirmed_output"] = "0"; wire["receipt_id"] = "original-receipt" }
    }
    func read() async throws { let prepared = try model.prepare(selected); await model.read(prepared) }
    func changeSelection(actor: String = "actor-A", revision: UInt64 = 1) {
        selected = UsageBinding(source: selected.source, sessionOperation: selected.sessionOperation,
            actorIdentity: Data(actor.utf8), selectionGeneration: UUID(), revision: revision)
    }
}

@MainActor struct UsageTests {
    @Test func exactOriginalGETAndBigIntegerUnknownThenActualZero() async throws {
        let h = try Harness(); try await h.read()
        guard case .loaded(let original) = h.model.state else { Issue.record("not loaded"); return }
        #expect(original.confirmedUnits == nil && original.confirmedOutput == nil && original.receiptID == nil)
        #expect(original.reservedUnits == h.wire["reserved_units"] as? String)
        #expect(h.requests.count == 1 && h.requests[0].method == .get && h.requests[0].headerFields[.cacheControl] == "no-store")
        let path = try #require(h.requests.first?.path)
        let query = try #require(URLComponents(string: "https://synthetic.invalid" + path)?.queryItems)
        #expect(query.count == 1 && query[0].name == "attempt_id")
        #expect(Data((query[0].value ?? "").utf8) == Data(h.selected.source.attemptID.utf8))
        h.wire["status"] = "settled"; h.wire["confirmed_units"] = "0"; h.wire["confirmed_output"] = "0"; h.wire["receipt_id"] = "r"
        try await h.read()
        guard case .loaded(let settled) = h.model.state else { Issue.record("not settled"); return }
        #expect(settled.confirmedUnits == "0" && settled.confirmedOutput == "0" && settled.receiptID == "r")
    }
    @Test(arguments: ["reserved", "unknown", "released", "settled"])
    func statesAndBilingualMeaning(_ status: String) async throws {
        let h = try Harness(status: status); try await h.read()
        guard case .loaded(let result) = h.model.state else { Issue.record("missing status"); return }
        #expect(result.status.rawValue == status)
        #expect(!result.status.label(.english).isEmpty && !result.status.label(.chinese).isEmpty)
        if status == "settled" {
            h.wire["cancelled"] = true; h.wire["exceeded"] = true; try await h.read()
            guard case .loaded(let final) = h.model.state else { Issue.record("cancelled receipt unreadable"); return }
            #expect(final.cancelled && final.exceeded)
        }
    }
    @Test(arguments: ["leading-zero", "negative", "number", "missing", "receipt-conflict", "released-live", "reserved-cancelled", "unknown-exceeded", "null-settled", "bool-number", "extra", "bad-id", "normalized-id", "operation", "run", "blank-message"])
    func invalidWireFailsExplicitly(_ mutation: String) async throws {
        let h = try Harness()
        switch mutation {
        case "leading-zero": h.wire["reserved_units"] = "01"
        case "negative": h.wire["confirmed_units"] = "-1"
        case "number": h.wire["reserved_units"] = 1
        case "missing": h.wire.removeValue(forKey: "confirmed_units")
        case "receipt-conflict": h.wire["receipt_id"] = "r"
        case "released-live": h.wire["status"] = "released"
        case "reserved-cancelled": h.wire["status"] = "reserved"; h.wire["cancelled"] = true
        case "unknown-exceeded": h.wire["exceeded"] = true
        case "null-settled": h.wire["status"] = "settled"
        case "bool-number": h.wire["cancelled"] = 1
        case "extra": h.wire["balance"] = "0"
        case "bad-id": h.wire["unit"] = ""
        case "normalized-id": h.wire["attempt_id"] = h.selected.source.attemptID.precomposedStringWithCanonicalMapping
        case "operation": h.wire["operation_id"] = "other"
        case "run": h.wire["run_id"] = "other"
        default: h.wire["message_en"] = ""
        }
        try await h.read()
        guard case .failed = h.model.state else { Issue.record("invalid wire accepted: \(mutation)"); return }
    }
    @Test(arguments: ["trace", "type", "cache", "redirect", "oversize", "duplicate", "malformed", "error"])
    func transportFailureIsSanitized(_ mutation: String) async throws {
        let h = try Harness()
        switch mutation {
        case "trace": h.trace = "bad"
        case "type": h.contentType = "text/plain"
        case "cache": h.cache = "public"
        case "redirect": h.responseStatus = .temporaryRedirect
        case "oversize": h.raw = Data(repeating: 32, count: 20000)
        case "duplicate": h.raw = Data("{\"request_id\":\"\(h.trace)\",\"request_id\":\"\(h.trace)\",\"attempt\":{}}".utf8)
        case "malformed": h.raw = Data("[".utf8)
        default:
            h.responseStatus = .serviceUnavailable
            h.raw = Data("{\"request_id\":\"\(h.trace)\",\"error\":{\"code\":\"PROVIDER_UNAVAILABLE\",\"message_en\":\"Unavailable\",\"message_zh\":\"不可用\",\"recovery\":\"none\"}}".utf8)
        }
        try await h.read()
        guard case .failed = h.model.state else { Issue.record("bad transport accepted"); return }
    }
    @Test func missingConfigurationAndSourceNeverRequest() throws {
        let h = try Harness()
        let model = UsageViewModel(session: h.session, currentBinding: { h.selected })
        #expect(throws: UsageFailure.unavailable) { try model.prepare(h.selected) }
        #expect(model.state == .unavailable && h.requests.isEmpty)
        h.selected = UsageBinding(source: UsageSource(attemptID: ""), sessionOperation: h.selected.sessionOperation,
            actorIdentity: Data("A".utf8), selectionGeneration: UUID(), revision: 1)
        #expect(throws: UsageFailure.unavailable) { try h.model.prepare(h.selected) }
    }
    @Test func preparationIsOneShotAndOwnedByOneModel() async throws {
        let h = try Harness(); let prepared = try h.model.prepare(h.selected)
        let other = UsageViewModel(session: h.session, currentBinding: { h.selected })
        await other.read(prepared); #expect(h.requests.isEmpty)
        await h.model.read(prepared); await h.model.read(prepared)
        #expect(h.requests.count == 1)
    }
    @Test func equalRevisionPrepareReentryDoesNotOverwriteNewOwner() async throws {
        let h = try Harness(); var inner: PreparedUsageRead?
        h.currentHook = {
            h.currentHook = nil
            inner = try? h.model.prepare(h.selected)
        }
        #expect(throws: UsageFailure.stale) { try h.model.prepare(h.selected) }
        #expect(h.model.state == .loading)
        await h.model.read(try #require(inner))
        guard case .loaded = h.model.state else { Issue.record("inner owner lost"); return }
    }
    @Test(arguments: ["actor", "ABA", "session", "credential-error", "credential-reentry", "response-ABA", "final-callback"])
    func lifecycleFences(_ stage: String) async throws {
        let h = try Harness(); var newer: PreparedUsageRead?
        if stage == "response-ABA" {
            h.responseHook = { h.changeSelection(); h.changeSelection() }
        } else if stage == "final-callback" {
            // Observe a response, then count subsequent validation callbacks. The
            // fifth callback is the final settlement check after generated decode.
            var afterResponse = false; var count = 0
            h.responseHook = { afterResponse = true }
            h.currentHook = {
                if afterResponse { count += 1; if count == 5 { h.changeSelection() } }
            }
        } else {
            h.credentialHook = {
                switch stage {
                case "actor": h.changeSelection(actor: "actor-B")
                case "ABA": h.changeSelection(); h.changeSelection()
                case "session": _ = try h.session.beginTrustedSDKSave()
                case "credential-error": h.changeSelection(); throw UsageFailure.exchangeFailed
                default:
                    h.credentialHook = nil
                    newer = try h.model.prepare(h.selected)
                    await h.model.read(try #require(newer))
                    throw UsageFailure.exchangeFailed
                }
                return "synthetic-not-a-credential"
            }
        }
        try await h.read()
        if stage == "credential-reentry" {
            guard case .loaded = h.model.state else { Issue.record("old error overwrote newer task"); return }
            #expect(h.requests.count == 1)
        } else {
            #expect(h.model.state == .unavailable)
            if !["response-ABA", "final-callback"].contains(stage) { #expect(h.requests.isEmpty) }
        }
    }
}

private actor BodyGate {
    private(set) var started = false
    private var delivered = false
    private var continuation: CheckedContinuation<HTTPBody.ByteChunk?, Never>?
    func next() async -> HTTPBody.ByteChunk? {
        guard !delivered else { return nil }; delivered = true; started = true
        return await withCheckedContinuation { continuation = $0 }
    }
    func release(_ bytes: Data) { continuation?.resume(returning: ArraySlice(bytes)); continuation = nil }
}

@MainActor extension UsageTests {
    @Test func canonicalDefaultReadTransportWithGeneratedClient() async throws {
        let h = try Harness()
        let transport = try NoRedirectTransport(interceptedTransport: Intercept { request, body, _, _ in
            #expect(request.method == .get && body == nil)
            let items = try #require(URLComponents(string: "https://synthetic.invalid" + (request.path ?? ""))?.queryItems)
            #expect(items.count == 1 && Data((items[0].value ?? "").utf8) == Data(h.selected.source.attemptID.utf8))
            var response = HTTPResponse(status: .ok)
            response.headerFields[.contentType] = "application/json"
            response.headerFields[.cacheControl] = "no-store"
            response.headerFields[HTTPField.Name("X-Request-ID")!] = h.trace
            return (response, HTTPBody(try JSONSerialization.data(withJSONObject: ["request_id": h.trace, "attempt": h.wire])))
        }, previewEndpoint: nil, validatePreview: nil)
        let model = UsageViewModel(session: h.session, endpoint: h.endpoint, credentials: { _ in "synthetic" },
            currentBinding: { h.selected }, liveReadTransport: transport)
        let prepared = try model.prepare(h.selected); await model.read(prepared)
        guard case .loaded = model.state else { Issue.record("canonical default GET failed"); return }
    }
    @Test func missingCredentialsAndInvalidationNeverBecomeZero() async throws {
        let h = try Harness(); h.credentialHook = { nil }; try await h.read()
        #expect(h.model.state == .failed(.unavailable) && h.requests.isEmpty)
        h.credentialHook = nil; try await h.read(); h.model.invalidate()
        #expect(h.model.state == .unavailable)
    }
    @Test(arguments: [false, true])
    func bodyAwaitSelectionSwitchAndLateCancellationDoNotClearNewRead(_ cancel: Bool) async throws {
        let h = try Harness()
        let gate = BodyGate()
        let stream = AsyncThrowingStream<HTTPBody.ByteChunk, any Error>(unfolding: { await gate.next() })
        h.delayedBody = HTTPBody(stream, length: .unknown)
        let prepared = try h.model.prepare(h.selected)
        let old = Task { await h.model.read(prepared) }
        while !(await gate.started) { await Task.yield() }
        h.changeSelection(); h.delayedBody = nil
        let newer = try h.model.prepare(h.selected)
        await h.model.read(newer)
        if cancel { old.cancel() }
        await gate.release(try JSONSerialization.data(withJSONObject: ["request_id": h.trace, "attempt": h.wire]))
        await old.value
        guard case .loaded = h.model.state else { Issue.record("old body/cancel cleared new result"); return }
        #expect(h.requests.count == 2)
    }
    @Test func finalCallbackReentryPreservesNewerPreparation() async throws {
        let h = try Harness(); var received = false; var count = 0; var newer: PreparedUsageRead?
        h.responseHook = { received = true }
        h.currentHook = {
            guard received else { return }
            count += 1
            if count == 5 {
                h.currentHook = nil
                newer = try? h.model.prepare(h.selected)
            }
        }
        try await h.read()
        #expect(newer != nil && h.model.state == .loading)
        await h.model.read(try #require(newer))
        guard case .loaded = h.model.state else { Issue.record("final callback lost newer owner"); return }
    }
}
