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
            return fire > now ? .exact(opens: opens, fire: fire) : .alreadyOpen
        }
        guard let fire = calendar.date(bySettingHour: morningHour, minute: 0, second: 0, of: firstDay) else { return .unknownWindow }
        return fire > now ? .firstDay(day: firstDay, fire: fire) : .alreadyOpen
    }

    static func request(for rule: LioAttractionBookingRule, visit: Date, now: Date, language: LioLanguage) -> Request? {
        let id = "g2c.attraction.\(rule.id).\(dayKey(visit))"
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
