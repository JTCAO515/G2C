import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJAPI
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class EditStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
@MainActor private final class EditCredentials: MessageCredentialsProvider {
    var callback: (() -> Void)?
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { callback?(); return "synthetic-only" }
}
private actor EditMessageWire: ClientTransport {
    var posts: [Data] = []
    var sequence: Int64 = 0
    var accepted: [String: Any]?
    var lostACK = false
    var persist = true
    var rejected = false
    var unknown = false
    var malformedError = false
    var changedNamespace = false
    func configure(lostACK: Bool = false, persist: Bool = true, rejected: Bool = false,
                   unknown: Bool = false, malformedError: Bool = false, changedNamespace: Bool = false) {
        self.lostACK=lostACK; self.persist=persist; self.rejected=rejected
        self.unknown=unknown; self.malformedError=malformedError; self.changedNamespace=changedNamespace
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let trace=UUID().uuidString
        var value: [String: Any], status=200
        if operationID == "receiveTripEditV4" {
            #expect(request.path == "/v4/messages" && request.method == .post)
            let raw=try await Data(collecting:#require(body),upTo:65536);posts.append(raw)
            let original=try OriginalTripEdit(raw:raw,maximumBytes:65536)
            if rejected || unknown || malformedError {
                status=409
                var error: [String: Any] = ["code":"MESSAGE_CONTEXT_CONFLICT","category":"conflict","message_en":"Request unavailable","message_zh":"请求不可用",
                    "outcome":unknown ? "unknown" : "failed","recovery":unknown ? "reconcile_original" : "do_not_retry"]
                if malformedError { error.removeValue(forKey:"message_zh") }
                value=["request_id":trace,"error":error]
            } else {
                sequence += persist ? 1 : 0
                let hash=SHA256.hash(data:raw).map { String(format:"%02x",$0) }.joined()
                let receipt: [String: Any] = ["message_id":original.messageID,"conversation_id":original.head.conversation_id,
                    "generation":original.head.generation,"sequence":original.head.last_sequence+1,"run_id":"run-original","input_sha256":hash]
                var reference=receipt
                reference.merge(["version":"MESSAGE-edit-reference.1","message_version":"MESSAGE-send.4",
                    "modification_intent":original.intent.rawValue,"trip_context":original.trip.object,
                    "resolved_item_ids":original.trip.itemIDs,"content_version":"structured.2",
                    "namespace":["kind":"travel","id":changedNamespace ? String(repeating:"c",count:32) : original.namespace.id,"version":original.namespace.expectedVersion],
                    "needs_reference":original.needs.map { ["id":$0.id,"expected_version":$0.expectedVersion] as Any } ?? NSNull(),"selection_epoch":1],uniquingKeysWith:{_,b in b})
                value=["request_id":trace,"version":"MESSAGE-accept.4","receipt":receipt,"reference":reference]
                if persist { accepted=value }
                if lostACK { throw URLError(.networkConnectionLost) }
            }
        } else {
            #expect(operationID == "readTripEditStatusV4" && request.method == .get && request.path?.hasPrefix("/v4/message-send-status?") == true)
            let query=URLComponents(string:request.path!)!.queryItems!
            let id=query.first { $0.name == "message_id" }?.value
            let selected=id == nil ? nil : accepted
            value=["request_id":trace,"version":"MESSAGE-send-status.4","receipt":selected?["receipt"] ?? NSNull(),
                "reference":selected?["reference"] ?? NSNull(),"head":["conversation_id":"chat","generation":"g","last_sequence":sequence]]
        }
        var headers=HTTPFields();headers[.init("x-request-id")!]=trace;headers[.contentType]="application/json";headers[.cacheControl]="no-store"
        return (HTTPResponse(status:.init(code:status),headerFields:headers),HTTPBody(try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys])))
    }
}

