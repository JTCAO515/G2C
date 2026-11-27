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

extension LioPlaceTripAdd {
    /// What the Stay and Explore tools show as "added": the place is on the "Want to go" list, now or already.
    var isOnWantToGoList: Bool { self == .added || self == .alreadyThere }

    /// Today, by the clock in China, where the trip happens.
    @Sendable static func todayInChina() -> LioTripDay { LioTripDay(date: Date(), timeZone: LioTripChecklist.beijing) }

    /// The host's "Add to trip" (#2057, #2004, #2005), one rule for the place card and the tool pages: nil unless the
    /// canvas is on in this build (`canvasOn`) and the phone has a trip folder (`store`), so the button is not shown;
    /// otherwise adds to the canvas of the current plan, read when the button is tapped.
    @MainActor
    static func adder(canvasOn: Bool, store: LioTripCanvasStore?, plans: [LioPlanSummary],
                      today: @escaping @Sendable () -> LioTripDay = LioPlaceTripAdd.todayInChina) -> (@MainActor @Sendable (LioPlace) -> LioPlaceTripAdd)? {
        guard canvasOn, let store else { return nil }
        return { place in
            store.addWish(place, plan: LioTripChecklist.currentPlan(profile: nil, plans: plans, today: today()))
        }
    }

    /// The tool pages' `lioAddPlaceToTrip`: the same add, answered as "did the place end up on the list" (a failed
    /// write says no, so no "Added" notice).
    @MainActor
    static func toolAdder(canvasOn: Bool, store: LioTripCanvasStore?, plans: [LioPlanSummary],
                          today: @escaping @Sendable () -> LioTripDay = LioPlaceTripAdd.todayInChina) -> (@MainActor (LioPlace) -> Bool)? {
        guard let add = adder(canvasOn: canvasOn, store: store, plans: plans, today: today) else { return nil }
        return { (place: LioPlace) -> Bool in add(place).isOnWantToGoList }
    }
}
