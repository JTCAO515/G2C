import Foundation
import Testing
import CJMessageHTTP
@testable import CJLioUser

private actor ReadFailureCounter {
    var attempts = 0
    func read() throws -> LioTimelineWire.Page { attempts += 1; throw URLError(.timedOut) }
}
@MainActor struct LioReadFailureTests {
    @Test func failedReadIsVisibleBeforeTheObservationWindowWithoutAnEmptySuccess() async {
        let boundary = ReadFailureCounter()
        let service = LioService.timeline(send: { _ in Issue.record("Read-only recovery must not send"); return .uncertain },
            read: { _,_ in try await boundary.read() }, pollInterval: .milliseconds(10), observationWindow: .seconds(5))
        let model = LioConversation(service: service)
        let reader = Task { await model.refreshTimeline() }
        let clock = ContinuousClock()
        let deadline = clock.now.advanced(by: .seconds(1))
        while !model.timelineUnavailable && clock.now < deadline { await Task.yield() }
        #expect(!model.hasLoadedTimeline && model.timelineUnavailable && model.turns.isEmpty)
        #expect(await boundary.attempts > 0)
        reader.cancel()
        await reader.value
    }
}
