import Foundation
import CryptoKit
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJAPI
import CJMessageClient
@testable import CJMessageHTTP

@MainActor private final class DiscussionStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
@MainActor private final class DiscussionCredentials: MessageCredentialsProvider {
    var callback: (() -> Void)?
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { callback?(); return "synthetic-only" }
}
private actor DiscussionWire: ClientTransport {
    var posts: [Data] = []
    var sequence: Int64 = 0
    var accepted: [String: Any]?
    var lostACK = false
    var persist = true
    var corrupt = false
    var statusError = false
    func configure(lostACK: Bool = false, persist: Bool = true, corrupt: Bool = false, statusError: Bool = false) {
        self.lostACK = lostACK; self.persist = persist; self.corrupt = corrupt; self.statusError = statusError
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let trace = UUID().uuidString
        var value: [String: Any], status = 200
        if operationID == "receiveTripDiscussionV3" {
            #expect(request.path == "/v3/messages" && request.method == .post)
            let raw = try await Data(collecting: #require(body), upTo: 65536); posts.append(raw)
            let original = try OriginalTripDiscussion(raw: raw, maximumBytes: 65536)
            sequence += persist ? 1 : 0
            let hash = SHA256.hash(data: raw).map { String(format: "%02x", $0) }.joined()
            let receipt: [String: Any] = ["message_id": original.messageID, "conversation_id": original.head.conversation_id, "generation": original.head.generation, "sequence": original.head.last_sequence + 1, "run_id": "r1", "input_sha256": hash]
            var reference = receipt
            reference.merge(["version": "MESSAGE-trip-reference.1", "message_version": "MESSAGE-send.3", "selection_epoch": 1, "context_kind": original.trip == nil ? "none" : "trip", "context_id": original.trip?.id as Any? ?? NSNull(), "context_version": original.trip?.expectedVersion as Any? ?? NSNull(), "trip_context": original.trip.map { $0.object as Any } ?? NSNull(), "content_version": original.trip == nil ? NSNull() : "structured.2", "content_sha256": original.trip == nil ? NSNull() : String(repeating: "a", count: 64)], uniquingKeysWith: { _, new in new })
            if corrupt { reference["run_id"] = "other" }
            value = ["request_id": trace, "version": "MESSAGE-accept.3", "receipt": receipt, "reference": reference]
            if persist { accepted = value }
            if lostACK { throw URLError(.networkConnectionLost) }
        } else {
            #expect(operationID == "readTripDiscussionStatusV3" && request.path?.hasPrefix("/v3/message-send-status?") == true && request.method == .get)
            let query = URLComponents(string: request.path!)!.queryItems!
            let id = query.first { $0.name == "message_id" }?.value
            let selected = id == nil ? nil : accepted
            value = ["request_id": trace, "version": "MESSAGE-send-status.3", "receipt": selected?["receipt"] ?? NSNull(), "reference": selected?["reference"] ?? NSNull(), "head": ["conversation_id": "chat", "generation": "g", "last_sequence": sequence]]
            if statusError {
                status = 503
                value = ["request_id": trace, "error": ["code": "MESSAGE_CONTEXT_UNAVAILABLE", "category": "dependency", "message_en": "Request unavailable", "message_zh": "请求不可用", "outcome": "unknown", "recovery": "reconcile_original"]]
            }
        }
        var headers = HTTPFields(); headers[.init("x-request-id")!] = trace; headers[.contentType] = "application/json"; headers[.cacheControl] = "no-store"
        return (HTTPResponse(status: .init(code: status), headerFields: headers), HTTPBody(try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])))
    }
}
@MainActor struct TripDiscussionSendTests {
    private func setup(_ wire: DiscussionWire, storage: DiscussionStorage = DiscussionStorage(), scope: StorageScope? = nil, credentials: DiscussionCredentials = DiscussionCredentials()) throws -> (MessageRecovery, Lease, MessageHTTPClient, StorageScope) {
        let scope = try scope ?? StorageScope(environment: UUID().uuidString, account: "synthetic")
        let recovery = MessageRecovery(storage: storage)
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 65536, maximumResponseBytes: 65536)
        return (recovery, lease, MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint, credentials: credentials, interceptedTestTransport: wire), scope)
    }
    @Test func explicitSelectionUsesOriginalBytesAndReceiptOnly() async throws {
        let wire = DiscussionWire(); let (recovery, lease, client, _) = try setup(wire)
        #expect(try !client.canStartTripDiscussion(conversationID: "chat", lease: lease))
        _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease)
        let choice = try MessageTripSelection(id: "trip-a", expectedVersion: 8, day: nil, itemID: "i1")
        let record = try client.stageTripDiscussion(messageID: "m1", conversationID: "chat", text: "原文", trip: choice, lease: lease)
        #expect(try !client.canStartTripDiscussion(conversationID: "chat", lease: lease))
        guard case .accepted = try await client.submitPreparedTripDiscussion(messageID: "m1", lease: lease) else { Issue.record("not accepted"); return }
        #expect(await wire.posts == [record.originalUTF8])
        #expect(try client.acceptedTripDiscussionReference(messageID: "m1", lease: lease).trip == choice)
        #expect(try recovery.action(messageID: "m1", lease: lease)?.phase == .accepted)
        #expect(try client.canStartTripDiscussion(conversationID: "chat", lease: lease))
    }
    @Test func lostACKReopenOnlyQueriesOriginalUntilReceipt() async throws {
        let wire = DiscussionWire(), storage = DiscussionStorage()
        let (recovery, lease, client, scope) = try setup(wire, storage: storage)
        _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease)
        let original = try client.stageTripDiscussion(messageID: "m1", conversationID: "chat", text: "explicit unbound", trip: nil, lease: lease)
        await wire.configure(lostACK: true)
        await #expect(throws: (any Error).self) { try await client.submitPreparedTripDiscussion(messageID: "m1", lease: lease) }
        recovery.invalidate()
        let (_, next, reopened, _) = try setup(wire, storage: storage, scope: scope)
        await #expect(throws: RecoveryError.queryOnly) { try await reopened.submitPreparedTripDiscussion(messageID: "m1", lease: next, confirmRestored: true) }
        #expect(try await reopened.reconcileTripDiscussion(messageID: "m1", lease: next) == .accepted)
        #expect(try reopened.acceptedTripDiscussionReference(messageID: "m1", lease: next).trip == nil)
        #expect(await wire.posts == [original.originalUTF8])
    }
    @Test func absenceRequiresExplicitConfirmationAndRetainsOriginal() async throws {
        let wire = DiscussionWire(), storage = DiscussionStorage()
        let (recovery, lease, client, scope) = try setup(wire, storage: storage)
        _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease)
        let original = try client.stageTripDiscussion(messageID: "m1", conversationID: "chat", text: "original", trip: nil, lease: lease)
        await wire.configure(lostACK: true, persist: false)
        await #expect(throws: (any Error).self) { try await client.submitPreparedTripDiscussion(messageID: "m1", lease: lease) }
        recovery.invalidate()
        let (_, next, reopened, _) = try setup(wire, storage: storage, scope: scope)
        #expect(try await reopened.reconcileTripDiscussion(messageID: "m1", lease: next) == .resubmitOriginal)
        await #expect(throws: RecoveryError.queryOnly) { try await reopened.submitPreparedTripDiscussion(messageID: "m1", lease: next) }
        #expect(await wire.posts.count == 1)
        await wire.configure()
        _ = try await reopened.submitPreparedTripDiscussion(messageID: "m1", lease: next, confirmRestored: true)
        #expect(await wire.posts == [original.originalUTF8, original.originalUTF8])
    }
    @Test func malformedAssociationStaysUnknownAndCannotUnlockNewID() async throws {
        let wire = DiscussionWire(); let (recovery, lease, client, _) = try setup(wire)
        _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease)
        try client.stageTripDiscussion(messageID: "m1", conversationID: "chat", text: "original", trip: nil, lease: lease)
        await wire.configure(corrupt: true)
        await #expect(throws: (any Error).self) { try await client.submitPreparedTripDiscussion(messageID: "m1", lease: lease) }
        #expect(try recovery.action(messageID: "m1", lease: lease)?.phase == .queryRequired)
        await #expect(throws: (any Error).self) { try await client.reconcileTripDiscussion(messageID: "m1", lease: lease) }
        _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease)
        #expect(try !client.canStartTripDiscussion(conversationID: "chat", lease: lease))
        #expect(await wire.posts.count == 1)
    }
    @Test func credentialCallbackAccountChangePreventsDispatch() async throws {
        let wire = DiscussionWire(), credentials = DiscussionCredentials()
        let (recovery, lease, client, _) = try setup(wire, credentials: credentials)
        _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease)
        try client.stageTripDiscussion(messageID: "m1", conversationID: "chat", text: "original", trip: nil, lease: lease)
        credentials.callback = { recovery.invalidate() }
        await #expect(throws: (any Error).self) { try await client.submitPreparedTripDiscussion(messageID: "m1", lease: lease) }
        #expect(await wire.posts.isEmpty)
    }
    @Test func explicitServerRefusalIsNotEmptyHeadOrSuccess() async throws {
        let wire = DiscussionWire(); let (_, lease, client, _) = try setup(wire)
        await wire.configure(statusError: true)
        do { _ = try await client.readTripDiscussionHead(conversationID: "chat", lease: lease); Issue.record("refusal swallowed") }
        catch MessageReadFailure.rejected(let status, let error) { #expect(status == 503 && error.error.code == "MESSAGE_CONTEXT_UNAVAILABLE") }
        #expect(try !client.canStartTripDiscussion(conversationID: "chat", lease: lease))
        #expect(await wire.posts.isEmpty)
    }
}
