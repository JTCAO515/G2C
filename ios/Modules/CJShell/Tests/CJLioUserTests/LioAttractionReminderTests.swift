import Foundation
import Testing
@testable import CJLioUser

/// Local release reminders: computed on the phone in Beijing time, scheduled with the system's
/// local notifications only; nothing is uploaded.
struct LioAttractionReminderTests {
    private let calendar = LioAttractionBookingRule.calendar

    private func beijing(_ y: Int, _ m: Int, _ d: Int, _ h: Int = 0, _ min: Int = 0) -> Date {
        calendar.date(from: DateComponents(year: y, month: m, day: d, hour: h, minute: min))!
    }

    private func rule(_ id: String) -> LioAttractionBookingRule {
        LioAttractionBookingRule.all.first { $0.id == id }!
    }

    @Test func exactReleaseRemindsTenMinutesBeforeTicketsOpen() {
        // Palace Museum: tickets for 5 Dec open on 28 Nov at 20:00 Beijing time.
        let plan = LioAttractionReminder.plan(for: rule("beijing.palace-museum"),
                                              visit: beijing(2026, 12, 5), now: beijing(2026, 11, 25, 9))
        guard case .exact(let opens, let fire) = plan else { Issue.record("\(plan)"); return }
        #expect(opens == beijing(2026, 11, 28, 20))
        #expect(fire == beijing(2026, 11, 28, 19, 50))
    }

    @Test func windowWithoutAStatedTimeRemindsInTheMorningAndSaysTheTimeIsUnknown() {
        // Mao Mausoleum: up to 6 days ahead; the release time is not published.
        let plan = LioAttractionReminder.plan(for: rule("beijing.mao-mausoleum"),
                                              visit: beijing(2026, 12, 9), now: beijing(2026, 11, 25, 9))
        guard case .firstDay(let day, let fire) = plan else { Issue.record("\(plan)"); return }
        #expect(day == beijing(2026, 12, 3))
        #expect(fire == beijing(2026, 12, 3, 9))
    }

    @Test func alreadyOpenOrNoWindowGivesNoReminder() {
        let palace = rule("beijing.palace-museum")
        #expect(LioAttractionReminder.plan(for: palace, visit: beijing(2026, 11, 30), now: beijing(2026, 11, 25, 9))
                == .alreadyOpen)
        #expect(LioAttractionReminder.plan(for: rule("xian.qin-mausoleum-museum"),
                                           visit: beijing(2026, 12, 30), now: beijing(2026, 11, 25)) == .unknownWindow)
        #expect(LioAttractionReminder.plan(for: rule("shanghai.museum-east"),
                                           visit: beijing(2026, 12, 30), now: beijing(2026, 11, 25)) == .notNeeded)
        #expect(LioAttractionReminder.plan(for: palace, visit: beijing(2026, 11, 20), now: beijing(2026, 11, 25))
                == .pastVisit)
    }

    @Test func closedDayIsFlaggedSoTheUserCanPickAnotherDay() {
        // 7 Dec 2026 is a Monday; the Palace Museum is closed on Mondays except public holidays.
        #expect(rule("beijing.palace-museum").closedOn(beijing(2026, 12, 7)))
        #expect(!rule("beijing.palace-museum").closedOn(beijing(2026, 12, 8)))
        #expect(!rule("xian.beilin-museum").closedOn(beijing(2026, 12, 7)))
    }

    @Test func staleRuleGivesNoReminder() {
        let palace = rule("beijing.palace-museum")
        let late = calendar.date(byAdding: .day, value: 60, to: LioAttractionBookingRule.day(palace.checkedOn)!)!
        let visit = calendar.date(byAdding: .day, value: 20, to: late)!
        #expect(LioAttractionReminder.plan(for: palace, visit: visit, now: late) == .stale)
    }

    @Test func notificationIsLocalAndCarriesNoPersonalData() throws {
        let palace = rule("beijing.palace-museum")
        let request = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                                 now: beijing(2026, 11, 25, 9), language: .english))
        #expect(request.id == "g2c.attraction.beijing.palace-museum.2026-12-05")
        #expect(request.fire == beijing(2026, 11, 28, 19, 50))
        #expect(request.title == "The Palace Museum: tickets open at 20:00")
        #expect(request.body.contains("5 Dec") && request.body.contains("official"))
        let zh = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                            now: beijing(2026, 11, 25, 9), language: .chinese))
        #expect(zh.title == "故宫博物院 20:00 放票")
        #expect(zh.body.contains("12月5日") && zh.body.contains("以官方为准"))
    }

    @Test func schedulerAsksOnceThenAddsAndCancels() async throws {
        let center = FakeReminderCenter()
        let scheduler = LioAttractionReminderScheduler(center: center)
        let palace = rule("beijing.palace-museum")
        let request = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                                 now: beijing(2026, 11, 25, 9), language: .chinese))
        #expect(try await scheduler.schedule(request) == .scheduled)
        #expect(await center.added.map(\.id) == [request.id])
        #expect(await scheduler.isScheduled(request.id))
        await scheduler.cancel(request.id)
        #expect(await !scheduler.isScheduled(request.id))

        let denied = FakeReminderCenter(granted: false)
        #expect(try await LioAttractionReminderScheduler(center: denied).schedule(request) == .notAllowed)
        #expect(await denied.added.isEmpty)
    }
}

actor FakeReminderCenter: LioAttractionReminderCenter {
    let granted: Bool
    private(set) var added: [LioAttractionReminder.Request] = []
    private var pending: Set<String> = []
    init(granted: Bool = true) { self.granted = granted }
    func requestAuthorization() async -> Bool { granted }
    func add(_ request: LioAttractionReminder.Request) async throws { added.append(request); pending.insert(request.id) }
    func pendingIDs() async -> Set<String> { pending }
    func remove(_ id: String) async { pending.remove(id) }
}
