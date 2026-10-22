import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class ReadStore: SecureMessageStorage {
    func load(scope:StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot:Snapshot,scope:StorageScope) throws { }
}
@MainActor private final class ReadCredentials: MessageCredentialsProvider {
    func bearer(for scope:StorageScope,lease:Lease) async throws -> String? { "synthetic-read-only" }
}
private actor ReadInterceptor: ClientTransport {
    var bodies:[Data]; let status:Int; let trace:String
    var calls:[HTTPRequest.Method]=[]
    let hook:(@Sendable () async -> Void)?
    init(_ bodies:[Data],status:Int=200,trace:String,hook:(@Sendable () async -> Void)?=nil) {
        self.bodies=bodies; self.status=status; self.trace=trace; self.hook=hook
    }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls.append(request.method)
        guard !bodies.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        let data=bodies.removeFirst(); await hook?()
        var response=HTTPResponse(status:.init(code:status))
        response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        response.headerFields[.contentType]="application/json"
        return (response,HTTPBody(data))
    }
}
@Suite @MainActor struct HistoryReadTests {
    let trace="a5f7f63f-853b-42d8-b689-2dfc3cdbe3fa"
    private var limits:MessageReadLimits { get throws { try MessageReadLimits(maximumPageItems:2,maximumCursorBytes:50,maximumDecodedBytes:2048,maximumPages:4) } }
    private func encoded(_ fields:[String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject:fields.merging(["request_id":trace]) { old,_ in old }) }
    private func chat(_ id:String,_ sequence:Int)->[String:Any] { ["conversation_id":id,"generation":"g1","epoch":0,"list_sequence":sequence] }
    private func historyItem(text:String="原正文",sequence:Int=1)->[String:Any] {
        let raw=Data("{\"message_id\":\"m1\",\"conversation_id\":\"chat\",\"text\":\"原正文\"}".utf8)
        let hash=SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()
        return ["receipt":["message_id":"m1","conversation_id":"chat","generation":"g1","run_id":"r1","sequence":sequence,"input_sha256":hash],"original_utf8_base64":raw.base64EncodedString(),"text":text]
    }
    private func setup(_ transport:ReadInterceptor) throws -> (MessageRecovery,Lease,MessageHTTPClient) {
        let recovery=MessageRecovery(storage:ReadStore()); let scope=try StorageScope(environment:UUID().uuidString,account:"a")
        let lease=try recovery.activate(scope)
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:2048,maximumResponseBytes:10000)
        return (recovery,lease,MessageHTTPClient(recovery:recovery,scope:scope,endpoint:endpoint,credentials:ReadCredentials(),interceptedTestTransport:transport))
    }
    @Test func generatedConversationPagesAndBoundContinuation() async throws {
        let t=ReadInterceptor([try encoded(["conversations":[chat("a",1)],"next_cursor":"opaque-1"]),try encoded(["conversations":[chat("b",3)],"next_cursor":NSNull()])],trace:trace)
        let (state,lease,client)=try setup(t)
        let first=try await client.conversations(limit:1,limits:limits,lease:lease)
        let next=try #require(first.next)
        await #expect(throws:(any Error).self) { try await client.history(conversationID:"chat",limit:1,after:next,limits:limits,lease:lease) }
        let last=try await client.conversations(limit:1,after:next,limits:limits,lease:lease)
        #expect(first.value[0].conversation_id=="a" && last.value[0].conversation_id=="b" && last.next==nil)
        #expect(await t.calls==[.get,.get])
        state.invalidate()
        #expect(throws:RecoveryError.self) { try client.validateRead(last,lease:lease) }
    }
    @Test func listDuplicateMissingAndInvalidCursorNeverEmptySuccess() async throws {
        let cases:[[String:Any]]=[
            ["conversations":[chat("a",1),chat("a",2)],"next_cursor":NSNull()],
            ["conversations":[]],
            ["conversations":[],"next_cursor":false],
            ["conversations":[],"next_cursor":"nonempty"],
            ["conversations":[chat("a",1),chat("b",2)],"next_cursor":NSNull()]]
        for (index,item) in cases.enumerated() {
            let t=ReadInterceptor([try encoded(item)],trace:trace); let (_,lease,client)=try setup(t)
            await #expect(throws:(any Error).self) { try await client.conversations(limit:index==4 ? 1:2,limits:limits,lease:lease) }
        }
    }
    @Test func historyGeneratedBodyAndStrictOriginalBinding() async throws {
        let good=ReadInterceptor([try encoded(["messages":[historyItem()],"next_cursor":NSNull()])],trace:trace)
        let (_,lease,client)=try setup(good)
        let page=try await client.history(conversationID:"chat",limit:1,limits:limits,lease:lease)
        #expect(page.value[0].text=="原正文" && page.next==nil)
        var badBase64=historyItem(); badBase64["original_utf8_base64"]="Zh=="
        for item in [historyItem(text:"invented"),historyItem(sequence:2),badBase64] {
            let t=ReadInterceptor([try encoded(["messages":[item],"next_cursor":NSNull()])],trace:trace)
            let (_,l,c)=try setup(t)
            await #expect(throws:(any Error).self) { try await c.history(conversationID:"chat",limit:1,limits:limits,lease:l) }
        }
    }
    @Test func draftNullEmptyAndMalformedAreDistinct() async throws {
        let empty:[String:Any]=["conversation_id":"chat","generation":"g1","revision":1,"original_utf8_base64":""]
        for value in [NSNull(),empty] as [Any] {
            let t=ReadInterceptor([try encoded(["draft":value])],trace:trace); let (_,lease,client)=try setup(t)
            let result=try await client.draft(conversationID:"chat",generation:"g1",limits:limits,lease:lease)
            #expect((result.value==nil)==(value is NSNull))
        }
        for item in [[String:Any](),["draft":false],["draft":["conversation_id":"chat","generation":"wrong","revision":1,"original_utf8_base64":""]]] {
            let t=ReadInterceptor([try encoded(item)],trace:trace); let (_,lease,client)=try setup(t)
            await #expect(throws:(any Error).self) { try await client.draft(conversationID:"chat",generation:"g1",limits:limits,lease:lease) }
        }
    }
    @Test func resyncAndLateResponseNeverPublishPrivatePage() async throws {
        let error=try encoded(["error":["code":"HISTORY_RESYNC_REQUIRED","category":"conflict","message_en":"resync","message_zh":"重同步","outcome":"failed","recovery":"retry_safe_read"]])
        let t=ReadInterceptor([error],status:409,trace:trace); let (_,lease,client)=try setup(t)
        await #expect(throws:MessageReadFailure.self) { try await client.conversations(limit:1,limits:limits,lease:lease) }
        let state=MessageRecovery(storage:ReadStore()); let scope=try StorageScope(environment:UUID().uuidString,account:"a"); let l=try state.activate(scope)
        let late=ReadInterceptor([try encoded(["conversations":[chat("private",1)],"next_cursor":NSNull()])],trace:trace,hook:{await state.invalidate()})
        let c=MessageHTTPClient(recovery:state,scope:scope,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:2048,maximumResponseBytes:10000),credentials:ReadCredentials(),interceptedTestTransport:late)
        await #expect(throws:RecoveryError.self) { try await c.conversations(limit:1,limits:limits,lease:l) }
        #expect(await late.calls==[.get])
    }
    @Test func explicitReadBudgetsRejectBeforePartialSuccess() async throws {
        let t=ReadInterceptor([try encoded(["messages":[historyItem()],"next_cursor":NSNull()])],trace:trace)
        let (_,lease,client)=try setup(t)
        let tiny=try MessageReadLimits(maximumPageItems:1,maximumCursorBytes:4,maximumDecodedBytes:1,maximumPages:1)
        await #expect(throws:MessageHTTPFailure.self) { try await client.conversations(limit:2,limits:tiny,lease:lease) }
        #expect(await t.calls.isEmpty)
        await #expect(throws:MessageHTTPFailure.self) { try await client.history(conversationID:"chat",limit:1,limits:tiny,lease:lease) }
        let long=ReadInterceptor([try encoded(["conversations":[chat("a",1)],"next_cursor":"too-long"])],trace:trace)
        let (_,l,c)=try setup(long)
        await #expect(throws:MessageReadFailure.self) { try await c.conversations(limit:1,limits:tiny,lease:l) }
    }

    @Test func repeatedOpaqueCursorRequiresResync() async throws {
        let t=ReadInterceptor([try encoded(["conversations":[chat("a",1)],"next_cursor":"same"]),try encoded(["conversations":[chat("b",2)],"next_cursor":"same"])],trace:trace)
        let (_,lease,client)=try setup(t)
        let first=try await client.conversations(limit:1,limits:limits,lease:lease)
        await #expect(throws:MessageReadFailure.self) { try await client.conversations(limit:1,after:first.next,limits:limits,lease:lease) }
    }
}
