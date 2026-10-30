import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJRunClient

@MainActor private final class TravelRunSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws { }
    func clearAndBlock() throws { }
}
private let travelTrace = "7ac6d943-3772-4aa2-aea7-aed4c819a6f5"
private func travelReceipt() -> Components.Schemas.MessageReceipt {
    .init(message_id:"m/+e\u{301}",conversation_id:"chat",generation:"g",run_id:"run",sequence:3,input_sha256:String(repeating:"a",count:64))
}
private func travelReference(version: Int = 7,epoch: Int = 2) -> Components.Schemas.MessageTravelReference {
    .travel(.init(version:.MESSAGE_hyphen_travel_hyphen_reference_period_1,conversation_id:"chat",generation:"g",message_id:travelReceipt().message_id,
        run_id:"run",sequence:3,input_sha256:String(repeating:"a",count:64),message_version:.MESSAGE_hyphen_send_period_2,context_kind:.travel,
        context_id:String(repeating:"a",count:32),context_version:version,selection_epoch:epoch))
}
private actor TravelRunWire: ClientTransport {
    var operations: [String] = []
    var bodies: [Data] = []
    var status = "running"
    var mutation = ""
    var postMode = ""
    var hook: (@MainActor @Sendable () -> Void)?
    func configure(_ mutation: String = "",postMode: String = "") { self.mutation = mutation;self.postMode = postMode }
    func onReturn(_ hook: @escaping @MainActor @Sendable () -> Void) { self.hook = hook }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        operations.append(operationID)
        #expect(request.headerFields[.authorization] == "Bearer synthetic-only")
        let original = travelReceipt()
        let reference = try JSONSerialization.jsonObject(with:JSONEncoder().encode(travelReference(version:mutation == "reference" ? 8 : 7)))
        var object: [String:Any]
        if operationID == "getTravelRunDisplay" {
            #expect(request.path?.hasPrefix("/v2/run-display?") == true && request.method == .get)
            object = ["request_id":travelTrace,"version":"RUN-display.2","snapshot":["message_id":original.message_id,"conversation_id":"chat",
                "generation":"g","run_id":"run","message_sequence":3,"event_highwater":status == "running" ? 2 : 3,
                "status":status,"text":"原回答e\u{301}","text_state":"partial"],"reference":reference]
            if mutation == "version" { object["version"] = "RUN-display.9" }
            if mutation == "missing" { object.removeValue(forKey:"reference") }
        } else if operationID == "getTravelRunDraftStatus" {
            #expect(request.path?.hasPrefix("/v3/run-draft-status?") == true)
            object = ["request_id":travelTrace,"version":"RUN-draft-status.3","message_id":original.message_id,"conversation_id":"chat","generation":"g",
                "run_id":"run","message_sequence":3,"event_highwater":status == "running" ? 2 : 3,"run_status":status,
                "draft_outcome":"not_requested","budget_exhausted_stage":mutation == "budget" ? "answer" : "none","reference":reference]
            if mutation == "draftReference" { object["reference"] = try JSONSerialization.jsonObject(with:JSONEncoder().encode(travelReference(epoch:3))) }
        } else {
            #expect(operationID == "cancelOriginalTravelRun" && request.method == .post && request.path == "/v2/run-cancellations")
            let raw = try await Data(collecting:body!,upTo:65536);bodies.append(raw)
            let input = try JSONDecoder().decode(Components.Schemas.RunTravelCancellationRequest.self,from:raw)
            #expect(Data(input.message_id.utf8) == Data(original.message_id.utf8))
            status = "cancelled"
            if postMode == "lostACK" { throw URLError(.networkConnectionLost) }
            object = ["request_id":travelTrace,"version":"RUN-cancel.2","message_id":original.message_id,"run_id":"run","status":status,"event_highwater":3,"reference":reference]
            if postMode == "reference" { object["reference"] = try JSONSerialization.jsonObject(with:JSONEncoder().encode(travelReference(epoch:3))) }
        }
        if let hook { await hook() }
        var response = HTTPResponse(status:.ok);response.headerFields[.contentType] = "application/json"
        response.headerFields[.cacheControl] = "no-store";response.headerFields[HTTPField.Name("X-Request-ID")!] = travelTrace
        return (response,HTTPBody(try JSONSerialization.data(withJSONObject:object)))
    }
}
@MainActor private final class TravelRunFixture {
    let session = SessionLifecycle(persistence:TravelRunSessionStore(),restorePolicy:.userInitiatedOnly)
    let operation: SessionOperation
    let wire = TravelRunWire()
    let model: RunDisplayModel
    var current = true
    init(draft: Bool = true) throws {
        operation = try session.beginTrustedSDKSave()
        let endpoint = try MessageEndpoint(url:URL(string:"https://synthetic.invalid")!,maximumRequestBytes:65536,maximumResponseBytes:65536)
        let cancel = RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,travel:true,validate:{})
        model = try RunDisplayModel(endpoint:endpoint,maximumMessageIDBytes:16384,maximumTextBytes:10000,
            credentials:{ _ in "synthetic-only" },transport:wire,cancellationTransport:cancel,readsDraftStatus:draft)
        let source = try RunDisplaySource(receipt:travelReceipt(),travelReference:travelReference(),session:session,operation:operation,isCurrent:{ [weak self] in self?.current == true })
        #expect(model.select(source))
    }
    func read() async { await model.perform(model.prepareRead()) }
}

