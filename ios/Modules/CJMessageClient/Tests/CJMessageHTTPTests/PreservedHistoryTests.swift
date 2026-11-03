import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

private let humanTrace = "00000000-0000-4000-8000-000000000501"
private func humanJSON(_ value: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
}
private func humanRow(_ state: String = "erased") throws -> [String: Any] {
    let selection: [String: Any] = ["id":"trip-a", "expected_version":1, "day":NSNull(), "item_id":NSNull()]
    let raw = try humanJSON(["version":"MESSAGE-send.3", "conversation_id":"chat", "message_id":"m1", "text":" e\u{301} 中文 ",
        "trip_id":NSNull(), "creation_intent":"none", "expected_generation":"g1", "expected_sequence":0,
        "travel_context":NSNull(), "needs_reference":NSNull(), "trip_context":selection])
    let receipt: [String: Any] = ["message_id":"m1", "conversation_id":"chat", "generation":"g1", "sequence":1,
        "run_id":"r1", "input_sha256":SHA256.hash(data:raw).map { String(format:"%02x", $0) }.joined()]
    var ref = receipt
    ref.merge(["version":"MESSAGE-trip-reference.1", "message_version":"MESSAGE-send.3", "selection_epoch":1,
        "context_kind":"trip", "context_id":"trip-a", "context_version":1, "trip_context":selection,
        "content_version":"structured.2", "content_sha256":String(repeating:"a",count:64)], uniquingKeysWith:{_,new in new})
    return ["receipt":receipt, "original_utf8_base64":raw.base64EncodedString(), "text":" e\u{301} 中文 ",
        "reference":state == "retained" ? ref : NSNull(), "source_state":state]
}
private func humanHistory(_ rows: [[String: Any]]) throws -> Data {
    try humanJSON(["request_id":humanTrace,"version":"MESSAGE-history.5","messages":rows,"next_cursor":NSNull()])
}
private func humanRun(_ row: [String: Any], state: String = "erased", change: (inout [String: Any]) -> Void = {_ in}) throws -> Data {
    var snapshot: [String: Any] = ["conversation_id":"chat","generation":"g1","message_id":"m1","run_id":"r1",
        "message_sequence":1,"status":"completed","event_highwater":2,"text":"保留的原回答","text_state":"complete"]
    change(&snapshot)
    return try humanJSON(["request_id":humanTrace,"version":"RUN-display.6","snapshot":snapshot,
        "reference":state == "retained" ? row["reference"]! : NSNull(),"source_state":state])
}
@MainActor private final class HumanStore: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}
@MainActor private final class HumanCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-human-only" }
}
private actor HumanSpy: ClientTransport {
    var bodies: [Data]
    var requests: [(HTTPRequest.Method, String, String)] = []
    let after: @Sendable (String) async -> Void
    init(_ bodies: [Data], after: @escaping @Sendable (String) async -> Void = {_ in}) { self.bodies=bodies;self.after=after }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        requests.append((request.method,request.path!,operationID)); await after(operationID)
        guard !bodies.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json"
        response.headerFields[.cacheControl]="no-store";response.headerFields[HTTPField.Name("X-Request-ID")!]=humanTrace
        return (response,HTTPBody(bodies.removeFirst()))
    }
}
@MainActor struct PreservedHistoryTests {
    func limits() throws -> MessageReadLimits { try .init(maximumPageItems:2,maximumCursorBytes:128,maximumDecodedBytes:8192,maximumPages:4) }
    private func client(_ wire: HumanSpy, recovery: MessageRecovery? = nil) throws -> (MessageRecovery, Lease, MessageHTTPClient) {
        let recovery = recovery ?? MessageRecovery(storage:HumanStore())
        let scope=try StorageScope(environment:UUID().uuidString,account:"synthetic")
        let lease=try recovery.activate(scope)
        return (recovery,lease,MessageHTTPClient(recovery:recovery,scope:scope,
            endpoint:try .init(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:16384,maximumResponseBytes:32768),
            credentials:HumanCredentials(),interceptedTestTransport:wire))
    }
    @Test func erasedHumanTextAndAnswerAreReadWithoutAnyWriteOrEffectReference() async throws {
        let row=try humanRow(),wire=HumanSpy([try humanHistory([row]),try humanRun(row)])
        let (_,lease,client)=try client(wire)
        let page=try await client.preservedHistory(conversationID:"chat",limit:2,limits:limits(),lease:lease)
        let item=try #require(page.value.first)
        #expect(item.sourceState == .erased && Data(item.text.utf8)==Data(" e\u{301} 中文 ".utf8))
        let result=try await client.preservedRun(for:item,page:page,limits:limits(),lease:lease)
        #expect(result.value.sourceState == .erased && result.value.snapshot.text=="保留的原回答")
        #expect(!String(reflecting:item).contains("中文") && !String(reflecting:result.value).contains("原回答"))
        #expect(await wire.requests.map(\.0)==[.get,.get])
        #expect(await wire.requests.map(\.2)==["readPreservedMessageHistoryV5","readPreservedRunDisplayV6"])
    }
    @Test(arguments: ["retained-null","erased-reference","formal-not-applicable","unknown","text","generation","boolean-sequence","extra"])
    func malformedStateAndOriginalReceiptCannotBecomeReadable(kind: String) throws {
        var row=try humanRow()
        switch kind {
        case "retained-null":row["source_state"]="retained"
        case "erased-reference":row["reference"]=try humanRow("retained")["reference"]
        case "formal-not-applicable":row["source_state"]="not_applicable"
        case "unknown":row["source_state"]="unknown"
        case "text":row["text"]="invented"
        case "generation":var r=row["receipt"] as! [String:Any];r["generation"]="other";row["receipt"]=r
        case "boolean-sequence":var r=row["receipt"] as! [String:Any];r["sequence"]=true;row["receipt"]=r
        default:row["owner"]="other"
        }
        #expect(throws:(any Error).self) { try PreservedHistoryPage(raw:humanHistory([row]),maximumBytes:32768,decodedLimit:8192,limit:2,requestID:humanTrace) }
    }
    @Test func sourceCanBecomeErasedButCannotBeRecreatedByLaterDisplay() throws {
        let retained=try humanRow("retained")
        let page=try PreservedHistoryPage(raw:humanHistory([retained]),maximumBytes:32768,decodedLimit:8192,limit:2,requestID:humanTrace)
        let row=try #require(page.rows.first)
        #expect(try decodePreservedRun(humanRun(retained),maximumBytes:32768,textLimit:8192,trace:humanTrace,row:row).sourceState == .erased)
        let erasedPage=try PreservedHistoryPage(raw:humanHistory([humanRow()]),maximumBytes:32768,decodedLimit:8192,limit:2,requestID:humanTrace)
        let erased=try #require(erasedPage.rows.first)
        #expect(throws:(any Error).self) { try decodePreservedRun(humanRun(retained,state:"retained"),maximumBytes:32768,textLimit:8192,trace:humanTrace,row:erased) }
        #expect(throws:(any Error).self) { try decodePreservedRun(humanRun(retained) {$0["run_id"]="other"},maximumBytes:32768,textLimit:8192,trace:humanTrace,row:row) }
        #expect(throws:(any Error).self) { try decodePreservedRun(humanRun(retained) {$0["status"]="running"},maximumBytes:32768,textLimit:8192,trace:humanTrace,row:row) }
        for value in [false, "not-an-object", [], 1] as [Any] {
            var malformed = retained; malformed["reference"] = value
            #expect(throws:(any Error).self) { try decodePreservedRun(humanRun(malformed,state:"retained"),maximumBytes:32768,textLimit:8192,trace:humanTrace,row:row) }
        }
    }
    @Test func foreignClientOrPageNeverDispatchesAndLateAccountResultIsWithheld() async throws {
        let row=try humanRow(),wire=HumanSpy([try humanHistory([row])])
        let (_,lease,first)=try client(wire)
        let page=try await first.preservedHistory(conversationID:"chat",limit:2,limits:limits(),lease:lease)
        let (_,otherLease,other)=try client(wire)
        await #expect(throws:(any Error).self) { try await other.preservedRun(for:#require(page.value.first),page:page,limits:limits(),lease:otherLease) }
        #expect(await wire.requests.count==1)
        let recovery=MessageRecovery(storage:HumanStore())
        let late=HumanSpy([try humanHistory([row]),try humanRun(row)],after:{op in if op=="readPreservedRunDisplayV6" { await recovery.invalidate() }})
        let (_,l,c)=try client(late,recovery:recovery)
        let p=try await c.preservedHistory(conversationID:"chat",limit:2,limits:limits(),lease:l)
        await #expect(throws:(any Error).self) { try await c.preservedRun(for:#require(p.value.first),page:p,limits:limits(),lease:l) }
    }
    @Test func noSelectorBodyHostOrAmbiguousQueryCanEnterHumanReads() throws {
        let hash=String(repeating:"a",count:64)
        let invalid=["/v5/message-history?conversation_id=chat&limit=2&owner=other", "/v5/message-history?conversation_id=chat&limit=2&limit=1",
            "/v5/message-history?conversation_id=chat+A&limit=2", "/v5/message-history?conversation_id=chat&limit=2#fragment",
            "/v6/run-display?message_id=m1&run_id="+hash]
        for path in invalid { #expect(!PreservedHistoryRoute.accepts(HTTPRequest(method:.get,scheme:nil,authority:nil,path:path),hasBody:false,operationID:path.hasPrefix("/v5") ? "readPreservedMessageHistoryV5" : "readPreservedRunDisplayV6")) }
        let good=HTTPRequest(method:.get,scheme:nil,authority:nil,path:"/v6/run-display?message_id=m1")
        #expect(PreservedHistoryRoute.accepts(good,hasBody:false,operationID:"readPreservedRunDisplayV6"))
        #expect(!PreservedHistoryRoute.accepts(good,hasBody:true,operationID:"readPreservedRunDisplayV6"))
        var host=good;host.headerFields[HTTPField.Name("Host")!]="other.invalid"
        #expect(!PreservedHistoryRoute.accepts(host,hasBody:false,operationID:"readPreservedRunDisplayV6"))
    }
}
