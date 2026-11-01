import Foundation
import Testing
import CryptoKit
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

struct ScopedMessageReadWireTests {
    let trace="00000000-0000-4000-8000-000000000360"
    func payload(_ schema:String,kind:String="clarification_required") throws -> [String:Any] {
        var root=URL(fileURLWithPath:#filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let object=try #require(JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("contracts/message/edit-result-examples.1.json"))) as? [String:Any])
        let rows=try #require(object["read_positive"] as? [[String:Any]])
        let row=try #require(rows.first { row in
            guard row["schema"] as? String == schema,let value=row["value"] as? [String:Any] else { return false }
            let pointer=(value["scoped_result"] as? [String:Any]) ?? ((value["messages"] as? [[String:Any]])?.first?["scoped_result"] as? [String:Any])
            return pointer?["kind"] as? String == kind
        })
        var value=try #require(row["value"] as? [String:Any]);value["request_id"]=trace;return value
    }
    func raw(_ value:[String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]) }
    func original(_ kind:String="clarification_required") throws -> OriginalTripEdit {
        let history=try payload("MessageHistory4",kind:kind),items=try #require(history["messages"] as? [[String:Any]])
        let encoded=try #require(items.first?["original_utf8_base64"] as? String)
        let bytes=try #require(Data(base64Encoded:encoded))
        return try OriginalTripEdit(raw:bytes,maximumBytes:65536)
    }
    @Test(arguments:["clarification_required","expansion_required"])
    func newStatusAndHistoryKeepOriginalOctetsWithoutMintingAnAction(kind:String) throws {
        let source=try original(kind),status=try payload("MessageStatus5",kind:kind)
        let decoded=try TripEditStatus(raw:raw(status),maximumBytes:65536,requestID:trace,conversationID:source.head.conversation_id,original:source,scopedResults:true)
        #expect(decoded.scopedResult?.kind.rawValue==kind)
        let accepted=try #require(decoded.acceptedUTF8),fields=try #require(JSONSerialization.jsonObject(with:accepted) as? [String:Any])
        #expect(fields["version"] as? String == "MESSAGE-accept.4" && fields["scoped_result"] == nil)
        let history=try TripDiscussionHistory(raw:raw(payload("MessageHistory4",kind:kind)),maximumBytes:65536,decodedLimit:65536,limit:20,requestID:trace,edit:true,scopedResults:true)
        #expect(history.rows.count==1 && history.rows[0].originalUTF8==source.originalUTF8)
        #expect(history.rows[0].scopedResult==decoded.scopedResult)
        #expect(throws:(any Error).self) { try TripEditStatus(raw:raw(status),maximumBytes:65536,requestID:trace,conversationID:source.head.conversation_id,original:source) }
        #expect(throws:(any Error).self) { try TripDiscussionHistory(raw:raw(payload("MessageHistory4",kind:kind)),maximumBytes:65536,decodedLimit:65536,limit:20,requestID:trace,edit:true) }
    }
    @Test func explicitNullHeadOnlyStatusIsNotAResultOrReceipt() throws {
        var value=try payload("MessageStatus5");value["receipt"]=NSNull();value["reference"]=NSNull()
        #expect(throws:(any Error).self) { try TripEditStatus(raw:raw(value),maximumBytes:65536,requestID:trace,conversationID:"chat",original:nil,scopedResults:true) }
        value["scoped_result"]=NSNull()
        let status=try TripEditStatus(raw:raw(value),maximumBytes:65536,requestID:trace,conversationID:"chat",original:nil,scopedResults:true)
        #expect(status.acceptance==nil && status.scopedResult==nil)
        value.removeValue(forKey:"scoped_result")
        #expect(throws:(any Error).self) { try TripEditStatus(raw:raw(value),maximumBytes:65536,requestID:trace,conversationID:"chat",original:nil,scopedResults:true) }
    }
    @Test(arguments:["message_id","run_id","input_sha256","owner"])
    func statusAndHistoryRejectForeignOrInventedPointerFields(field:String) throws {
        let source=try original();var status=try payload("MessageStatus5"),pointer=try #require(status["scoped_result"] as? [String:Any])
        pointer[field]=field=="input_sha256" ? String(repeating:"a",count:64) : "other-original";status["scoped_result"]=pointer
        #expect(throws:(any Error).self) { try TripEditStatus(raw:raw(status),maximumBytes:65536,requestID:trace,conversationID:"chat",original:source,scopedResults:true) }
        var history=try payload("MessageHistory4"),items=try #require(history["messages"] as? [[String:Any]]);items[0]["scoped_result"]=pointer;history["messages"]=items
        #expect(throws:(any Error).self) { try TripDiscussionHistory(raw:raw(history),maximumBytes:65536,decodedLimit:65536,limit:20,requestID:trace,edit:true,scopedResults:true) }
    }
    @Test func oldMessagesInNewHistoryCannotAcquireAResultAssociation() throws {
        var value=try payload("MessageHistory4"),items=try #require(value["messages"] as? [[String:Any]])
        let input:[String:Any]=["version":"MESSAGE-send.1","message_id":"legacy-original","conversation_id":"chat","text":"SYNTHETIC legacy","trip_id":NSNull(),"creation_intent":"none"]
        let bytes=try raw(input),hash=SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined()
        items[0]["original_utf8_base64"]=bytes.base64EncodedString();items[0]["text"]="SYNTHETIC legacy";items[0]["reference"]=NSNull()
        items[0]["receipt"]=["message_id":"legacy-original","conversation_id":"chat","generation":"g","run_id":"legacy-run","sequence":1,"input_sha256":hash]
        value["messages"]=items
        #expect(throws:(any Error).self) { try TripDiscussionHistory(raw:raw(value),maximumBytes:65536,decodedLimit:65536,limit:20,requestID:trace,edit:true,scopedResults:true) }
        items[0]["scoped_result"]=NSNull();value["messages"]=items
        let page=try TripDiscussionHistory(raw:raw(value),maximumBytes:65536,decodedLimit:65536,limit:20,requestID:trace,edit:true,scopedResults:true)
        #expect(page.rows[0].originalUTF8==bytes && page.rows[0].scopedResult==nil)
    }
}

