import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJRunClient

private let tripRunTrace="7ac6d943-3772-4aa2-aea7-aed4c819a6f5"
private func tripRunReceipt() -> Components.Schemas.MessageReceipt {
    .init(message_id:"m/+e\u{301}",conversation_id:"chat",generation:"g",run_id:"run",sequence:3,input_sha256:String(repeating:"a",count:64))
}
private func tripRunReference(epoch:Int=2) -> [String:Any] {
    ["version":"MESSAGE-trip-reference.1","message_version":"MESSAGE-send.3","message_id":tripRunReceipt().message_id,
     "conversation_id":"chat","generation":"g","run_id":"run","sequence":3,"input_sha256":String(repeating:"a",count:64),
     "selection_epoch":epoch,"context_kind":"trip","context_id":"trip-a","context_version":7,
     "trip_context":["id":"trip-a","expected_version":7,"day":["date":"2026-11-01","timezone":"Asia/Shanghai"],"item_id":"item-a"],
     "content_version":"structured.2","content_sha256":String(repeating:"b",count:64)]
}
@MainActor private final class TripRunStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material:SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor TripRunWire: ClientTransport {
    var operations:[String]=[],bodies:[Data]=[]
    var mutation="",postMode="",status="running"
    var returned:(@MainActor @Sendable ()->Void)?
    func configure(_ mutation:String="",postMode:String="") { self.mutation=mutation;self.postMode=postMode }
    func onReturn(_ callback:@escaping @MainActor @Sendable ()->Void) { returned=callback }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        operations.append(operationID)
        #expect(request.headerFields[.authorization]=="Bearer synthetic-only")
        let original=tripRunReceipt()
        var reference=tripRunReference(epoch:mutation=="reference" ? 3 : 2)
        if mutation=="hash" { reference["content_sha256"]=String(repeating:"c",count:64) }
        if mutation=="day" { reference["trip_context"]=["id":"trip-a","expected_version":7,"day":NSNull(),"item_id":"item-a"] }
        var value:[String:Any]
        if operationID=="getTripRunDisplayV3" {
            #expect(request.path?.hasPrefix("/v3/run-display?")==true && request.method == .get)
            value=["request_id":tripRunTrace,"version":"RUN-display.3","reference":reference,
                "snapshot":["conversation_id":"chat","generation":"g","message_id":original.message_id,"run_id":"run","message_sequence":3,
                "event_highwater":status=="running" ? 2 : 3,"status":status,"text":"原回答e\u{301}","text_state":"partial"]]
            if mutation=="version" { value["version"]="RUN-display.4" }
            if mutation=="missing" { value.removeValue(forKey:"reference") }
            if mutation=="owner" { value["owner_scope"]="caller" }
        } else if operationID=="getTripRunDraftStatusV4" {
            #expect(request.path?.hasPrefix("/v4/run-draft-status?")==true)
            value=["request_id":tripRunTrace,"version":"RUN-draft-status.4","reference":mutation=="draftReference" ? tripRunReference(epoch:3) : reference,
                "conversation_id":"chat","generation":"g","message_id":original.message_id,"run_id":"run","message_sequence":3,
                "event_highwater":status=="running" ? 2 : 3,"run_status":status,"draft_outcome":"not_requested","budget_exhausted_stage":"none"]
        } else {
            #expect(operationID=="cancelOriginalTripRunV3" && request.method == .post && request.path=="/v3/run-cancellations")
            let raw=try await Data(collecting:#require(body),upTo:65536);bodies.append(raw)
            let fields=try #require(JSONSerialization.jsonObject(with:raw) as? [String:Any])
            #expect(Set(fields.keys)==["version","message_id"] && fields["version"] as? String == "RUN-cancel.3")
            #expect(Data((fields["message_id"] as! String).utf8)==Data(original.message_id.utf8))
            status="cancelled"
            if postMode=="lostACK" { throw URLError(.networkConnectionLost) }
            value=["request_id":tripRunTrace,"version":"RUN-cancel.3","reference":postMode=="reference" ? tripRunReference(epoch:3) : reference,
                "message_id":original.message_id,"run_id":"run","event_highwater":3,"status":status]
        }
        var bytes=try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys])
        if mutation=="decimal" { bytes=Data(String(decoding:bytes,as:UTF8.self).replacingOccurrences(of:"\"message_sequence\":3",with:"\"message_sequence\":3.0").utf8) }
        if mutation=="referenceDecimal" { bytes=Data(String(decoding:bytes,as:UTF8.self).replacingOccurrences(of:"\"expected_version\":7",with:"\"expected_version\":7.0").utf8) }
        if let returned { await returned() }
        var headers=HTTPFields();headers[.contentType]=mutation=="media" ? "text/html" : "application/json"
        headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=tripRunTrace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(bytes))
    }
}
@MainActor private final class TripRunFixture {
    let session=SessionLifecycle(persistence:TripRunStore(),restorePolicy:.userInitiatedOnly)
    let operation:SessionOperation
    let wire=TripRunWire()
    let model:RunDisplayModel
    var current=true
    init() throws {
        operation=try session.beginTrustedSDKSave()
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let cancel=RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,tripCompatible:true,validate:{})
        model=try RunDisplayModel(endpoint:endpoint,maximumMessageIDBytes:16384,maximumTextBytes:10000,credentials:{ _ in "synthetic-only" },transport:wire,cancellationTransport:cancel,readsDraftStatus:true)
        let bytes=try JSONSerialization.data(withJSONObject:["reference":tripRunReference()])
        let reference=try MessageTripReference.decodeResponseReference(bytes,maximumBytes:65536)
        let source=try RunDisplaySource(receipt:tripRunReceipt(),tripReference:reference,session:session,operation:operation,isCurrent:{ [weak self] in self?.current==true })
        #expect(model.select(source))
    }
    func read() async { await model.perform(model.prepareRead()) }
}
@MainActor struct TripRunTests {
    @Test func originalTripDayItemEpochAndHashSurviveReadAndDraftStatus() async throws {
        let f=try TripRunFixture();await f.read()
        guard case .loaded(let answer)=f.model.state,case .loadedTrip(let draft)=f.model.draftStatus else { Issue.record("original Trip response missing");return }
        #expect(Data(answer.snapshot.text.utf8)==Data("原回答e\u{301}".utf8))
        #expect(draft.reference.trip?.day?.timezone=="Asia/Shanghai" && draft.reference.trip?.itemID=="item-a" && draft.reference.selectionEpoch==2)
        #expect(draft.draftOutcome == .not_requested && f.model.draftStatus.budgetLabel(.chinese)==nil)
        #expect(!f.model.supportsStreaming && f.model.prepareStream()==nil)
        #expect(await f.wire.operations==["getTripRunDisplayV3","getTripRunDraftStatusV4"])
    }
    @Test(arguments:["reference","hash","day","version","missing","owner","decimal","referenceDecimal","media"])
    func malformedOrChangedReferenceNeverFallsBackToOldWire(mutation:String) async throws {
        let f=try TripRunFixture();await f.wire.configure(mutation);await f.read()
        guard case .unavailable=f.model.state else { Issue.record("changed original reference published");return }
        #expect(await f.wire.operations==["getTripRunDisplayV3"])
    }
    @Test func mismatchedDraftReferenceCannotReplaceVerifiedAnswer() async throws {
        let f=try TripRunFixture();await f.wire.configure("draftReference");await f.read()
        guard case .loaded=f.model.state,case .unavailable=f.model.draftStatus else { Issue.record("draft mismatch hidden");return }
    }
    @Test func cancellationUsesOriginalV3AndReadsBackSameAssociation() async throws {
        let f=try TripRunFixture();await f.read();#expect(f.model.canCancel)
        await f.model.performCancellation(f.model.prepareCancellation())
        guard case .loaded(let answer)=f.model.state else { Issue.record("cancel readback missing");return }
        #expect(answer.snapshot.status == .cancelled && f.model.cancellationState == .idle)
        #expect(await f.wire.bodies.count==1)
        #expect(await f.wire.operations==["getTripRunDisplayV3","getTripRunDraftStatusV4","cancelOriginalTripRunV3","getTripRunDisplayV3","getTripRunDraftStatusV4"])
    }
    @Test func unknownCancellationOnlyQueriesOriginalAndNeverAutomaticallyPostsAgain() async throws {
        let f=try TripRunFixture();await f.read();await f.wire.configure(postMode:"lostACK")
        await f.model.performCancellation(f.model.prepareCancellation());#expect(f.model.cancellationState == .unknown && !f.model.canCancel)
        await f.model.performCancellation(f.model.prepareCancellation());#expect(await f.wire.bodies.count==1)
        await f.read()
        guard case .loaded(let answer)=f.model.state else { Issue.record("original cancellation unreadable");return }
        #expect(answer.snapshot.status == .cancelled && !f.model.canCancel)
    }
    @Test func cancelEpochChangeOrAccountRetirementWithholdsPrivateResponse() async throws {
        let f=try TripRunFixture();await f.read();await f.wire.configure(postMode:"reference")
        await f.model.performCancellation(f.model.prepareCancellation());#expect(f.model.cancellationState == .unknown)
        guard case .unavailable=f.model.state else { Issue.record("wrong epoch published");return }
        let other=try TripRunFixture();await other.wire.onReturn { other.current=false };await other.read()
        guard case .unavailable=other.model.state else { Issue.record("retired owner response published");return }
        #expect(await other.wire.operations==["getTripRunDisplayV3"])
    }
    @Test func previousCancellationCapabilitiesCannotAcquireV3Writes() async throws {
        let wire=TripRunWire(),endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let raw=try JSONSerialization.data(withJSONObject:["version":"RUN-cancel.3","message_id":tripRunReceipt().message_id])
        var request=HTTPRequest(method:.post,scheme:nil,authority:nil,path:"/v3/run-cancellations")
        request.headerFields[.contentType]="application/json";request.headerFields[.authorization]="Bearer synthetic-only"
        for transport in [RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,validate:{}),
            RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,travel:true,validate:{}),
            RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,compatible:true,validate:{})] {
            await #expect(throws:RunDisplayFailure.invalidReference) {
                try await transport.sendBound(request,body:HTTPBody(raw),baseURL:endpoint.url,operationID:"cancelOriginalTripRunV3",validateOriginal:{})
            }
        }
        let compatible=RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,tripCompatible:true,validate:{})
        await #expect(throws:RunDisplayFailure.invalidReference) {
            try await compatible.sendBound(request,body:HTTPBody(Data("{\"version\":\"RUN-cancel.2\",\"message_id\":\"m\"}".utf8)),baseURL:endpoint.url,operationID:"cancelOriginalTripRunV3",validateOriginal:{})
        }
        #expect(await wire.operations.isEmpty)
    }
}
