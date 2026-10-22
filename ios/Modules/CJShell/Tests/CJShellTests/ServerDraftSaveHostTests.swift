import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
import CJMessageHTTP
import CJAuth
import CJSession
@testable import CJShell

@MainActor private final class SaveStore: SecureMessageStorage {
    var value: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { value = snapshot }
}
@MainActor private final class SaveCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}
@MainActor private final class SaveSession: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private struct SaveReply: Sendable { let bytes: Data?; var status = 200 }
private actor SaveTransport: ClientTransport {
    var replies: [SaveReply]
    var methods: [HTTPRequest.Method] = []
    var putBytes: [Data] = []
    let holdPUT: Bool
    var waiting: CheckedContinuation<Void, Never>?
    init(_ replies: [SaveReply], holdPUT: Bool = false) { self.replies = replies; self.holdPUT = holdPUT }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        methods.append(request.method)
        if request.method == .put {
            if let body { putBytes.append(try await Data(collecting: body, upTo:4096)) }
            if holdPUT { await withCheckedContinuation { waiting = $0 } }
        }
        guard !replies.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        let reply = replies.removeFirst()
        guard let bytes = reply.bytes else { throw URLError(.networkConnectionLost) }
        var response = HTTPResponse(status:.init(code:reply.status))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = "00000000-0000-4000-8000-000000000001"
        response.headerFields[.contentType] = "application/json"
        return (response,HTTPBody(bytes))
    }
    func release() { waiting?.resume(); waiting = nil }
    var isWaiting: Bool { waiting != nil }
}