private actor ScopedMessageReadRoute: ClientTransport {
    let status:Data
    let history:Data
    let trace:String
    var operations:[String]=[]
    init(status:Data,history:Data,trace:String) { self.status=status;self.history=history;self.trace=trace }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        operations.append(operationID)
        #expect(request.method == .get && body == nil && request.headerFields[.authorization] == "Bearer synthetic-only")
        var value:[String:Any]
        if operationID=="readTripEditStatusV5" {
            #expect(request.path?.hasPrefix("/v5/message-send-status?")==true)
            value=try #require(JSONSerialization.jsonObject(with:status) as? [String:Any])
            let query=URLComponents(string:request.path!)!.queryItems!
            if !query.contains(where:{$0.name=="message_id"}) { value["receipt"]=NSNull();value["reference"]=NSNull();value["scoped_result"]=NSNull() }
        } else {
            guard operationID=="readTripEditHistoryV4" else { throw MessageHTTPFailure.invalidConfiguration }
            #expect(request.path?.hasPrefix("/v4/message-history?")==true)
            value=try #require(JSONSerialization.jsonObject(with:history) as? [String:Any]);value["next_cursor"]="synthetic-next-page"
        }
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=trace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys])))
    }
}
@MainActor private final class ScopedMessageWireStore:SecureMessageStorage {
    var snapshot:Snapshot?
    func load(scope:StorageScope) throws -> Snapshot? { snapshot }
    func save(_ value:Snapshot,scope:StorageScope) throws { snapshot=value }
}
@MainActor private final class ScopedMessageWireCredentials:MessageCredentialsProvider {
    func bearer(for scope:StorageScope,lease:Lease) async throws -> String? { "synthetic-only" }
}
extension ScopedMessageReadWireTests {
    @MainActor @Test func explicitlySelectedNewRoutesRecoverOriginalBytesUsingGETOnly() async throws {
        let source=try original(),wire=ScopedMessageReadRoute(status:try raw(payload("MessageStatus5")),history:try raw(payload("MessageHistory4")),trace:trace)
        let state=MessageRecovery(storage:ScopedMessageWireStore()),scope=try StorageScope(environment:UUID().uuidString,account:"synthetic"),lease=try state.activate(scope)
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let client=MessageHTTPClient(recovery:state,scope:scope,endpoint:endpoint,credentials:ScopedMessageWireCredentials(),interceptedTestTransport:wire,readsScopedEditResults:true)
        let limits=try MessageReadLimits(maximumPageItems:20,maximumCursorBytes:4096,maximumDecodedBytes:65536,maximumPages:5)
        let page=try await client.tripEditHistory(conversationID:"chat",limit:1,limits:limits,lease:lease)
        try client.validateRead(page,lease:lease)
        #expect(page.value[0].originalUTF8==source.originalUTF8 && page.value[0].scopedResult?.kind == .clarificationRequired)
        #expect(try state.localProjection(scope:scope,lease:lease).actions.isEmpty)
        await #expect(throws:(any Error).self) { try await client.tripDiscussionHistory(conversationID:"chat",limit:1,after:page.next,limits:limits,lease:lease) }
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease)
        try state.stage(messageID:source.messageID,originalUTF8:source.originalUTF8,lease:lease)
        let uncertain=try state.beginSubmission(messageID:source.messageID,lease:lease)
        try state.observeUnknown(uncertain.operation)
        #expect(try await client.reconcileTripEdit(messageID:source.messageID,lease:lease) == .accepted)
        #expect(try state.action(messageID:source.messageID,lease:lease)?.originalUTF8==source.originalUTF8)
        #expect(await wire.operations == ["readTripEditHistoryV4","readTripEditStatusV5","readTripEditStatusV5"])
    }
}
