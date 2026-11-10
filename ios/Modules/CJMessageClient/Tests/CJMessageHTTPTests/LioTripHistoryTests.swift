import CJMessageClient
import Foundation
import Testing
@testable import CJMessageHTTP

@MainActor
struct LioTripHistoryTests {
    @Test func uncertainUndoSurvivesReactivationAndIsOnlyRead() async throws {
        let page = try history()
        let target = try #require(page.undoTarget)
        let store = UndoFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let firstRecovery = MessageRecovery(storage: store)
        let firstLease = try firstRecovery.activate(scope)
        var submissions: [Data] = []
        let first = LioTripHistoryClient(recovery: firstRecovery, scope: scope, lease: firstLease,
            readHistory: { _ in page }, submit: { undo in
                submissions.append(undo.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { _ in nil })

        #expect(try await first.undo(target) == .pending)
        #expect(try first.hasPendingUndo())
        let original = try #require(submissions.first)

        let restoredRecovery = MessageRecovery(storage: store)
        let restoredLease = try restoredRecovery.activate(scope)
        var observed: [Data] = []
        let restored = LioTripHistoryClient(recovery: restoredRecovery, scope: scope, lease: restoredLease,
            readHistory: { _ in page }, submit: { undo in
                submissions.append(undo.originalUTF8)
                throw URLError(.networkConnectionLost)
            }, readReceipt: { undo in
                observed.append(undo.originalUTF8)
                if observed.count == 1 { return nil }
                return Data("""
                    {"version":"LIO-trip-undo-receipt.1","action_id":"\(undo.actionID)","committed":true}
                    """.utf8)
            })

        #expect(try restored.hasPendingUndo())
        #expect(try await restored.undo(target) == .pending)
        #expect(try await restored.reconcileUndo() == .pending)
        #expect(try restored.hasPendingUndo())
        #expect(try await restored.reconcileUndo() == .committed)
        #expect(try !restored.hasPendingUndo())
        #expect(submissions == [original])
        #expect(observed == [original, original])
    }

    @Test func refusesHistoryForMoreThanOneItinerary() throws {
        let data = historyJSON(historyTripID: "trip:other")
        #expect(throws: MessageHTTPFailure.invalidResponse) { try LioTripHistoryWire.decodePage(data) }
    }

    @Test func aRefusedTargetDoesNotAuthorizeAnAutomaticNewUndo() async throws {
        let page = try history()
        let target = try #require(page.undoTarget)
        let store = UndoFixtureStore()
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: store)
        let lease = try recovery.activate(scope)
        var sends = 0
        let client = LioTripHistoryClient(recovery: recovery, scope: scope, lease: lease,
            readHistory: { _ in page }, submit: { _ in
                sends += 1
                return .conflict(Data(#"{"failure":"unavailable"}"#.utf8))
            }, readReceipt: { _ in Issue.record("A rejected undo needs a fresh trip read, not a receipt"); return nil })

        #expect(try await client.undo(target) == .changed)
        #expect(try !client.hasPendingUndo())
        #expect(try await client.reconcileUndo() == nil)
        #expect(sends == 1)
    }

    private func history() throws -> LioTripHistoryWire.Page {
        try LioTripHistoryWire.decodePage(historyJSON(historyTripID: "trip:synthetic"))
    }

    private func historyJSON(historyTripID: String) -> Data {
        Data("""
            {"version":"LIO-trip-history.1",
             "current":{"trip_id":"trip:synthetic","title":"Current plan","days":[
               {"date":"2026-11-10","items":[{"item_id":"walk","label":"Park walk","start_time":null,"end_time":null,"fixed":null}]}
             ]},
             "history":[{"trip_id":"\(historyTripID)","title":"Previous plan","days":[
               {"date":"2026-11-10","items":[{"item_id":"walk","label":"River walk","start_time":null,"end_time":null,"fixed":null}]}
             ]}],
             "undo_target":"fixture_target","next_before":null}
            """.utf8)
    }
}

@MainActor
private final class UndoFixtureStore: SecureMessageStorage {
    private var snapshot: Snapshot?

    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
