import Foundation
import CryptoKit
import Testing
import CJTripClient
import CJAPI
import CJMessageKeys
import OpenAPIRuntime
import HTTPTypes
@testable import CJMessageHTTP
@testable import CJManualPreviewClient

private actor PlanningWire:ClientTransport {
    let discovery:Data
    let trace:String
    let tripID:String
    var requests:[(String,Data?)]=[]
    var action:Data?
    var loseACK=false
    var nullReceipt=false
    var callback:(@MainActor @Sendable ()->Void)?
    init() throws {
        let f=try NeedsPlanningWireTests().fixture();var wire=f["discovery"] as! [String:Any],d=wire["discovery"] as! [String:Any],p=d["proposal"] as! [String:Any]
        // Client-only L0 sample; the opaque hash is not server authority.
        p["expires_at"]=Int(Date().timeIntervalSince1970)+3600;d["proposal"]=p;wire["discovery"]=d
        discovery=try canonical(wire);trace=wire["request_id"] as! String;tripID=p["trip_id"] as! String
    }
    func configure(loseACK:Bool=false,nullReceipt:Bool=false,callback:(@MainActor @Sendable ()->Void)?=nil) {
        self.loseACK=loseACK;self.nullReceipt=nullReceipt;self.callback=callback
    }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        let bytes:Data?
        if let body { bytes=try await Data(collecting:body,upTo:32768) } else { bytes=nil }
        requests.append((request.path!,bytes))
        let output:Data
        if operationID=="discoverNeedsPlanningV1" { output=discovery }
        else {
            if let bytes { action=bytes }
            if loseACK,bytes != nil { throw PreviewFailure.unknown }
            let retained=try #require(action),a=try NeedsPlanningAction(originalUTF8:retained)
            let receipt:Any=nullReceipt ? NSNull() : ["action_id":a.actionID,"kind":a.kind.rawValue,"proposal_id":a.proposalID,
                "candidate_hash":a.candidateHash,"trip_id":tripID,"committed_version":a.kind == .accept ? 1 as Any : NSNull()]
            output=try canonical(["version":"TRIP-needs-result.1","request_id":trace,"receipt":receipt])
        }
        if let callback { await callback() }
        var response=HTTPResponse(status:.ok)
        response.headerFields[.init("x-request-id")!]=trace;response.headerFields[.cacheControl]="no-store";response.headerFields[.contentType]="application/json"
        return (response,HTTPBody(output))
    }
}
@MainActor private final class PlanningHarness {
    let root:URL
    let binding=TripBinding(environment:UUID(),account:UUID(),generation:UUID(),selection:UUID())
    let wire:PlanningWire
    let source:AcceptedTravelMessageSource
    let originals:ScopedJournal<NeedsPlanningOriginal>
    let settlements:ScopedJournal<NeedsPlanningSettlement>
    var current=true
    var sourceCurrent=true
    init() throws {
        wire=try PlanningWire();let f=try NeedsPlanningWireTests().fixture()
        let receipt=try JSONDecoder().decode(Components.Schemas.MessageReceipt.self,from:canonical(f["message_receipt"]))
        let reference=try JSONDecoder().decode(Components.Schemas.MessageTravelReference.self,from:canonical(f["reference"]))
        source=AcceptedTravelMessageSource(receipt:receipt,reference:reference,creationIntent:.considerTrip,needsID:"visit",needsVersion:1)
        root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        let a=root.appendingPathComponent("originals"),b=root.appendingPathComponent("settlements")
        for path in [a,b] { try FileManager.default.createDirectory(at:path,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700]) }
        let key=SymmetricKey(size:.bits256),kid=UUID(),namespace=MessageKeyNamespace(environment:binding.environment,account:binding.account,purpose:.localTripPendingV1)
        originals=try .init(directory:a,maximumBytes:6_000_000,maximumRecords:20,namespace:namespace,keyID:kid,domain:"CJNeedsPlanningOriginal.1",key:{key})
        settlements=try .init(directory:b,maximumBytes:7_000_000,maximumRecords:20,namespace:namespace,keyID:kid,domain:"CJNeedsPlanningSettlement.1",key:{key})
    }
    func client() throws -> NeedsPlanningClient {
        try .init(endpoint:MessageEndpoint(url:URL(string:"http://127.0.0.1:1234")!,maximumRequestBytes:32768,maximumResponseBytes:4_000_000,allowLoopbackHTTP:true),
            binding:binding,credentials:{[self] _ in guard current else {throw PreviewFailure.retired};return "synthetic-bearer"},
            validate:{[self] in guard current else {throw PreviewFailure.retired}},transport:wire,originals:originals,settlements:settlements)
    }
    func read(_ client:NeedsPlanningClient) async throws -> NeedsPlanningRead {
        try await client.discover(original:source) {[self] in guard sourceCurrent else {throw PreviewFailure.retired}}
    }
    func clean() { try! FileManager.default.removeItem(at:root) }
}
@MainActor struct NeedsPlanningRuntimeTests {
    @Test func durableOnePostAndRestartOriginalGETOnly() async throws {
        let h=try PlanningHarness();defer{h.clean()};let client=try h.client(),read=try await h.read(client)
        let work=try client.stage(.accept,read:read),retained=try #require(h.originals.pending().first)
        #expect(retained.actionID==work.actionID)
        guard case .confirmed(let receipt)=try await client.perform(work) else { Issue.record("missing original receipt");return }
        #expect(receipt.committedVersion==1 && receipt.actionID==work.actionID)
        await #expect(throws:(any Error).self) {try await client.perform(work)}
        let restored=try h.client()
        guard case .confirmed(let again)=try await restored.queryOriginal(work.actionID) else {Issue.record("missing restored receipt");return}
        #expect(again.actionID==receipt.actionID && again.tripID==receipt.tripID)
        #expect(await h.wire.requests.filter{$0.0=="/v1/trip-needs-actions"}.map(\.1)==[retained.actionUTF8])
        #expect(throws:(any Error).self) {try client.stage(.reject,read:read)}
    }
    @Test func lostACKAndNullNeverAuthorizeReplacementOrCachedSuccess() async throws {
        let h=try PlanningHarness();defer{h.clean()};let client=try h.client(),read=try await h.read(client),work=try client.stage(.accept,read:read)
        await h.wire.configure(loseACK:true)
        await #expect(throws:(any Error).self) {try await client.perform(work)}
        let restored=try h.client();await h.wire.configure(nullReceipt:true)
        guard case .unknown=try await restored.queryOriginal(work.actionID) else {Issue.record("null became success");return}
        #expect(try h.settlements.pending().isEmpty)
        #expect(throws:(any Error).self) {try client.stage(.accept,read:read)}
        await h.wire.configure()
        guard case .confirmed(let receipt)=try await restored.queryOriginal(work.actionID) else {Issue.record("missing reconciliation");return}
        #expect(receipt.actionID==work.actionID)
        #expect(await h.wire.requests.filter{$0.0=="/v1/trip-needs-actions"}.count==1)
    }
    @Test func lateSourceAndAccountRetirementCannotDispatchOrPublish() async throws {
        let h=try PlanningHarness();defer{h.clean()};let client=try h.client()
        await h.wire.configure(callback:{h.sourceCurrent=false})
        await #expect(throws:(any Error).self) {try await h.read(client)}
        h.sourceCurrent=true;await h.wire.configure()
        let read=try await h.read(client),work=try client.stage(.reject,read:read)
        h.current=false
        await #expect(throws:(any Error).self) {try await client.perform(work)}
        #expect(throws:(any Error).self) {try client.originalActions()}
        #expect(await h.wire.requests.allSatisfy{!$0.0.hasPrefix("/v1/trip-needs-actions")})
    }
}
