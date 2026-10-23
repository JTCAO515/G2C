import Foundation
import Testing
import CJSession
@testable import CJMessageHTTP
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJFeasibilityClient

@MainActor private final class MemorySession: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private struct Interceptor: ClientTransport {
    let sendFixture: @MainActor @Sendable (HTTPRequest, HTTPBody?, URL, String) async throws -> (HTTPResponse, HTTPBody?)
    func send(_ r: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        try await sendFixture(r, body, baseURL, operationID)
    }
}
@MainActor private final class Fixture {
    let session = SessionLifecycle(persistence: MemorySession(), restorePolicy: .userInitiatedOnly)
    var selected: FeasibilityBinding!
    var currentHook: (() -> Void)?
    var credentialsHook: (() async throws -> Void)?
    var transportHook: (() async throws -> Void)?
    var wire: [String: Any] = [:]
    var raw: Data?
    var type = "application/json"
    var cache = "no-store"
    var headerTrace = "00000000-0000-4000-8000-000000000001"
    var status: HTTPResponse.Status = .ok
    var responseCap = 262144
    var requests: [HTTPRequest] = []
    var body: HTTPBody?
    var maxItems = 128
    var canonicalTransport = false
    let original = "\n { \"action_id\":\"source-1\",\"needs_id\":\"needs-1\",\"source\":{\"kind\":\"manual\",\"text\":\"e\u{301} 原始\"},\"expected_version\":0,\"changes\":{\"budget_total\":{\"state\":\"known\",\"value\":\"100.000001\"}} }\n"
    lazy var model = try! makeModel()
    init() throws {
        selected = .init(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID(),
                         sessionOperation: try session.beginTrustedSDKSave(), needsID: "needs-1")
        let hash = digest(Data(original.utf8))
        let evidence: [String: Any] = ["path":"budget_total", "declaration":["state":"known","value":"100.000001"],
                                      "revision":1,"action_id":"source-1","original_input_sha256":hash]
        let check: [String: Any] = ["code":"BUDGET_SCOPE_UNPROVEN","status":"UNKNOWN","missing":["typed_cost_coverage"],
                                   "zh":"预算口径待核实","en":"Budget coverage unverified","details":[["amount","100.000001"]],"evidence":[evidence]]
        wire = ["request_id":headerTrace,"evaluation":["version":"CJ-FEASIBILITY-CURRENT-READ@0.1.0-candidate.1",
            "evaluator_version":"CJ-FEASIBILITY-NEEDS@0.1.0-candidate.1","status":"UNKNOWN","needs_id":"needs-1",
            "revision":1,"content_sha256":String(repeating:"a",count:64),"overall":"UNKNOWN","checks":[check],
            "sources":[["revision":1,"action_id":"source-1","original_input_utf8":original,"original_input_sha256":hash]]]]
    }
    func makeModel() throws -> FeasibilityModel {
        FeasibilityModel(session: session,
            endpoint: try MessageEndpoint(url: URL(string:"https://fixture.invalid")!, maximumRequestBytes:4096, maximumResponseBytes:responseCap),
            limits: try .init(maximumCollectionItems:maxItems, maximumSourceBytes:131072),
            credentials: { [self] _ in try await credentialsHook?(); return "synthetic-not-a-live-credential" },
            currentBinding: { [self] in currentHook?(); return selected },
            interceptedTransport: try transport())
    }
    func transport() throws -> any ClientTransport {
        let interceptor = Interceptor { [self] request, body, url, operation in
                #expect(body == nil && operation == "evaluateCurrentNeedsFeasibility" && url.absoluteString == "https://fixture.invalid")
                requests.append(request); try await transportHook?()
                var response = HTTPResponse(status:status)
                response.headerFields[.contentType] = type; response.headerFields[.cacheControl] = cache
                response.headerFields[.init("X-Request-ID")!] = headerTrace
                if let responseBody = self.body { return (response, responseBody) }
                return (response, HTTPBody(try raw ?? JSONSerialization.data(withJSONObject:wire)))
            }
        if canonicalTransport { return try NoRedirectTransport(interceptedTransport:interceptor, previewEndpoint:nil, validatePreview:nil) }
        return interceptor
    }
    func edit(_ action: (inout [String: Any]) -> Void) {
        var report = wire["evaluation"] as! [String: Any]; action(&report); wire["evaluation"] = report
    }
    func change(account: Bool = false, environment: Bool = false) {
        selected = .init(environment: environment ? UUID() : selected.environment, account: account ? UUID() : selected.account,
                         generation:selected.generation, selection:UUID(), sessionOperation:selected.sessionOperation, needsID:selected.needsID)
    }
    func read() async throws { let work = try model.prepare(selected); await model.read(work) }
}

