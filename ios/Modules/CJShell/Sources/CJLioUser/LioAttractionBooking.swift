import Foundation

/// 工具：景点预约与放票提醒. One reservation rule per popular sight, read from the venue's
/// official page (or a government page) and dated. A value the source does not state stays nil and
/// is never shown as a number. Booking and payment always happen outside the app.
struct LioAttractionBookingRule: Identifiable, Sendable {
    enum Requirement: Sendable, Equatable {
        /// Real-name booking is required for ordinary individual visitors.
        case required
        /// Booking in advance and buying on site both work.
        case bookingOrOnSite
        /// Ordinary visits need no booking.
        case notRequired
        /// The sources read do not settle it.
        case unknown
    }

    enum Passport: Sendable, Equatable {
        /// The booking rules list a passport as an accepted document.
        case accepted
        /// The rules only say "valid ID"; whether a passport works is not written.
        case notStated
    }

    struct Clock: Sendable, Equatable {
        let hour: Int
        let minute: Int
        var text: String { String(format: "%02d:%02d", hour, minute) }
    }

    struct Channel: Sendable {
        let nameEN: String
        let nameZH: String
        let url: URL
        func name(_ language: LioLanguage) -> String { language.text(nameEN, nameZH) }
    }

    let id: String
    let nameEN: String
    let nameZH: String
    let cityEN: String
    let cityZH: String
    /// Other names a plan may use (both languages, compared case-insensitively and exactly).
    let aliases: [String]
    let requirement: Requirement
    /// The furthest ahead a visit can be booked, counted from the visit day.
    let windowDays: Int?
    /// When tickets for the furthest bookable day go on sale, Beijing time; nil when unpublished.
    let releaseTime: Clock?
    let passport: Passport
    /// Calendar weekdays (1 = Sunday, 2 = Monday …) when the venue is closed; nil when unpublished.
    let closedWeekdays: Set<Int>?
    let openOnPublicHolidays: Bool
    let limitsEN: [String]
    let limitsZH: [String]
    let notesEN: [String]
    let notesZH: [String]
    let officialChannel: Channel
    /// Whether a Klook / Trip.com search is offered. Off where the venue says it authorises no
    /// third-party agents or the ticket is only sold through its own channel.
    let partnerLinks: Bool
    let sources: [URL]
    /// The day the sources were read, `yyyy-MM-dd` in Beijing time.
    let checkedOn: String

    func name(_ language: LioLanguage) -> String { language.text(nameEN, nameZH) }
    func city(_ language: LioLanguage) -> String { language.text(cityEN, cityZH) }
    func limits(_ language: LioLanguage) -> [String] { language == .chinese ? limitsZH : limitsEN }
    func notes(_ language: LioLanguage) -> [String] { language == .chinese ? notesZH : notesEN }
}

extension LioAttractionBookingRule {
    /// Rules older than this are treated as possibly changed: numbers and reminders are withheld.
    static let reviewDays = 30

    static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        calendar.locale = Locale(identifier: "en_US_POSIX")
        return calendar
    }()

    static func day(_ text: String) -> Date? {
        let parts = text.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    static func officialFirst(_ language: LioLanguage) -> String {
        language.text("Rules change often. Always check the official channel before you go.",
                      "规则常有调整，以官方为准，出发前请再核对官方渠道。")
    }

    func isStale(on date: Date) -> Bool {
        guard let checked = Self.day(checkedOn),
              let due = Self.calendar.date(byAdding: .day, value: Self.reviewDays, to: checked) else { return true }
        return date >= due
    }

    func closedOn(_ date: Date) -> Bool {
        closedWeekdays?.contains(Self.calendar.component(.weekday, from: date)) ?? false
    }

    /// One line for itinerary stops and lists. Only numbers the source states appear.
    func summary(_ language: LioLanguage, on date: Date = .now) -> String {
        if isStale(on: date) {
            return language.text("Rules may have changed; check the official channel", "规则可能已变化，请查官方渠道")
        }
        switch requirement {
        case .notRequired:
            return language.text("No booking needed for regular galleries", "常设展免预约")
        case .unknown:
            return language.text("Booking rules not yet listed; check the official channel", "预约规则暂未收录，请查官方渠道")
        case .bookingOrOnSite:
            return language.text("Book ahead or buy on site", "可预约，也可现场购票")
        case .required:
            var parts = [language.text("Booking required", "需实名预约")]
            switch (windowDays, releaseTime) {
            case (let days?, let time?):
                parts.append(language.text("opens \(days) days ahead at \(time.text)", "提前 \(days) 天 \(time.text) 放票"))
            case (let days?, nil):
                parts.append(language.text("up to \(days) days ahead", "最多提前 \(days) 天"))
            default:
                break
            }
            return parts.joined(separator: " · ")
        }
    }

    /// Exact name or alias match only, so a café next to a museum does not inherit its rules.
    static func match(nameZH: String, nameEN: String) -> LioAttractionBookingRule? {
        let keys = [nameZH, nameEN].map(normalized).filter { !$0.isEmpty }
        guard !keys.isEmpty else { return nil }
        return all.first { rule in
            let names = ([rule.nameZH, rule.nameEN] + rule.aliases).map(normalized)
            return keys.contains { names.contains($0) }
        }
    }

    private static func normalized(_ text: String) -> String {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if value.hasPrefix("the ") { value.removeFirst(4) }
        return value.replacingOccurrences(of: "’", with: "'")
    }
}

/// Shown only when the build's Info.plist sets `G2CAttractionBookingEnabled` to the string YES.
enum LioAttractionBookingFeature {
    static let infoKey = "G2CAttractionBookingEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }
}
