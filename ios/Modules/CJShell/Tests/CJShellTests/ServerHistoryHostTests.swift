import Foundation
import CryptoKit
import Testing
import CJMessageClient
import CJMessageHTTP
import CJAPI
import OpenAPIRuntime
import HTTPTypes
@testable import CJShell

@MainActor private final class HistoryStore: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}
@MainActor private final class HistoryCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
private actor HistoryInterceptor: ClientTransport {
    var bodies: [Data]
    let heldOperation: String?
    var holding = false
    var releaseReply: CheckedContinuation<Void, Never>?
    var methods: [HTTPRequest.Method] = []
    var operations:[String]=[]
    let noStore:Bool
    init(_ bodies: [Data], hold: String? = nil,noStore:Bool=false) { self.bodies = bodies; heldOperation = hold;self.noStore=noStore }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        methods.append(request.method)
        operations.append(operationID)
        guard !bodies.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        let bytes = bodies.removeFirst()
        if heldOperation == operationID && !holding {
            holding = true
            await withCheckedContinuation { releaseReply = $0 }
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = "00000000-0000-4000-8000-000000000001"
        response.headerFields[.contentType] = "application/json"
        if noStore { response.headerFields[.cacheControl]="no-store" }
        return (response, HTTPBody(bytes))
    }
    func release() { releaseReply?.resume(); releaseReply = nil }
}

