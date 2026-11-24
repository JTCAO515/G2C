import Testing
@testable import CJLioUser

/// #1421 item 5: relocating to the same coordinate must never leave the page spinning or showing a stale failure.
@Suite struct LioNearbyPhaseTests {
    @Test func restoresResultsWhenNothingElseChanged() {
        #expect(LioNearbyPhase.locating.afterRelocatingToSameSpot(before: .ready) == .show(.ready))
    }

    @Test func aSearchStillRunningKeepsShowingProgress() {
        #expect(LioNearbyPhase.locating.afterRelocatingToSameSpot(before: .searching) == .show(.searching))
    }

    @Test func aSearchThatFinishedWhileLocatingIsNotOverwritten() {
        #expect(LioNearbyPhase.ready.afterRelocatingToSameSpot(before: .searching) == .keep)
        #expect(LioNearbyPhase.failed(.timedOut).afterRelocatingToSameSpot(before: .searching) == .keep)
        #expect(LioNearbyPhase.searching.afterRelocatingToSameSpot(before: .ready) == .keep)
    }

    @Test func anEarlierFailureIsRetriedInsteadOfShownAgain() {
        #expect(LioNearbyPhase.locating.afterRelocatingToSameSpot(before: .failed(.locationDenied)) == .searchAgain)
        #expect(LioNearbyPhase.locating.afterRelocatingToSameSpot(before: .failed(.unavailable)) == .searchAgain)
    }

    @Test func noResultsYetSearches() {
        #expect(LioNearbyPhase.locating.afterRelocatingToSameSpot(before: .locating) == .searchAgain)
    }
}
