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

    /// The signed-in account these tests set reminders for; ids carry its hashed segment (#1922).
    private let scope = LioAttractionReminderScope(account: "6F1B0C52-4F2E-4C58-9E57-0C1B8E6A7D01")

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

    @Test func reminderThatWouldFireAfterTheRuleIsDueForReviewIsNotSet() {
        // Checked 2026-11-25, due for review 30 days later; a February visit would remind in late January.
        let palace = rule("beijing.palace-museum")
        #expect(LioAttractionReminder.plan(for: palace, visit: beijing(2027, 2, 1), now: beijing(2026, 11, 25, 9)) == .stale)
        #expect(LioAttractionReminder.request(for: palace, visit: beijing(2027, 2, 1), now: beijing(2026, 11, 25, 9),
                                              language: .chinese, scope: scope) == nil)
    }

    @Test func firstDayReminderAfterTheReviewDateIsNotSetEither() {
        // Mao Memorial Hall: window only, no release time; a January visit would remind after the review date.
        #expect(LioAttractionReminder.plan(for: rule("beijing.mao-mausoleum"),
                                           visit: beijing(2027, 1, 10), now: beijing(2026, 11, 25)) == .stale)
    }

    @Test func inTheTenMinutesBeforeReleaseItSaysTicketsOpenSoonNotAlreadyOpen() {
        // 28 Nov 19:55: the reminder time has passed but tickets for 5 Dec open at 20:00.
        let plan = LioAttractionReminder.plan(for: rule("beijing.palace-museum"),
                                              visit: beijing(2026, 12, 5), now: beijing(2026, 11, 28, 19, 55))
        #expect(plan == .opensSoon(opens: beijing(2026, 11, 28, 20)))
        #expect(LioAttractionReminder.plan(for: rule("beijing.palace-museum"),
                                           visit: beijing(2026, 12, 5), now: beijing(2026, 11, 28, 20)) == .alreadyOpen)
    }

    @Test func notificationIsLocalAndCarriesNoPersonalData() throws {
        let palace = rule("beijing.palace-museum")
        let request = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                                 now: beijing(2026, 11, 25, 9), language: .english, scope: scope))
        #expect(request.id == "g2c.attraction.\(scope.segment).beijing.palace-museum.2026-12-05")
        #expect(request.fire == beijing(2026, 11, 28, 19, 50))
        #expect(request.title == "The Palace Museum: tickets open at 20:00")
        #expect(request.body.contains("5 Dec") && request.body.contains("official"))
        let zh = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                            now: beijing(2026, 11, 25, 9), language: .chinese, scope: scope))
        #expect(zh.title == "故宫博物院 20:00 放票")
        #expect(zh.body.contains("12月5日") && zh.body.contains("以官方为准"))
    }

    @Test func scheduledRemindersCanBeReadWithoutChangingThem() async throws {
        // The trip home page reads what is set; it never adds, removes or asks for permission.
        let center = FakeReminderCenter(granted: false, pending: [
            scope.prefix + "beijing.palace-museum.2026-12-05",
            scope.prefix + "beijing.mao-mausoleum.2026-12-09",
            scope.prefix + "nowhere.unknown-sight.2026-12-01",   // rule no longer in the table
            scope.prefix + "beijing.palace-museum.2026-13-40",   // not a date
            "g2c.other-feature.2026-12-01",                      // another feature's notification
        ])
        let items = await LioAttractionReminderScheduler(center: center, scope: scope).scheduled()
        #expect(items.map(\.ruleID) == ["beijing.palace-museum", "beijing.mao-mausoleum"], "sorted by visit day")
        #expect(items.map(\.visit) == [beijing(2026, 12, 5), beijing(2026, 12, 9)])
        #expect(items[0].id == scope.prefix + "beijing.palace-museum.2026-12-05")
        #expect(items[0].rule?.nameZH == "故宫博物院")
        #expect(items[0].plan(now: beijing(2026, 11, 25, 9)) == .exact(opens: beijing(2026, 11, 28, 20), fire: beijing(2026, 11, 28, 19, 50)))
        #expect(items[1].plan(now: beijing(2026, 11, 25, 9)) == .firstDay(day: beijing(2026, 12, 3), fire: beijing(2026, 12, 3, 9)))
        #expect(await center.added.isEmpty)
        #expect(await center.authorizationRequests == 0, "reading never asks for permission")
        #expect(await center.pendingIDs().count == 5, "reading removes nothing")
    }

    @Test func reminderIDsRoundTrip() throws {
        let palace = rule("beijing.palace-museum")
        let request = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                                 now: beijing(2026, 11, 25, 9), language: .english, scope: scope))
        // Other features (the trip home page) build the same identifier through this function.
        #expect(LioAttractionReminder.reminderID(for: palace, visit: beijing(2026, 12, 5), scope: scope) == request.id)
        #expect(LioAttractionReminder.reminderID(for: palace, visit: beijing(2026, 12, 5, 23, 59), scope: scope) == request.id,
                "any time on the visit day gives the same identifier")
        let item = try #require(LioAttractionReminderItem(id: request.id))
        #expect(item.ruleID == palace.id && item.visit == beijing(2026, 12, 5))
        #expect(LioAttractionReminderItem(id: "g2c.attraction.") == nil)
        #expect(LioAttractionReminderItem(id: "g2c.attraction.beijing.palace-museum") == nil)
    }

    @Test func schedulerAsksOnceThenAddsAndCancels() async throws {
        let center = FakeReminderCenter()
        let scheduler = LioAttractionReminderScheduler(center: center, scope: scope)
        let palace = rule("beijing.palace-museum")
        let request = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5),
                                                                 now: beijing(2026, 11, 25, 9), language: .chinese, scope: scope))
        #expect(try await scheduler.schedule(request) == .scheduled)
        #expect(await center.added.map(\.id) == [request.id])
        #expect(await scheduler.isScheduled(request.id))
        await scheduler.cancel(request.id)
        #expect(await !scheduler.isScheduled(request.id))

        let denied = FakeReminderCenter(granted: false)
        #expect(try await LioAttractionReminderScheduler(center: denied, scope: scope).schedule(request) == .notAllowed)
        #expect(await denied.added.isEmpty)
    }
}

actor FakeReminderCenter: LioAttractionReminderCenter {
    let granted: Bool
    private(set) var added: [LioAttractionReminder.Request] = []
    private(set) var authorizationRequests = 0
    private var pending: Set<String>
    init(granted: Bool = true, pending: Set<String> = []) { self.granted = granted; self.pending = pending }
    func requestAuthorization() async -> Bool { authorizationRequests += 1; return granted }
    func add(_ request: LioAttractionReminder.Request) async throws { added.append(request); pending.insert(request.id) }
    func pendingIDs() async -> Set<String> { pending }
    func remove(_ id: String) async { pending.remove(id) }
}
