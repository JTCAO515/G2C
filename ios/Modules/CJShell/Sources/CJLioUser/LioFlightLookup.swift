import Foundation

/// Look up one flight by number (#2007), over FLIGHTS.1 (`contracts/api/FLIGHTS.1.md`). Read-only: the page
/// shows what the supplier says and never claims more; times and status are the supplier's own words.

struct LioFlightQuery: Equatable, Sendable {
    enum Problem: Error, Equatable, Sendable {
        case emptyNumber, badNumber, pastDate, tooFarAhead

        func message(_ language: LioLanguage) -> String {
            switch self {
            case .emptyNumber:
                language.text("Enter a flight number, for example MU5102.", "请输入航班号，例如 MU5102。")
            case .badNumber:
                language.text("That doesn't look like a flight number. Use the airline code and digits, like CA981.",
                              "这不像航班号。请输入航司代码加数字，例如 CA981。")
            case .pastDate:
                language.text("Pick today, or yesterday at the earliest.", "请选今天，最早昨天。")
            case .tooFarAhead:
                language.text("Flights can be looked up up to 60 days ahead.", "最多可查 60 天内的航班。")
            }
        }
    }

    /// Normalized, e.g. `MU5102`.
    let number: String
    /// `yyyy-MM-dd`, China time.
    let day: String

    /// Airline code (2–3 letters or digits) then 1–4 digits and an optional letter, as the server checks it.
    static let pattern = #"^[A-Z0-9]{2,3}[0-9]{1,4}[A-Z]?$"#

    /// Upper-case, no spaces, dashes or full-width forms: "mu 5102" and "ＭＵ５１０２" both give `MU5102`.
    static func normalize(_ text: String) -> String {
        let folded = text.applyingTransform(.fullwidthToHalfwidth, reverse: false) ?? text
        return folded.uppercased().filter { !$0.isWhitespace && $0 != "-" && $0 != "·" }
    }

    static func make(number: String, date: Date, today: Date = Date()) -> Result<Self, Problem> {
        let normalized = normalize(number)
        guard !normalized.isEmpty else { return .failure(.emptyNumber) }
        guard normalized.range(of: pattern, options: .regularExpression) != nil,
              normalized.contains(where: \.isLetter) else { return .failure(.badNumber) }
        let day = LioTransportQuery.dayString(date)
        let calendar = LioTransportQuery.calendar
        let yesterday = calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: today)) ?? today
        guard day >= LioTransportQuery.dayString(yesterday) else { return .failure(.pastDate) }
        guard day <= LioTransportQuery.dayString(LioTransportQuery.lastBookableDay(today: today)) else {
            return .failure(.tooFarAhead)
        }
        return .success(Self(number: normalized, day: day))
    }
}

/// One flight row from FLIGHTS.1; everything but the number is optional and shown only when present.
struct LioFlightStatus: Decodable, Equatable, Identifiable, Sendable {
    let flightNumber: String
    let departure: String?
    let arrival: String?
    let codeshare: Bool?
    let status: String?
    let plannedDeparture: String?
    let plannedArrival: String?
    let actualDeparture: String?
    let actualArrival: String?
    let departureTerminal: String?
    let arrivalTerminal: String?
    let gate: String?
    let checkInCounter: String?
    let baggageCarousel: String?
    let airlineNameZh: String?
    let airlineNameEn: String?
    let departureAirportNameZh: String?
    let departureAirportNameEn: String?
    let arrivalAirportNameZh: String?
    let arrivalAirportNameEn: String?

    var id: String { [flightNumber, departure ?? "", arrival ?? "", plannedDeparture ?? ""].joined(separator: "|") }

    func airline(_ language: LioLanguage) -> String? {
        language == .chinese ? airlineNameZh ?? airlineNameEn : airlineNameEn ?? airlineNameZh
    }

    /// The airport's name for `code`: the supplier's own, else the bundled city table's, else the code.
    func airportName(departure isDeparture: Bool, _ language: LioLanguage) -> String? {
        let code = isDeparture ? departure : arrival
        let zh = isDeparture ? departureAirportNameZh : arrivalAirportNameZh
        let en = isDeparture ? departureAirportNameEn : arrivalAirportNameEn
        if let supplied = language == .chinese ? zh ?? en : en ?? zh { return supplied }
        guard let code else { return nil }
        if let known = LioTransportCity.all.lazy.flatMap(\.airports).first(where: { $0.code == code }) {
            return known.name(in: language)
        }
        return code
    }
}

struct LioFlightLookupResult: Equatable, Sendable {
    let query: LioFlightQuery
    let flights: [LioFlightStatus]
    /// The supplier had more rows than we show.
    let more: Bool
}

enum LioFlightTimeText {
    /// `HH:mm` when the supplier gives a date-time on the queried day, `MM-dd HH:mm` on another day, the text
    /// as is when it can't be read. The supplier's clock is China time, so no conversion is made.
    static func display(_ raw: String, queriedDay: String) -> String {
        let pattern = #"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$"#
        if let match = raw.firstMatch(of: try! Regex(pattern)),
           match.output.count == 6,
           let year = match.output[1].substring, let month = match.output[2].substring,
           let day = match.output[3].substring, let hour = match.output[4].substring,
           let minute = match.output[5].substring {
            let clock = "\(hour):\(minute)"
            return "\(year)-\(month)-\(day)" == queriedDay ? clock : "\(month)-\(day) \(clock)"
        }
        if raw.range(of: #"^([01]\d|2[0-3]):[0-5]\d$"#, options: .regularExpression) != nil { return raw }
        return raw
    }
}