@Suite @MainActor struct ServerDraftSaveHostTests {
    private func json(_ fields:[String:Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject:fields.merging(["request_id":"00000000-0000-4000-8000-000000000001"]){x,_ in x})
    }
    private func saved(_ text: String, revision: Int = 1) throws -> Data {
        try json(["draft":["conversation_id":"a","generation":"g1","revision":revision,"original_utf8_base64":Data(text.utf8).base64EncodedString()]])
    }
    private func setup(_ replies:[SaveReply], hold: Bool = false, capability: Bool = true) async throws -> (ShellState,ServerHistoryHost,MessageRecovery,Lease,SaveTransport) {
        let shell = ShellState(preferences:try #require(UserDefaults(suiteName:"draft-host-"+UUID().uuidString)))
        let prefix = [SaveReply(bytes:try json(["conversations":[["conversation_id":"a","generation":"g1","epoch":0,"list_sequence":1]],"next_cursor":NSNull()])),
                      SaveReply(bytes:try json(["draft":NSNull()]))]
        let transport = SaveTransport(prefix+replies,holdPUT:hold)
        let recovery = MessageRecovery(storage:SaveStore())
        let scope = try StorageScope(environment:UUID().uuidString,account:"synthetic")
        let lease = try recovery.activate(scope)
        let client = MessageHTTPClient(recovery:recovery,scope:scope,
            endpoint:try .init(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:4096,maximumResponseBytes:16384),
            credentials:SaveCredentials(),interceptedTestTransport:transport)
        let host = ServerHistoryHost(shell:shell)
        #expect(host.bind(.init(client:client,recovery:recovery,scope:scope,lease:lease,generation:shell.generation,
            limit:2,limits:try .init(maximumPageItems:2,maximumCursorBytes:128,maximumDecodedBytes:4096,maximumPages:5),
            synthetic:true,draftWriteCapability:capability ? .interceptedTestOnly : nil,isCurrent:{true})))
        await host.loadConversations(context:host.captureReadContext())
        #expect(host.selectConversation(host.conversations[0],token:host.conversationSelectionToken))
        await host.loadServerDraft(context:host.captureReadContext())
        return (shell,host,recovery,lease,transport)
    }
    private func waitForPUT(_ transport:SaveTransport) async {
        for _ in 0..<1000 { if await transport.isWaiting { return }; await Task.yield() }
        #expect(Bool(false),"Synthetic PUT did not enter its controlled suspension")
    }
    @Test func getPermissionAloneNeverGrantsWrite() async throws {
        let (shell,host,_,_,transport) = try await setup([],capability:false)
        shell.draft="editor"
        #expect(host.draftStatus == .empty && host.captureDraftWriteContext() == nil)
        #expect(host.saveServerDraft(context:nil) == nil && host.draftWriteStatus == .unavailable)
        #expect(await transport.methods == [.get,.get])
    }
    @Test(arguments:["原草稿", ""]) func exactConfirmationMarksOnlyOriginalEditorAndLanguageDoesNotChangeIt(text:String) async throws {
        let (shell,host,_,_,transport) = try await setup([SaveReply(bytes:try saved(text))])
        shell.draft=text
        let context = try #require(host.captureDraftWriteContext())
        let revision=shell.draftRevision; shell.selectLanguage(.chinese)
        #expect(shell.draftRevision == revision)
        let task=try #require(host.saveServerDraft(context:context)); await task.value
        #expect(host.draftWriteStatus == .savedCurrentEdit && shell.draft == text)
        #expect(await transport.putBytes == [Data(text.utf8)])
        shell.draft="new edit"; shell.draft=text
        #expect(host.draftWriteStatus == .savedEarlierEdit)
    }
    @Test func editWhileSavingIsPreservedEvenWhenBytesReturnToOriginal() async throws {
        let (shell,host,_,_,transport)=try await setup([SaveReply(bytes:try saved("A"))],hold:true)
        shell.draft="A"; let task=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()))
        await waitForPUT(transport)
        await host.loadConversations(context:host.captureReadContext())
        #expect(await transport.methods == [.get,.get,.put])
        #expect(host.selectedConversation?.conversation_id == "a" && host.draftWriteStatus == .saving)
        shell.draft="B";shell.draft="A"
        await transport.release();await task.value
        #expect(shell.draft == "A" && host.draftWriteStatus == .savedEarlierEdit)
    }
    @Test(arguments:[true,false]) func unknownReadbackDoesNotGrantReplacementSave(null:Bool) async throws {
        let readback = try null ? json(["draft":NSNull()]) : saved("A")
        let (shell,host,recovery,lease,transport)=try await setup([SaveReply(bytes:nil),SaveReply(bytes:readback)])
        shell.draft="A";let task=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()));await task.value
        let pendingRecord=try recovery.draftSave(conversationID:"a",lease:lease)
        let original=try #require(pendingRecord)
        #expect(original.confirmedRevision == nil && host.captureDraftWriteContext() == nil)
        let query = try #require(host.captureDraftQueryContext());await host.queryOriginalDraft(context:query)
        await host.queryOriginalDraft(context:query) // same queued query cannot run again
        #expect(host.draftQueryStatus == (null ? .missing:.observed))
        #expect(try recovery.draftSave(conversationID:"a",lease:lease) == original)
        shell.draft="replacement"; #expect(host.captureDraftWriteContext() == nil)
        #expect(await transport.methods == [.get,.get,.put,.get])
    }
    @Test func staleEditorOrIdentityContextDoesNotStartPUT() async throws {
        let (shell,host,_,_,transport)=try await setup([])
        shell.draft="A";let old=try #require(host.captureDraftWriteContext())
        shell.draft="B";#expect(host.saveServerDraft(context:old) == nil)
        let current=try #require(host.captureDraftWriteContext())
        shell.invalidateIdentity();#expect(host.saveServerDraft(context:current) == nil)
        #expect(await transport.methods == [.get,.get])
    }
    @Test func localCancelRetainsCASAndCannotResave() async throws {
        let (shell,host,recovery,lease,transport)=try await setup([SaveReply(bytes:try saved("A"))],hold:true)
        shell.draft="A";let task=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()))
        await waitForPUT(transport)
        host.cancelServerDraftSave(context: host.captureDraftCancelContext());await transport.release();await task.value
        #expect(try recovery.draftSave(conversationID:"a",lease:lease)?.confirmedRevision == nil)
        #expect(host.captureDraftWriteContext() == nil && shell.draft == "A")
    }
    @Test func conflictKeepsOriginalCASAndNeverRetries() async throws {
        let error=try json(["error":["code":"VERSION_CONFLICT","category":"conflict","message_en":"conflict","message_zh":"冲突","outcome":"failed","recovery":"reconcile_original"]])
        let (shell,host,recovery,lease,transport)=try await setup([SaveReply(bytes:error,status:409)])
        shell.draft="A";let task=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()));await task.value
        #expect(host.draftWriteStatus == .conflict && host.captureDraftWriteContext() == nil)
        #expect(try recovery.draftSave(conversationID:"a",lease:lease)?.originalUTF8 == Data("A".utf8))
        #expect(await transport.methods == [.get,.get,.put])
    }
    @Test func identityInvalidationHidesLateSaveWithoutOverwritingNewEditor() async throws {
        let (shell,host,_,_,transport)=try await setup([SaveReply(bytes:try saved("A"))],hold:true)
        shell.draft="A";let task=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()))
        await waitForPUT(transport)
        shell.invalidateIdentity();shell.draft="new identity editor"
        await transport.release();await task.value
        #expect(host.draftWriteStatus == .unavailable && host.captureDraftQueryContext() == nil)
        #expect(shell.draft == "new identity editor")
    }
    @Test func oldUnknownQueryCannotReadReplacementAccount() async throws {
        let (shell,host,_,_,oldTransport)=try await setup([SaveReply(bytes:nil)])
        shell.draft="A";let task=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()));await task.value
        let oldQuery=try #require(host.captureDraftQueryContext())
        let account=AccountHost(shell:shell,session:SessionLifecycle(persistence:SaveSession(),restorePolicy:.userInitiatedOnly)) { _,_ in UnconfiguredSDKAdapter() }
        account.clearLocalSession()
        let recovery=MessageRecovery(storage:SaveStore())
        let scope=try StorageScope(environment:UUID().uuidString,account:"replacement")
        let lease=try recovery.activate(scope)
        let replacement=SaveTransport([SaveReply(bytes:try json(["conversations":[["conversation_id":"a","generation":"g1","epoch":0,"list_sequence":1]],"next_cursor":NSNull()]))])
        let client=MessageHTTPClient(recovery:recovery,scope:scope,endpoint:try .init(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:4096,maximumResponseBytes:16384),credentials:SaveCredentials(),interceptedTestTransport:replacement)
        #expect(host.bind(.init(client:client,recovery:recovery,scope:scope,lease:lease,generation:shell.generation,limit:2,limits:try .init(maximumPageItems:2,maximumCursorBytes:128,maximumDecodedBytes:4096,maximumPages:5),synthetic:true,isCurrent:{true})))
        await host.loadConversations(context:host.captureReadContext())
        #expect(host.selectConversation(host.conversations[0],token:host.conversationSelectionToken))
        await host.queryOriginalDraft(context:oldQuery)
        #expect(host.captureDraftQueryContext() == nil && host.draftQueryStatus == .idle)
        #expect(await replacement.methods == [.get])
        #expect(await oldTransport.methods == [.get,.get,.put])
    }
    @Test func pendingRecordForOldServerGenerationIsNotExposedOrWritable() async throws {
        let (_,host,recovery,lease,transport)=try await setup([])
        _ = try recovery.beginDraftSave(conversationID:"a",generation:"old-generation",expectedRevision:0,originalUTF8:Data("private old".utf8),lease:lease)
        #expect(host.draftWriteStatus == .blocked && host.captureDraftQueryContext() == nil && host.captureDraftWriteContext() == nil)
        #expect(await transport.methods == [.get,.get])
    }

    @Test(arguments:[false,true]) func staleCancelCannotCancelNewSaveButCurrentCancelStillWorks(cancelCurrent:Bool) async throws {
        let (shell,host,recovery,lease,transport)=try await setup([SaveReply(bytes:try saved("A")),SaveReply(bytes:try saved("B",revision:2))],hold:true)
        shell.draft="A"
        let first=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()))
        await waitForPUT(transport)
        let cancelOrigin = try #require(host.captureDraftCancelContext())
        let oldCancel:@MainActor () -> Void = { host.cancelServerDraftSave(context: cancelOrigin) }
        await transport.release();await first.value
        #expect(host.draftWriteStatus == .savedCurrentEdit)
        shell.draft="B"
        let second=try #require(host.saveServerDraft(context:host.captureDraftWriteContext()))
        await waitForPUT(transport)
        oldCancel()
        #expect(host.draftWriteStatus == .saving && !second.isCancelled)
        if cancelCurrent {
            host.cancelServerDraftSave(context: host.captureDraftCancelContext())
            #expect(second.isCancelled)
        }
        await transport.release();await second.value
        let record=try recovery.draftSave(conversationID:"a",lease:lease)
        if cancelCurrent {
            #expect(record?.confirmedRevision == nil && host.captureDraftWriteContext() == nil)
        } else {
            #expect(record?.confirmedRevision == 2 && host.draftWriteStatus == .savedCurrentEdit)
        }
        #expect(shell.draft == "B")
        #expect(await transport.methods == [.get,.get,.put,.put])
    }

}
