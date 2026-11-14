import Foundation

/// Validated display values, not a structured decoder or a protected read/write source.
/// The eventual protected read maps original structured.4 values into this view model.
struct LioRichItinerary: Sendable {
    enum Kind: String, CaseIterable, Sendable {
        case sight, meal, hotel, transport, freeTime = "free_time"
        var symbol: String {
            switch self {
            case .sight: "camera"
            case .meal: "fork.knife"
            case .hotel: "bed.double"
            case .transport: "tram"
            case .freeTime: "leaf"
            }
        }
        func title(_ language: LioLanguage) -> String {
            switch self {
            case .sight: language.text("Sight", "景点")
            case .meal: language.text("Food", "餐饮")
            case .hotel: language.text("Stay", "住宿")
            case .transport: language.text("Travel", "交通")
            case .freeTime: language.text("Free time", "自由活动")
            }
        }
    }
    struct Place: Sendable {
        let nameZH: String
        let nameEN: String
        let address: String?
        let matched: Bool
        /// Only a protected, validated original provider GCJ-02 coordinate may be mapped here.
        let point: LioItinerary.Point?

        func displayName(_ language: LioLanguage) -> String { language == .chinese ? nameZH : nameEN }
        var driverAddress: String? { matched ? address : nil }
        var mapPoint: LioItinerary.Point? { matched ? point : nil }
    }
    struct Stop: Identifiable, Sendable {
        let id: String
        let kind: Kind
        let text: String
        let time: String?
        let place: Place
        let note: String?
        let tip: String?
        let fixed: Bool?

        init(id: String, kind: Kind, text: String, time: String?, place: Place, note: String?, tip: String?, fixed: Bool? = nil) {
            self.id = id; self.kind = kind; self.text = text; self.time = time
            self.place = place; self.note = note; self.tip = tip; self.fixed = fixed
        }
    }
    struct Leg: Sendable {
        enum Mode: String, Sendable { case walking, transit, taxi }
        struct Estimate: Sendable {
            let mode: Mode
            let seconds: Double
            let metres: Double
        }
        let fromID: String
        let toID: String
        let estimate: Estimate?

        func description(_ language: LioLanguage) -> String {
            guard let estimate else { return language.text("Travel details not available yet", "交通安排待定") }
            let mode: String
            switch estimate.mode {
            case .walking: mode = language.text("Walk", "步行")
            case .transit: mode = language.text("Public transport", "公共交通")
            case .taxi: mode = language.text("Taxi", "出租车")
            }
            let minutes = ceil(estimate.seconds / 60).formatted(.number.precision(.fractionLength(0)))
            let kilometres = (estimate.metres / 1000).formatted(.number.precision(.fractionLength(0...1)))
            return language.text("\(mode) · about \(minutes) min · \(kilometres) km",
                                 "\(mode) · 约 \(minutes) 分钟 · \(kilometres) 公里")
        }
        var symbol: String {
            switch estimate?.mode { case .walking: "figure.walk"; case .transit: "tram"; case .taxi: "car"; case nil: "arrow.down" }
        }
    }
    struct Day: Identifiable, Sendable {
        let number: Int
        let date: String?
        let theme: String
        let area: String
        let stops: [Stop]
        let legs: [Leg]
        var id: Int { number }
        var mapDay: LioItinerary.Day {
            LioItinerary.Day(number: number, stops: stops.map {
                LioItinerary.Stop(id: $0.id, name: $0.place.nameZH, time: $0.time, point: $0.place.mapPoint, fixed: nil)
            }, date: date)
        }
        /// Keep original list numbers even when some places have no coordinates.
        var mapNumbers: [Int] { stops.enumerated().compactMap { $0.element.place.mapPoint == nil ? nil : $0.offset + 1 } }
        func leg(after index: Int) -> Leg? {
            guard index + 1 < stops.count else { return nil }
            return legs.first { $0.fromID == stops[index].id && $0.toID == stops[index + 1].id }
        }
    }
    struct Hotel: Identifiable, Sendable {
        let id: String
        let place: Place
        let note: String?
    }
    let title: String
    let undated: Bool
    let days: [Day]
    let lodgingArea: String
    let hotels: [Hotel]
}
