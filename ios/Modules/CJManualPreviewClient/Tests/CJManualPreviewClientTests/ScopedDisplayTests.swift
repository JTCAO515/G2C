import Foundation
import Testing
import CJTripClient
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJManualPreviewClient

private let displayTrace="00000000-0000-4000-8000-000000000336"
private func displaySource() throws -> (MessageEditReference,RunScopedResultReference,[String:Any]) {
    let raw=try scopedFixture(),original=try scopedReference(raw)
    let json=try ScopedWireJSON(raw,maximumBytes:4_000_000),discovery=try #require(json.object["discovery"] as? [String:Any])
    let pointer:[String:Any]=["version":"RUN-scoped-result.1","kind":"expansion_required","result_id":"original-result","message_id":original.messageID,"run_id":original.runID,"input_sha256":original.inputSHA256]
    let decoded=try RunScopedResultReference.decodeResponseReference(canonical(["scoped_result":pointer]),maximumBytes:65536,matching:original)
    return (original,try #require(decoded),discovery["reference"] as! [String:Any])
}
private func displayFixture(_ kind:ScopedRunResultKind = .expansionRequired) throws -> (Data,MessageEditReference,RunScopedResultReference) {
    let (original,_,reference)=try displaySource()
    let p:[String:Any]=["version":"RUN-scoped-result.1","kind":kind.rawValue,"result_id":"original-result","message_id":original.messageID,"run_id":original.runID,"input_sha256":original.inputSHA256]
    let decoded=try RunScopedResultReference.decodeResponseReference(canonical(["scoped_result":p]),maximumBytes:65536,matching:original),pointer=try #require(decoded)
    let selection:[String:Any]=original.trip.day.map {["kind":"dates","dates":[$0.date]]} ?? ["kind":"items","item_ids":original.trip.itemIDs]
    var explanation:[String:Any]=["version":"TRIP-scoped-explanation.1","trip_id":original.trip.id,"expected_version":original.trip.expectedVersion,
        "original_selection":selection,"resolved_item_ids":kind == .clarificationRequired ? [] : original.resolvedItemIDs,
        "status":kind == .clarificationRequired ? "CLARIFICATION_REQUIRED" : "EXPANSION_REQUIRED","reason":["en":"SYNTHETIC choose explicitly","zh":"合成资料：请明确选择"]]
    let report:Any
    if kind == .clarificationRequired {
        explanation.merge(["reason_codes":["EXPLICIT_SELECTION_UNRESOLVED"],"outside_item_ids":[],"outside_dates":[],"changes":[],"required_selection":NSNull(),
            "facts":["unknown_date_item_ids":original.resolvedItemIDs,"cross_day_item_ids":[],"unmatched_dates":[],"observed_dates":["known":[],"incomplete":true]]],uniquingKeysWith:{$1});report=NSNull()
    } else {
        explanation.merge(["reason_codes":["ITEMS_OUTSIDE_SELECTION"],"outside_item_ids":["outside-item"],"outside_dates":[],
            "changes":[["item_id":"outside-item","field":"text","before":"Original declared text","after":"Requested text"]],
            "required_selection":["item_ids":original.resolvedItemIDs+["outside-item"],"dates":["known":[],"incomplete":true],"whole_trip":false,"local_selection_sufficient":true]],uniquingKeysWith:{$1})
        report=["status":"UNKNOWN","checks":[["code":"ROUTE_UNKNOWN","status":"UNKNOWN","missing":["route"],"en":"Unknown route","zh":"路线未知"]],
            "output_check":["accepted":false,"codes":["REVIEW"],"en":"Not an acceptance","zh":"不代表接受"]]
    }
    let content:[String:Any]=["result_id":pointer.resultID,"kind":kind.rawValue,"reference":reference,"explanation":explanation,"feasibility":report]
    return (try canonical(["version":"TRIP-scoped-display.1","request_id":displayTrace,"display":["result_id":pointer.resultID,"state":"current","expected_version":original.trip.expectedVersion,"current_version":original.trip.expectedVersion,"result":content]]),original,pointer)
}
struct ScopedDisplayTests {
    @Test(arguments:[ScopedRunResultKind.clarificationRequired,.expansionRequired])
    func currentDataPreservesReasonsUnknownAndRequiredScopeWithoutAnAction(kind:ScopedRunResultKind) throws {
        let (bytes,original,pointer)=try displayFixture(kind),value=try ScopedResultDisplay.decode(bytes,requestID:displayTrace,pointer:pointer,original:original)
        let content=try #require(value.result)
        #expect(value.state == .current && value.expectedVersion == original.trip.expectedVersion)
        #expect(content.kind == kind && content.explanation.chinese == "合成资料：请明确选择")
        if kind == .clarificationRequired { #expect(content.feasibility == nil && content.explanation.requiredSelection == nil && content.explanation.changes.isEmpty) }
        else {
            #expect(content.explanation.requiredSelection?.dates.incomplete == true)
            #expect(content.feasibility?.status == "UNKNOWN" && content.feasibility?.outputAccepted == false)
            #expect(String(decoding:content.explanation.changes[0].beforeUTF8,as:UTF8.self)=="\"Original declared text\"")
        }
    }
    @Test func staleMetadataCannotCarryOldContentOrPretendToBeCurrent() throws {
        let (_,original,pointer)=try displayFixture()
        var d:[String:Any]=["result_id":pointer.resultID,"state":"stale","expected_version":original.trip.expectedVersion,"current_version":original.trip.expectedVersion+1,"result":NSNull()]
        func response() throws -> Data { try canonical(["version":"TRIP-scoped-display.1","request_id":displayTrace,"display":d]) }
        #expect(try ScopedResultDisplay.decode(response(),requestID:displayTrace,pointer:pointer,original:original).result == nil)
        d["result"]=["old":"private explanation"]
        #expect(throws:(any Error).self) { try ScopedResultDisplay.decode(response(),requestID:displayTrace,pointer:pointer,original:original) }
        d["result"]=NSNull();d["current_version"]=original.trip.expectedVersion
        #expect(throws:(any Error).self) { try ScopedResultDisplay.decode(response(),requestID:displayTrace,pointer:pointer,original:original) }
    }
    @Test(arguments:["pointer","reference","version","permission","boolean","modelBytes"])
    func mismatchedOrInjectedDataWithholdsTheWholeDisplay(change:String) throws {
        let (bytes,original,pointer)=try displayFixture()
        var envelope=try #require(JSONSerialization.jsonObject(with:bytes) as? [String:Any]),d=envelope["display"] as! [String:Any],r=d["result"] as! [String:Any]
        switch change {
        case "pointer":r["result_id"]="other-result"
        case "reference":var ref=r["reference"] as! [String:Any];ref["input_sha256"]=String(repeating:"a",count:64);r["reference"]=ref
        case "version":d["expected_version"]=true
        case "modelBytes":r["model_input"]="private raw model"
        default:
            var e=r["explanation"] as! [String:Any],required=e["required_selection"] as! [String:Any]
            if change == "permission" { required["accept_url"]="/act" }
            else { required["whole_trip"]=1.0 }
            e["required_selection"]=required;r["explanation"]=e
        }
        d["result"]=r;envelope["display"]=d
        #expect(throws:(any Error).self) { try ScopedResultDisplay.decode(canonical(envelope),requestID:displayTrace,pointer:pointer,original:original) }
    }
}
private actor ScopedDisplayWire:ClientTransport {
    let bytes:Data
    var callback:(@MainActor @Sendable ()->Void)?
    var requests:[String]=[]
    init(bytes:Data) { self.bytes=bytes }
    func onReturn(_ callback:@escaping @MainActor @Sendable ()->Void) { self.callback=callback }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && body == nil && request.path=="/v1/trip-scoped-results?result_id=original-result" && operationID=="readScopedDisplayV1")
        #expect(request.headerFields[.authorization]=="Bearer synthetic-only")
        requests.append(request.path!)
        if let callback { await callback() }
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=displayTrace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(bytes))
    }
}
@MainActor private final class ScopedDisplayHarness {
    var current=true
    let binding=TripBinding(environment:UUID(),account:UUID(),generation:UUID(),selection:UUID())
    func client(_ wire:ScopedDisplayWire) throws -> ScopedDisplayClient {
        try .init(endpoint:MessageEndpoint(url:URL(string:"https://synthetic.invalid")!,maximumRequestBytes:32768,maximumResponseBytes:4_000_000),binding:binding,
            credentials:{ _ in "synthetic-only" },validate:{ [self] in guard current else { throw PreviewFailure.retired } },transport:wire)
    }
}
@MainActor struct ScopedDisplayReadTests {
    @Test func onlyOriginalGetRunsAndLateRetirementWithholdsTheResult() async throws {
        let (bytes,original,pointer)=try displayFixture(),wire=ScopedDisplayWire(bytes:bytes),h=ScopedDisplayHarness(),client=try h.client(wire)
        let read=try await client.read(pointer:pointer,original:original,validateOriginal:{ guard h.current else { throw PreviewFailure.retired } })
        try client.validateRead(read)
        let initialRequests=await wire.requests
        #expect(read.value.state == .current && initialRequests.count==1)
        await wire.onReturn { h.current=false }
        await #expect(throws:(any Error).self) { try await client.read(pointer:pointer,original:original,validateOriginal:{ guard h.current else { throw PreviewFailure.retired } }) }
        #expect(throws:(any Error).self) { try client.validateRead(read) }
        let finalRequests=await wire.requests
        #expect(finalRequests.count==2)
    }
}
