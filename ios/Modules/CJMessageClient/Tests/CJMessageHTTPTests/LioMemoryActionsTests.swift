import CJMessageClient
import CryptoKit
import Foundation
import Testing
@testable import CJMessageHTTP

@MainActor
struct LioMemoryActionsTests {
    @Test func explicitChoiceSurvivesReactivationAndKeepsItsOriginalBody() async throws {
        let tag = try tagFromTimeline()
        let store = MemoryChoiceFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let firstRecovery = MessageRecovery(storage: store)
        let firstLease = try firstRecovery.activate(scope)
        var writes: [Data] = []
        let first = LioMemoryActionsClient(recovery: firstRecovery, scope: scope, lease: firstLease,
            submit: { action in
                writes.append(action.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { _ in throw URLError(.notConnectedToInternet) })

        #expect(try await first.reconcileChoice() == nil)
        #expect(writes.isEmpty)
        #expect(try await first.choose(.remember, tag: tag) == .pending)
        let original = try #require(writes.first)

        let recovery = MessageRecovery(storage: store)
        let lease = try recovery.activate(scope)
        var observed: [Data] = []
        let restored = LioMemoryActionsClient(recovery: recovery, scope: scope, lease: lease,
            submit: { action in
                writes.append(action.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { action in
                observed.append(action.originalUTF8)
                let status = observed.count == 1 ? "pending" : "remembered"
                return Data("""
                    {"version":"LIO-memory-action-receipt.1","action_id":"\(action.actionID)","status":"\(status)"}
                    """.utf8)
            })

        #expect(try restored.hasPendingChoice())
        #expect(try await restored.choose(.remember, tag: tag) == .pending)
        #expect(try await restored.reconcileChoice() == .pending)
        #expect(try await restored.reconcileChoice() == .remembered)
        #expect(try !restored.hasPendingChoice())
        #expect(try await restored.choose(.remember, tag: tag) == .remembered)
        #expect(writes == [original])
        #expect(observed == [original, original])
    }

    @Test func dismissNeverAcceptsARememberedResult() throws {
        let action = try LioMemoryWire.Action(choice: .dismiss, tag: tagFromTimeline())
        let response = Data("""
            {"version":"LIO-memory-action-receipt.1","action_id":"\(action.actionID)","status":"remembered"}
            """.utf8)
        #expect(throws: MessageHTTPFailure.invalidResponse) { try action.outcome(response) }
    }

    @Test func erasureRemovesOnlyTheStoppedItemsChoiceOriginalsAcrossReopen() async throws {
        let environment = UUID(), account = UUID()
        let scope = try StorageScope(environment: environment.uuidString, account: account.uuidString)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let storage = try EncryptedFileStorage(directory: directory, keys: MemoryChoiceFixtureKey())
        defer { try? FileManager.default.removeItem(at: directory) }
        let recovery = MessageRecovery(storage: storage)
        let lease = try recovery.activate(scope)
        var sent: [LioMemoryWire.Action] = []
        let client = LioMemoryActionsClient(recovery: recovery, scope: scope, lease: lease, submit: { action in
            sent.append(action)
            if sent.count == 3 { throw URLError(.networkConnectionLost) }
            return .receipt(Data("""
                {"version":"LIO-memory-action-receipt.1","action_id":"\(action.actionID)","status":"remembered"}
                """.utf8))
        }, readReceipt: { _ in throw URLError(.notConnectedToInternet) })
        let removed = try tagFromTimeline(id: "preference-one", text: "Likes museums")
        let other = try tagFromTimeline(id: "preference-two", text: "Likes walking")
        let pending = try tagFromTimeline(id: "preference-one", text: "Likes history museums")
        #expect(try await client.choose(.remember, tag: removed) == .remembered)
        #expect(try await client.choose(.remember, tag: other) == .remembered)
        #expect(try await client.choose(.remember, tag: pending) == .pending)
        #expect(throws: RecoveryError.inactive) {
            try client.clearErasedItem(removed.id, environment: environment, account: UUID())
        }
        try client.clearErasedItem(removed.id, environment: environment, account: account)
        #expect(try await client.choose(.remember, tag: removed) == .changed)
        #expect(sent.count == 3)
        recovery.invalidate()

        let restored = MessageRecovery(storage: storage)
        let reopened = try restored.activate(scope)
        #expect(try restored.action(messageID: sent[0].actionID, lease: reopened) == nil)
        #expect(try restored.action(messageID: sent[2].actionID, lease: reopened) == nil)
        #expect(try restored.action(messageID: sent[1].actionID, lease: reopened)?.originalUTF8 == sent[1].originalUTF8)
    }

    private func tagFromTimeline(id: String = "preference-1", text: String = "Likes museums") throws -> LioMemoryWire.Tag {
        let bytes = Data("{\"candidate_id\":\"\(id)\",\"text\":\"\(text)\"}".utf8)
        let target = bytes.base64EncodedString().replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
        let page = try LioTimelineWire.decodePage(Data("""
            {"version":"LIO-timeline.1","conversation_id":"lio-dialogue-0123456789abcdef0123456789abcdef",
             "messages":[{"message_id":"one","text":"I like museums.","answer":"Noted.","status":"completed",
                          "failure":null,"sources":[],"trip":null,"memory":{"tags":[
                            {"id":"\(id)","kind":"preference","text":"\(text)","target":"\(target)"}
                          ]}}],
             "next_before":null}
            """.utf8))
        return try #require(page.messages.first?.memoryTags.first)
    }
}

@MainActor
private final class MemoryChoiceFixtureKey: MessageEncryptionKeyProvider {
    private let key = MessageStorageKey(id: UUID(), key: SymmetricKey(size: .bits256))
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? { key }
}

@MainActor
private final class MemoryChoiceFixtureStore: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
