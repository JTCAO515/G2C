import Foundation

/// Local "tickets open soon" reminders. Computed on the phone in Beijing time and scheduled with
/// the system's local notifications; nothing leaves the device.
enum LioAttractionReminder {
    /// How long before an exact release time the reminder fires.
    static let leadMinutes = 10
    /// When the release time is unpublished, remind at this Beijing hour on the first bookable day.
    static let morningHour = 9

    enum Plan: Equatable, Sendable {
        /// Tickets for the visit open at `opens`; remind at `fire`.
        case exact(opens: Date, fire: Date)
        /// Booking opens on `day`, at a time the venue does not publish; remind at `fire`.
        case firstDay(day: Date, fire: Date)
        /// The reminder time has passed but tickets open at `opens`, within the next few minutes.
        case opensSoon(opens: Date)
        case alreadyOpen, unknownWindow, notNeeded, pastVisit, stale
    }

    struct Request: Equatable, Sendable {
        let id: String
        let fire: Date
        let title: String
        let body: String
    }

    static func plan(for rule: LioAttractionBookingRule, visit: Date, now: Date) -> Plan {
        let calendar = LioAttractionBookingRule.calendar
        let visitDay = calendar.startOfDay(for: visit)
        if visitDay < calendar.startOfDay(for: now) { return .pastVisit }
        if rule.isStale(on: now) { return .stale }
        switch rule.requirement {
        case .notRequired: return .notNeeded
        case .unknown: return .unknownWindow
        case .required, .bookingOrOnSite: break
        }
        guard let window = rule.windowDays,
              let firstDay = calendar.date(byAdding: .day, value: -window, to: visitDay) else { return .unknownWindow }
        if let time = rule.releaseTime {
            guard let opens = calendar.date(bySettingHour: time.hour, minute: time.minute, second: 0, of: firstDay),
                  let fire = calendar.date(byAdding: .minute, value: -leadMinutes, to: opens) else { return .unknownWindow }
            if opens <= now { return .alreadyOpen }
            if fire <= now { return .opensSoon(opens: opens) }
            return rule.isStale(on: fire) ? .stale : .exact(opens: opens, fire: fire)
        }
        guard let fire = calendar.date(bySettingHour: morningHour, minute: 0, second: 0, of: firstDay) else { return .unknownWindow }
        if fire <= now { return .alreadyOpen }
        // A reminder must not fire after the rule is due for review: it would repeat a number that may have changed.
        return rule.isStale(on: fire) ? .stale : .firstDay(day: firstDay, fire: fire)
    }

    static func request(for rule: LioAttractionBookingRule, visit: Date, now: Date, language: LioLanguage) -> Request? {
        let id = reminderID(for: rule, visit: visit)
        let day = visitText(visit, language)
        let check = language.text("Book on the official channel; check the official rules.", "请到官方渠道预约，以官方为准。")
        switch plan(for: rule, visit: visit, now: now) {
        case .exact(let opens, let fire):
            let time = LioAttractionBookingRule.Clock(hour: LioAttractionBookingRule.calendar.component(.hour, from: opens),
                                                      minute: LioAttractionBookingRule.calendar.component(.minute, from: opens)).text
            return Request(id: id, fire: fire,
                           title: language.text("\(rule.nameEN): tickets open at \(time)", "\(rule.nameZH) \(time) 放票"),
                           body: language.text("Tickets for your visit on \(day) open at \(time) Beijing time. \(check)",
                                               "\(day)的门票北京时间 \(time) 开放预约。\(check)"))
        case .firstDay(_, let fire):
            return Request(id: id, fire: fire,
                           title: language.text("\(rule.nameEN): booking opens today", "\(rule.nameZH) 今天可以预约"),
                           body: language.text("Today is the first day you can book your visit on \(day). The release time is not published. \(check)",
                                               "今天起可以预约\(day)的参观，官方未公布具体放票时间。\(check)"))
        default:
            return nil
        }
    }

    /// The notification identifier for a sight and visit day, `g2c.attraction.<rule id>.<yyyy-MM-dd>`.
    /// Other features use it to tell whether a reminder is set, instead of building the format themselves.
    static func reminderID(for rule: LioAttractionBookingRule, visit: Date) -> String {
        LioAttractionReminderItem.prefix + "\(rule.id).\(dayKey(visit))"
    }

