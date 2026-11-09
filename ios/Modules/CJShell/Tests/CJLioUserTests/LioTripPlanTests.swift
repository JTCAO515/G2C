import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

@MainActor
struct LioTripPlanTests {
    @Test func newTripCardDoesNotBorrowAnOlderUndoTarget() async throws {
        let before = try page(stop: "Park", target: "first")
        let edited = try page(stop: "Museum", target: "second")
        let originalCard = try card("initial-plan", before)
        let editedCard = try card("updated-plan", edited)
        let service = TripPlanningStub(before)
        let model = LioTripPlan(client: service)

        await model.reload(for: originalCard)
        #expect(model.current(in: originalCard) == originalCard.itinerary)
        #expect(model.current(in: editedCard) == nil)
        let earlierTarget = try #require(model.target)

        service.page = edited
        await model.reload(for: editedCard)
        #expect(model.current(in: originalCard) == nil)
        #expect(model.current(in: editedCard) == editedCard.itinerary)
        await model.undo(earlierTarget)
        #expect(service.writes.isEmpty)

        let other = try card("other-trip", page(stop: "Tea house", target: "third", tripID: "trip:other"))
        await model.reload(for: other)
        #expect(model.current(in: other) == nil)
    }

    @Test func pendingUndoIsObservedOnceAndRestoredCardIsShared() async throws {
        let edited = try page(stop: "Museum", target: "second")
        let editedCard = try card("updated-plan", edited)
        let service = TripPlanningStub(edited)
        let model = LioTripPlan(client: service)
        await model.reload(for: editedCard)
        let target = try #require(model.target)

        await model.undo(target)
        await model.undo(target)
        #expect(model.pending)
        #expect(service.writes == [target])

        service.page = try page(stop: "Park", target: "third")
        await model.awaitUndo()

        #expect(service.receiptReads == 1)
        #expect(service.writes == [target])
        #expect(!model.pending)
        #expect(model.current(in: editedCard)?.days.first?.stops.first?.name == "Park")
        #expect(model.current(for: editedCard) == model.current)
        #expect(model.target == service.page.undoTarget)
    }

    @Test func lateHistoryReadCannotReplaceTheEditedCardOrItsTarget() async throws {
        let original = try page(stop: "Park", target: "first")
        let updated = try page(stop: "Museum", target: "second")
        let originalCard = try card("initial-plan", original)
        let updatedCard = try card("updated-plan", updated)
        let service = TripPlanningStub(original)
        let model = LioTripPlan(client: service)
        let (started, signal) = AsyncStream<CheckedContinuation<Void, Never>>.makeStream()
        service.pauseNextRead = {
            await withCheckedContinuation { continuation in
                signal.yield(continuation)
                signal.finish()
            }
        }
        let loading = Task { await model.reload(for: originalCard) }
        var reads = started.makeAsyncIterator()
        let resume = await reads.next()

        service.page = updated
        await model.reload(for: updatedCard)
        resume?.resume()
        await loading.value

        #expect(model.current(in: originalCard) == nil)
        #expect(model.current(in: updatedCard) == updatedCard.itinerary)
        #expect(model.target == updated.undoTarget)
    }

    private func card(_ turnID: String, _ page: LioTripHistoryWire.Page) throws -> LioTripCard {
        let trip = try #require(page.current)
        return LioTripCard(turnID: Data(turnID.utf8), itinerary: LioItinerary(trip))
    }

    private func page(stop: String, target: String, tripID: String = "trip:beijing") throws -> LioTripHistoryWire.Page {
        try LioTripHistoryWire.decodePage(Data("""
            {"version":"LIO-trip-history.1",
             "current":{"trip_id":"\(tripID)","title":"Beijing","days":[{"date":"2026-11-10",
                       "items":[{"item_id":"visit","label":"\(stop)","start_time":"14:00"}]}]},
             "history":[{"trip_id":"\(tripID)","title":"Beijing","days":[]}],
             "undo_target":"\(target)","next_before":null}
            """.utf8))
    }
}

@MainActor
private final class TripPlanningStub: LioTripPlanning {
    var page: LioTripHistoryWire.Page
    var pending = false
    var writes: [LioTripHistoryWire.Target] = []
    var receiptReads = 0
    var pauseNextRead: (@MainActor () async -> Void)?

    init(_ page: LioTripHistoryWire.Page) { self.page = page }

    func history(before: String?) async throws -> LioTripHistoryWire.Page {
        let result = page
        let pause = pauseNextRead
        pauseNextRead = nil
        await pause?()
        return result
    }
    func hasPendingUndo() throws -> Bool { pending }

    func undo(_ target: LioTripHistoryWire.Target) async throws -> LioTripHistoryClient.UndoState {
        writes.append(target)
        pending = true
        return .pending
    }

    func reconcileUndo() async throws -> LioTripHistoryClient.UndoState? {
        receiptReads += 1
        pending = false
        return .committed
    }
}
