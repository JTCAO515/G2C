import Foundation

/// #1996 / #1995: the trip canvas (T-2) to the trip map's input (T-3).
///
/// Days are numbered across the whole trip in the order the timeline shows them (day 1 is the first day of the first
/// city segment), and a day keeps its colour by that position, so the map and the timeline agree. A point's number is
/// its place in its day, the same as in the timeline. The "want to go" inbox is not on a day, so it is not on the map.
/// The way between two neighbouring points becomes the label of that leg ("Transit 25 min"). Coordinates go through
/// unchanged (GCJ-02, see LioTripMapModel.swift).
extension LioTripMapInput {
    init(canvas: LioTripCanvas, language: LioLanguage) {
        let days = canvas.segments.flatMap(\.days)
        self.init(days: days.enumerated().map { dayIndex, day in
            let points = day.points.enumerated().map { index, point in
                Point(id: point.id, name: point.name(language),
                      latitude: point.coordinate?.latitude, longitude: point.coordinate?.longitude, number: index + 1)
            }
            let segments = day.points.indices.dropLast().compactMap { index -> Segment? in
                guard let leg = canvas.leg(after: index, in: day) else { return nil }
                return Segment(fromID: leg.fromID, toID: leg.toID, label: Self.legLabel(leg, language: language))
            }
            return Day(number: dayIndex + 1, colorSlot: LioTripMapPalette.slot(forDayIndex: dayIndex),
                       points: points, segments: segments)
        })
    }

    /// "Walk 15 min", "公共交通 25 分钟"; nil when the canvas has no usable estimate for the leg.
    static func legLabel(_ leg: LioTripCanvas.Leg, language: LioLanguage) -> String? {
        guard leg.seconds.isFinite, leg.seconds > 0 else { return nil }
        let mode: String
        switch leg.mode {
        case .walking: mode = language.text("Walk", "步行")
        case .transit: mode = language.text("Transit", "公共交通")
        case .taxi: mode = language.text("Taxi", "打车")
        }
        return "\(mode) \(duration(minutes: Int(min(ceil(leg.seconds / 60), 99_999)), language: language))"
    }
}
