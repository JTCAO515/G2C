import Foundation
import Testing
import CJAPI
import CJMessageClient
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class ConversationTestStore:SecureMessageStorage {
    var value:Snapshot?
    func load(scope:StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot:Snapshot,scope:StorageScope) throws { value=snapshot }
}
@MainActor private final class ConversationCredentials:MessageCredentialsProvider {
    var callback:(()->Void)?
    func bearer(for scope:StorageScope,lease:Lease) async throws -> String? { callback?();return "synthetic-only" }
}
private actor ConversationWire:ClientTransport {
    var puts:[String]=[],reads:[String]=[]
    var opened:String?
    var loseACK=false,wrongID=false,deny=false
    var edit=false
    func configure(loseACK:Bool=false,wrongID:Bool=false,deny:Bool=false,edit:Bool=false) { self.loseACK=loseACK;self.wrongID=wrongID;self.deny=deny;self.edit=edit }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        let path=try #require(request.path)
        let query=try #require(URLComponents(string:path)?.queryItems),id=try #require(query.first?.value),trace=UUID().uuidString
        #expect(query.count==1 && query[0].name=="conversation_id" && body==nil)
        var value:[String:Any],status=200
        if operationID==Operations.openConversation.id {
            #expect(request.method == .put);puts.append(request.path!)
            if deny {
                status=401;value=["request_id":trace,"error":["code":"ACCESS_DENIED","category":"access","message_en":"Denied","message_zh":"拒绝","outcome":"failed","recovery":"do_not_retry"]]
            } else {
                opened=id
                if loseACK { throw URLError(.networkConnectionLost) }
                value=["request_id":trace,"conversation_id":wrongID ? "other" : id,"generation":"g","last_sequence":0]
            }
        } else {
            #expect(operationID==(edit ? "readTripEditStatusV4" : "readTripDiscussionStatusV3") && request.method == .get);reads.append(request.path!)
            value=["request_id":trace,"version":edit ? "MESSAGE-send-status.4" : "MESSAGE-send-status.3","receipt":NSNull(),"reference":NSNull(),"head":opened == id ? ["conversation_id":id,"generation":"g","last_sequence":0] : NSNull()]
        }
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=trace
        return (HTTPResponse(status:.init(code:status),headerFields:headers),HTTPBody(try JSONSerialization.data(withJSONObject:value)))
    }
}
@MainActor struct DiscussionConversationTests {
    @Test func scopedOpeningUsesOriginalIDAndOnlyFourthStatusAfterUnknownACK() async throws {
        let wire=ConversationWire(),store=ConversationTestStore()
        let (recovery,lease,client,scope)=try setup(wire,store:store)
        let work=try client.prepareNewTripEditConversation(lease:lease)
        await wire.configure(loseACK:true,edit:true)
        await #expect(throws:(any Error).self) { try await client.performDiscussionConversation(work) }
        recovery.invalidate()
        let (_,next,reopened,_)=try setup(wire,store:store,scope:scope)
        let query=try reopened.prepareTripEditConversationQuery(id:work.conversationID,lease:next)
        guard case .available(let id)=try await reopened.performDiscussionConversation(query) else { Issue.record("original scoped chat unavailable");return }
        #expect(id==work.conversationID)
        #expect(await wire.puts.count==1)
        #expect(await wire.reads.count==1)
        #expect(await wire.reads.first?.hasPrefix("/v4/message-send-status?")==true)
    }
    private func setup(_ wire:ConversationWire,store:ConversationTestStore=ConversationTestStore(),scope:StorageScope?=nil,credentials:ConversationCredentials=ConversationCredentials()) throws -> (MessageRecovery,Lease,MessageHTTPClient,StorageScope) {
        let scope=try scope ?? StorageScope(environment:UUID().uuidString,account:"synthetic"),recovery=MessageRecovery(storage:store),lease=try recovery.activate(scope)
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:16384,maximumResponseBytes:65536)
        return (recovery,lease,MessageHTTPClient(recovery:recovery,scope:scope,endpoint:endpoint,credentials:credentials,interceptedTestTransport:wire),scope)
    }
    @Test func uniqueOpeningIsDurableBeforePUTAndCannotDispatchTwice() async throws {
        let wire=ConversationWire(),(recovery,lease,client,_)=try setup(wire)
        let work=try client.prepareNewDiscussionConversation(lease:lease)
        #expect(try recovery.conversationOpenings(lease:lease).first?.conversationID==work.conversationID)
        #expect(await wire.puts.isEmpty)
        guard case .available(let id)=try await client.performDiscussionConversation(work) else { Issue.record("missing original chat");return }
        let phase=try recovery.conversationOpenings(lease:lease).first?.phase
        #expect(id==work.conversationID && phase == .available)
        await #expect(throws:(any Error).self) { try await client.performDiscussionConversation(work) }
        #expect(await wire.puts.count==1)
    }
    @Test func lostACKReopenCanOnlyReadSameOriginalAndNeverCreatesAnotherChat() async throws {
        let wire=ConversationWire(),store=ConversationTestStore(),(recovery,lease,client,scope)=try setup(wire,store:store)
        let work=try client.prepareNewDiscussionConversation(lease:lease);await wire.configure(loseACK:true)
        await #expect(throws:(any Error).self) { try await client.performDiscussionConversation(work) }
        recovery.invalidate()
        let (restored,next,reopened,_)=try setup(wire,store:store,scope:scope)
        #expect(throws:RecoveryError.queryOnly) { try reopened.prepareNewDiscussionConversation(lease:next) }
        let query=try reopened.prepareDiscussionConversationQuery(id:work.conversationID,lease:next)
        guard case .available(let id)=try await reopened.performDiscussionConversation(query) else { Issue.record("original absent");return }
        let phase=try restored.conversationOpenings(lease:next).first?.phase
        #expect(id==work.conversationID && phase == .available)
        #expect(await wire.puts.count==1);#expect(await wire.reads.count==1)
    }
    @Test func emptyOriginalReadIsUnknownAndDoesNotPermitANewOpening() async throws {
        let wire=ConversationWire(),store=ConversationTestStore(),(recovery,lease,client,scope)=try setup(wire,store:store)
        let work=try client.prepareNewDiscussionConversation(lease:lease)
        // Simulate process loss before dispatch: no network result can be inferred.
        recovery.invalidate();let (_,next,reopened,_)=try setup(wire,store:store,scope:scope)
        let query=try reopened.prepareDiscussionConversationQuery(id:work.conversationID,lease:next)
        guard case .unknown=try await reopened.performDiscussionConversation(query) else { Issue.record("empty read settled unknown");return }
        #expect(throws:RecoveryError.queryOnly) { try reopened.prepareNewDiscussionConversation(lease:next) }
        #expect(await wire.puts.isEmpty)
    }
    @Test func wrongReceiptAndChangedIdentityCannotGrantChatOrSendingAuthority() async throws {
        let wire=ConversationWire(),credentials=ConversationCredentials(),(recovery,lease,client,_)=try setup(wire,credentials:credentials)
        let work=try client.prepareNewDiscussionConversation(lease:lease);await wire.configure(wrongID:true)
        await #expect(throws:(any Error).self) { try await client.performDiscussionConversation(work) }
        #expect(try recovery.conversationOpenings(lease:lease).first?.phase == .queryRequired)
        let otherWire=ConversationWire(),otherCredentials=ConversationCredentials(),(otherRecovery,next,other,_)=try setup(otherWire,credentials:otherCredentials)
        let pending=try other.prepareNewDiscussionConversation(lease:next);otherCredentials.callback={ otherRecovery.invalidate() }
        await #expect(throws:(any Error).self) { try await other.performDiscussionConversation(pending) }
        #expect(await otherWire.puts.isEmpty)
    }
    @Test func definiteFailedOpeningRetainsProofAndDoesNotEraseEarlierDrafts() async throws {
        let wire=ConversationWire(),(recovery,lease,client,_)=try setup(wire)
        try recovery.saveDraft(Data("SYNTHETIC old draft".utf8),conversationID:"old-chat",lease:lease)
        let work=try client.prepareNewDiscussionConversation(lease:lease);await wire.configure(deny:true)
        guard case .rejected(let status,_)=try await client.performDiscussionConversation(work) else { Issue.record("rejection lost");return }
        let phase=try recovery.conversationOpenings(lease:lease).first?.phase
        #expect(status==401 && phase == .failed)
        #expect(try recovery.draft(conversationID:"old-chat",lease:lease)==Data("SYNTHETIC old draft".utf8))
        #expect(try client.prepareNewDiscussionConversation(lease:lease).conversationID != work.conversationID)
    }
}