@MainActor struct FeasibilityTests {
    @Test(arguments: ["CONFLICT", "UNKNOWN"])
    func officialGETPreservesSourcesAndDecimal(_ status: String) async throws {
        let f = try Fixture(); f.edit { $0["status"] = status }; try await f.read()
        guard case .loaded(let result) = f.model.state else { Issue.record("missing report"); return }
        #expect(result.report.status.rawValue == status && result.report.overall == .UNKNOWN)
        #expect(Data(result.report.sources[0].original_input_utf8.utf8) == Data(f.original.utf8))
        #expect(result.report.sources[0].original_input_sha256 == digest(Data(f.original.utf8)))
        let declaration = try JSONSerialization.jsonObject(with: JSONEncoder().encode(result.report.checks[0].evidence[0].declaration)) as? [String:Any]
        #expect(declaration?["value"] as? String == "100.000001")
        #expect(result.report.checks[0].zh == "预算口径待核实" && result.report.checks[0].en == "Budget coverage unverified")
        #expect(f.requests.count == 1 && f.requests[0].path == "/v1/needs-feasibility?needs_id=needs-1")
        #expect(f.requests[0].headerFields[.cacheControl] == "no-store")
    }
    @Test(arguments:["wrong-needs","overall","invalid","version","revision-bool","revision-float","hash","source-hash","source-id","source-revision","evidence-hash","mixed-null","extra","missing","null","collection","empty-checks","detail","utf8","duplicate","truncated","content-type","trace","cache","redirect","byte-cap"])
    func malformedOrMisboundWireIsNeverSuccess(_ mutation: String) async throws {
        let f = try Fixture()
        switch mutation {
        case "wrong-needs": f.edit { $0["needs_id"] = "other" }
        case "overall": f.edit { $0["overall"] = "FEASIBLE" }
        case "invalid": f.edit { $0["status"] = "INVALID" }
        case "version": f.edit { $0["version"] = "future" }
        case "revision-bool": f.edit { $0["revision"] = true }
        case "revision-float": f.edit { $0["revision"] = 1.5 }
        case "hash": f.edit { $0["content_sha256"] = "bad" }
        case "source-hash", "source-id", "source-revision":
            f.edit { r in var sources = r["sources"] as! [[String:Any]]
                sources[0][mutation == "source-hash" ? "original_input_sha256" : mutation == "source-id" ? "action_id" : "revision"] = mutation == "source-revision" ? 2 : "bad"
                r["sources"] = sources }
        case "evidence-hash", "mixed-null", "detail":
            f.edit { r in var checks = r["checks"] as! [[String:Any]]
                if mutation == "detail" { checks[0]["details"] = [["one"]] }
                else { var evidence = checks[0]["evidence"] as! [[String:Any]]
                    evidence[0][mutation == "mixed-null" ? "revision" : "original_input_sha256"] = mutation == "mixed-null" ? NSNull() : "bad"
                    checks[0]["evidence"] = evidence }
                r["checks"] = checks }
        case "extra": f.edit { $0["permission"] = true }
        case "missing": f.wire.removeValue(forKey:"evaluation")
        case "null": f.wire["evaluation"] = NSNull()
        case "collection": f.edit { $0["checks"] = Array(repeating:($0["checks"] as! [Any])[0],count:129) }
        case "empty-checks": f.edit { $0["checks"] = [] }
        case "utf8": f.raw = Data([0xff,0xfe])
        case "duplicate": f.raw = Data(#"{"request_id":"x","request_\u0069d":"y"}"#.utf8)
        case "truncated": f.raw = Data("{\"request_id\":".utf8)
        case "content-type": f.type = "text/plain"
        case "trace": f.headerTrace = UUID().uuidString
        case "cache": f.cache = "public"
        case "redirect": f.status = .temporaryRedirect
        default: f.responseCap = 16
        }
        try await f.read()
        guard case .failed = f.model.state else { Issue.record("accepted malformed fixture: \(mutation)"); return }
    }
    @Test func nullDeclarationAndUnattributedEvidenceRemainVisible() async throws {
        let f = try Fixture()
        f.edit { r in var checks = r["checks"] as! [[String:Any]]
            var evidence = checks[0]["evidence"] as! [[String:Any]]
            for key in ["declaration","revision","action_id","original_input_sha256"] { evidence[0][key] = NSNull() }
            checks[0]["evidence"] = evidence; r["checks"] = checks }
        try await f.read()
        guard case .loaded(let result) = f.model.state else { Issue.record("null original declaration lost"); return }
        #expect(result.report.overall == .UNKNOWN)
    }
    @Test func invalidBASE503StaysExplicitFailure() async throws {
        let f = try Fixture(); f.status = .serviceUnavailable
        f.wire = ["request_id":f.headerTrace,"error":["code":"FEASIBILITY_INPUT_INVALID","category":"dependency",
            "message_en":"Unverified","message_zh":"待核实","outcome":"unknown","recovery":"retry_safe_read"]]
        try await f.read()
        guard case .failed(.rejected(503,"FEASIBILITY_INPUT_INVALID")) = f.model.state else { Issue.record("BASE error coerced"); return }
        #expect(f.requests.count == 1)
    }
    @Test func oneUseAndOwnerBoundWork() async throws {
        let f = try Fixture(); let work = try f.model.prepare(f.selected)
        let other = try f.makeModel(); await other.read(work); #expect(f.requests.isEmpty)
        await f.model.read(work); await f.model.read(work); #expect(f.requests.count == 1)
    }
    @Test(arguments:["account","environment","selection","session","invalidate"])
    func lateResultsDoNotPublish(_ change: String) async throws {
        let f = try Fixture()
        f.transportHook = {
            switch change {
            case "account": f.change(account:true)
            case "environment": f.change(environment:true)
            case "selection": f.change()
            case "session": _ = try f.session.beginTrustedSDKSave()
            default: f.model.invalidate()
            }
        }
        try await f.read()
        guard case .unavailable = f.model.state else { Issue.record("late result published"); return }
    }
    @Test func credentialSwitchFencesBeforeGET() async throws {
        let f = try Fixture(); f.credentialsHook = { f.change(account:true) }
        try await f.read(); #expect(f.requests.isEmpty)
        guard case .unavailable = f.model.state else { Issue.record("credential switch not fenced"); return }
    }
    @Test func callbackReentryDoesNotConsumeNewWork() async throws {
        let f = try Fixture(); let old = try f.model.prepare(f.selected)
        var replacement: PreparedFeasibilityRead?
        f.currentHook = { f.currentHook = nil; f.change(); replacement = try! f.model.prepare(f.selected) }
        await f.model.read(old); #expect(f.requests.isEmpty)
        await f.model.read(try #require(replacement)); #expect(f.requests.count == 1)
        guard case .loaded = f.model.state else { Issue.record("replacement damaged"); return }
    }
    @Test func cancellationLeavesLoadingAndDoesNotRetry() async throws {
        let f = try Fixture(); let work = try f.model.prepare(f.selected)
        let task = Task { withUnsafeCurrentTask { $0?.cancel() }; await f.model.read(work) }
        await task.value
        guard case .cancelled = f.model.state else { Issue.record("cancel stuck loading"); return }
        #expect(f.requests.isEmpty)
        await f.model.read(work); #expect(f.requests.isEmpty)
    }
    @Test(arguments:[false,true])
    func snapshotRevisionAndHashAreMatched(_ wrongHash: Bool) async throws {
        let f = try Fixture(); let old = f.selected!
        f.selected = .init(environment:old.environment,account:old.account,generation:old.generation,selection:old.selection,
            sessionOperation:old.sessionOperation,needsID:old.needsID,acceptedRevision:wrongHash ? 1 : 2,acceptedContentSHA256:String(repeating:wrongHash ? "b" : "a",count:64))
        try await f.read()
        guard case .failed = f.model.state else { Issue.record("old snapshot accepted"); return }
    }
    @Test func publicFactoryAndMissingSourceCannotRequest() async throws {
        let f = try Fixture(); let closed = FeasibilityModel(session:f.session,currentBinding:{ f.selected })
        #expect(throws:FeasibilityFailure.unavailable) { _ = try closed.prepare(f.selected) }
        f.selected = nil
        guard case .unavailable = closed.state else { Issue.record("missing source enabled"); return }
        #expect(f.requests.isEmpty)
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
    func release(_ bytes: Data) { continuation?.resume(returning:ArraySlice(bytes)); continuation = nil }
}
@MainActor extension FeasibilityTests {
    @Test func canonicalTransport94AndSessionComposeWithOfficialGET() async throws {
        let f = try Fixture(); f.canonicalTransport = true
        try await f.read()
        guard case .loaded = f.model.state else { Issue.record("canonical GET composition failed"); return }
        #expect(f.requests.count == 1)
    }
    @Test func everyValidationCallbackCanInvalidateWithoutPublishing() async throws {
        let baseline = try Fixture(); var callbacks = 0
        baseline.currentHook = { callbacks += 1 }
        try await baseline.read(); let total = callbacks
        #expect(total > 5)
        for stop in 1...total {
            let f = try Fixture(); var count = 0
            f.currentHook = { count += 1; if count == stop { f.model.invalidate() } }
            do { try await f.read() } catch FeasibilityFailure.stale {}
            guard case .unavailable = f.model.state else { Issue.record("callback \(stop) published stale state"); continue }
        }
    }
    @Test(arguments:[false,true])
    func lateBodyAndCancellationCannotOverwriteNewResult(_ cancelled: Bool) async throws {
        let f = try Fixture(); let gate = BodyGate()
        let stream = AsyncThrowingStream<HTTPBody.ByteChunk, any Error>(unfolding: { await gate.next() })
        f.body = HTTPBody(stream,length:.unknown)
        let work = try f.model.prepare(f.selected); let old = Task { await f.model.read(work) }
        while !(await gate.started) { await Task.yield() }
        f.change(); f.body = nil
        try await f.read()
        if cancelled { old.cancel() }
        await gate.release(try JSONSerialization.data(withJSONObject:f.wire)); await old.value
        guard case .loaded = f.model.state else { Issue.record("old body damaged replacement"); return }
        #expect(f.requests.count == 2)
    }
    @Test func finalCallbackReentryKeepsNewPreparation() async throws {
        let baseline = try Fixture(); var callbacks = 0
        baseline.currentHook = { callbacks += 1 }; try await baseline.read(); let final = callbacks
        let f = try Fixture(); var count = 0; var replacement: PreparedFeasibilityRead?
        f.currentHook = {
            count += 1
            if count == final { f.currentHook = nil; replacement = try! f.model.prepare(f.selected) }
        }
        try await f.read()
        guard case .loading = f.model.state else { Issue.record("new prepare cleared"); return }
        await f.model.read(try #require(replacement))
        guard case .loaded = f.model.state else { Issue.record("new prepare unusable"); return }
    }
}

import Observation
@MainActor private final class ObservationProbeBox { var changed = false }
extension FeasibilityTests {
 @Test func testingObservationReentryMustNotPublishOldNeedsUnderNewBinding() async throws {
  let f = try Fixture(); let model = f.model
  let work = try model.prepare(f.selected)
  let box = ObservationProbeBox()
  withObservationTracking {
   _ = model.state
  } onChange: {
   MainActor.assumeIsolated {
    guard !box.changed else { return }
    box.changed = true
    let old = f.selected!
    f.selected = .init(environment: old.environment, account: old.account,
      generation: old.generation, selection: UUID(), sessionOperation: old.sessionOperation,
      needsID: "needs-2")
    _ = try? model.prepare(f.selected)
   }
  }
  await model.read(work)
  #expect(box.changed)
  if case .loaded(let observation) = model.state {
   #expect(observation.report.needs_id == f.selected.needsID)
  }
 }
}

@MainActor private final class PublicationProbeBox {
    var changes = 0
    var replacement: PreparedFeasibilityRead?
    var observedOldNeeds = false
    func track(_ f: Fixture, target: Int) {
            withObservationTracking { _ = f.model.state } onChange: {
                MainActor.assumeIsolated {
                    self.changes += 1
                    if self.changes < target { self.track(f, target: target); return }
                    guard self.changes == target else { return }
                    let old = f.selected!
                    f.selected = .init(environment: old.environment, account: old.account,
                        generation: old.generation, selection: UUID(), sessionOperation: old.sessionOperation,
                        needsID: "needs-2")
                    // The current host has changed even before its replacement preparation.
                    if case .loaded = f.model.state { self.observedOldNeeds = true }
                    self.replacement = try? f.model.prepare(f.selected)
                }
            }
    }
}
@MainActor extension FeasibilityTests {
    @Test(arguments: ["prepare-reset", "prepare-loading", "loaded", "failed", "cancelled", "invalidate"])
    func observedPublicationReentryKeepsReplacementUsable(_ stage: String) async throws {
        let f = try Fixture(); let model = f.model
        // Start from a real old loaded observation to exercise the prepare gap too.
        try await f.read()
        let oldWork = try model.prepare(f.selected)
        if stage == "failed" { f.transportHook = { throw FeasibilityFailure.exchangeFailed } }
        if stage == "cancelled" { f.transportHook = { throw CancellationError() } }
        let box = PublicationProbeBox()
        let target = stage == "prepare-loading" ? 2 : 1
        box.track(f, target: target)
        if stage.hasPrefix("prepare-") {
            #expect(throws: FeasibilityFailure.stale) { _ = try model.prepare(f.selected) }
        } else if stage == "invalidate" { model.invalidate() }
        else { await model.read(oldWork) }
        #expect(box.changes >= target && !box.observedOldNeeds)
        guard case .loading = model.state else { Issue.record("replacement publication lost at \(stage)"); return }
        let replacement = try #require(box.replacement)
        f.transportHook = nil
        let original = f.original.replacingOccurrences(of:"needs-1",with:"needs-2")
        let hash = digest(Data(original.utf8))
        f.edit { report in
            report["needs_id"] = "needs-2"
            var sources = report["sources"] as! [[String:Any]]
            sources[0]["original_input_utf8"] = original; sources[0]["original_input_sha256"] = hash
            report["sources"] = sources
            var checks = report["checks"] as! [[String:Any]]
            var evidence = checks[0]["evidence"] as! [[String:Any]]
            evidence[0]["original_input_sha256"] = hash; checks[0]["evidence"] = evidence; report["checks"] = checks
        }
        await model.read(replacement)
        guard case .loaded(let observation) = model.state else { Issue.record("replacement unusable at \(stage)"); return }
        #expect(observation.report.needs_id == "needs-2")
        #expect(f.requests.last?.path == "/v1/needs-feasibility?needs_id=needs-2")
    }
    @Test func observedPrepareDoesNotExposePriorLoadedValueBeforeMutation() async throws {
        let f = try Fixture(); try await f.read()
        let model = f.model; let box = PublicationProbeBox()
        withObservationTracking { _ = model.state } onChange: {
            MainActor.assumeIsolated {
                box.changes += 1
                if case .loaded = model.state { box.observedOldNeeds = true }
            }
        }
        _ = try model.prepare(f.selected)
        #expect(box.changes == 1 && !box.observedOldNeeds)
        guard case .loading = model.state else { Issue.record("prepare notification lost"); return }
    }
}
