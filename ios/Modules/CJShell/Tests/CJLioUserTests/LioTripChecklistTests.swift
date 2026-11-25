import Foundation
import Testing
@testable import CJLioUser

/// Trip home phase 1 (T2): tasks come only from sourced rules and the tools' own state on this phone,
/// with an injected clock. Each test row names the rule it covers in trip-plan.md.
struct LioTripChecklistTests {
    private static let shanghai = TimeZone(identifier: "Asia/Shanghai")!
    private static let losAngeles = TimeZone(identifier: "America/Los_Angeles")!

    private static func at(_ text: String, _ timeZone: TimeZone = shanghai) -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.date(from: text)!
    }

    private static func day(_ text: String) -> LioTripDay { LioTripDay(text)! }

    private static func plan(_ id: String = "plan-1", start: String? = "2026-12-08",
                             days: [[(String, String?)]]) -> LioPlanSummary {
        LioPlanSummary(tripID: id, tripVersion: 1, title: "Beijing", startDate: start, undated: start == nil,
                       days: days.enumerated().map { index, items in
            LioPlanSummary.Day(number: index + 1, date: nil, items: items.enumerated().map { position, item in
                LioPlanSummary.Item(id: "\(index)-\(position)", label: item.0, startTime: item.1, endTime: nil, fixed: nil)
            })
        })
    }

    /// Arrives 8 Dec 2026 for 7 days (last day 14 Dec), first city Beijing.
    private static func profile(arrival: String? = "2026-12-08", stayDays: Int? = 7, planID: String? = nil) -> LioTripProfile {
        LioTripProfile(arrival: arrival.map(day), stayDays: stayDays, cityID: "beijing", planID: planID,
                       startedAt: at("2026-11-25 09:00"))
    }

    private static let beijingPlan = plan(days: [
        [("Hotel check-in", "15:00")],
        [("故宫博物院", "09:00"), ("景山公园", "14:00"), ("王府井", "18:30")],
        [("八达岭长城", "08:00")],
        [("故宫角楼咖啡", "10:00"), ("中国国家博物馆", "13:00")]
    ])

    private static func everything(_ now: Date, _ timeZone: TimeZone = shanghai,
                                   ticks: LioTripTicks = .init()) -> LioTripChecklistInput {
        LioTripChecklistInput(now: now, timeZone: timeZone, profile: profile(), plans: [beijingPlan], ticks: ticks,
                              entry: .visaFree(maxDays: 30, checkedOn: "2026-11-25"),
                              arrivalChecklist: .init(done: [], total: 6), hotelSaved: false, showCards: true,
                              attractionBooking: true)
    }

    // MARK: - Phase

    @Test(arguments: [
        ("2026-12-01", LioTripPhase.beforeTrip(daysToGo: 7)),
        ("2026-12-07", .beforeTrip(daysToGo: 1)),
        ("2026-12-08", .arrivalDay),
        ("2026-12-09", .inChina(day: 2)),
        ("2026-12-13", .inChina(day: 6)),
        ("2026-12-14", .departureDay(day: 7)),
        ("2026-12-15", .ended)
    ])
    func phaseFollowsTheTripDays(today: String, expected: LioTripPhase) {
        #expect(LioTripChecklist.phase(arrival: Self.day("2026-12-08"), lastDay: Self.day("2026-12-14"),
                                       today: Self.day(today)) == expected)
    }

    @Test func undatedTripsAreBeforeTheTripAndOpenEndedTripsNeverEnd() {
        #expect(LioTripChecklist.phase(arrival: nil, lastDay: nil, today: Self.day("2026-12-08")) == .beforeTrip(daysToGo: nil))
        #expect(LioTripChecklist.phase(arrival: Self.day("2026-12-08"), lastDay: nil, today: Self.day("2027-03-01"))
                == .inChina(day: 84))
        // A one-day trip: its only day is the arrival day.
        #expect(LioTripChecklist.phase(arrival: Self.day("2026-12-08"), lastDay: Self.day("2026-12-08"),
                                       today: Self.day("2026-12-08")) == .arrivalDay)
    }

    @Test func todayIsThePhonesOwnDate() {
        // 7 Dec 18:00 in Los Angeles is already 8 Dec in Beijing; the traveller has not flown yet.
        let input = LioTripChecklistInput(now: Self.at("2026-12-07 18:00", Self.losAngeles), timeZone: Self.losAngeles,
                                          profile: Self.profile())
        #expect(LioTripChecklist(input).phase == .beforeTrip(daysToGo: 1))
    }

    // MARK: - Without a trip

    @Test func noProfileAndNoPlanMeansNoTripAndNoTasks() {
        let list = LioTripChecklist(.init(now: Self.at("2026-11-26 10:00"), entry: .missingDetails,
                                          arrivalChecklist: .init(done: [], total: 6), hotelSaved: false,
                                          showCards: true, attractionBooking: true))
        #expect(!list.hasTrip)
        #expect(list.tasks.isEmpty)
        #expect(list.now == nil)
        #expect(list.schedule.isEmpty)
    }

    @Test func skippingTheQuestionsGivesTheGeneralList() {
        // "Just get ready" without answers: a profile with no dates, no city.
        let profile = LioTripProfile(arrival: nil, stayDays: nil, cityID: nil, startedAt: Self.at("2026-11-25 09:00"))
        let list = LioTripChecklist(.init(now: Self.at("2026-11-26 10:00"), profile: profile, entry: .missingDetails,
                                          arrivalChecklist: .init(done: [], total: 6), hotelSaved: false,
                                          showCards: true, attractionBooking: true))
        #expect(list.hasTrip)
        #expect(list.phase == .beforeTrip(daysToGo: nil))
        #expect(list.tasks.map(\.key) == ["entry", "arrival-card", "payment", "internet", "hotel", "medical-card",
                                          "landing", "check-in"])
        #expect(list.tasks.first?.kind == .entry(.missingDetails))
        #expect(list.schedule.isEmpty)
    }

    // MARK: - Each task follows its tool's switch

    @Test func withEveryToolOffOnlyPaymentAndTheMedicalCardRemain() {
        let list = LioTripChecklist(.init(now: Self.at("2026-11-26 10:00"), profile: Self.profile(), plans: [Self.beijingPlan]))
        #expect(list.tasks.map(\.key) == ["payment", "medical-card"])
        #expect(list.tasks.allSatisfy { $0.tick == .manual && $0.done == .open && $0.stage == .beforeTrip })
    }

    @Test func withEveryToolOnTheSeedTableIsInOrder() {
        let list = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00")))
        #expect(list.tasks.map(\.key) == [
            "entry", "arrival-card", "payment", "internet", "hotel",
            "booking.beijing.palace-museum.2026-12-09", "booking.beijing.national-museum.2026-12-11",
            "medical-card", "landing", "check-in"
        ])
        #expect(list.tasks(in: .arrivalDay).map(\.key) == ["landing", "check-in"])
        #expect(list.tasks(in: .inChina).isEmpty)
        #expect(list.tasks(in: .departure).isEmpty)
    }

    // MARK: - Entry (Arrival Mode's sourced rules)

    @Test(arguments: [
        (LioTripEntryStatus.visaFree(maxDays: 30, checkedOn: "2026-11-25"), LioTripTask.Done.automatic, LioTripTask.Tick.statusOnly),
        (.transit(maxDays: 10, checkedOn: "2026-11-25"), .open, .manual),
        (.visaRequired(checkedOn: "2026-11-25"), .open, .manual),
        (.officialOnly, .open, .manual),
        (.missingDetails, .open, .manual)
    ])
    func onlyAVisaFreeDecisionCompletesEntryByItself(status: LioTripEntryStatus, done: LioTripTask.Done,
                                                     tick: LioTripTask.Tick) {
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        input.entry = status
        let entry = LioTripChecklist(input).tasks.first { $0.key == "entry" }
        #expect(entry?.kind == .entry(status))
        #expect(entry?.done == done)
        #expect(entry?.tick == tick)
    }

    @Test func aManualTickIsKeptByKeyAcrossRegeneration() {
        var ticks = LioTripTicks()
        ticks.set("entry", done: true, at: Self.at("2026-11-26 10:00"))
        ticks.set("payment", done: true, at: Self.at("2026-11-26 10:00"))
        var input = Self.everything(Self.at("2026-11-26 10:00"), ticks: ticks)
        input.entry = .visaRequired(checkedOn: "2026-11-25")
        let tasks = LioTripChecklist(input).tasks
        #expect(tasks.first { $0.key == "entry" }?.done == .ticked)
        #expect(tasks.first { $0.key == "payment" }?.done == .ticked)
        #expect(tasks.first { $0.key == "arrival-card" }?.done == .open)
    }

    // MARK: - Arrival Mode's checklist and Back to Hotel

    @Test func internetAndLandingFollowArrivalModesTicks() {
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        input.arrivalChecklist = .init(done: ["internet"], total: 6)
        var tasks = LioTripChecklist(input).tasks
        #expect(tasks.first { $0.key == "internet" }?.done == .followsArrival)
        #expect(tasks.first { $0.key == "internet" }?.tick == .arrivalStep("internet"))
        #expect(tasks.first { $0.key == "landing" }?.done == .open)
        #expect(tasks.first { $0.key == "landing" }?.tick == .arrivalStep("taxi"))
        input.arrivalChecklist = .init(done: ["internet", "taxi"], total: 6)
        tasks = LioTripChecklist(input).tasks
        #expect(tasks.first { $0.key == "landing" }?.done == .followsArrival)
    }

    @Test func aSavedHotelCompletesTheHotelTask() {
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        #expect(LioTripChecklist(input).tasks.first { $0.key == "hotel" }?.done == .open)
        input.hotelSaved = true
        let hotel = LioTripChecklist(input).tasks.first { $0.key == "hotel" }
        #expect(hotel?.done == .automatic)
        #expect(hotel?.tick == .statusOnly)
    }

    // MARK: - Attraction booking (the rule table; exact names only)

    @Test func bookingTasksComeOnlyFromExactRuleMatchesThatNeedBooking() {
        let list = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00")))
        let booking = list.tasks.compactMap { task -> String? in
            if case .booking(let id, _, _, _) = task.kind { return id }
            return nil
        }
        // 故宫角楼咖啡 is a café, not the museum; Badaling can be bought on site, so it is no task.
        #expect(booking == ["beijing.palace-museum", "beijing.national-museum"])
    }

    @Test func releaseTimesComeFromTheRuleTable() throws {
        let list = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00")))
        let palace = try #require(list.tasks.first { $0.key == "booking.beijing.palace-museum.2026-12-09" })
        // The Palace Museum opens 7 days ahead at 20:00 Beijing time: 2 Dec, 20:00 for a visit on 9 Dec.
        #expect(palace.kind == .booking(ruleID: "beijing.palace-museum", visit: Self.day("2026-12-09"),
                                        timing: .opensAt(Self.at("2026-12-02 20:00")), reminderSet: false))
        #expect(palace.stage == .beforeTrip)
        #expect(palace.tick == .manual)
    }

    @Test func aReminderSetInAttractionBookingShowsOnTheTask() {
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        input.scheduledReminders = ["g2c.attraction.beijing.palace-museum.2026-12-09"]
        let palace = LioTripChecklist(input).tasks.first { $0.key == "booking.beijing.palace-museum.2026-12-09" }
        guard case .booking(_, _, _, let reminderSet)? = palace?.kind else { Issue.record("no booking"); return }
        #expect(reminderSet)
        let rule = LioAttractionBookingRule.match(nameZH: "故宫博物院", nameEN: "")!
        #expect(LioTripChecklist.reminderID(rule: rule, visit: Self.day("2026-12-09"))
                == LioAttractionReminder.request(for: rule, visit: Self.day("2026-12-09").start(in: Self.shanghai),
                                                 now: Self.at("2026-11-26 10:00"), language: .english)?.id)
    }

    @Test func releasesDuringTheTripAreGroupedInChina() throws {
        // Arriving 1 Dec: the 9 Dec Palace Museum release (2 Dec 20:00) falls inside the trip.
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        input.profile = Self.profile(arrival: "2026-12-01", stayDays: 14)
        let palace = try #require(LioTripChecklist(input).tasks.first { $0.key == "booking.beijing.palace-museum.2026-12-09" })
        #expect(palace.stage == .inChina)
    }

    @Test func openWindowsPastVisitsAndStaleRules() throws {
        // On 5 Dec the 9 Dec tickets are already on sale.
        var list = LioTripChecklist(Self.everything(Self.at("2026-12-05 10:00")))
        let palace = try #require(list.tasks.first { $0.key == "booking.beijing.palace-museum.2026-12-09" })
        guard case .booking(_, _, let timing, _) = palace.kind else { Issue.record("no booking"); return }
        #expect(timing == .openNow)
        // On 10 Dec the 9 Dec visit is over: the task goes.
        list = LioTripChecklist(Self.everything(Self.at("2026-12-10 10:00")))
        #expect(!list.tasks.contains { $0.key == "booking.beijing.palace-museum.2026-12-09" })
        // A rule past its 30-day review (checked 25 Nov) shows no numbers, only the official channel.
        var later = Self.everything(Self.at("2026-12-26 10:00"))
        later.profile = Self.profile(arrival: "2027-01-05")
        later.plans = [Self.plan(start: "2027-01-05", days: [[("故宫博物院", "09:00")]])]
        let stale = try #require(LioTripChecklist(later).tasks.first { $0.key == "booking.beijing.palace-museum.2027-01-05" })
        #expect(stale.kind == .booking(ruleID: "beijing.palace-museum", visit: Self.day("2027-01-05"),
                                       timing: .checkOfficial, reminderSet: false))
    }

    @Test func anUndatedPlanHasNoVisitDayToCountFrom() throws {
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        input.profile = Self.profile(arrival: nil, stayDays: nil)
        input.plans = [Self.plan(start: nil, days: [[("故宫", "09:00")]])]
        let task = try #require(LioTripChecklist(input).tasks.first { $0.key == "booking.beijing.palace-museum.undated" })
        #expect(task.kind == .booking(ruleID: "beijing.palace-museum", visit: nil, timing: .noVisitDay, reminderSet: false))
        input.now = Self.at("2026-12-26 10:00")
        let stale = try #require(LioTripChecklist(input).tasks.first { $0.key == "booking.beijing.palace-museum.undated" })
        #expect(stale.kind == .booking(ruleID: "beijing.palace-museum", visit: nil, timing: .checkOfficial, reminderSet: false))
    }

    @Test func theSameSightTwiceOnOneDayIsOneTask() {
        var input = Self.everything(Self.at("2026-11-26 10:00"))
        input.plans = [Self.plan(days: [[("故宫博物院", "09:00"), ("The Palace Museum", "15:00")]])]
        #expect(LioTripChecklist(input).tasks.filter { $0.key.hasPrefix("booking.") }.count == 1)
    }

    // MARK: - Which plan is this trip

    @Test func thePickedPlanThenDatesThenTheNewest() {
        let today = Self.day("2026-11-26")
        let december = Self.plan("dec", start: "2026-12-09", days: [[], []])
        let january = Self.plan("jan", start: "2027-01-05", days: [[]])
        let undated = Self.plan("undated", start: nil, days: [[]])
        let past = Self.plan("past", start: "2026-10-01", days: [[]])
        let plans = [undated, january, december, past]
        #expect(LioTripChecklist.currentPlan(profile: Self.profile(planID: "jan"), plans: plans, today: today)?.tripID == "jan")
        #expect(LioTripChecklist.currentPlan(profile: Self.profile(), plans: plans, today: today)?.tripID == "dec")
        // Dates that match no dated plan take the newest undated one, and nothing when there is none.
        #expect(LioTripChecklist.currentPlan(profile: Self.profile(arrival: "2027-03-01"), plans: plans, today: today)?.tripID == "undated")
        #expect(LioTripChecklist.currentPlan(profile: Self.profile(arrival: "2027-03-01"), plans: [january, december, past],
                                             today: today) == nil)
        #expect(LioTripChecklist.currentPlan(profile: nil, plans: plans, today: today)?.tripID == "dec")
        #expect(LioTripChecklist.currentPlan(profile: nil, plans: [undated, past], today: today)?.tripID == "undated")
        #expect(LioTripChecklist.currentPlan(profile: nil, plans: [past], today: today)?.tripID == "past")
        #expect(LioTripChecklist.currentPlan(profile: Self.profile(arrival: nil, stayDays: nil), plans: [past, undated],
                                             today: today)?.tripID == "undated")
    }

    @Test func aDatedPlanAloneIsATrip() {
        let list = LioTripChecklist(.init(now: Self.at("2026-12-09 10:00"), plans: [Self.beijingPlan]))
        #expect(list.hasTrip)
        #expect(list.arrival == Self.day("2026-12-08"))
        #expect(list.lastDay == Self.day("2026-12-11"))
        #expect(list.phase == .inChina(day: 2))
    }

    // MARK: - The "Now" card

    @Test func beforeTheTripTheNextTaskIsAnUrgentBookingElseTheFirstOpenOne() {
        // 26 Nov: the first release is 2 Dec (6 days away), so the table's first open task leads.
        var ticks = LioTripTicks()
        ticks.set("arrival-card", done: true, at: Self.at("2026-11-26 09:00"))
        var list = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00"), ticks: ticks))
        guard case .prepare(let done, let total, let next) = list.now else { Issue.record("\(String(describing: list.now))"); return }
        #expect(done == 2) // entry (visa-free) and the arrival card
        #expect(total == 8)
        #expect(next?.key == "payment")
        // 30 Nov: the 2 Dec release is within three days and comes first.
        list = LioTripChecklist(Self.everything(Self.at("2026-11-30 10:00"), ticks: ticks))
        guard case .prepare(_, _, let urgent) = list.now else { Issue.record("not preparing"); return }
        #expect(urgent?.key == "booking.beijing.palace-museum.2026-12-09")
    }

    @Test func everythingReadyCountsDownToTheTrip() {
        let input = LioTripChecklistInput(now: Self.at("2026-12-01 10:00"), profile: Self.profile(),
                                          ticks: LioTripTicks(done: ["payment": .now, "medical-card": .now]))
        #expect(LioTripChecklist(input).now == .ready(daysToGo: 7))
    }

    @Test func arrivalDayShowsArrivalModeOrTheDaysOwnTasks() {
        var input = Self.everything(Self.at("2026-12-08 16:00"))
        input.arrivalChecklist = .init(done: ["entry", "payment"], total: 6)
        #expect(LioTripChecklist(input).now == .landing(done: 2, total: 6))
        input.arrivalChecklist = nil
        input.entry = nil
        guard case .landingTasks(_, let total, let next) = LioTripChecklist(input).now else { Issue.record("not landing"); return }
        // Payment, hotel, medical card, check-in; the bookings still ahead now sit with the days in China.
        #expect(total == 4)
        #expect(next?.key == "payment")
    }

    @Test(arguments: [
        ("2026-12-09 08:00", LioTripNow.today(day: 2, next: .init(name: "故宫博物院", time: "09:00"), remaining: 3)),
        ("2026-12-09 12:00", .today(day: 2, next: .init(name: "景山公园", time: "14:00"), remaining: 2)),
        ("2026-12-09 18:45", .backToHotel(saved: false)),
        ("2026-12-09 19:00", .backToHotel(saved: false)),
        ("2026-12-10 04:59", .backToHotel(saved: false)),
        ("2026-12-10 05:00", .today(day: 3, next: .init(name: "八达岭长城", time: "08:00"), remaining: 1)),
        ("2026-12-12 10:00", .today(day: 5, next: nil, remaining: 0)),
        ("2026-12-14 20:00", .today(day: 7, next: nil, remaining: 0)),
        ("2026-12-15 10:00", .ended(days: 7))
    ])
    func inChinaTheCardFollowsTheDayAndTheClock(now: String, expected: LioTripNow) {
        #expect(LioTripChecklist(Self.everything(Self.at(now))).now == expected)
    }

    @Test func withoutBackToHotelTheEveningKeepsTodaysPlan() {
        var input = Self.everything(Self.at("2026-12-09 20:00"))
        input.hotelSaved = nil
        #expect(LioTripChecklist(input).now == .today(day: 2, next: nil, remaining: 0))
        input.hotelSaved = true
        #expect(LioTripChecklist(input).now == .backToHotel(saved: true))
    }

    // MARK: - Day by day

    @Test func scheduleShowsTheFirstTwoDaysThenTodayAndTomorrow() {
        var list = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00")))
        #expect(list.schedule.map(\.number) == [1, 2])
        #expect(list.schedule.map(\.date) == [Self.day("2026-12-08"), Self.day("2026-12-09")])
        #expect(list.moreDays == 2)
        list = LioTripChecklist(Self.everything(Self.at("2026-12-10 10:00")))
        #expect(list.schedule.map(\.number) == [3, 4])
        #expect(list.schedule.first?.isToday == true)
        #expect(list.schedule.first?.stops == [.init(name: "八达岭长城", time: "08:00")])
        list = LioTripChecklist(Self.everything(Self.at("2026-12-11 10:00")))
        #expect(list.schedule.map(\.number) == [4])
        list = LioTripChecklist(Self.everything(Self.at("2026-12-20 10:00")))
        #expect(list.schedule.isEmpty)
    }

    @Test func anUndatedPlanIsShownByDayNumberWithoutDates() {
        var input = Self.everything(Self.at("2026-12-09 10:00"))
        input.plans = [Self.plan(start: nil, days: [[("A", nil)], [("B", nil)], [("C", nil)]])]
        let list = LioTripChecklist(input)
        #expect(list.schedule.map(\.number) == [2, 3])
        #expect(list.schedule.map(\.date) == [nil, nil])
        #expect(list.schedule.first?.isToday == true)
        #expect(list.now == .today(day: 2, next: .init(name: "B", time: nil), remaining: 1))
    }

    // MARK: - Page order (JT 2026-11-25)

    @Test func inChinaTodaysPlanComesFirstAndEarlierStagesFoldIntoOneLine() {
        var list = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00")))
        #expect(!list.showsScheduleFirst)
        #expect(list.pastTasks.isEmpty)
        list = LioTripChecklist(Self.everything(Self.at("2026-12-08 16:00")))
        #expect(!list.showsScheduleFirst)
        #expect(list.pastTasks.allSatisfy { $0.stage == .beforeTrip } && !list.pastTasks.isEmpty)
        list = LioTripChecklist(Self.everything(Self.at("2026-12-09 12:00")))
        #expect(list.showsScheduleFirst)
        #expect(Set(list.pastTasks.map(\.stage)) == [.beforeTrip, .arrivalDay])
        // Without a plan there is no day to put first.
        var noPlan = Self.everything(Self.at("2026-12-09 12:00"))
        noPlan.plans = []
        #expect(!LioTripChecklist(noPlan).showsScheduleFirst)
    }

    @Test func thePastLineSaysWhatIsLeftAndWhatIsDone() {
        #expect(LioTripHomeCopy.pastSummary(open: 1, done: 8, .chinese) == "还有 1 项没勾 · 已完成 8 项")
        #expect(LioTripHomeCopy.pastSummary(open: 0, done: 10, .chinese) == "已完成 10 项")
        #expect(LioTripHomeCopy.pastSummary(open: 2, done: 0, .english) == "2 not ticked")
        #expect(LioTripHomeCopy.pastSummary(open: 1, done: 8, .english) == "1 not ticked · 8 done")
    }

    // MARK: - #1649 review

    @Test func aBookingStillAheadStaysInChinaOnceTheTripHasStarted() throws {
        // 9 Dec, in China: the 11 Dec National Museum tickets opened on 4 Dec, before arrival.
        let list = LioTripChecklist(Self.everything(Self.at("2026-12-09 12:00")))
        let museum = try #require(list.tasks.first { $0.key == "booking.beijing.national-museum.2026-12-11" })
        #expect(museum.stage == .inChina)
        #expect(!list.pastTasks.contains { $0.key.hasPrefix("booking.") })
        // Before the trip the same booking is a before-you-fly task.
        let before = LioTripChecklist(Self.everything(Self.at("2026-11-26 10:00")))
        #expect(before.tasks.first { $0.key == "booking.beijing.national-museum.2026-12-11" }?.stage == .beforeTrip)
    }

    @Test func extremeDayNumbersFromADamagedPlanDoNotCrash() {
        var input = Self.everything(Self.at("2026-12-09 12:00"))
        input.plans = [LioPlanSummary(tripID: "bad", tripVersion: 1, title: "Bad", startDate: "2026-12-08", undated: false,
                                      days: [.init(number: .min, date: nil, items: [.init(id: "a", label: "故宫博物院", startTime: nil, endTime: nil, fixed: nil)]),
                                             .init(number: .max, date: nil, items: [])])]
        let list = LioTripChecklist(input)
        #expect(list.hasTrip)
        #expect(LioTripDay("2026-12-08")!.tripDay(.min) == LioTripDay("2026-12-08")!.adding(days: -36_601))
    }

    @Test func anEmptyTickKeyIsRefusedOnWriteAsOnRead() {
        var ticks = LioTripTicks()
        ticks.set("", done: true, at: Self.at("2026-11-26 10:00"))
        #expect(ticks.done.isEmpty)
    }

    // MARK: - #1649 review, P3 follow-ups

    @Test func nowAndTheDayByDayAgreeOnTodayWhenTheDatesDiffer() {
        // The traveller lands 8 Dec; the saved plan starts 9 Dec. On 10 Dec (trip day 3) the plan's day is its day 2.
        var input = Self.everything(Self.at("2026-12-10 08:00"))
        input.plans = [Self.plan(start: "2026-12-09", days: [[("A", "09:00")], [("B", "09:00")], [("C", "09:00")]])]
        let list = LioTripChecklist(input)
        #expect(list.now == .today(day: 3, next: .init(name: "B", time: "09:00"), remaining: 1))
        #expect(list.schedule.first?.number == 2)
        #expect(list.schedule.first?.isToday == true)
        #expect(list.schedule.filter(\.isToday).count == 1)
    }

    @Test func theLastDayKeepsItsOwnBookingOpen() throws {
        var input = Self.everything(Self.at("2026-12-14 08:00"))
        input.plans = [Self.plan(days: [[], [], [], [], [], [], [("故宫博物院", "09:00")]])]
        let list = LioTripChecklist(input)
        #expect(list.phase == .departureDay(day: 7))
        let palace = try #require(list.tasks.first { $0.key == "booking.beijing.palace-museum.2026-12-14" })
        #expect(palace.stage == .inChina)
        #expect(!list.pastTasks.contains(palace))
        #expect(list.schedule.first?.number == 7)
    }

    @Test func anUndatedPlansBookingStaysOpenDuringTheTrip() throws {
        var input = Self.everything(Self.at("2026-12-09 10:00"))
        input.plans = [Self.plan(start: nil, days: [[("故宫", "09:00")]])]
        let list = LioTripChecklist(input)
        let palace = try #require(list.tasks.first { $0.key == "booking.beijing.palace-museum.undated" })
        #expect(palace.stage == .inChina)
        #expect(!list.pastTasks.contains(palace))
    }

    // MARK: - #1665 review

    @Test func aPlanDayWithItsOwnDateIsTodayOnlyOnThatDate() {
        // Landing 7 Dec; the plan starts 8 Dec. On 7 Dec nothing in the plan is today.
        var input = Self.everything(Self.at("2026-12-07 16:00"))
        input.profile = Self.profile(arrival: "2026-12-07", stayDays: 7)
        let first = LioTripChecklist(input)
        #expect(first.phase == .arrivalDay)
        #expect(!first.schedule.contains { $0.isToday })
        #expect(first.schedule.map(\.number) == [1, 2])
        // On 8 Dec, trip day 2, the plan's day 1 is today.
        input.now = Self.at("2026-12-08 10:00")
        let second = LioTripChecklist(input)
        #expect(second.schedule.first { $0.isToday }?.number == 1)
        #expect(second.now == .today(day: 2, next: .init(name: "Hotel check-in", time: "15:00"), remaining: 1))
    }

    @Test func theReminderIDIsAttractionBookingsOwn() {
        let rule = LioAttractionBookingRule.match(nameZH: "故宫博物院", nameEN: "")!
        #expect(LioTripChecklist.reminderID(rule: rule, visit: Self.day("2026-12-09"))
                == LioAttractionReminder.reminderID(for: rule, visit: Self.day("2026-12-09").start(in: Self.shanghai)))
    }

    // MARK: - #1667 review P2

    @Test func anEndedPlanIsNotTheTripAgain() {
        // Only a saved plan, already over: it shows as ended until the traveller ends it, then the start page.
        var input = LioTripChecklistInput(now: Self.at("2026-12-20 10:00"), plans: [Self.beijingPlan])
        #expect(LioTripChecklist(input).phase == .ended)
        input.endedPlanIDs = [Self.beijingPlan.tripID]
        let list = LioTripChecklist(input)
        #expect(!list.hasTrip)
        #expect(list.plan == nil)
        // A newer plan is still picked up.
        input.plans = [Self.plan("next", start: "2027-01-05", days: [[]]), Self.beijingPlan]
        #expect(LioTripChecklist(input).plan?.tripID == "next")
    }
}
