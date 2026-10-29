import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJRunClient

private let draftTrace = "7ac6d943-3772-4aa2-aea7-aed4c819a6f5"
private let draftID = "original/+%e\u{301}中文"
@MainActor private final class DraftStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor DraftTransport: ClientTransport {
    var outcome: String
    var mutation: String
    var paths: [String] = []
    var continuation: CheckedContinuation<Void, Never>?
    var held = false
    var entered = false
    init(_ outcome: String, mutation: String) { self.outcome = outcome; self.mutation = mutation }
    func pause() { held = true }
    func release() { held = false; continuation?.resume(); continuation = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && body == nil)
        #expect(request.headerFields[.authorization] == "Bearer synthetic")
        paths.append(request.path ?? "")
        let draft = request.path?.hasPrefix("/v1/run-draft-status?") == true
        let status = mutation == "cancelled" ? "cancelled" : mutation == "unknown" ? "unknown" : "completed"
        var reference: [String: Any] = ["conversation_id":"conversation", "generation":"generation", "message_id":draftID,
            "run_id":"run", "message_sequence":1, "event_highwater":4]
        var object: [String: Any]
        if draft {
            #expect(operationID == "getRunDraftStatus")
            #expect(URLComponents(string: request.path!)?.queryItems?.first?.value == draftID)
            entered = true
            if held { await withCheckedContinuation { continuation = $0 } }
            if mutation == "offline" { throw URLError(.notConnectedToInternet) }
            reference["request_id"] = draftTrace; reference["version"] = "RUN-draft-status.1"
            reference["run_status"] = status; reference["draft_outcome"] = outcome
            if ["message_id", "run_id", "generation", "conversation_id"].contains(mutation) { reference[mutation] = "foreign" }
            if mutation == "sequence" { reference["message_sequence"] = 2 }
            if mutation == "highwater" { reference["event_highwater"] = 3 }
            if mutation == "terminal" { reference["run_status"] = "running"; reference["event_highwater"] = 5 }
            if mutation == "version" { reference["version"] = "RUN-draft-status.2" }
            if mutation == "trace" { reference["request_id"] = UUID().uuidString }
            if mutation == "extra" { reference["secret"] = "PRIVATE_SENTINEL" }
            object = reference
        } else {
            reference["status"] = status; reference["text"] = "Original answer"; reference["text_state"] = status == "completed" ? "complete" : "partial"
            object = ["request_id":draftTrace, "snapshot":reference]
        }
        var response = HTTPResponse(status: .init(code: draft && ["401","403"].contains(mutation) ? Int(mutation)! : 200))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = draftTrace
        response.headerFields[.cacheControl] = draft && mutation == "cache" ? "public" : "no-store"
        response.headerFields[.contentType] = "application/json"
        let data = try JSONSerialization.data(withJSONObject: object)
        return (response, HTTPBody(data))
    }
}
@MainActor private final class DraftFixture {
    let session = SessionLifecycle(persistence: DraftStore(), restorePolicy: .userInitiatedOnly)
    let transport: DraftTransport
    let model: RunDisplayModel
    var current = true
    init(_ outcome: String = "validation_failed", mutation: String = "", enabled: Bool = true) throws {
        let operation = try session.beginTrustedSDKSave()
        transport = DraftTransport(outcome, mutation: mutation)
        model = try RunDisplayModel(endpoint: MessageEndpoint(url: URL(string:"https://synthetic.invalid")!, maximumRequestBytes:2048, maximumResponseBytes:4096), maximumMessageIDBytes:256, maximumTextBytes:2000,
            credentials:{ _ in "synthetic" }, transport:transport, readsDraftStatus:enabled)
        let source = try RunDisplaySource(receipt:.init(message_id:draftID, conversation_id:"conversation", generation:"generation", run_id:"run", sequence:1, input_sha256:String(repeating:"a",count:64)), session:session, operation:operation, isCurrent:{ [weak self] in self?.current == true })
        #expect(model.select(source))
    }
    func read() async { await model.perform(model.prepareRead()) }
}
@MainActor struct RunDraftStatusTests {
    @Test(arguments: ["not_requested","not_recorded","published","validation_failed","provider_failed","provider_unknown"])
    func sixOutcomesPreserveAnswer(_ outcome: String) async throws {
        let f = try DraftFixture(outcome); await f.read()
        guard case .loaded(let answer) = f.model.state, case .loaded(let result) = f.model.draftStatus else { Issue.record("missing actual read"); return }
        #expect(answer.snapshot.text == "Original answer" && answer.snapshot.status == .completed)
        #expect(result.draft_outcome.rawValue == outcome)
        #expect(!f.model.draftStatus.label(.english).isEmpty && !f.model.draftStatus.label(.chinese).isEmpty)
        #expect(await f.transport.paths.count == 2)
        #expect(!String(reflecting:f.model.draftStatus).contains(draftID))
    }
    @Test(arguments: ["message_id","run_id","generation","conversation_id","sequence","highwater","terminal","version","trace","extra","cache","offline"])
    func rejectedDraftCannotReplaceAnswer(_ mutation: String) async throws {
        let f = try DraftFixture(mutation:mutation); await f.read()
        guard case .loaded(let answer) = f.model.state, case .unavailable = f.model.draftStatus else { Issue.record("must preserve answer and fail draft read"); return }
        #expect(answer.snapshot.text == "Original answer")
        #expect(await f.transport.paths.count == 2)
    }
    @Test(arguments:["401","403"])
    func serverRevocationHidesPrivateResults(_ status: String) async throws {
        let f = try DraftFixture(mutation:status); await f.read()
        if case .loaded = f.model.state { Issue.record("revoked answer visible") }
        if case .loaded = f.model.draftStatus { Issue.record("revoked draft visible") }
        #expect(await f.transport.paths.count == 2)
    }
    @Test func unknownEnumFailsClosed() async throws {
        let f = try DraftFixture("future_success"); await f.read()
        guard case .unavailable = f.model.draftStatus else { Issue.record("unknown enum accepted"); return }
        #expect(await f.transport.paths.count == 2)
    }
    @Test(arguments:["cancelled","unknown"])
    func draftDoesNotChangeRunTerminal(_ status: String) async throws {
        let f = try DraftFixture("provider_unknown", mutation:status); await f.read()
        guard case .loaded(let answer) = f.model.state, case .loaded(let draft) = f.model.draftStatus else { Issue.record("missing original results"); return }
        #expect(answer.snapshot.status.rawValue == status && draft.run_status.rawValue == status)
        #expect(await f.transport.paths.count == 2)
    }
    @Test(arguments:["source","session","selection"])
    func delayedResponseRetired(_ change: String) async throws {
        let f = try DraftFixture(); await f.transport.pause()
        let work = f.model.prepareRead()
        let task = Task { await f.model.perform(work) }
        while !(await f.transport.entered) { await Task.yield() }
        switch change {
        case "source": f.current = false
        case "session": _ = try f.session.beginTrustedSDKSave()
        default: f.model.invalidate()
        }
        await f.transport.release(); await task.value
        if case .loaded = f.model.draftStatus { Issue.record("old private response published") }
        if case .loaded = f.model.state { Issue.record("old answer remained") }
        #expect(await f.transport.paths.count == 2)
    }
    @Test func disabledConsumerMakesNoDraftRequest() async throws {
        let f = try DraftFixture(enabled:false); await f.read()
        #expect(await f.transport.paths.count == 1)
        guard case .unread = f.model.draftStatus else { Issue.record("unexpected activation"); return }
    }
}
