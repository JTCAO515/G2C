import Foundation

/// What "Add to trip" did with a place (#1991): put it in the trip canvas's "Want to go" list.
enum LioPlaceTripAdd: Equatable, Sendable {
    case added, alreadyThere, failed
}

extension LioTripCanvasStore {
    /// Adds `place` to the "Want to go" list of the canvas of `plan` (or the traveller's own canvas when there is no
    /// plan), on this phone only: nothing is sent. The point's id comes from the place's, so adding it twice changes
    /// nothing. A canvas file this build cannot read is never written over (the add fails and says so).
    func addWish(_ place: LioPlace, plan: LioPlanSummary?) -> LioPlaceTripAdd {
        let id = "place-" + place.id
        do {
            let tripID = plan?.tripID ?? LioTripCanvas.standaloneID
            let stored = try canvas(for: tripID)
            var canvas = plan.map { LioTripCanvas.resolved(stored: stored, plan: $0) } ?? stored ?? LioTripCanvas(emptyTripID: tripID)
            let there = canvas.wishlist + canvas.segments.flatMap { $0.days.flatMap(\.points) }
            if canvas.point(id) != nil || there.contains(where: { $0.placeID == place.id }) { return .alreadyThere }
            let coordinate = place.point.map { LioTripCanvas.Coordinate(latitude: $0.latitude, longitude: $0.longitude) }
            guard canvas.addWish(id: id, name: place.nameZH, nameEN: place.nameEN, placeID: place.id, coordinate: coordinate) else {
                return .failed
            }
            try save(canvas)
            return .added
        } catch {
            return .failed
        }
    }
}
