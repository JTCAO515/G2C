import Foundation
import Testing
import CJMessageHTTP
@testable import CJLioUser

/// The first read fails; every later read waits until it is cancelled, so the observation can never end on its
/// own (nor run out its window) while the test looks. Nothing here depends on how fast the machine is (#1661).
private actor ReadFailureBoundary {
    var attempts = 0
    func read() async throws -> LioTimelineWire.Page {
        attempts += 1
        if attempts == 1 { throw URLError(.timedOut) }
        try await Task.sleep(for: .seconds(3600))
        throw CancellationError()
    }
}

@MainActor private final class ReaderState {
    var finished = false
}

@MainActor struct LioReadFailureTests {
    @Test(.timeLimit(.minutes(1)))
    func failedReadIsVisibleBeforeTheObservationWindowWithoutAnEmptySuccess() async {
        let boundary = ReadFailureBoundary()
        let service = LioService.timeline(send: { _ in Issue.record("Read-only recovery must not send"); return .uncertain },
            read: { _,_ in try await boundary.read() }, pollInterval: .milliseconds(10), observationWindow: .seconds(3600))
        let model = LioConversation(service: service)
        let state = ReaderState()
        let reader = Task {
            await model.refreshTimeline()
            state.finished = true
        }
        // Wait for the condition itself, not for a wall-clock deadline. The time limit only stops a broken build:
        // it cancels this test, which ends the wait and lets the expectations below report the failure.
        while !model.timelineUnavailable && !Task.isCancelled { await Task.yield() }
        // Still observing: the failure showed up while the window was open, not because the stream ended.
        #expect(!state.finished)
        #expect(!model.hasLoadedTimeline && model.timelineUnavailable && model.turns.isEmpty)
        #expect(model.timelineFailure != nil)
        #expect(await boundary.attempts > 0)
        reader.cancel()
        await reader.value
        #expect(state.finished)
    }
}
