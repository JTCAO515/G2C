import Foundation

/// #1996: saved plans (#1453 / #1723) to the trip map's input.
///
/// Every stop becomes a point, numbered by its place in the day. A stop has a position only when its place is a
/// matched one with a GCJ-02 point (`LioRichItinerary.Place.mapPoint`): a chat plan saved without the places read
/// has none, so it gives points but no pins and the map shows its empty state with the places listed below.
/// Colours go by the day's place in the trip, so a day with no stops keeps its colour for the days after it.
extension LioTripMapInput {
    init(plan: LioPlanSummary, language: LioLanguage) {
        self.init(itinerary: plan.itinerary, language: language)
    }

    init(itinerary: LioRichItinerary, language: LioLanguage) {
        self.init(days: itinerary.days.enumerated().map { dayIndex, day in
            let points = day.stops.enumerated().map { index, stop in
                let point = stop.place.mapPoint
                return Point(id: stop.id, name: stop.place.displayName(language),
                             latitude: point?.latitude, longitude: point?.longitude, number: index + 1)
            }
            let segments = day.stops.indices.dropLast().compactMap { index -> Segment? in
                guard let leg = day.leg(after: index) else { return nil }
                return Segment(fromID: leg.fromID, toID: leg.toID, label: Self.legLabel(leg, language: language))
            }
            return Day(number: day.number, colorSlot: LioTripMapPalette.slot(forDayIndex: dayIndex),
                       points: points, segments: segments)
        })
    }

    /// "Walk 15 min", "公共交通 25 分钟", "Taxi 1 h 30 min"; nil when the leg has no estimate (or a zero one).
    static func legLabel(_ leg: LioRichItinerary.Leg, language: LioLanguage) -> String? {
        guard let estimate = leg.estimate, estimate.seconds.isFinite, estimate.seconds > 0 else { return nil }
        let mode: String
        switch estimate.mode {
        case .walking: mode = language.text("Walk", "步行")
        case .transit: mode = language.text("Transit", "公共交通")
        case .taxi: mode = language.text("Taxi", "打车")
        }
        return "\(mode) \(duration(minutes: Int(min(ceil(estimate.seconds / 60), 99_999)), language: language))"
    }

    static func duration(minutes: Int, language: LioLanguage) -> String {
        guard minutes >= 60 else { return language.text("\(minutes) min", "\(minutes) 分钟") }
        let (hours, rest) = minutes.quotientAndRemainder(dividingBy: 60)
        guard rest > 0 else { return language.text("\(hours) h", "\(hours) 小时") }
        return language.text("\(hours) h \(rest) min", "\(hours) 小时 \(rest) 分钟")
    }
}
