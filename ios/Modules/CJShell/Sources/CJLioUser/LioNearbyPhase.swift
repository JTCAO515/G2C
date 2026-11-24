import Foundation

/// What the Nearby page shows (#1421 item 5). Kept outside the iOS-only view so the relocation rule is tested on the host.
enum LioNearbyPhase: Equatable {
    case locating, searching, ready, failed(LioNearbyFailure)

    enum AfterSameSpot: Equatable { case keep, show(LioNearbyPhase), searchAgain }

    /// Relocating landed on the same coordinate, so the page's search task (keyed by the query) will not rerun.
    /// `before` is the phase when relocating started; `self` is the phase now.
    func afterRelocatingToSameSpot(before: LioNearbyPhase) -> AfterSameSpot {
        // A search that finished while locating already set the right phase.
        guard self == .locating else { return .keep }
        switch before {
        case .ready: return .show(.ready)
        case .searching: return .show(.searching) // That search is still running and will finish the page.
        case .locating, .failed: return .searchAgain // No results yet, or an earlier failure that is now stale.
        }
    }
}
