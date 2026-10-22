import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class PutStore: SecureMessageStorage {
    var value:Snapshot?
    func load(scope:StorageScope) throws -> Snapshot? { value }
    func save(_ snapshot:Snapshot,scope:StorageScope) throws { value=snapshot }
}
@MainActor private final class PutCredentials: MessageCredentialsProvider {
    func bearer(for scope:StorageScope,lease:Lease) async throws -> String? { "synthetic" }
}
private actor PutTransport: ClientTransport {
    var bodies:[Data]; let status:Int; let trace:String
    let hook:(@Sendable () async -> Void)?
    var methods:[HTTPRequest.Method]=[]; var sent:[Data]=[]; var paths:[String?]=[]
    init(_ bodies:[Data],status:Int=200,trace:String,hook:(@Sendable () async -> Void)?=nil) {self.bodies=bodies;self.status=status;self.trace=trace;self.hook=hook}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        methods.append(request.method); paths.append(request.path)
        if let body { sent.append(try await Data(collecting:body,upTo:10000)) }
        await hook?()
        guard !bodies.isEmpty else { throw URLError(.networkConnectionLost) }
        var response=HTTPResponse(status:.init(code:status)); response.headerFields[HTTPField.Name("X-Request-ID")!]=trace;response.headerFields[.contentType]="application/json"
        return (response,HTTPBody(bodies.removeFirst()))
    }
}
@MainActor private final class PutKeys: MessageEncryptionKeyProvider {
    let material=MessageStorageKey(id:UUID(),key:SymmetricKey(size:.bits256))
    func existing(for scope:StorageScope,expectedID:UUID?) throws -> MessageStorageKey? {material}
}
@Suite @MainActor struct DraftPutTests {
    let trace="a0515ef1-5557-4378-a786-b9599ea07283"
    var bytes:Data { Data(" draft 原字节 \n".utf8) }
    var limits:MessageReadLimits { get throws {try MessageReadLimits(maximumPageItems:2,maximumCursorBytes:100,maximumDecodedBytes:10000,maximumPages:3)} }
    func encoded(_ draft:Any) throws ->Data {try JSONSerialization.data(withJSONObject:["request_id":trace,"draft":draft])}
    func saved(_ raw:Data,revision:Int=1)->[String:Any] { ["conversation_id":"chat","generation":"g1","revision":revision,"original_utf8_base64":raw.base64EncodedString()] }
    private func setup(_ t:PutTransport) throws -> (PutStore,MessageRecovery,StorageScope,Lease,MessageHTTPClient) {
        let store=PutStore();let r=MessageRecovery(storage:store);let s=try StorageScope(environment:UUID().uuidString,account:"a");let l=try r.activate(s)
        try r.saveDraft(bytes,conversationID:"chat",lease:l)
        let c=MessageHTTPClient(recovery:r,scope:s,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),interceptedTestTransport:t)
        return (store,r,s,l,c)
    }
    @Test func exactCASBytesAndSuccessNeverOverwriteNewEdit() async throws {
        let store=PutStore();let r=MessageRecovery(storage:store);let s=try StorageScope(environment:UUID().uuidString,account:"a");let l=try r.activate(s)
        try r.saveDraft(bytes,conversationID:"chat",lease:l)
        let raw=bytes
        let t=PutTransport([try encoded(saved(raw))],trace:trace,hook:{try? await r.saveDraft(Data("new editor".utf8),conversationID:"chat",lease:l)})
        let c=MessageHTTPClient(recovery:r,scope:s,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),interceptedTestTransport:t)
        let confirmed=try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:raw,limits:limits,lease:l)
        #expect(!confirmed.matchesCurrentEditor)
        #expect(try r.draft(conversationID:"chat",lease:l)==Data("new editor".utf8))
        #expect(await t.sent == [raw]); #expect(await t.methods == [.put])
        let paths=await t.paths
        #expect((paths.first ?? nil)?.contains("expected_revision=0") == true)
    }
    @Test func unknownSurvivesReopenAndNullDoesNotPermitReplacementPut() async throws {
        let t=PutTransport([],trace:trace);let (store,r,s,l,c)=try setup(t)
        await #expect(throws:(any Error).self) {try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:bytes,limits:limits,lease:l)}
        #expect(try r.draftSave(conversationID:"chat",lease:l)?.originalUTF8==bytes)
        let restored=MessageRecovery(storage:store);let next=try restored.activate(s)
        let read=PutTransport([try encoded(NSNull())],trace:trace)
        let client=MessageHTTPClient(recovery:restored,scope:s,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),interceptedTestTransport:read)
        #expect(try await client.reconcileDraft(conversationID:"chat",limits:limits,lease:next).value == nil)
        for rev:Int64 in [0,1] {
            await #expect(throws:(any Error).self) {try await client.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:rev,originalUTF8:Data("replacement".utf8),limits:limits,lease:next)}
        }
        #expect(await read.methods == [.get])
    }
    @Test func malformedCommittedResponseAndConflictRetainOriginalCAS() async throws {
        let error=try JSONSerialization.data(withJSONObject:["request_id":trace,"error":["code":"conflict","category":"conflict","message_en":"conflict","message_zh":"冲突","outcome":"failed","recovery":"do_not_retry"]])
        for (data,status) in [(try encoded(saved(bytes,revision:2)),200),(Data("{}".utf8),200),(error,409)] {
            let t=PutTransport([data],status:status,trace:trace);let (_,r,_,l,c)=try setup(t)
            await #expect(throws:(any Error).self) {try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:bytes,limits:limits,lease:l)}
            #expect(try r.draftSave(conversationID:"chat",lease:l)?.expectedRevision == 0)
            #expect(try r.draftSave(conversationID:"chat",lease:l)?.confirmedRevision == nil)
            #expect(await t.methods == [.put])
        }
    }
    @Test func confirmationCannotMarkLaterSameBytesEditSaved() async throws {
        let t=PutTransport([try encoded(saved(bytes))],trace:trace);let (_,r,_,l,c)=try setup(t)
        let confirmation=try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:bytes,limits:limits,lease:l)
        #expect(try c.validateDraftConfirmation(confirmation,lease:l))
        try r.saveDraft(Data("new edit".utf8),conversationID:"chat",lease:l)
        try r.saveDraft(bytes,conversationID:"chat",lease:l)
        #expect(try !c.validateDraftConfirmation(confirmation,lease:l))
    }
    @Test func cancellationAfterResponseKeepsPendingCAS() async throws {
        let t=PutTransport([try encoded(saved(bytes))],trace:trace,hook:{withUnsafeCurrentTask{$0?.cancel()}})
        let (_,r,_,l,c)=try setup(t);let raw=bytes;let cap=try limits
        let task=Task {try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:raw,limits:cap,lease:l)}
        if case .success = await task.result {Issue.record("cancelled response must remain unknown")}
        #expect(try r.draftSave(conversationID:"chat",lease:l)?.confirmedRevision == nil)
        #expect(try r.draftSave(conversationID:"chat",lease:l)?.originalUTF8 == raw)
        #expect(await t.methods == [.put])
    }
    @Test func encryptedReopenRetainsUnknownDraftWrite() async throws {
        let dir=FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj009-put-"+UUID().uuidString)
        let keys=PutKeys();let storage=try EncryptedFileStorage(directory:dir,keys:keys)
        let r=MessageRecovery(storage:storage);let s=try StorageScope(environment:UUID().uuidString,account:"a");let l=try r.activate(s)
        let t=PutTransport([],trace:trace)
        let c=MessageHTTPClient(recovery:r,scope:s,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),interceptedTestTransport:t)
        await #expect(throws:(any Error).self) {try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:7,originalUTF8:bytes,limits:limits,lease:l)}
        let reopened=MessageRecovery(storage:try EncryptedFileStorage(directory:dir,keys:keys));let next=try reopened.activate(s)
        #expect(try reopened.draftSave(conversationID:"chat",lease:next)?.expectedRevision == 7)
        #expect(try reopened.localProjection(scope:s,lease:next).drafts.map(\.conversationID) == ["chat"])
        #expect(try reopened.draftSave(conversationID:"chat",lease:next)?.originalUTF8 == bytes)
        #expect(throws:RecoveryError.self) {try reopened.beginDraftSave(conversationID:"chat",generation:"new-g",expectedRevision:8,originalUTF8:Data(),lease:next)}
    }

    @Test func emptyDraftSuccessAndLateIdentityRemainDistinct() async throws {
        let t=PutTransport([try encoded(saved(Data()))],trace:trace);let (_,r,_,l,c)=try setup(t)
        try r.saveDraft(Data(),conversationID:"chat",lease:l)
        let confirmation=try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:Data(),limits:limits,lease:l)
        #expect(confirmation.snapshot.revision == 1)
        #expect(await t.sent == [Data()])
        let store=PutStore();let state=MessageRecovery(storage:store);let scope=try StorageScope(environment:UUID().uuidString,account:"a");let lease=try state.activate(scope)
        let late=PutTransport([try encoded(saved(bytes))],trace:trace,hook:{await state.invalidate()})
        let client=MessageHTTPClient(recovery:state,scope:scope,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),interceptedTestTransport:late)
        await #expect(throws:RecoveryError.self) {try await client.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:bytes,limits:limits,lease:lease)}
        let next=try state.activate(scope)
        #expect(try state.draftSave(conversationID:"chat",lease:next)?.confirmedRevision == nil)
    }
    @Test func matchingReadbackDoesNotSettleUnknownPut() async throws {
        let failed=PutTransport([],trace:trace);let (_,r,s,l,c)=try setup(failed)
        await #expect(throws:(any Error).self) {try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:bytes,limits:limits,lease:l)}
        let read=PutTransport([try encoded(saved(bytes))],trace:trace)
        let client=MessageHTTPClient(recovery:r,scope:s,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),interceptedTestTransport:read)
        let observed=try await client.reconcileDraft(conversationID:"chat",limits:limits,lease:l)
        #expect(observed.value?.revision == 1)
        #expect(try r.draftSave(conversationID:"chat",lease:l)?.confirmedRevision == nil)
        await #expect(throws:RecoveryError.self) {try await client.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:1,originalUTF8:bytes,limits:limits,lease:l)}
        #expect(await read.methods == [.get])
    }

    @Test func invalidLeaseAndLivePutNeverSend() async throws {
        let t=PutTransport([try encoded(saved(bytes))],trace:trace);let (_,r,s,l,_)=try setup(t)
        let live=try NoRedirectTransport(requestTimeout:1,resourceTimeout:1)
        let c=MessageHTTPClient(recovery:r,scope:s,endpoint:try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:10000,maximumResponseBytes:20000),credentials:PutCredentials(),liveReadTransport:live)
        await #expect(throws:MessageHTTPFailure.self) {try await c.saveDraft(conversationID:"chat",generation:"g1",expectedRevision:0,originalUTF8:bytes,limits:limits,lease:l)}
        #expect(try r.draftSave(conversationID:"chat",lease:l)==nil)
        await #expect(throws:MessageHTTPFailure.self) {try await live.send(HTTPRequest(method:.put,scheme:"https",authority:"synthetic.invalid",path:"/v1/message-drafts"),body:HTTPBody(bytes),baseURL:#require(URL(string:"https://synthetic.invalid")),operationID:"saveMessageDraft")}
        #expect(await t.methods.isEmpty)
    }
}
