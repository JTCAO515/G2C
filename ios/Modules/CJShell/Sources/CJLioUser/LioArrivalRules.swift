import CJStrictJSON
import Foundation

/// A calendar day in Beijing time, written `yyyy-MM-dd` in the rules file. Entry rules end at "24:00 Beijing time",
/// so days, not instants, are compared.
struct LioArrivalDay: Comparable, Hashable, Sendable, CustomStringConvertible, Decodable {
    let year: Int, month: Int, day: Int

    init?(_ text: String) {
        let parts = text.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
              let year = Int(parts[0]), let month = Int(parts[1]), let day = Int(parts[2]) else { return nil }
        var components = DateComponents(year: year, month: month, day: day)
        components.calendar = Self.calendar
        guard components.isValidDate else { return nil }
        self.year = year; self.month = month; self.day = day
    }

    /// The Beijing calendar day of an instant (used for "today").
    init(date: Date) { self.init(date: date, calendar: Self.calendar) }

    /// The day a person picked on their own calendar. A traveller in Tokyo who picks 1 January means 1 January,
    /// even though it is still 31 December in Beijing at that instant.
    init(date: Date, calendar: Calendar) {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        year = parts.year!; month = parts.month!; day = parts.day!
    }

    /// Midnight of this day on the given calendar, for date pickers.
    func date(in calendar: Calendar) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day))!
    }

    init(from decoder: any Decoder) throws {
        let text = try decoder.singleValueContainer().decode(String.self)
        guard let day = Self(text) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "bad day \(text)"))
        }
        self = day
    }

    func adding(days: Int) -> Self {
        Self(date: Self.calendar.date(byAdding: .day, value: days, to: date)!)
    }

    var description: String { String(format: "%04d-%02d-%02d", year, month, day) }

    static func < (lhs: Self, rhs: Self) -> Bool {
        (lhs.year, lhs.month, lhs.day) < (rhs.year, rhs.month, rhs.day)
    }

    private var date: Date { Self.calendar.date(from: DateComponents(year: year, month: month, day: day))! }

    private static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        return calendar
    }()
}

struct LioArrivalText: Decodable, Equatable, Sendable {
    let zh: String
    let en: String
    func text(_ language: LioLanguage) -> String { language.text(en, zh) }
}

struct LioArrivalSource: Decodable, Equatable, Sendable {
    let url: URL
    let publisher: LioArrivalText
    /// The notice's own date, when the page has one. Home pages have none.
    let published: LioArrivalDay?
}

struct LioArrivalPolicy: Decodable, Equatable, Sendable, Identifiable {
    enum Kind: String, Decodable, Sendable { case visaFree = "visa_free", transit }
    let id: String
    let kind: Kind
    let maxStayDays: Int
    let validFrom: LioArrivalDay?
    /// Last day of the published window (24:00 Beijing time); nil when the notice gives no end date.
    let validUntil: LioArrivalDay?
    let checkedAt: LioArrivalDay
    let summary: LioArrivalText
    let notCovered: LioArrivalText
    let sources: [LioArrivalSource]
}

struct LioArrivalCountry: Decodable, Equatable, Sendable {
    enum Otherwise: String, Decodable, Sendable {
        /// The official notices say travellers who do not qualify need a visa.
        case visaRequired = "visa_required"
        /// Not verified against an official source yet; say only "check official sources".
        case checkOfficial = "check_official"
    }
    let code: String
    let name: LioArrivalText
    let policies: [String]
    let otherwise: Otherwise
    let checkedAt: LioArrivalDay

    func sources(in rules: LioArrivalRules) -> [LioArrivalSource] {
        let own = policies.compactMap(rules.policy).flatMap(\.sources)
        return own.isEmpty ? rules.officialFallback : own
    }
}

struct LioArrivalCardNotice: Decodable, Equatable, Sendable {
    let checkedAt: LioArrivalDay
    let summary: LioArrivalText
    let sources: [LioArrivalSource]
}

