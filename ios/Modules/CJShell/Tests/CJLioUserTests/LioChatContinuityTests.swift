import CJMessageClient
@testable import CJMessageHTTP
import CryptoKit
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJLioUser

@MainActor struct LioChatContinuityTests {
    @Test func reauthenticatedClientReturnsToTheSameChatAndDraftWithoutSendingAgain() async throws {
        let fixture = try ChatContinuityFixture()
        let old = try fixture.library()
        let selected = old.newChat()
        let position = try #require(old.continuity)
        position.selectedID = selected.id
        let model = LioConversation(service: selected.service)
        model.send("A synthetic question", language: .english)
        await model.receive(try #require(model.pending))
        position.draft = "My unsent follow-up"
        let renewedPosition = LioChatContinuity()
        renewedPosition.inherit(position)
        let renewed = try fixture.library(continuity: renewedPosition)
        let restored = try #require(try await renewed.restore?())
        #expect(restored.id == selected.id && renewedPosition.draft == "My unsent follow-up")
        let restoredModel = LioConversation(service: restored.service)
        await restoredModel.refreshTimeline()
        #expect(restoredModel.turns.last?.answer == "A synthetic answer")
        #expect(await fixture.transport.posts == 1)
        // A new presentation starts empty unless the verified root transfers it.
        let other = try fixture.library()
        #expect(other.continuity?.selectedID == nil && other.continuity?.draft == "")
    }

    @Test func lostFirstReceiptIsReadByItsOriginalIDBeforeReturningToTheChat() async throws {
        let fixture = try ChatContinuityFixture()
        let old = try fixture.library()
        let selected = old.newChat()
        let position = try #require(old.continuity)
        position.selectedID = selected.id
        let original = try LioTimelineWire.Send(messageID: UUID().uuidString, text: "A synthetic question",
                                               locale: .english, destination: .newChat)
        position.firstQuestions[selected.id] = original.messageID
        await fixture.transport.loseNextReceipt()
        do {
            _ = try await fixture.client().submit(original)
            Issue.record("The synthetic first receipt must be lost")
        } catch let error as URLError { #expect(error.code == .networkConnectionLost) }
        let renewedPosition = LioChatContinuity()
        renewedPosition.inherit(position)
        let renewed = try fixture.library(continuity: renewedPosition)
        await fixture.transport.holdLookup(true)
        await #expect(throws: MessageHTTPFailure.exchangeUnknown) { _ = try await renewed.restore?() }
        #expect(renewedPosition.firstQuestions[selected.id] == original.messageID)
        await fixture.transport.holdLookup(false)
        let restored = try #require(try await renewed.restore?())
        #expect(restored.id == selected.id && renewedPosition.firstQuestions.isEmpty)
        let model = LioConversation(service: restored.service)
        await model.refreshTimeline()
        #expect(model.turns.last?.question.messageID == original.messageID)
        #expect(await fixture.transport.posts == 1)
        #expect(await fixture.transport.lookups == 2)
    }
}

@MainActor private struct ChatContinuityFixture {
    let transport = ChatContinuityTransport()
    let recovery = MessageRecovery(storage: ChatContinuityStorage())
    let scope: StorageScope
    let lease: Lease

    init() throws {
        scope = try StorageScope(environment: "synthetic", account: "continuity")
        lease = try recovery.activate(scope)
    }

    func client() throws -> LioTimelineHTTP {
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!,
            maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        let transport = try NoRedirectTransport(interceptedTransport: transport, messageEndpoint: endpoint,
                                               validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: ChatContinuityCredentials(),
                               transport: transport, firstChatRecovery: recovery)
    }

    func library(continuity: LioChatContinuity? = nil) throws -> LioChatLibrary {
        let client = try client()
        return .signed(client: client, defaultService: .signedTimeline(client), language: { .english },
            continuity: continuity) { id in
            LioTripHistoryClient(timeline: client, recovery: recovery, scope: scope, lease: lease, conversationID: id)
        }
    }
}

@MainActor private final class ChatContinuityStorage: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}

@MainActor private final class ChatContinuityCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "SYNTHETIC" }
}

private actor ChatContinuityTransport: ClientTransport {
    private let id = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private var original: LioTimelineWire.Send?
    private var originalDigest: String?
    private var loseReceipt = false
    private var lookupHeld = false
    private(set) var posts = 0
    private(set) var lookups = 0
    func loseNextReceipt() { loseReceipt = true }
    func holdLookup(_ held: Bool) { lookupHeld = held }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let route = try #require(URLComponents(string: request.path ?? ""))
        switch (request.method, route.path) {
        case (.post, "/v2/lio/messages"):
            posts += 1
            let body = try #require(body)
            let bytes = try await Data(collecting: body, upTo: 16_384)
            originalDigest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
            original = try LioTimelineWire.Send(messageID: #require(fields["message_id"] as? String),
                text: #require(fields["text"] as? String), locale: .english, destination: .newChat)
            if loseReceipt { throw URLError(.networkConnectionLost) }
            return try reply(["version": "LIO-message-receipt.2", "message_id": #require(original?.messageID), "conversation_id": id])
        case (.get, "/v2/lio/messages"):
            lookups += 1
            let original = try #require(original)
            #expect(route.queryItems?.contains(.init(name: "message_id", value: original.messageID)) == true)
            let digest = try #require(originalDigest)
            #expect(route.queryItems?.contains(.init(name: "input_sha256", value: digest)) == true)
            if lookupHeld { return try reply(["version": "LIO-message-lookup.2", "receipt": NSNull()]) }
            return try reply(["version": "LIO-message-lookup.2", "receipt": ["version": "LIO-message-receipt.2", "message_id": original.messageID, "conversation_id": id]])
        case (.get, "/v2/lio/timeline"):
            let original = try #require(original)
            return try reply(["version": "LIO-timeline.2", "conversation_id": id, "next_before": NSNull(),
                "messages": [["message_id": original.messageID, "text": "A synthetic question", "answer": "A synthetic answer", "status": "completed", "sources": []]]])
        default: throw MessageHTTPFailure.invalidConfiguration
        }
    }

    private func reply(_ fields: [String: Any], status: HTTPResponse.Status = .ok) throws -> (HTTPResponse, HTTPBody?) {
        var response = HTTPResponse(status: status)
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(try JSONSerialization.data(withJSONObject: fields)))
    }

}
