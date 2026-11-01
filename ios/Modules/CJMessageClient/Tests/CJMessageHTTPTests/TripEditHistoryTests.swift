import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

private actor EditHistoryWire: ClientTransport {
    let bytes: Data
    let trace: String
    var calls=0
    init(bytes:Data,trace:String) { self.bytes=bytes;self.trace=trace }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls += 1
        #expect(operationID == "readTripEditHistoryV3" && request.method == .get && request.path?.hasPrefix("/v3/message-history?") == true && body == nil)
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=trace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(bytes))
    }
}
@MainActor private final class EditHistoryStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    func load(scope:StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot:Snapshot,scope:StorageScope) throws { self.snapshot=snapshot }
}
@MainActor private final class EditHistoryCredentials: MessageCredentialsProvider {
    func bearer(for scope:StorageScope,lease:Lease) async throws -> String? { "synthetic-only" }
}
struct TripEditHistoryTests {
    private func row() throws -> [String:Any] {
        let fixture=TripEditWireTests(),original=try fixture.original()
        let acceptance=try #require(JSONSerialization.jsonObject(with:fixture.accepted(original)) as? [String:Any])
        return ["receipt":acceptance["receipt"]!,"reference":acceptance["reference"]!,"text":original.text,"original_utf8_base64":original.originalUTF8.base64EncodedString()]
    }
    private func encoded(_ value:[String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]) }
    private func page(_ rows:[[String:Any]],next:Any=NSNull(),version:String="MESSAGE-history.3") -> [String:Any] {
        ["version":version,"request_id":TripEditWireTests().trace,"messages":rows,"next_cursor":next]
    }
    @Test func newHistoryRetainsOldAndNewOriginalAssociationsWithoutStaging() throws {
        let old=TripDiscussionWireTests(),raw=try old.original { $0["expected_sequence"] = 1 }
        let original=try OriginalTripDiscussion(raw:raw,maximumBytes:16384)
        let acceptance=try #require(JSONSerialization.jsonObject(with:old.acceptance(original:original,trace:TripEditWireTests().trace)) as? [String:Any])
        let older:[String:Any]=["receipt":acceptance["receipt"]!,"reference":acceptance["reference"]!,"text":original.text,"original_utf8_base64":raw.base64EncodedString()]
        let result=try TripDiscussionHistory(raw:encoded(page([try row(),older])),maximumBytes:65536,decodedLimit:32768,limit:2,requestID:TripEditWireTests().trace,edit:true)
        #expect(result.rows.count==2)
        guard case .edit(let current)=result.rows[0].association,case .trip(let prior)=result.rows[1].association else { Issue.record("original versions lost");return }
        #expect(current.namespace.id==String(repeating:"b",count:32) && current.needs?.expectedVersion==2)
        #expect(prior.trip?.id=="trip-a" && result.rows[1].originalUTF8==raw)
    }
    @Test func oldHistoryCannotStripTheNewReference() throws {
        let bytes=try encoded(page([try row()],version:"MESSAGE-history.2"))
        #expect(throws:(any Error).self) { try TripDiscussionHistory(raw:bytes,maximumBytes:65536,decodedLimit:32768,limit:2,requestID:TripEditWireTests().trace) }
    }
    @Test(arguments:["text","namespace","raw","sequence"])
    func changedOriginalCannotBeDisplayedAsTheSameRow(mutation:String) throws {
        var changed=try row()
        switch mutation {
        case "text":changed["text"]="another original"
        case "namespace":var reference=changed["reference"] as! [String:Any];reference["namespace"]=["kind":"travel","id":String(repeating:"c",count:32),"version":1];changed["reference"]=reference
        case "raw":changed["original_utf8_base64"]=Data("{\"version\":\"MESSAGE-send.4\"}".utf8).base64EncodedString()
        default:var receipt=changed["receipt"] as! [String:Any];receipt["sequence"]=2;changed["receipt"]=receipt
        }
        #expect(throws:(any Error).self) { try TripDiscussionHistory(raw:encoded(page([changed])),maximumBytes:65536,decodedLimit:32768,limit:2,requestID:TripEditWireTests().trace,edit:true) }
    }
    @MainActor @Test func newCursorCannotBeReusedByOldHistoryAndReadCreatesNoAction() async throws {
        let wire=EditHistoryWire(bytes:try encoded(page([try row()],next:"synthetic-cursor")),trace:TripEditWireTests().trace)
        let state=MessageRecovery(storage:EditHistoryStorage()),scope=try StorageScope(environment:UUID().uuidString,account:"synthetic"),lease=try state.activate(scope)
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let client=MessageHTTPClient(recovery:state,scope:scope,endpoint:endpoint,credentials:EditHistoryCredentials(),interceptedTestTransport:wire)
        let limits=try MessageReadLimits(maximumPageItems:20,maximumCursorBytes:4096,maximumDecodedBytes:65536,maximumPages:5)
        let result=try await client.tripEditHistory(conversationID:"chat",limit:2,limits:limits,lease:lease)
        try client.validateRead(result,lease:lease)
        #expect(result.value.count==1 && result.next != nil)
        await #expect(throws:(any Error).self) { try await client.tripDiscussionHistory(conversationID:"chat",limit:2,after:result.next,limits:limits,lease:lease) }
        #expect(await wire.calls==1)
        #expect(try state.localProjection(scope:scope,lease:lease).actions.isEmpty)
    }
}