/// What the traveller tells us; nothing here leaves the device.
struct LioArrivalTrip: Equatable, Sendable {
    var countryCode: String
    var arrival: LioArrivalDay
    var stayDays: Int
    var onwardToThirdCountry: Bool

    /// The day the traveller leaves China. `stayDays` counts calendar days in China, arrival and departure included.
    var lastDay: LioArrivalDay { arrival.adding(days: max(stayDays, 1) - 1) }
}

struct LioArrivalDecision: Equatable, Sendable {
    enum Reason: Equatable, Sendable {
        case notCovered, notVerified, policyEnded, policyMayEndDuringTrip, overdueForReview
        /// One day over the limit as we count it. Official notices count the stay from 00:00 the day after
        /// entry, so this may still fit; we do not decide that for the traveller.
        case stayAtLimit
    }
    enum Outcome: Equatable, Sendable {
        case visaFree(LioArrivalPolicy)
        case transit(LioArrivalPolicy)
        case visaRequired
        case checkOfficial(Reason)
    }
    let outcome: Outcome
    let sources: [LioArrivalSource]
    let checkedAt: LioArrivalDay
}

/// Entry rules bundled as `LioArrivalRules.v1.json`. Every rule names an official source and the day it was
/// checked; the file is rejected as a whole otherwise. Anything not covered, unverified, past its window or overdue for
/// review is answered only with "check official sources" and official links.
struct LioArrivalRules: Decodable, Equatable, Sendable {
    let dataVersion: Int
    let checkedAt: LioArrivalDay
    let reviewEveryDays: Int
    let officialFallback: [LioArrivalSource]
    let policies: [LioArrivalPolicy]
    let countries: [LioArrivalCountry]
    let arrivalCard: LioArrivalCardNotice

    static var bundledURL: URL? { Bundle.module.url(forResource: "LioArrivalRules.v1", withExtension: "json") }

    static func bundled() throws -> Self {
        guard let url = bundledURL else { throw CocoaError(.fileNoSuchFile) }
        return try decode(Data(contentsOf: url))
    }

    static func decode(_ data: Data) throws -> Self {
        var reader = StrictJSONReader<LioArrivalJSONPolicy>(bytes: Array(data))
        try reader.check()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let rules = try decoder.decode(Self.self, from: data)
        guard rules.isComplete else { throw CocoaError(.fileReadCorruptFile) }
        return rules
    }

    /// Chinese government hosts only: `gov.cn` and its subdomains (NIA, MFA and its English site, embassies,
    /// consulates, local governments). HTTPS, no credentials, no custom port.
    static func isOfficial(_ url: URL) -> Bool {
        guard url.scheme == "https", url.user == nil, url.password == nil, url.port == nil,
              let host = url.host?.lowercased() else { return false }
        return host == "gov.cn" || host.hasSuffix(".gov.cn")
    }

    func policy(_ id: String) -> LioArrivalPolicy? { policies.first { $0.id == id } }
    func country(_ code: String) -> LioArrivalCountry? { countries.first { $0.code == code } }

    var reviewDue: LioArrivalDay { checkedAt.adding(days: reviewEveryDays) }
    func isOverdue(today: LioArrivalDay) -> Bool { today > reviewDue }

