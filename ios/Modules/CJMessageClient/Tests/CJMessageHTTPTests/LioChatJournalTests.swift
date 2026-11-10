import CJMessageClient
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

@MainActor
struct LioChatJournalTests {
    @Test func verifiedFirstReceiptReopensOnlyForTheSameAccount() async throws {
        let store = ChatJournalStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: store)
        let lease = try recovery.activate(scope)
        let exit = ChatJournalExit()
        let client = try makeClient(scope, lease, recovery: recovery, exit: exit)
        let first = try LioTimelineWire.Send(messageID: "first-chat", text: "Beijing trip",
                                             locale: .english, destination: .newChat)
        #expect(try client.savedChats().isEmpty)
        let outcome = try await client.submit(first)
        guard case .accepted(let id) = outcome else { Issue.record("First receipt not accepted"); return }
        #expect(id == ChatJournalExit.conversationID)
        #expect(try client.savedChats().map(\.title) == ["Beijing trip"])
        #expect(await exit.originals == [first.originalUTF8])

        recovery.invalidate()
        #expect(throws: RecoveryError.inactive) { try client.savedChats() }
        let restored = MessageRecovery(storage: store)
        let restoredLease = try restored.activate(scope)
        let reopened = try makeClient(scope, restoredLease, recovery: restored, exit: exit)
        #expect(try reopened.savedChats().map(\.id) == [id])
        let another = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let anotherLease = try restored.activate(another)
        let otherClient = try makeClient(another, anotherLease, recovery: restored, exit: exit)
        #expect(try otherClient.savedChats().isEmpty)
        #expect(throws: RecoveryError.inactive) { try reopened.savedChats() }
    }

    @Test func lostFirstReceiptLeavesTheExactOriginalAndBlocksAnotherCreation() async throws {
        let store = ChatJournalStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: store)
        let lease = try recovery.activate(scope)
        let exit = ChatJournalExit(losesReceipt: true)
        let client = try makeClient(scope, lease, recovery: recovery, exit: exit)
        let first = try LioTimelineWire.Send(messageID: "lost-chat", text: "Beijing trip",
                                             locale: .english, destination: .newChat)
        await #expect(throws: URLError.self) { _ = try await client.submit(first) }
        let action = try recovery.action(messageID: first.messageID, lease: lease)
        let recorded = try #require(action)
        #expect(recorded.phase == .queryRequired && recorded.originalUTF8 == first.originalUTF8)
        recovery.invalidate()

        let restored = MessageRecovery(storage: store)
        let restoredLease = try restored.activate(scope)
        let reopened = try makeClient(scope, restoredLease, recovery: restored, exit: exit)
        #expect(try await reopened.reconcileFirstChat() == nil)
        #expect(try restored.action(messageID: first.messageID, lease: restoredLease)?.phase == .notObserved)
        let another = try LioTimelineWire.Send(messageID: "another-chat", text: "Shanghai trip",
                                               locale: .english, destination: .newChat)
        await #expect(throws: RecoveryError.queryOnly) { _ = try await reopened.submit(another) }
        #expect(try reopened.savedChats().isEmpty)

        await exit.setLookupReply(messageID: another.messageID)
        await #expect(throws: MessageHTTPFailure.invalidResponse) { _ = try await reopened.reconcileFirstChat() }
        #expect(try reopened.savedChats().isEmpty)

        await exit.setLookupReply(messageID: first.messageID)
        #expect(try await reopened.reconcileFirstChat() == ChatJournalExit.conversationID)
        #expect(try reopened.savedChats().map(\.id) == [ChatJournalExit.conversationID])
        #expect(try reopened.savedChats().map(\.title) == ["Beijing trip"])
        #expect(await exit.originals == [first.originalUTF8])
        #expect(await exit.lookupDigests == Array(repeating: recorded.inputSHA256, count: 3))
    }

    private func makeClient(_ scope: StorageScope, _ lease: Lease, recovery: MessageRecovery,
                            exit: ChatJournalExit) throws -> LioTimelineHTTP {
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
                                                validateMessage: {}, lio: true)
        return LioTimelineHTTP(scope: scope, lease: lease, credentials: ChatJournalCredentials(),
                               transport: transport, firstChatRecovery: recovery)
    }
}

@MainActor
private final class ChatJournalCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "fixture" }
}

@MainActor
private final class ChatJournalStore: SecureMessageStorage {
    private var snapshots: [String: Snapshot] = [:]

    func load(scope: StorageScope) throws -> Snapshot? { snapshots[key(scope)] }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { snapshots[key(scope)] = snapshot }
    private func key(_ scope: StorageScope) -> String { scope.environment + "\0" + scope.account }
}

private actor ChatJournalExit: ClientTransport {
    static let conversationID = "lio-dialogue-0123456789abcdef0123456789abcdef"
    let losesReceipt: Bool
    private(set) var originals: [Data] = []
    private(set) var lookupDigests: [String] = []
    private var lookupReplyID: String?

    init(losesReceipt: Bool = false) { self.losesReceipt = losesReceipt }

    func setLookupReply(messageID: String) { lookupReplyID = messageID }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        if request.method == .get {
            let path = try #require(request.path)
            let route = try #require(URLComponents(string: path))
            #expect(route.path == "/v2/lio/messages" && body == nil)
            #expect(route.queryItems?.first(where: { $0.name == "message_id" })?.value == "lost-chat")
            let digest = try #require(route.queryItems?.first(where: { $0.name == "input_sha256" })?.value)
            lookupDigests.append(digest)
            let reply = lookupReplyID.map(receipt) ?? "null"
            return (response, HTTPBody("{\"version\":\"LIO-message-lookup.2\",\"receipt\":\(reply)}"))
        }
        #expect(request.method == .post && request.path == "/v2/lio/messages")
        let body = try #require(body)
        let bytes = try await Data(collecting: body, upTo: 16_384)
        originals.append(bytes)
        if losesReceipt { throw URLError(.networkConnectionLost) }
        let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let id = try #require(fields["message_id"] as? String)
        return (response, HTTPBody(receipt(id)))
    }

    private func receipt(_ id: String) -> String {
        """
            {"version":"LIO-message-receipt.2","message_id":"\(id)","conversation_id":"\(Self.conversationID)"}
            """
    }
}