@MainActor struct TravelRunTests {
    @Test func explicitTravelReadUsesOnlyTypedRoutesAndKeepsOriginalPayload() async throws {
        let f = try TravelRunFixture();await f.read()
        guard case .loaded(let answer) = f.model.state,case .loadedTravel(let draft) = f.model.draftStatus else { Issue.record("typed read missing");return }
        #expect(Data(answer.snapshot.text.utf8) == Data("原回答e\u{301}".utf8))
        guard case .travel(let reference) = draft.reference else { Issue.record("lost original reference");return }
        #expect(reference.context_version == 7 && reference.selection_epoch == 2)
        #expect(f.model.draftStatus.budgetLabel(.chinese) == nil && f.model.draftStatus.runStatus == .running)
        #expect(!f.model.supportsStreaming && f.model.prepareStream() == nil)
        #expect(await f.wire.operations == ["getTravelRunDisplay","getTravelRunDraftStatus"])
    }
    @Test(arguments:["reference","version","missing"])
    func referenceAndVersionMismatchNeverPublishOrTryLegacy(mutation: String) async throws {
        let f = try TravelRunFixture();await f.wire.configure(mutation);await f.read()
        guard case .unavailable = f.model.state else { Issue.record("invalid typed snapshot published");return }
        #expect(await f.wire.operations == ["getTravelRunDisplay"])
    }
    @Test func draftReferenceMismatchLeavesVerifiedAnswerButDraftUnavailable() async throws {
        let f = try TravelRunFixture();await f.wire.configure("draftReference");await f.read()
        guard case .loaded = f.model.state,case .unavailable = f.model.draftStatus else { Issue.record("draft reference mismatch hidden");return }
    }
    @Test func cancellationIsOriginalBoundAndReadBackThroughTypedReference() async throws {
        let f = try TravelRunFixture();await f.read();#expect(f.model.canCancel)
        await f.model.performCancellation(f.model.prepareCancellation())
        guard case .loaded(let value) = f.model.state else { Issue.record("cancel readback missing");return }
        #expect(value.snapshot.status == .cancelled && value.snapshot.text == "原回答e\u{301}")
        #expect(await f.wire.bodies.count == 1)
        #expect(await f.wire.operations == ["getTravelRunDisplay","getTravelRunDraftStatus","cancelOriginalTravelRun","getTravelRunDisplay","getTravelRunDraftStatus"])
    }
    @Test func lostCancellationACKOnlyAllowsOriginalReadBeforeAnyNewStop() async throws {
        let f = try TravelRunFixture();await f.read();await f.wire.configure(postMode:"lostACK")
        await f.model.performCancellation(f.model.prepareCancellation())
        #expect(f.model.cancellationState == .unknown && !f.model.canCancel)
        await f.model.performCancellation(f.model.prepareCancellation());#expect(await f.wire.bodies.count == 1)
        await f.read()
        guard case .loaded(let value) = f.model.state else { Issue.record("original cancellation result missing");return }
        #expect(value.snapshot.status == .cancelled && !f.model.canCancel)
    }
    @Test func cancelledResponseCannotRebindOriginalSelectionEpoch() async throws {
        let f = try TravelRunFixture();await f.read();await f.wire.configure(postMode:"reference")
        await f.model.performCancellation(f.model.prepareCancellation())
        #expect(f.model.cancellationState == .unknown)
        guard case .unavailable = f.model.state else { Issue.record("wrong cancellation association published");return }
        #expect(await f.wire.operations.filter({ $0 == "getTravelRunDisplay" }).count == 1)
    }
    @Test func invalidSourceAssociationAndRetiredIdentityCannotPublish() async throws {
        let f = try TravelRunFixture()
        #expect(throws:RunDisplayFailure.invalidReference) { try RunDisplaySource(receipt:travelReceipt(),travelReference:travelReference(epoch:4),session:f.session,operation:f.operation,isCurrent:{true}) }
        await f.wire.onReturn { f.current = false }
        await f.read()
        guard case .unavailable = f.model.state else { Issue.record("late original leaked");return }
        #expect(await f.wire.operations == ["getTravelRunDisplay"])
    }
}