    func evaluate(_ trip: LioArrivalTrip, today: LioArrivalDay) -> LioArrivalDecision {
        guard let country = country(trip.countryCode) else {
            return LioArrivalDecision(outcome: .checkOfficial(.notCovered), sources: officialFallback,
                                      checkedAt: checkedAt)
        }
        let sources = country.sources(in: self)
        func decision(_ outcome: LioArrivalDecision.Outcome) -> LioArrivalDecision {
            switch outcome {
            case .visaFree(let policy), .transit(let policy):
                // An answer cites the notice it rests on.
                LioArrivalDecision(outcome: outcome, sources: policy.sources, checkedAt: policy.checkedAt)
            default:
                LioArrivalDecision(outcome: outcome, sources: sources, checkedAt: country.checkedAt)
            }
        }
        if isOverdue(today: today) { return decision(.checkOfficial(.overdueForReview)) }

        let own = country.policies.compactMap(policy)
        var ended = false, mayEnd = false, atLimit = false
        for kind in [LioArrivalPolicy.Kind.visaFree, .transit] {
            for policy in own where policy.kind == kind {
                if kind == .transit && !trip.onwardToThirdCountry { continue }
                guard trip.stayDays >= 1, trip.stayDays <= policy.maxStayDays + 1 else { continue }
                if let from = policy.validFrom, trip.arrival < from { continue }
                if let until = policy.validUntil {
                    if trip.arrival > until { ended = true; continue }
                    if trip.lastDay > until { mayEnd = true; continue }
                }
                if trip.stayDays == policy.maxStayDays + 1 { atLimit = true; continue }
                return decision(kind == .visaFree ? .visaFree(policy) : .transit(policy))
            }
        }
        if atLimit { return decision(.checkOfficial(.stayAtLimit)) }
        if mayEnd { return decision(.checkOfficial(.policyMayEndDuringTrip)) }
        if ended { return decision(.checkOfficial(.policyEnded)) }
        switch country.otherwise {
        case .visaRequired: return decision(.visaRequired)
        case .checkOfficial: return decision(.checkOfficial(.notVerified))
        }
    }

    private var isComplete: Bool {
        func valid(_ sources: [LioArrivalSource]) -> Bool {
            !sources.isEmpty && sources.allSatisfy {
                Self.isOfficial($0.url) && !$0.publisher.zh.isEmpty && !$0.publisher.en.isEmpty
            }
        }
        let ids = policies.map(\.id), codes = countries.map(\.code)
        return dataVersion == 1 && reviewEveryDays > 0 && reviewEveryDays <= 90
            && valid(officialFallback) && valid(arrivalCard.sources)
            && !policies.isEmpty && Set(ids).count == ids.count
            && policies.allSatisfy { policy in
                valid(policy.sources) && policy.maxStayDays > 0 && policy.checkedAt <= checkedAt
                    && !policy.summary.zh.isEmpty && !policy.summary.en.isEmpty
                    && !policy.notCovered.zh.isEmpty && !policy.notCovered.en.isEmpty
                    && (policy.validFrom.map { from in policy.validUntil.map { from <= $0 } ?? true } ?? true)
            }
            && !countries.isEmpty && Set(codes).count == codes.count
            && countries.allSatisfy { country in
                country.code.count == 2 && country.code == country.code.uppercased()
                    && country.policies.allSatisfy { ids.contains($0) }
                    && (!country.policies.isEmpty || country.otherwise == .checkOfficial)
                    && country.checkedAt <= checkedAt
            }
    }
}

/// The online arrival card opens only the National Immigration Administration's own page. The address is fixed in
/// code, not in the rules file, so a data update cannot point it elsewhere. Fake sites charge for this free service.
enum LioArrivalCard {
    static let officialURL = URL(string: "https://s.nia.gov.cn/ArrivalCardFillingPC/")!

    static func isOfficial(_ url: URL) -> Bool {
        url.scheme == "https" && url.host == "s.nia.gov.cn" && url.user == nil && url.password == nil
            && url.port == nil && url.query == nil && url.fragment == nil
            && url.path.hasPrefix("/ArrivalCardFillingPC")
    }
}

/// Rejects duplicate keys and other JSON Foundation would accept silently.
private enum LioArrivalJSONPolicy: StrictJSONPolicy {
    static var failure: CocoaError { CocoaError(.fileReadCorruptFile) }
    static var requiresObjectRoot: Bool { true }
    static var maximumDepth: Int { 8 }
}
