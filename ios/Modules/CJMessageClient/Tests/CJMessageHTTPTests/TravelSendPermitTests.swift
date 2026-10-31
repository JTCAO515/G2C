import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJAPI
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class TravelPermitStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot,scope: StorageScope) throws { self.snapshot = snapshot }
}
@MainActor private final class TravelPermitCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope,lease: Lease) async throws -> String? { "synthetic-only" }
}
private actor TravelPermitWire: ClientTransport {
    let id = "0123456789abcdef0123456789abcdef"
    var posts: [Data] = []
    var contextReads = 0
    var contextVersion = 2
    var sequence = 0
    var accepted: [String:Any]?
    var loseACK = false
    var persistOnPost = true
    var corruptReference = false
    func configure(version: Int = 2,loseACK: Bool = false,persist: Bool = true,corrupt: Bool = false) {
        contextVersion = version;self.loseACK = loseACK;persistOnPost = persist;corruptReference = corrupt
    }
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        let trace = UUID().uuidString
        let value: [String:Any]
        if operationID == Operations.getTravelContext.id {
            contextReads += 1
            value = ["request_id":trace,"version":"TRAVEL-context.1","travel_context":["id":id,"version":contextVersion,"active":true,"created_at":"2026-10-30T11:12:13.123456Z"]]
        } else if operationID == Operations.receiveMessageV2.id {
            #expect(request.method == .post && request.path == "/v2/messages")
            let raw = try await Data(collecting:body!,upTo:65536);posts.append(raw)
            let original = try JSONSerialization.jsonObject(with:raw) as! [String:Any]
            let selection = original["travel_context"] as? [String:Any]
            let next = sequence + 1
            let receipt: [String:Any] = ["message_id":original["message_id"]!,"conversation_id":"chat","generation":"g1","run_id":"run-original","sequence":next,"input_sha256":SHA256.hash(data:raw).map { String(format:"%02x",$0) }.joined()]
            var reference = receipt
            reference["version"] = "MESSAGE-travel-reference.1";reference["message_version"] = "MESSAGE-send.2"
            reference["context_kind"] = selection == nil ? "none" : "travel"
            reference["context_id"] = selection?["id"] ?? NSNull();reference["context_version"] = selection?["expected_version"] ?? NSNull()
            reference["selection_epoch"] = corruptReference ? next + 1 : 1
            value = ["request_id":trace,"version":"MESSAGE-accept.2","receipt":receipt,"reference":reference]
            if persistOnPost { accepted = value;sequence = next }
            if loseACK { loseACK = false;throw URLError(.networkConnectionLost) }
        } else {
            #expect(operationID == Operations.getMessageSendStatusV2.id && request.method == .get)
            let originalQuery = request.path?.contains("message_id=") == true
            value = ["request_id":trace,"version":"MESSAGE-send-status.2","head":["conversation_id":"chat","generation":"g1","last_sequence":sequence],"receipt":originalQuery ? accepted?["receipt"] ?? NSNull() : NSNull(),"reference":originalQuery ? accepted?["reference"] ?? NSNull() : NSNull()]
        }
        var response = HTTPResponse(status:.ok);response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response,HTTPBody(try JSONSerialization.data(withJSONObject:value)))
    }
}