@MainActor struct TripEditSendTests {
    private func setup(_ wire: EditMessageWire, storage: EditStorage = EditStorage(), scope: StorageScope? = nil,
                       credentials: EditCredentials = EditCredentials()) throws -> (MessageRecovery, Lease, MessageHTTPClient, StorageScope) {
        let scope=try scope ?? StorageScope(environment:UUID().uuidString,account:"synthetic")
        let state=MessageRecovery(storage:storage),lease=try state.activate(scope)
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        return (state,lease,MessageHTTPClient(recovery:state,scope:scope,endpoint:endpoint,credentials:credentials,interceptedTestTransport:wire),scope)
    }
    private func stage(_ client: MessageHTTPClient, lease: Lease, id: String = "m1", version: Int64 = 8) throws -> ActionRecord {
        try client.stageTripEdit(messageID:id,conversationID:"chat",text:"SYNTHETIC 明确本次候选",intent:.proposeScopedEdit,
            trip:MessageEditTripSelection(id:"formal-trip",expectedVersion:version,contentSHA256:String(repeating:"a",count:64),day:nil,itemIDs:["item-a"]),
            namespace:MessageEditNamespace(id:String(repeating:"b",count:32),expectedVersion:1),
            needs:MessageNeedsSelection(id:"needs",expectedVersion:2),content:MessageTripContent(version:"structured.2",sha256:String(repeating:"a",count:64)),lease:lease)
    }
    @Test func explicitIntentAndIndependentNamespaceKeepOriginalBytes() async throws {
        let wire=EditMessageWire();let (state,lease,client,_)=try setup(wire)
        #expect(try !client.canStartTripEdit(conversationID:"chat",lease:lease))
        #expect(throws:RecoveryError.queryOnly) { try stage(client,lease:lease) }
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease)
        let original=try stage(client,lease:lease)
        guard case .accepted = try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) else { Issue.record("not accepted");return }
        #expect(await wire.posts == [original.originalUTF8])
        let ref=try client.acceptedTripEditReference(messageID:"m1",lease:lease)
        #expect(ref.intent == .proposeScopedEdit && ref.trip.itemIDs == ["item-a"] && ref.needs?.expectedVersion == 2)
        #expect(ref.namespace.id == String(repeating:"b",count:32) && ref.trip.id == "formal-trip")
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .accepted)
    }
    @Test func lostAcknowledgementReopensOnlyOriginalQuery() async throws {
        let wire=EditMessageWire(),storage=EditStorage();let (state,lease,client,scope)=try setup(wire,storage:storage)
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease);let original=try stage(client,lease:lease)
        await wire.configure(lostACK:true)
        await #expect(throws:(any Error).self) { try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) }
        state.invalidate();let (_,next,reopened,_)=try setup(wire,storage:storage,scope:scope)
        await #expect(throws:RecoveryError.queryOnly) { try await reopened.submitPreparedTripEdit(messageID:"m1",lease:next,confirmRestored:true) }
        #expect(try await reopened.reconcileTripEdit(messageID:"m1",lease:next) == .accepted)
        #expect(try reopened.acceptedTripEditReference(messageID:"m1",lease:next).trip.expectedVersion == 8)
        #expect(await wire.posts == [original.originalUTF8])
    }
    @Test func nullLookupCannotAuthorizeNewOriginalOrAutomaticResend() async throws {
        let wire=EditMessageWire(),storage=EditStorage();let (state,lease,client,scope)=try setup(wire,storage:storage)
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease);let original=try stage(client,lease:lease)
        await wire.configure(lostACK:true,persist:false)
        await #expect(throws:(any Error).self) { try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) }
        state.invalidate();let (_,next,reopened,_)=try setup(wire,storage:storage,scope:scope)
        #expect(try await reopened.reconcileTripEdit(messageID:"m1",lease:next) == .resubmitOriginal)
        _=try await reopened.readTripEditHead(conversationID:"chat",lease:next)
        #expect(try !reopened.canStartTripEdit(conversationID:"chat",lease:next))
        #expect(throws:RecoveryError.queryOnly) { try stage(reopened,lease:next,id:"new-id",version:9) }
        await #expect(throws:RecoveryError.queryOnly) { try await reopened.submitPreparedTripEdit(messageID:"m1",lease:next) }
        #expect(await wire.posts == [original.originalUTF8])
    }
    @Test func verifiedPostFailurePreservesProofAndAllowsFreshExplicitRequest() async throws {
        let wire=EditMessageWire(),storage=EditStorage();let (state,lease,client,_)=try setup(wire,storage:storage)
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease);let original=try stage(client,lease:lease)
        await wire.configure(rejected:true)
        guard case .rejected(let status,_) = try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) else { Issue.record("expected rejection");return }
        #expect(status == 409)
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .notAccepted)
        let savedProof=try state.submissionRejection(messageID:"m1",lease:lease)
        let proof=try #require(savedProof)
        #expect(proof.httpStatus == 409 && !proof.responseUTF8.isEmpty)
        #expect(try !client.canStartTripEdit(conversationID:"chat",lease:lease))
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease)
        #expect(try client.canStartTripEdit(conversationID:"chat",lease:lease))
        _=try stage(client,lease:lease,id:"m2",version:9)
        await wire.configure()
        guard case .accepted = try await client.submitPreparedTripEdit(messageID:"m2",lease:lease) else { Issue.record("fresh request blocked");return }
        #expect(try state.action(messageID:"m1",lease:lease)?.originalUTF8 == original.originalUTF8)
        #expect(try state.submissionRejection(messageID:"m1",lease:lease) == proof)
        #expect(await wire.posts.count == 2)
    }
    @Test(arguments:[true,false]) func unknownOrMalformedErrorCannotBecomeDefiniteFailure(malformed: Bool) async throws {
        let wire=EditMessageWire();let (state,lease,client,_)=try setup(wire)
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease);_=try stage(client,lease:lease)
        await wire.configure(unknown:!malformed,malformedError:malformed)
        if malformed { await #expect(throws:(any Error).self) { try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) } }
        else { _=try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) }
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .queryRequired)
        #expect(try state.submissionRejection(messageID:"m1",lease:lease) == nil)
    }
    @Test func mismatchingAcceptedNamespaceRemainsUnknown() async throws {
        let wire=EditMessageWire();let (state,lease,client,_)=try setup(wire)
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease);_=try stage(client,lease:lease)
        await wire.configure(changedNamespace:true)
        await #expect(throws:(any Error).self) { try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) }
        #expect(try state.action(messageID:"m1",lease:lease)?.phase == .queryRequired)
        #expect(throws:RecoveryError.queryOnly) { try client.acceptedTripEditReference(messageID:"m1",lease:lease) }
    }
    @Test func credentialCallbackCannotDispatchAfterInvalidation() async throws {
        let wire=EditMessageWire(),credentials=EditCredentials();let (state,lease,client,_)=try setup(wire,credentials:credentials)
        _=try await client.readTripEditHead(conversationID:"chat",lease:lease);_=try stage(client,lease:lease)
        credentials.callback = { state.invalidate() }
        await #expect(throws:(any Error).self) { try await client.submitPreparedTripEdit(messageID:"m1",lease:lease) }
        #expect(await wire.posts.isEmpty)
    }
}
