import Foundation

/// #1509 travel roadbook: a printable, offline handbook for one trip.
/// It wraps the same `LioRichItinerary` the day-by-day plan shows (#1453) instead of keeping its own trip model;
/// everything here is derived on the device from that value.
struct LioRoadbook: Identifiable, Sendable {
    enum Source: String, CaseIterable, Sendable {
        case saved, planned, template

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .saved: language.text("My trips", "我的行程")
            case .planned: language.text("Planned with Lio", "Lio 规划")
            case .template: language.text("Popular routes", "热门路线")
            }
        }
    }

    struct City: Equatable, Sendable {
        let nameZH: String
        let nameEN: String

        func name(_ language: LioLanguage) -> String { language.text(nameEN, nameZH) }
    }

    let id: String
    let source: Source
    let city: City?
    let createdAt: Date
    let itinerary: LioRichItinerary
    /// Places filled in through ROADBOOK.1, by stop id; kept with the offline copy and printed in the PDF.
    var details: [String: LioRoadbookDetail] = [:]

    func coverTitle(_ language: LioLanguage) -> String { city?.name(language) ?? itinerary.title }

    /// "3 天 · 12月1日–12月3日" / "3 days · Dec 1 – Dec 3"; undated trips say so instead of inventing dates.
    func coverLine(_ language: LioLanguage) -> String {
        let count = itinerary.days.count
        let days = language.text(count == 1 ? "1 day" : "\(count) days", "\(count) 天")
        return days + " · " + (dateRange(language) ?? language.text("Dates not set", "日期待定"))
    }

    func dateRange(_ language: LioLanguage) -> String? {
        let dates = itinerary.days.compactMap(\.date)
        guard !itinerary.undated, let first = dates.first, let last = dates.last else { return nil }
        let start = Self.shortDate(first, language), end = Self.shortDate(last, language)
        if first == last { return start }
        return language.text("\(start) – \(end)", "\(start)–\(end)")
    }

    func dayTitle(_ day: LioRichItinerary.Day, _ language: LioLanguage) -> String {
        let number = language.text("Day \(day.number)", "第 \(day.number) 天")
        guard !itinerary.undated, let date = day.date else { return number }
        return number + " · " + Self.shortDate(date, language)
    }

    static func shortDate(_ value: String, _ language: LioLanguage) -> String {
        let parser = DateFormatter()
        parser.calendar = Calendar(identifier: .gregorian)
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.timeZone = TimeZone(identifier: "UTC")
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: value) else { return value }
        parser.dateFormat = language == .chinese ? "M月d日" : "MMM d"
        return parser.string(from: date)
    }

    /// Shown with every reminder: opening hours, bookings and prices are never live data here.
    static func officialNotice(_ language: LioLanguage) -> String {
        language.text("Check opening hours, bookings and prices with official sources.",
                      "开放时间、预约和票价以官方为准。")
    }

    /// "Take a taxi here" reuses the taxi page; only a checked place with a checked coordinate can be a destination.
    static func taxiDestination(_ place: LioRichItinerary.Place) -> LioTaxiPlace? {
        LioTaxiPlace(itineraryPlace: place)
    }

    /// Trimmed note text, or nil when there is nothing to show.
    static func visibleNote(_ note: String?) -> String? {
        guard let text = note?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        return text
    }

    /// The driver card shows only a checked address.
    static func driverAddress(_ place: LioRichItinerary.Place) -> String? { place.driverAddress }
}

/// Morning / afternoon / evening, from the stop's start time.
enum LioRoadbookPeriod: Int, CaseIterable, Comparable, Sendable {
    case morning, afternoon, evening

    /// Reads a leading "H:mm" or "HH:mm" (the plan's start time); anything else has no period of its own.
    init?(time: String?) {
        guard let time else { return nil }
        let parts = time.prefix { $0.isNumber || $0 == ":" }.split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count >= 2, (1...2).contains(parts[0].count), parts[1].count == 2,
              let hour = Int(parts[0]), let minute = Int(parts[1]), (0..<24).contains(hour), (0..<60).contains(minute) else {
            return nil
        }
        switch hour {
        case ..<12: self = .morning
        case ..<18: self = .afternoon
        default: self = .evening
        }
    }

    static func < (lhs: Self, rhs: Self) -> Bool { lhs.rawValue < rhs.rawValue }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .morning: language.text("Morning", "上午")
        case .afternoon: language.text("Afternoon", "下午")
        case .evening: language.text("Evening", "晚上")
        }
    }

    var symbol: String {
        switch self {
        case .morning: "sunrise"
        case .afternoon: "sun.max"
        case .evening: "moon.stars"
        }
    }
}

struct LioRoadbookEntry: Identifiable, Sendable {
    /// The stop's number in the whole day, matching the plan and its map.
    let number: Int
    let stop: LioRichItinerary.Stop
    let legAfter: LioRichItinerary.Leg?
    var id: String { stop.id }
}

struct LioRoadbookSegment: Identifiable, Sendable {
    let period: LioRoadbookPeriod
    let entries: [LioRoadbookEntry]
    var id: LioRoadbookPeriod { period }
}

extension LioRoadbook {
    /// Keeps the plan's order. A stop without its own start time, or one earlier than the stop before it,
    /// stays in the current period so a day never jumps back from evening to morning.
    static func segments(_ day: LioRichItinerary.Day) -> [LioRoadbookSegment] {
        var segments: [LioRoadbookSegment] = []
        var current = LioRoadbookPeriod.morning
        var entries: [LioRoadbookEntry] = []
        for (index, stop) in day.stops.enumerated() {
            let period = max(current, LioRoadbookPeriod(time: stop.time) ?? current)
            if period != current, !entries.isEmpty {
                segments.append(.init(period: current, entries: entries))
                entries = []
            }
            current = period
            entries.append(.init(number: index + 1, stop: stop, legAfter: day.leg(after: index)))
        }
        if !entries.isEmpty { segments.append(.init(period: current, entries: entries)) }
        return segments
    }
}

/// #1515: the Roadbook tool is shown only when the build's Info.plist sets `G2CRoadbookEnabled` to the string YES.
enum LioRoadbookFeature {
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }
}

extension LioRoadbook {
    /// A saved trip (#1547 / #1723), from its stored itinerary: a chat plan has names and times only (no taxi,
    /// driver card or map); a saved popular route keeps its checked places.
    /// One roadbook per saved version, so a kept copy of an older version stays beside a changed plan.
    init(savedPlan plan: LioPlanSummary, createdAt: Date = .now) {
        self.init(id: "saved.\(plan.tripID).v\(plan.tripVersion)", source: .saved, city: nil,
                  createdAt: createdAt, itinerary: plan.itinerary)
    }
}

extension LioRoadbook {
    /// The same roadbook stamped with the moment it is kept on this phone.
    func kept(at date: Date = .now) -> LioRoadbook {
        LioRoadbook(id: id, source: source, city: city, createdAt: date, itinerary: itinerary, details: details)
    }
}

extension LioRoadbook {
    /// The library order: kept copies replace the same roadbook offered again; then my trips, Lio's plans
    /// and the popular routes (#1509), one card per id.
    static func library(kept: [LioRoadbook], candidates: [LioRoadbook], language: LioLanguage) -> [LioRoadbook] {
        var seen = Set<String>()
        let all = (kept + candidates + LioRoadbookTemplates.all(language)).filter { seen.insert($0.id).inserted }
        return Source.allCases.flatMap { source in all.filter { $0.source == source } }
    }
}
