import Foundation

/// The taxi page's "trip places" (#1741): the confirmed places of the formal saved trip (saved plans v2, their
/// `itinerary`), not the chat's draft itineraries. A place is a destination only when it was matched to a real
/// place with a checked coordinate (`LioTaxiPlace(itineraryPlace:)` reads `mapPoint`, which is nil unless matched);
/// unmatched names are never offered, since the driver would be sent to a guess.
enum LioTaxiTripPlaces {
    /// Stops in day order, then the stays, for each saved plan newest first; each place once.
    static func confirmed(in plans: [LioPlanSummary]) -> [LioTaxiPlace] {
        var seen = Set<LioTaxiPlace.ID>()
        return plans.flatMap { plan in
            plan.itinerary.days.flatMap { $0.stops.map(\.place) } + plan.itinerary.hotels.map(\.place)
        }
        .compactMap(LioTaxiPlace.init(itineraryPlace:))
        .filter { seen.insert($0.id).inserted }
    }
}