@MainActor struct TravelSendPermitTests {
    private func setup(_ wire: TravelPermitWire,storage: TravelPermitStorage = TravelPermitStorage(),scope: StorageScope? = nil) throws -> (MessageRecovery,Lease,MessageHTTPClient,StorageScope) {
        let scope = try scope ?? StorageScope(environment:UUID().uuidString,account:"synthetic")
        let recovery = MessageRecovery(storage:storage),lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let client = MessageHTTPClient(recovery:recovery,scope:scope,endpoint:endpoint,credentials:TravelPermitCredentials(),interceptedTestTransport:wire)
        return (recovery,lease,client,scope)
    }
    @Test func exactOriginalRetainsReadTravelVersionAndImmutableReceipt() async throws {
        let wire = TravelPermitWire();let (recovery,lease,client,_) = try setup(wire)
        let selection = try await client.readTravelContext(id:wire.id,lease:lease)
        _ = try await client.readTravelSendHead(conversationID:"chat",lease:lease)
        let record = try client.stageTravelSend(messageID:"m1",conversationID:"chat",text:"原文",creationIntent:.none,travelContext:selection,needsReference:nil,lease:lease)
        #expect(try !client.canStartTravelSend(conversationID:"chat",lease:lease))
        await wire.configure(version:9)
        guard case .accepted = try await client.submitPreparedTravelSend(messageID:"m1",lease:lease) else { Issue.record("receipt was not accepted");return }
        #expect(await wire.posts == [record.originalUTF8])
        let original = try OriginalTravelMessageSend(raw:record.originalUTF8,maximumBytes:65536)
        #expect(original.travelContext?.expectedVersion == 2)
        let accepted = try #require(recovery.action(messageID:"m1",lease:lease)?.receipt)
        let value = try JSONDecoder().decode(Components.Schemas.MessageReceiveV2Response.self,from:accepted)
        guard case .travel(let reference) = value.reference else { Issue.record("lost original travel");return }
        #expect(reference.context_version == 2 && reference.selection_epoch == 1)
        #expect(try client.canStartTravelSend(conversationID:"chat",lease:lease))
    }
    @Test func lostACKReopenQueriesOriginalAndNeverRefreshesSelectionOrResends() async throws {
        let storage = TravelPermitStorage(),wire = TravelPermitWire()
        let (recovery,lease,client,scope) = try setup(wire,storage:storage)
        let selection = try await client.readTravelContext(id:wire.id,lease:lease)
        _ = try await client.readTravelSendHead(conversationID:"chat",lease:lease)
        let record = try client.stageTravelSend(messageID:"m1",conversationID:"chat",text:"original",creationIntent:.none,travelContext:selection,needsReference:nil,lease:lease)
        await wire.configure(loseACK:true)
        await #expect(throws:(any Error).self) { try await client.submitPreparedTravelSend(messageID:"m1",lease:lease) }
        recovery.invalidate()
        let (restored,next,reopened,_) = try setup(wire,storage:storage,scope:scope)
        await wire.configure(version:15)
        await #expect(throws:RecoveryError.queryOnly) { try await reopened.submitPreparedTravelSend(messageID:"m1",lease:next,confirmRestored:true) }
        #expect(try await reopened.reconcileTravelSend(messageID:"m1",lease:next) == .accepted)
        #expect(await wire.posts == [record.originalUTF8]);#expect(await wire.contextReads == 1)
        #expect(try restored.action(messageID:"m1",lease:next)?.phase == .accepted)
    }
    @Test func originalAbsenceAfterReopenRequiresConfirmationAndExactBytes() async throws {
        let storage = TravelPermitStorage(),wire = TravelPermitWire()
        let (recovery,lease,client,scope) = try setup(wire,storage:storage)
        _ = try await client.readTravelSendHead(conversationID:"chat",lease:lease)
        let record = try client.stageTravelSend(messageID:"m1",conversationID:"chat",text:"explicit none",creationIntent:.none,travelContext:nil,needsReference:nil,lease:lease)
        await wire.configure(loseACK:true,persist:false)
        await #expect(throws:(any Error).self) { try await client.submitPreparedTravelSend(messageID:"m1",lease:lease) }
        recovery.invalidate()
        let (_,next,reopened,_) = try setup(wire,storage:storage,scope:scope)
        #expect(try await reopened.reconcileTravelSend(messageID:"m1",lease:next) == .resubmitOriginal)
        await #expect(throws:RecoveryError.queryOnly) { try await reopened.submitPreparedTravelSend(messageID:"m1",lease:next) }
        #expect(await wire.posts.count == 1)
        await wire.configure()
        guard case .accepted = try await reopened.submitPreparedTravelSend(messageID:"m1",lease:next,confirmRestored:true) else { Issue.record("receipt was not accepted");return }
        #expect(await wire.posts == [record.originalUTF8,record.originalUTF8])
    }
    @Test func invalidAssociationRemainsUnknownAndCannotUnlockNewSend() async throws {
        let wire = TravelPermitWire();let (recovery,lease,client,_) = try setup(wire)
        _ = try await client.readTravelSendHead(conversationID:"chat",lease:lease)
        try client.stageTravelSend(messageID:"m1",conversationID:"chat",text:"original",creationIntent:.none,travelContext:nil,needsReference:nil,lease:lease)
        await wire.configure(corrupt:true)
        await #expect(throws:(any Error).self) { try await client.submitPreparedTravelSend(messageID:"m1",lease:lease) }
        #expect(try recovery.action(messageID:"m1",lease:lease)?.phase == .queryRequired)
        await #expect(throws:(any Error).self) { try await client.reconcileTravelSend(messageID:"m1",lease:lease) }
        _ = try await client.readTravelSendHead(conversationID:"chat",lease:lease)
        #expect(try !client.canStartTravelSend(conversationID:"chat",lease:lease))
        #expect(await wire.posts.count == 1)
    }
    @Test func anotherClientReadAndExpiredLeaseCannotStage() async throws {
        let wire = TravelPermitWire();let (_,lease,client,_) = try setup(wire)
        let (otherRecovery,otherLease,other,_) = try setup(wire)
        let selection = try await client.readTravelContext(id:wire.id,lease:lease)
        _ = try await other.readTravelSendHead(conversationID:"chat",lease:otherLease)
        #expect(throws:RecoveryError.inactive) { try other.stageTravelSend(messageID:"m1",conversationID:"chat",text:"original",creationIntent:.none,travelContext:selection,needsReference:nil,lease:otherLease) }
        otherRecovery.invalidate()
        #expect(throws:RecoveryError.inactive) { try other.stageTravelSend(messageID:"m1",conversationID:"chat",text:"original",creationIntent:.none,travelContext:nil,needsReference:nil,lease:otherLease) }
        #expect(await wire.posts.isEmpty)
    }
    @Test func needsSelectionOnlyAcceptsFrozenIdentifierAndVersion() throws {
        _ = try MessageNeedsSelection(id:"Needs_1.a:b-c",expectedVersion:1)
        for id in ["", "_prefix", "a/b", "a?owner=x", "旅行",String(repeating:"a",count:97)] {
            #expect(throws:RecoveryError.invalidInput) { try MessageNeedsSelection(id:id,expectedVersion:1) }
        }
        #expect(throws:RecoveryError.invalidInput) { try MessageNeedsSelection(id:"valid",expectedVersion:0) }
    }
}