    static func dayKey(_ date: Date) -> String {
        let c = LioAttractionBookingRule.calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }

    static func visitText(_ date: Date, _ language: LioLanguage) -> String {
        let c = LioAttractionBookingRule.calendar.dateComponents([.month, .day], from: date)
        let month = c.month ?? 1, day = c.day ?? 1
        let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return language.text("\(day) \(months[max(0, min(11, month - 1))])", "\(month)月\(day)日")
    }
}

/// One reminder that is set, read back from its notification identifier
/// `g2c.attraction.<rule id>.<yyyy-MM-dd>`; nothing else is stored.
struct LioAttractionReminderItem: Equatable, Sendable {
    static let prefix = "g2c.attraction."
    let id: String
    let ruleID: String
    /// The visit day, midnight Beijing time.
    let visit: Date

    init?(id: String) {
        guard id.hasPrefix(Self.prefix) else { return nil }
        let rest = id.dropFirst(Self.prefix.count)
        guard let dot = rest.lastIndex(of: ".") else { return nil }
        let ruleID = String(rest[..<dot]), day = String(rest[rest.index(after: dot)...])
        guard !ruleID.isEmpty, let visit = LioAttractionBookingRule.day(day),
              LioAttractionReminder.dayKey(visit) == day else { return nil }
        (self.id, self.ruleID, self.visit) = (id, ruleID, visit)
    }

    var rule: LioAttractionBookingRule? { LioAttractionBookingRule.all.first { $0.id == ruleID } }

    /// When tickets open and when the reminder fires, as of `now`.
    func plan(now: Date) -> LioAttractionReminder.Plan? {
        rule.map { LioAttractionReminder.plan(for: $0, visit: visit, now: now) }
    }
}

/// The system notification centre, behind a protocol so scheduling can be tested without it.
protocol LioAttractionReminderCenter: Sendable {
    func requestAuthorization() async -> Bool
    func add(_ request: LioAttractionReminder.Request) async throws
    func pendingIDs() async -> Set<String>
    func remove(_ id: String) async
}

struct LioAttractionReminderScheduler: Sendable {
    enum Outcome: Equatable, Sendable { case scheduled, notAllowed }
    let center: any LioAttractionReminderCenter

    func schedule(_ request: LioAttractionReminder.Request) async throws -> Outcome {
        guard await center.requestAuthorization() else { return .notAllowed }
        try await center.add(request)
        return .scheduled
    }

    func isScheduled(_ id: String) async -> Bool { await center.pendingIDs().contains(id) }

    /// Read-only view of the reminders set on this phone, soonest visit first, for the trip home page.
    /// It neither adds nor removes anything and does not ask for permission.
    func scheduled() async -> [LioAttractionReminderItem] {
        await center.pendingIDs().compactMap(LioAttractionReminderItem.init(id:))
            .filter { $0.rule != nil }
            .sorted { ($0.visit, $0.ruleID) < ($1.visit, $1.ruleID) }
    }

    func cancel(_ id: String) async { await center.remove(id) }
}

#if canImport(UserNotifications)
import UserNotifications

/// Local notifications only: no push token, no server, nothing uploaded.
struct LioSystemReminderCenter: LioAttractionReminderCenter {
    private var center: UNUserNotificationCenter { .current() }

    func requestAuthorization() async -> Bool {
        (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
    }

    func add(_ request: LioAttractionReminder.Request) async throws {
        let content = UNMutableNotificationContent()
        content.title = request.title
        content.body = request.body
        content.sound = .default
        let parts = LioAttractionBookingRule.calendar.dateComponents(in: LioAttractionBookingRule.calendar.timeZone, from: request.fire)
        var when = DateComponents()
        when.calendar = LioAttractionBookingRule.calendar
        when.timeZone = LioAttractionBookingRule.calendar.timeZone
        (when.year, when.month, when.day, when.hour, when.minute) = (parts.year, parts.month, parts.day, parts.hour, parts.minute)
        let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: false)
        try await center.add(UNNotificationRequest(identifier: request.id, content: content, trigger: trigger))
    }

    func pendingIDs() async -> Set<String> {
        Set(await center.pendingNotificationRequests().map(\.identifier))
    }

    func remove(_ id: String) async {
        center.removePendingNotificationRequests(withIdentifiers: [id])
    }
}
#endif
