import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJTripClient
import CJMessageHTTP
import CJMessageClient
import CryptoKit
@testable import CJShell

private let discussionTripTrace = "00000000-0000-4000-8000-000000000021"
private actor DiscussionTripRead: ClientTransport {
    let raw: Data
    var calls = 0
    init(_ raw: Data) { self.raw=raw }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && body == nil && operationID == "readStructuredTripV1")
        calls += 1
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=discussionTripTrace
        return (HTTPResponse(status:.ok,headerFields:headers),HTTPBody(raw))
    }
}
@MainActor private final class DiscussionTripLifetime {
    let binding=TripBinding(environment:UUID(),account:UUID(),generation:UUID(),selection:UUID())
    var current=true
}
@MainActor struct TripDiscussionEntryTests {
    private func source(_ name:String) throws -> Data {
        struct Golden: Decodable { let name:String;let canonical_utf8_base64:String;let sha256:String }
        var root=URL(fileURLWithPath:#filePath)
        for _ in 0..<4 { root.deleteLastPathComponent() }
        let values=try JSONDecoder().decode([Golden].self,from:Data(contentsOf:root.appendingPathComponent("CJTripClient/Tests/CJTripClientTests/Fixtures/STRUCTURED-V1.json")))
        let fixture=try #require(values.first { $0.name==name }),raw=try #require(Data(base64Encoded:fixture.canonical_utf8_base64))
        return Data(("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\""+discussionTripTrace+"\",\"trip\":{\"trip_id\":\"trip-a\",\"version\":7,\"content_sha256\":\""+fixture.sha256+"\",\"content\":"+String(decoding:raw,as:UTF8.self)+"}}").utf8)
    }
    private func setup(_ name:String,shell:ShellState?=nil) throws -> (TripTimelineHost,TripClient,DiscussionTripLifetime,ShellGeneration,DiscussionTripRead) {
        let lifetime=DiscussionTripLifetime(),shell=try shell ?? ShellState(preferences:#require(UserDefaults(suiteName:UUID().uuidString)))
        let wire=DiscussionTripRead(try source(name))
        let client=TripClient(endpoint:try TripEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:16384,maximumResponseBytes:100000),credentials:{ _ in "synthetic" },currentBinding:{ lifetime.current ? lifetime.binding : nil },interceptedTransport:wire)
        let host=TripTimelineHost(client:client,binding:lifetime.binding,generation:shell.generation,current:{ lifetime.current })
        return (host,client,lifetime,shell.generation,wire)
    }
    @Test func onlyAcceptedExplicitSourceMintsDayItemAndWholeTrip() async throws {
        let (host,_,lifetime,generation,wire)=try setup("explicit")
        #expect(throws:(any Error).self) { try host.discussion(context:host.display()?.discussion,day:nil,itemID:nil) }
        await host.perform(try host.select("trip-a"))
        let day=try MessageTripSelection.Day(date:"2026-11-01",timezone:"Asia/Shanghai")
        let choice=try host.discussion(context:host.display()?.discussion,day:day,itemID:"item-1")
        try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation)
        #expect(choice.selection.id=="trip-a" && choice.selection.expectedVersion==7 && choice.selection.day==day && choice.selection.itemID=="item-1")
        let whole=try host.discussion(context:host.display()?.discussion,day:nil,itemID:nil)
        #expect(whole.selection.day==nil && whole.selection.itemID==nil)
        #expect(Mirror(reflecting:choice).children.isEmpty)
        #expect(await wire.calls==1)
        #expect(throws:(any Error).self) { try host.discussion(context:host.display()?.discussion,day:nil,itemID:"other-item") }
        #expect(throws:(any Error).self) { try host.discussion(context:host.display()?.discussion,day:MessageTripSelection.Day(date:"2026-11-01",timezone:"America/New_York"),itemID:"item-1") }
    }
    @Test func unknownScheduleNeverBecomesDeviceDayButItemIsStillExplicit() async throws {
        let (host,_,_,_,_)=try setup("unknown")
        await host.perform(try host.select("trip-a"))
        let item=try host.discussion(context:host.display()?.discussion,day:nil,itemID:"item-1")
        #expect(item.selection.day==nil && item.selection.itemID=="item-1")
        #expect(throws:(any Error).self) { try host.discussion(context:host.display()?.discussion,day:MessageTripSelection.Day(date:"2026-11-01",timezone:"Asia/Shanghai"),itemID:"item-1") }
    }
    @Test func closingViewKeepsCapturedSourceButABAOrOwnerChangeRetiresIt() async throws {
        let (host,client,lifetime,generation,_)=try setup("explicit")
        await host.perform(try host.select("trip-a"))
        let choice=try host.discussion(context:host.display()?.discussion,day:nil,itemID:"item-1")
        host.invalidate()
        try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation)
        #expect(throws:TripFailure.staleBinding) { try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:UUID().uuidString,generation:generation) }
        _=try client.prepareStructuredDetail(id:"trip-b",binding:lifetime.binding)
        _=try client.prepareStructuredDetail(id:"trip-a",binding:lifetime.binding)
        #expect(throws:TripFailure.staleBinding) { try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation) }
    }
    @Test func identityRetirementHidesSourceAndCannotMintAnotherEntry() async throws {
        let (host,_,lifetime,generation,_)=try setup("explicit")
        await host.perform(try host.select("trip-a"))
        let choice=try host.discussion(context:host.display()?.discussion,day:nil,itemID:nil)
        let displayed=host.display()?.discussion
        lifetime.current=false
        #expect(host.display()==nil)
        #expect(throws:TripFailure.staleBinding) { try host.discussion(context:displayed,day:nil,itemID:nil) }
        #expect(throws:TripFailure.staleBinding) { try choice.validate(scopeEnvironment:lifetime.binding.environment.uuidString,scopeAccount:lifetime.binding.account.uuidString,generation:generation) }
    }
    @Test func displayedDiscussionContextCannotSilentlyBindANewerReadOfSameTrip() async throws {
        let (host,_,_,_,_)=try setup("explicit")
        await host.perform(try host.select("trip-a"))
        let old=try #require(host.display()?.discussion)
        await host.perform(try host.select("trip-a"))
        #expect(throws:TripFailure.staleBinding) { try host.discussion(context:old,day:nil,itemID:"item-1") }
        _=try host.discussion(context:host.display()?.discussion,day:nil,itemID:"item-1")
    }
    private func messages(_ shell:ShellState,lifetime:DiscussionTripLifetime,wire:DiscussionMessageWire,storage:DiscussionMessageStore=DiscussionMessageStore(),messageID:String?=nil) throws -> (AssistantMessageHost,MessageRecovery) {
        let recovery=MessageRecovery(storage:storage)
        let scope=try StorageScope(environment:lifetime.binding.environment.uuidString,account:lifetime.binding.account.uuidString),lease=try recovery.activate(scope)
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let client=MessageHTTPClient(recovery:recovery,scope:scope,endpoint:endpoint,credentials:DiscussionMessageCredentials(),interceptedTestTransport:wire)
        let host=AssistantMessageHost(shell:shell)
        #expect(host.bind(.init(recovery:recovery,scope:scope,lease:lease,generation:shell.generation,conversationID:messageID == nil ? nil : "chat",messageID:messageID,synthetic:true,isCurrent:{ lifetime.current },invalidateResources:{},sendClient:client,tripDiscussions:true)))
        return (host,recovery)
    }
    private func wait(_ condition:()->Bool) async {
        for _ in 0..<2000 { if condition() { return };await Task.yield() }
        #expect(condition())
    }
    @Test func explicitUnboundChoiceSendsOnlyDiscussionAndCapturesOriginalReference() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        #expect(host.selectConversationForSending("chat"));await wait { !host.isBusy }
        shell.draft="SYNTHETIC ambiguous this Trip"
        #expect(!host.canSend)
        #expect(host.selectUnboundDiscussion() && host.canSend)
        host.creationIntent = .considerTrip;#expect(!host.canSend);host.creationIntent = .none
        host.sendNew();await wait { !host.isBusy }
        let accepted=try #require(host.captureAcceptedRunReceipt()),ref=try #require(accepted.tripReference)
        #expect(ref.trip==nil && accepted.travelReference==nil && accepted.isCurrent())
        let raw=try #require(await wire.posts.first),value=try #require(JSONSerialization.jsonObject(with:raw) as? [String:Any])
        #expect(value["version"] as? String == "MESSAGE-send.3" && value["creation_intent"] as? String == "none" && value["trip_context"] is NSNull && value["needs_reference"] is NSNull)
    }
    @Test func actualAcceptedTripEntryBindsOriginalDayItemAndSelectionChangeRetiresRun() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (timeline,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        await timeline.perform(try timeline.select("trip-a"))
        let choice=try timeline.discussion(context:timeline.display()?.discussion,day:MessageTripSelection.Day(date:"2026-11-01",timezone:"Asia/Shanghai"),itemID:"item-1")
        await wire.useContent(choice.content)
        #expect(host.selectTripDiscussion(choice));timeline.invalidate()
        #expect(host.selectConversationForSending("chat"));await wait { !host.isBusy }
        shell.draft="SYNTHETIC discuss original item";#expect(host.canSend);host.sendNew();await wait { !host.isBusy }
        let accepted=try #require(host.captureAcceptedRunReceipt()),ref=try #require(accepted.tripReference)
        #expect(ref.trip==choice.selection && ref.trip?.expectedVersion==7 && ref.trip?.day?.date=="2026-11-01" && ref.trip?.itemID=="item-1")
        #expect(ref.contentSHA256==choice.content.sha256 && ref.contentVersion==choice.content.version)
        #expect(host.selectUnboundDiscussion());#expect(!accepted.isCurrent() && host.captureAcceptedRunReceipt()==nil)
    }
    @Test func refusedHeadRemainsExplicitAfterChoiceAndNeverCreatesMessage() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        await wire.refuseHead()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        #expect(host.selectConversationForSending("chat"));await wait { !host.isBusy }
        #expect(host.discussionRefusal?.status==503 && host.discussionRefusal?.code=="MESSAGE_CONTEXT_UNAVAILABLE")
        #expect(host.selectUnboundDiscussion());shell.draft="retained";host.sendNew()
        #expect(host.discussionRefusal != nil && !host.canSend && host.visibleRecord==nil && shell.draft=="retained")
        #expect(await wire.posts.isEmpty)
    }
    @Test func lostACKReopenQueriesOriginalWithoutNewSelectionOrPOST() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire(),storage=DiscussionMessageStore()
        let (host,recovery)=try messages(shell,lifetime:lifetime,wire:wire,storage:storage)
        #expect(host.selectConversationForSending("chat"));await wait { !host.isBusy }
        #expect(host.selectUnboundDiscussion());shell.draft="original";await wire.loseACK()
        host.sendNew();await wait { !host.isBusy }
        let original=try #require(host.visibleRecord);#expect(original.phase == .queryRequired && !host.canResubmit)
        host.invalidate();recovery.invalidate()
        let nextShell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (restored,_)=try messages(nextShell,lifetime:lifetime,wire:wire,storage:storage,messageID:original.messageID)
        #expect(restored.canQuery && !restored.canResubmit && !restored.canSend)
        restored.queryOriginal();await wait { !restored.isBusy }
        #expect(restored.visibleRecord?.phase == .accepted && restored.captureAcceptedRunReceipt()?.tripReference?.messageID==original.messageID)
        #expect(await wire.posts==[original.originalUTF8])
    }
    @Test func identityChangeWhilePostReturnsCannotPublishOldReceipt() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        #expect(host.selectConversationForSending("chat"));await wait { !host.isBusy }
        #expect(host.selectUnboundDiscussion());shell.draft="original"
        await wire.onReturn { shell.invalidateIdentity() }
        host.sendNew();await wait { !host.isBusy }
        #expect(host.visibleRecord==nil && host.captureAcceptedRunReceipt()==nil && !host.supportsTripDiscussions)
        #expect(await wire.posts.count==1)
    }
    @Test func newDiscussionChatUsesOneFreshIDAndDoesNotCarryEarlierTripDraft() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        #expect(host.selectConversationForSending("chat"));await wait { !host.isBusy }
        shell.draft="SYNTHETIC old travel condition";host.saveDraft();#expect(host.selectUnboundDiscussion())
        let intent=try #require(host.captureNewConversationIntent());host.performConversationIntent(intent);await wait { !host.isBusy }
        let cid=try #require(host.selectedConversation)
        #expect(cid.hasPrefix("discussion.") && shell.draft.isEmpty && host.canSend==false)
        #expect(await wire.created==[cid]);#expect(await wire.posts.isEmpty)
        host.performConversationIntent(intent);#expect(await wire.created.count==1)
        let projection=try #require(host.visibleProjection),old=try #require(projection.drafts.first { $0.conversationID=="chat" })
        #expect(host.selectDraft(old,from:projection));#expect(shell.draft=="SYNTHETIC old travel condition")
    }
    @Test func unknownNewChatReopenOnlyReconcilesOriginalAndDoesNotReplaceCurrentEditor() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire(),storage=DiscussionMessageStore()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire,storage:storage)
        #expect(host.selectUnboundDiscussion());await wire.loseOpeningACK()
        host.performConversationIntent(try #require(host.captureNewConversationIntent()));await wait { !host.isBusy }
        let cid=try #require(host.conversationOpenings.first?.conversationID)
        #expect(host.captureNewConversationIntent()==nil);host.invalidate()
        let nextShell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (restored,_)=try messages(nextShell,lifetime:lifetime,wire:wire,storage:storage)
        nextShell.draft="SYNTHETIC unassigned editor"
        restored.performConversationIntent(try #require(restored.captureConversationQuery(id:cid)));await wait { !restored.isBusy }
        #expect(nextShell.draft=="SYNTHETIC unassigned editor" && restored.selectedConversation==nil)
        #expect(restored.conversationOpenings.first?.phase == .available)
        #expect(await wire.created==[cid])
    }
    @Test func renderedNewChatIntentCannotBindAChangedChoiceOrEditedDraft() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        #expect(host.selectUnboundDiscussion());let old=try #require(host.captureNewConversationIntent())
        #expect(host.selectUnboundDiscussion());host.performConversationIntent(old)
        #expect(host.conversationOpenings.isEmpty)
        let beforeEdit=try #require(host.captureNewConversationIntent());shell.draft="SYNTHETIC unsaved edit"
        host.performConversationIntent(beforeEdit);#expect(host.conversationOpenings.isEmpty && shell.draft=="SYNTHETIC unsaved edit")
        #expect(await wire.created.isEmpty)
    }
    @Test func accountChangeAtNewChatReplyCannotExposeOriginalChatInReplacementRoot() async throws {
        let shell=ShellState(preferences:try #require(UserDefaults(suiteName:UUID().uuidString)))
        let (_,_,lifetime,_,_)=try setup("explicit",shell:shell),wire=DiscussionMessageWire()
        let (host,_)=try messages(shell,lifetime:lifetime,wire:wire)
        #expect(host.selectUnboundDiscussion());await wire.beforeOpeningReturn { shell.invalidateIdentity() }
        host.performConversationIntent(try #require(host.captureNewConversationIntent()));await wait { !host.isBusy }
        #expect(host.conversationOpenings.isEmpty && host.selectedConversation==nil && host.captureNewConversationIntent()==nil)
        #expect(await wire.created.count==1)
    }
}

@MainActor private final class DiscussionMessageStore:SecureMessageStorage {
    var value:Snapshot?
    func load(scope:StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot:Snapshot,scope:StorageScope) throws { value=snapshot }
}
@MainActor private final class DiscussionMessageCredentials:MessageCredentialsProvider {
    func bearer(for scope:StorageScope,lease:Lease) async throws -> String? { "synthetic-only" }
}
private actor DiscussionMessageWire:ClientTransport {
    var posts:[Data]=[],sequences:[String:Int]=[:]
    var created:[String]=[]
    var lostOpening=false
    var openingReturned:(@MainActor @Sendable ()->Void)?
    var accepted:[String:Any]?
    var refuse=false,lost=false
    var returned:(@MainActor @Sendable ()->Void)?
    var content:MessageTripContent?
    func useContent(_ value:MessageTripContent) { content=value }
    func refuseHead() { refuse=true }
    func loseACK() { lost=true }
    func onReturn(_ callback:@escaping @MainActor @Sendable ()->Void) { returned=callback }
    func loseOpeningACK() { lostOpening=true }
    func beforeOpeningReturn(_ callback:@escaping @MainActor @Sendable ()->Void) { openingReturned=callback }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        let trace=UUID().uuidString
        var value:[String:Any],status=200
        if operationID=="openConversation" {
            #expect(request.method == .put && body==nil)
            let cid=try #require(URLComponents(string:request.path!)?.queryItems?.first?.value)
            created.append(cid)
            if lostOpening { lostOpening=false;throw URLError(.networkConnectionLost) }
            value=["request_id":trace,"conversation_id":cid,"generation":"g","last_sequence":0]
            if let openingReturned { self.openingReturned=nil;await openingReturned() }
        } else if operationID=="receiveTripDiscussionV3" {
            let raw=try await Data(collecting:#require(body),upTo:65536);posts.append(raw)
            let input=try #require(JSONSerialization.jsonObject(with:raw) as? [String:Any]),trip=input["trip_context"] as? [String:Any]
            let cid=try #require(input["conversation_id"] as? String),sequence=(sequences[cid] ?? 0)+1;sequences[cid]=sequence
            let receipt:[String:Any]=["message_id":input["message_id"]!,"conversation_id":cid,"generation":"g","sequence":sequence,"run_id":"r1","input_sha256":SHA256.hash(data:raw).map { String(format:"%02x",$0) }.joined()]
            let contentVersion:Any,contentHash:Any
            if trip != nil { let value=try #require(content);contentVersion=value.version;contentHash=value.sha256 }
            else { contentVersion=NSNull();contentHash=NSNull() }
            var ref=receipt
            ref.merge(["version":"MESSAGE-trip-reference.1","message_version":"MESSAGE-send.3","selection_epoch":1,"context_kind":trip == nil ? "none" : "trip","context_id":trip?["id"] ?? NSNull(),"context_version":trip?["expected_version"] ?? NSNull(),"trip_context":trip as Any? ?? NSNull(),"content_version":contentVersion,"content_sha256":contentHash],uniquingKeysWith:{ _,new in new })
            value=["request_id":trace,"version":"MESSAGE-accept.3","receipt":receipt,"reference":ref];accepted=value
            if lost { lost=false;throw URLError(.networkConnectionLost) }
            if let returned { self.returned=nil;await returned() }
        } else {
            #expect(operationID=="readTripDiscussionStatusV3")
            let query=URLComponents(string:request.path!)?.queryItems
            let message=query?.first { $0.name=="message_id" }?.value,cid=try #require(query?.first { $0.name=="conversation_id" }?.value)
            let original=message == nil ? nil : accepted
            value=["request_id":trace,"version":"MESSAGE-send-status.3","receipt":original?["receipt"] ?? NSNull(),"reference":original?["reference"] ?? NSNull(),"head":cid=="chat" || created.contains(cid) ? ["conversation_id":cid,"generation":"g","last_sequence":sequences[cid] ?? 0] : NSNull()]
            if refuse {
                status=503;value=["request_id":trace,"error":["code":"MESSAGE_CONTEXT_UNAVAILABLE","category":"dependency","message_en":"Request unavailable","message_zh":"请求不可用","outcome":"unknown","recovery":"reconcile_original"]]
            }
        }
        var headers=HTTPFields();headers[.contentType]="application/json";headers[.cacheControl]="no-store";headers[.init("x-request-id")!]=trace
        return (HTTPResponse(status:.init(code:status),headerFields:headers),HTTPBody(try JSONSerialization.data(withJSONObject:value)))
    }
}
