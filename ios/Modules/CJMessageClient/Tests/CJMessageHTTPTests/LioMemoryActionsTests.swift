import CJMessageClient
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

    private func tagFromTimeline() throws -> LioMemoryWire.Tag {
        let page = try LioTimelineWire.decodePage(Data("""
            {"version":"LIO-timeline.1","conversation_id":"lio-dialogue-0123456789abcdef0123456789abcdef",
             "messages":[{"message_id":"one","text":"I like museums.","answer":"Noted.","status":"completed",
                          "failure":null,"sources":[],"trip":null,"memory":{"tags":[
                            {"id":"preference-1","kind":"preference","text":"Likes museums","target":"fixture_target"}
                          ]}}],
             "next_before":null}
            """.utf8))
        return try #require(page.messages.first?.memoryTags.first)
    }
}

@MainActor
private final class MemoryChoiceFixtureStore: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