@Suite @MainActor struct ServerHistoryHostTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.server.read." + UUID().uuidString)))
    }
    private func json(_ fields: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: fields.merging(["request_id":"00000000-0000-4000-8000-000000000001"]) { x, _ in x })
    }
    private func chat(_ id: String, _ n: Int) -> [String: Any] {
        ["conversation_id":id,"generation":"g1","epoch":0,"list_sequence":n]
    }
    private func history(_ conversation: String, sequence: Int = 1) -> [String: Any] {
        let raw = Data("{\"message_id\":\"m-\(conversation)-\(sequence)\",\"conversation_id\":\"\(conversation)\",\"text\":\"synthetic \(conversation)\"}".utf8)
        return ["receipt":["message_id":"m-"+conversation+"-"+String(sequence),"conversation_id":conversation,"generation":"g1","run_id":"synthetic-run","sequence":sequence,
                           "input_sha256":SHA256.hash(data: raw).map { String(format:"%02x",$0) }.joined()],
                "original_utf8_base64":raw.base64EncodedString(),"text":"synthetic "+conversation]
    }
    private func setup(_ shell: ShellState, _ transport: HistoryInterceptor,tripDiscussions:Bool=false) throws -> ServerHistoryHost {
        let recovery = MessageRecovery(storage: HistoryStore())
        let scope = try StorageScope(environment: UUID().uuidString, account: "synthetic")
        let lease = try recovery.activate(scope)
        let client = MessageHTTPClient(recovery: recovery, scope: scope,
            endpoint: try MessageEndpoint(url: #require(URL(string:"https://synthetic.invalid")), maximumRequestBytes:4096, maximumResponseBytes:16384),
            credentials: HistoryCredentials(), interceptedTestTransport: transport)
        let host = ServerHistoryHost(shell: shell)
        #expect(host.bind(ServerHistoryBinding(client: client, recovery: recovery, scope: scope, lease: lease, generation: shell.generation,
            limit:2, limits:try MessageReadLimits(maximumPageItems:2,maximumCursorBytes:128,maximumDecodedBytes:4096,maximumPages:5), synthetic:true,tripDiscussions:tripDiscussions,isCurrent:{true})))
        return host
    }
    private func waitForHold(_ transport: HistoryInterceptor) async {
        for _ in 0..<1000 { if await transport.holding { return }; await Task.yield() }
        #expect(Bool(false), "Synthetic response did not enter held state")
    }
    private func tripHistory(_ conversation:String,sequence:Int=1) throws -> [String:Any] {
        let mid="m-"+conversation+"-"+String(sequence),text="SYNTHETIC "+conversation
        let raw=try JSONSerialization.data(withJSONObject:["version":"MESSAGE-send.3","conversation_id":conversation,"message_id":mid,"text":text,"trip_id":NSNull(),"creation_intent":"none","expected_generation":"g1","expected_sequence":sequence-1,"travel_context":NSNull(),"needs_reference":NSNull(),"trip_context":NSNull()],options:[.sortedKeys])
        let receipt:[String:Any]=["message_id":mid,"conversation_id":conversation,"generation":"g1","run_id":"run-"+mid,"sequence":sequence,"input_sha256":SHA256.hash(data:raw).map { String(format:"%02x",$0) }.joined()]
        var ref=receipt
        ref.merge(["version":"MESSAGE-trip-reference.1","message_version":"MESSAGE-send.3","selection_epoch":1,"context_kind":"none","context_id":NSNull(),"context_version":NSNull(),"trip_context":NSNull(),"content_version":NSNull(),"content_sha256":NSNull()],uniquingKeysWith:{ _,new in new })
        return ["receipt":receipt,"reference":ref,"text":text,"original_utf8_base64":raw.base64EncodedString()]
    }
    @Test func discussionHistoryUsesTypedRouteAndRetainsReferencesBesideTextProjection() async throws {
        let first=try tripHistory("a"),second=try tripHistory("a",sequence:2)
        let wire=HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()]),
            try json(["version":"MESSAGE-history.2","messages":[first],"next_cursor":"opaque"]),
            try json(["version":"MESSAGE-history.2","messages":[second],"next_cursor":NSNull()])],noStore:true)
        let host=try setup(shell(),wire,tripDiscussions:true)
        await host.loadConversations(context:host.captureReadContext())
        #expect(host.selectConversation(try #require(host.conversations.first),token:host.conversationSelectionToken))
        await host.loadHistory(context:host.captureReadContext());#expect(host.hasMoreMessages)
        await host.loadHistory(context:host.captureReadContext(),more:true)
        #expect(host.messages.count==2 && host.tripMessages.count==2 && !host.hasMoreMessages)
        guard case .trip(let ref)=try #require(host.tripMessages.first).association else { Issue.record("reference discarded");return }
        #expect(ref.messageID=="m-a-1" && ref.trip==nil)
        #expect(host.messages.first?.original_utf8_base64==first["original_utf8_base64"] as? String)
        #expect(await wire.operations==["listConversations","readTripDiscussionHistoryV2","readTripDiscussionHistoryV2"])
    }
    @Test func retiredAccountCannotPublishLateDiscussionHistoryOrTextProjection() async throws {
        let shell=try shell(),wire=HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()]),
            try json(["version":"MESSAGE-history.2","messages":[tripHistory("a")],"next_cursor":NSNull()])],hold:"readTripDiscussionHistoryV2",noStore:true)
        let host=try setup(shell,wire,tripDiscussions:true)
        await host.loadConversations(context:host.captureReadContext())
        #expect(host.selectConversation(try #require(host.conversations.first),token:host.conversationSelectionToken))
        let read=Task { await host.loadHistory(context:host.captureReadContext()) }
        await waitForHold(wire);shell.invalidateIdentity();await wire.release();await read.value
        #expect(host.historyStatus == .unconfigured && host.messages.isEmpty && host.tripMessages.isEmpty)
    }
    @Test func defaultUnavailableAndValidEmptyAreDifferent() async throws {
        let shell = try shell(); let empty = ServerHistoryHost(shell: shell)
        await empty.loadConversations(context: empty.captureReadContext()); #expect(empty.conversationsStatus == .unconfigured)
        let t = HistoryInterceptor([try json(["conversations":[],"next_cursor":NSNull()])])
        let host = try setup(shell,t); await host.loadConversations(context: host.captureReadContext())
        #expect(host.conversationsStatus == .empty && host.conversations.isEmpty)
        #expect(await t.methods == [.get])
    }
    @Test func pagesAppendOnceAndRepeatedCursorRequiresResync() async throws {
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":"same"]),
            try json(["conversations":[chat("b",2)],"next_cursor":"same"])])
        let host = try setup(try shell(),t)
        await host.loadConversations(context: host.captureReadContext()); #expect(host.hasMoreConversations)
        await host.loadConversations(context: host.captureReadContext(), more:true)
        #expect(host.conversationsStatus == .resync && host.conversations.isEmpty && !host.hasMoreConversations)
        await host.loadConversations(context: host.captureReadContext(), more:true); #expect(await t.methods == [.get,.get])
    }
    @Test func lateHistoryAIsNotDisplayedInSelectedB() async throws {
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1),chat("b",2)],"next_cursor":NSNull()]),
            try json(["messages":[history("a")],"next_cursor":NSNull()]),
            try json(["messages":[history("b")],"next_cursor":NSNull()])],hold:"readMessageHistory")
        let host = try setup(try shell(),t); await host.loadConversations(context: host.captureReadContext())
        #expect(host.selectConversation(host.conversations[0], token: host.conversationSelectionToken))
        let old = Task { await host.loadHistory(context: host.captureReadContext()) }
        await waitForHold(t)
        #expect(host.selectConversation(host.conversations[1], token: host.conversationSelectionToken))
        await host.loadHistory(context: host.captureReadContext())
        await t.release(); await old.value
        #expect(host.selectedConversation?.conversation_id == "b")
        #expect(host.messages.map(\.text) == ["synthetic b"])
    }
    @Test func nullAndSavedEmptyDraftNeverReplaceLocalEditor() async throws {
        let shell = try shell(); shell.draft = "local unsaved edit"
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()]),try json(["draft":NSNull()]),
            try json(["draft":["conversation_id":"a","generation":"g1","revision":1,"original_utf8_base64":""]])])
        let host = try setup(shell,t); await host.loadConversations(context: host.captureReadContext()); #expect(host.selectConversation(host.conversations[0], token: host.conversationSelectionToken))
        await host.loadServerDraft(context: host.captureReadContext()); #expect(host.draftStatus == .empty && host.serverDraft == nil)
        await host.loadServerDraft(context: host.captureReadContext()); #expect(host.draftStatus == .ready && host.serverDraft?.original_utf8_base64 == "")
        #expect(shell.draft == "local unsaved edit")
    }
    @Test func invalidReadFailsRatherThanEmptySuccess() async throws {
        let t = HistoryInterceptor([try json(["conversations":[]])])
        let host = try setup(try shell(),t); await host.loadConversations(context: host.captureReadContext())
        #expect(host.conversationsStatus == .failed && host.conversations.isEmpty)
    }
    @Test func identityFenceHidesLateResultsAndLanguagePreservesLifetime() async throws {
        let shell = try shell()
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()])],hold:"listConversations")
        let host = try setup(shell,t); let original = shell.generation
        let loading = Task { await host.loadConversations(context: host.captureReadContext()) }
        await waitForHold(t)
        shell.selectLanguage(.chinese); #expect(shell.generation == original && host.conversationsStatus == .loading)
        shell.invalidateIdentity()
        #expect(host.conversationsStatus == .unconfigured && host.conversations.isEmpty)
        await t.release(); await loading.value
        #expect(host.conversationsStatus == .unconfigured && host.conversations.isEmpty)
    }
    @Test func distinctCanonicalUnicodeCursorsKeepTheirOriginalUTF8Pages() async throws {
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":"é"]),
            try json(["conversations":[chat("b",2)],"next_cursor":"e\u{301}"]),
            try json(["conversations":[chat("c",3)],"next_cursor":NSNull()])])
        let host = try setup(try shell(),t)
        await host.loadConversations(context: host.captureReadContext())
        let oldToken = host.conversationSelectionToken
        let oldRow = host.conversations[0]
        await host.loadConversations(context: host.captureReadContext(), more:true)
        #expect(!host.selectConversation(oldRow, token: oldToken))
        #expect(host.conversationsStatus == .ready && host.hasMoreConversations)
        await host.loadConversations(context: host.captureReadContext(), more:true)
        #expect(host.conversations.map(\.conversation_id) == ["a","b","c"])
        #expect(host.conversationsStatus == .ready && !host.hasMoreConversations)
        #expect(await t.methods == [.get,.get,.get])
    }

    @Test func historyPagesKeepOneSelectedConversationAndOrderedServerSequence() async throws {
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()]),
            try json(["messages":[history("a")],"next_cursor":"history-next"]),
            try json(["messages":[history("a",sequence:2)],"next_cursor":NSNull()])])
        let host = try setup(try shell(),t); await host.loadConversations(context: host.captureReadContext())
        #expect(host.selectConversation(host.conversations[0], token: host.conversationSelectionToken))
        await host.loadHistory(context: host.captureReadContext()); #expect(host.hasMoreMessages)
        await host.loadHistory(context: host.captureReadContext(), more:true)
        #expect(host.historyStatus == .ready && host.messages.map(\.receipt.sequence) == [1,2] && !host.hasMoreMessages)
        await host.loadHistory(context: host.captureReadContext(), more:true); #expect(await t.methods == [.get,.get,.get])
    }
    @Test func historyGenerationDifferentFromSelectionRequiresResync() async throws {
        var item = history("a")
        var receipt = try #require(item["receipt"] as? [String:Any]); receipt["generation"] = "g2"; item["receipt"] = receipt
        let t = HistoryInterceptor([try json(["conversations":[chat("a",1)],"next_cursor":NSNull()]),
            try json(["messages":[item],"next_cursor":NSNull()])])
        let host = try setup(try shell(),t); await host.loadConversations(context: host.captureReadContext())
        #expect(host.selectConversation(host.conversations[0], token: host.conversationSelectionToken))
        await host.loadHistory(context: host.captureReadContext())
        #expect(host.historyStatus == .resync && host.messages.isEmpty)
    }

}
