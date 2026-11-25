import Foundation

/// The groups a trip's tasks are shown in, in the order a trip happens.
enum LioTripStage: Int, CaseIterable, Comparable, Sendable {
    case beforeTrip, arrivalDay, inChina, departure

    static func < (lhs: Self, rhs: Self) -> Bool { lhs.rawValue < rhs.rawValue }
}

/// Where the trip stands on the phone's current day.
enum LioTripPhase: Equatable, Sendable {
    /// Before arrival; `daysToGo` is nil while the dates are not set.
    case beforeTrip(daysToGo: Int?)
    case arrivalDay
    /// A day in China after the arrival day and before the last one; day 1 is the arrival day.
    case inChina(day: Int)
    /// The last day in China.
    case departureDay(day: Int)
    case ended

    /// The stage whose tasks matter today; earlier stages are shown folded.
    var stage: LioTripStage {
        switch self {
        case .beforeTrip: .beforeTrip
        case .arrivalDay: .arrivalDay
        case .inChina: .inChina
        // The last day is still a day in China: its bookings and plan stay open (#1649 review P3-6).
        case .departureDay: .inChina
        case .ended: .departure
        }
    }
}

/// What Arrival Mode's entry rules say for this traveller. The trip home never decides entry itself: the
/// Arrival Mode adapter turns its sourced, dated decision into one of these, and anything it cannot answer
/// is `officialOnly`.
enum LioTripEntryStatus: Equatable, Sendable {
    /// The passport nationality, the arrival day or the length of stay is still missing.
    case missingDetails
    case visaFree(maxDays: Int, checkedOn: String)
    /// `summary` is the policy's own sourced wording from Arrival Mode's rules, shown as it is.
    case transit(maxDays: Int, checkedOn: String, summary: LioTripText? = nil)
    case visaRequired(checkedOn: String)
    /// Not covered, past or crossing a policy's end date, or the rules are overdue for review.
    case officialOnly
}

/// Wording in both languages that comes from a sourced rules file, shown as it is.
struct LioTripText: Equatable, Sendable {
    let en: String
    let zh: String
    func text(_ language: LioLanguage) -> String { language.text(en, zh) }
}

/// Arrival Mode's checklist as the traveller ticked it there, by step name (`entry`, `internet`, `taxi` …).
struct LioTripArrivalChecklist: Equatable, Sendable {
    let done: Set<String>
    let total: Int

    var doneCount: Int { min(done.count, total) }
    func isDone(_ step: String) -> Bool { done.contains(step) }
}

/// When booking opens for a sight on the trip, from the attraction booking rule table only.
enum LioTripBookingTiming: Equatable, Sendable {
    /// Tickets for the visit day go on sale at this instant (Beijing time).
    case opensAt(Date)
    /// Booking opens on this Beijing day; the venue does not publish a time.
    case opensOn(LioTripDay)
    case openNow
    /// The venue publishes no booking window.
    case windowNotPublished
    /// The rule is past its review date: no numbers, only the official channel.
    case checkOfficial
    /// The plan has no date for this day, so there is no visit day to count from.
    case noVisitDay
}

/// One task on the trip home. The key is stable (rule plus object, such as a sight on a day), so a regenerated
/// list keeps its ticks; the wording comes from the rule each time.
struct LioTripTask: Identifiable, Equatable, Sendable {
    enum Kind: Equatable, Sendable {
        case entry(LioTripEntryStatus)
        case arrivalCard
        case payment
        case internet
        case hotel
        case booking(ruleID: String, visit: LioTripDay?, timing: LioTripBookingTiming, reminderSet: Bool)
        case medicalCard
        case landing
        case checkIn
    }

    enum Done: Equatable, Sendable {
        case open
        /// Ticked by hand on the trip home.
        case ticked
        /// A tool's own state says it is done (hotel saved, visa-free entry); it cannot be unticked here.
        case automatic
        /// Ticked in Arrival Mode's checklist; ticking here ticks it there.
        case followsArrival
    }

    /// How the circle behaves.
    enum Tick: Equatable, Sendable {
        /// The traveller ticks it here (stored by key).
        case manual
        /// Mirrors an Arrival Mode step: ticking here ticks that step.
        case arrivalStep(String)
        /// Done only by the tool's own state; the circle is a status, not a button.
        case statusOnly
    }

    let key: String
    let stage: LioTripStage
    let kind: Kind
    let done: Done
    let tick: Tick

    var id: String { key }
    var isDone: Bool { done != .open }
}

/// A place on the plan for one day, as the summary names it.
struct LioTripStopRef: Equatable, Sendable {
    let name: String
    let time: String?
}

/// One day of the plan as the trip home shows it.
struct LioTripScheduleDay: Equatable, Sendable, Identifiable {
    let number: Int
    let date: LioTripDay?
    let isToday: Bool
    let stops: [LioTripStopRef]
    var id: Int { number }
}

/// The one thing the "Now" card shows.
enum LioTripNow: Equatable, Sendable {
    /// Before the trip: how far the preparation is and the next task to do.
    case prepare(done: Int, total: Int, next: LioTripTask?)
    /// Before the trip with every preparation task done.
    case ready(daysToGo: Int?)
    /// Arrival day with Arrival Mode available: its checklist.
    case landing(done: Int, total: Int)
    /// Arrival day without Arrival Mode: the day's own tasks.
    case landingTasks(done: Int, total: Int, next: LioTripTask?)
    /// A day in China: the plan's next place today, or none.
    case today(day: Int, next: LioTripStopRef?, remaining: Int)
    /// Evening in China: back to the hotel; `saved` says whether a hotel is set.
    case backToHotel(saved: Bool)
    case ended(days: Int?)
}

/// What the generator reads. Every tool input is nil when that tool is off in this build, and a task that
/// needs an unavailable tool is left out rather than shown without a way to do it.
struct LioTripChecklistInput: Sendable {
    var now: Date
    var timeZone: TimeZone = .current
    var profile: LioTripProfile?
    /// Plans saved on this device (#1453), newest first.
    var plans: [LioPlanSummary] = []
    var ticks = LioTripTicks()
    /// Arrival Mode (`G2CArrivalModeEnabled`): its entry decision and its checklist.
    var entry: LioTripEntryStatus?
    var arrivalChecklist: LioTripArrivalChecklist?
    /// Back to Hotel (`G2CShowCardEnabled`): whether a stay hotel is saved.
    var hotelSaved: Bool?
    /// Show cards (`G2CShowCardEnabled`).
    var showCards = false
    /// Attraction booking (`G2CAttractionBookingEnabled`) and the reminders already set with the system.
    var attractionBooking = false
    var scheduledReminders: Set<String> = []
}

/// What the trip home shows, generated from the rules and the tools' state on this phone.
struct LioTripChecklist: Equatable, Sendable {
    static let eveningHour = 19
    static let nightEndHour = 5
    /// Booking tasks whose release is this close come first in "next task".
    static let urgentDays = 3

    let hasTrip: Bool
    let plan: LioPlanSummary?
    let arrival: LioTripDay?
    let lastDay: LioTripDay?
    let today: LioTripDay
    let phase: LioTripPhase
    let tasks: [LioTripTask]
    let now: LioTripNow?
    let schedule: [LioTripScheduleDay]
    /// Plan days not shown in `schedule`.
    let moreDays: Int

    func tasks(in stage: LioTripStage) -> [LioTripTask] { tasks.filter { $0.stage == stage } }

    /// In China (not on the arrival day), today's plan comes right under the "Now" card (JT 2026-11-25).
    var showsScheduleFirst: Bool {
        switch phase {
        case .inChina, .departureDay: plan != nil
        case .beforeTrip, .arrivalDay, .ended: false
        }
    }

    /// Tasks of stages already behind the traveller; the home shows them as one line at the end.
    var pastTasks: [LioTripTask] { tasks.filter { $0.stage < phase.stage } }

    init(_ input: LioTripChecklistInput) {
        let today = LioTripDay(date: input.now, timeZone: input.timeZone)
        let plan = Self.currentPlan(profile: input.profile, plans: input.plans, today: today)
        let arrival = input.profile?.arrival ?? plan?.startDate.flatMap(LioTripDay.init)
        let stayDays = input.profile?.stayDays ?? plan.map { max($0.days.count, 1) }
        let lastDay = arrival.flatMap { start in stayDays.map { start.adding(days: max($0, 1) - 1) } }
        let phase = Self.phase(arrival: arrival, lastDay: lastDay, today: today)
        self.today = today
        self.plan = plan
        self.arrival = arrival
        self.lastDay = lastDay
        self.phase = phase
        hasTrip = input.profile != nil || plan != nil
        guard hasTrip else {
            tasks = []
            now = nil
            schedule = []
            moreDays = 0
            return
        }
        let tasks = Self.tasks(input, plan: plan, arrival: arrival, today: today)
        self.tasks = tasks
        now = Self.nowCard(input, phase: phase, tasks: tasks, plan: plan, arrival: arrival, today: today,
                           stayDays: stayDays)
        let days = Self.scheduleDays(plan: plan, arrival: arrival, today: today, phase: phase)
        schedule = days
        moreDays = max((plan?.days.count ?? 0) - days.count, 0)
    }

    // MARK: - Which plan, which phase

    /// The plan the traveller picked, else the saved plan that matches the trip's dates (or the newest undated
    /// one), else (without dates) the newest saved plan that has not ended.
    static func currentPlan(profile: LioTripProfile?, plans: [LioPlanSummary], today: LioTripDay) -> LioPlanSummary? {
        if let id = profile?.planID, let picked = plans.first(where: { $0.tripID == id }) { return picked }
        func range(_ plan: LioPlanSummary) -> ClosedRange<LioTripDay>? {
            guard let start = plan.startDate.flatMap(LioTripDay.init) else { return nil }
            return start...start.adding(days: max(plan.days.count, 1) - 1)
        }
        if let arrival = profile?.arrival {
            let last = profile?.lastDay ?? arrival
            // A plan saved without dates is taken to be this trip's when no dated plan matches.
            return plans.first { plan in range(plan).map { $0.overlaps(arrival...max(arrival, last)) } ?? false }
                ?? plans.first { range($0) == nil }
        }
        if profile != nil {
            return plans.first { plan in range(plan).map { $0.upperBound >= today } ?? true }
        }
        let upcoming = plans.compactMap { plan in range(plan).map { (plan, $0) } }.filter { $0.1.upperBound >= today }
        if let soonest = upcoming.min(by: { $0.1.lowerBound < $1.1.lowerBound }) { return soonest.0 }
        if let undated = plans.first(where: { range($0) == nil }) { return undated }
        return plans.compactMap { plan in range(plan).map { (plan, $0) } }
            .max(by: { $0.1.upperBound < $1.1.upperBound })?.0
    }

    static func phase(arrival: LioTripDay?, lastDay: LioTripDay?, today: LioTripDay) -> LioTripPhase {
        guard let arrival else { return .beforeTrip(daysToGo: nil) }
        if today < arrival { return .beforeTrip(daysToGo: today.days(until: arrival)) }
        if today == arrival { return .arrivalDay }
        let day = arrival.days(until: today) + 1
        if let lastDay {
            if today > lastDay { return .ended }
            if today == lastDay { return .departureDay(day: day) }
        }
        return .inChina(day: day)
    }

    // MARK: - Tasks (the rules table in trip-plan.md)

    static func tasks(_ input: LioTripChecklistInput, plan: LioPlanSummary?, arrival: LioTripDay?,
                      today: LioTripDay) -> [LioTripTask] {
        var result: [LioTripTask] = []
        func manual(_ key: String, _ stage: LioTripStage, _ kind: LioTripTask.Kind) {
            result.append(.init(key: key, stage: stage, kind: kind, done: input.ticks.isDone(key) ? .ticked : .open,
                                tick: .manual))
        }
        func following(_ key: String, _ stage: LioTripStage, _ kind: LioTripTask.Kind, step: String,
                       checklist: LioTripArrivalChecklist) {
            result.append(.init(key: key, stage: stage, kind: kind,
                                done: checklist.isDone(step) ? .followsArrival : .open, tick: .arrivalStep(step)))
        }

        if let entry = input.entry {
            if case .visaFree = entry {
                result.append(.init(key: "entry", stage: .beforeTrip, kind: .entry(entry), done: .automatic, tick: .statusOnly))
            } else {
                manual("entry", .beforeTrip, .entry(entry))
            }
            manual("arrival-card", .beforeTrip, .arrivalCard)
        }
        manual("payment", .beforeTrip, .payment)
        if let checklist = input.arrivalChecklist {
            following("internet", .beforeTrip, .internet, step: "internet", checklist: checklist)
        }
        if let saved = input.hotelSaved {
            result.append(.init(key: "hotel", stage: .beforeTrip, kind: .hotel, done: saved ? .automatic : .open,
                                tick: .statusOnly))
        }
        if input.attractionBooking, let plan {
            result += bookingTasks(plan: plan, arrival: arrival, input: input)
        }
        manual("medical-card", .beforeTrip, .medicalCard)
        if let checklist = input.arrivalChecklist {
            following("landing", .arrivalDay, .landing, step: "taxi", checklist: checklist)
        }
        if input.showCards {
            manual("check-in", .arrivalDay, .checkIn)
        }
        // Stable order: by stage, then the table's order; booking tasks by when tickets open.
        return result.enumerated().sorted { lhs, rhs in
            if lhs.element.stage != rhs.element.stage { return lhs.element.stage < rhs.element.stage }
            return lhs.offset < rhs.offset
        }.map(\.element)
    }

    /// Real-name booking tasks for sights on the plan whose name matches the rule table exactly.
    static func bookingTasks(plan: LioPlanSummary, arrival: LioTripDay?, input: LioTripChecklistInput) -> [LioTripTask] {
        let start = plan.startDate.flatMap(LioTripDay.init)
        let today = LioTripDay(date: input.now, timeZone: input.timeZone)
        var seen = Set<String>()
        var found: [(task: LioTripTask, order: Date)] = []
        for day in plan.days {
            // Only dates the plan itself states; an undated plan has no visit day to count releases from.
            let visit = day.date.flatMap(LioTripDay.init) ?? start?.tripDay(day.number)
            for item in day.items {
                guard let rule = LioAttractionBookingRule.match(nameZH: item.label, nameEN: item.label),
                      rule.requirement == .required else { continue }
                let key = "booking.\(rule.id).\(visit?.description ?? "undated")"
                guard seen.insert(key).inserted else { continue }
                guard let timing = bookingTiming(rule: rule, visit: visit, now: input.now) else { continue }
                let reminderSet = visit.map { input.scheduledReminders.contains(reminderID(rule: rule, visit: $0)) } ?? false
                let release = releaseDay(timing)
                let stage: LioTripStage = {
                    guard let arrival else { return .beforeTrip }
                    // Once the trip is under way, a visit still ahead stays with the days in China, so it is not
                    // folded away with the stages already behind the traveller (#1649 review P2-1).
                    // An undated plan's booking has no visit day; during the trip it stays open too (P3-8).
                    if today >= arrival, visit.map({ $0 >= today }) ?? true { return .inChina }
                    guard let release else { return .beforeTrip }
                    return release < arrival ? .beforeTrip : .inChina
                }()
                let task = LioTripTask(key: key, stage: stage,
                                       kind: .booking(ruleID: rule.id, visit: visit, timing: timing, reminderSet: reminderSet),
                                       done: input.ticks.isDone(key) ? .ticked : .open, tick: .manual)
                found.append((task, releaseOrder(timing, visit: visit)))
            }
        }
        return found.sorted { $0.order < $1.order }.map(\.task)
    }

    /// Nil when the task should not appear: the visit day has passed or the sight needs no booking.
    static func bookingTiming(rule: LioAttractionBookingRule, visit: LioTripDay?, now: Date) -> LioTripBookingTiming? {
        guard let visit else { return rule.isStale(on: now) ? .checkOfficial : .noVisitDay }
        switch LioAttractionReminder.plan(for: rule, visit: visit.start(in: beijing), now: now) {
        case .exact(let opens, _), .opensSoon(let opens): return .opensAt(opens)
        case .firstDay(let day, _): return .opensOn(LioTripDay(date: day, timeZone: beijing))
        case .alreadyOpen: return .openNow
        case .unknownWindow: return .windowNotPublished
        case .stale: return .checkOfficial
        case .notNeeded, .pastVisit: return nil
        }
    }

    /// The same identifier attraction booking gives the system reminder for this sight and day.
    static func reminderID(rule: LioAttractionBookingRule, visit: LioTripDay) -> String {
        LioAttractionReminder.reminderID(for: rule, visit: visit.start(in: beijing))
    }

    private static func releaseDay(_ timing: LioTripBookingTiming) -> LioTripDay? {
        switch timing {
        case .opensAt(let date): LioTripDay(date: date, timeZone: beijing)
        case .opensOn(let day): day
        case .openNow, .windowNotPublished, .checkOfficial, .noVisitDay: nil
        }
    }

    private static func releaseOrder(_ timing: LioTripBookingTiming, visit: LioTripDay?) -> Date {
        switch timing {
        case .openNow: .distantPast
        case .opensAt(let date): date
        case .opensOn(let day): day.start(in: beijing)
        case .windowNotPublished, .checkOfficial, .noVisitDay: visit?.start(in: beijing) ?? .distantFuture
        }
    }

    static let beijing = TimeZone(identifier: "Asia/Shanghai")!

    // MARK: - The "Now" card

    static func nowCard(_ input: LioTripChecklistInput, phase: LioTripPhase, tasks: [LioTripTask],
                        plan: LioPlanSummary?, arrival: LioTripDay?, today: LioTripDay, stayDays: Int?) -> LioTripNow {
        switch phase {
        case .beforeTrip(let daysToGo):
            let preparing = tasks.filter { $0.stage == .beforeTrip }
            let open = preparing.filter { !$0.isDone }
            guard !open.isEmpty else { return .ready(daysToGo: daysToGo) }
            return .prepare(done: preparing.count - open.count, total: preparing.count,
                            next: nextTask(open, now: input.now))
        case .arrivalDay:
            if let checklist = input.arrivalChecklist { return .landing(done: checklist.doneCount, total: checklist.total) }
            let landing = tasks.filter { $0.stage <= .arrivalDay }
            let open = landing.filter { !$0.isDone }
            return .landingTasks(done: landing.count - open.count, total: landing.count, next: nextTask(open, now: input.now))
        case .inChina(let day), .departureDay(let day):
            let hour = LioTripDay.gregorian(input.timeZone).component(.hour, from: input.now)
            let evening = hour >= eveningHour || hour < nightEndHour
            if case .inChina = phase, evening, let saved = input.hotelSaved { return .backToHotel(saved: saved) }
            let stops = planDay(plan, number: day, today: today, arrival: arrival)?.items ?? []
            let clock = clockText(input.now, timeZone: input.timeZone)
            // Places without a time keep their order and count as still to come. Times are `HH:mm[:ss]`.
            let upcoming = stops.drop(while: { item in item.startTime.map { $0.prefix(5) < clock } ?? false })
            if stops.isEmpty || !upcoming.isEmpty {
                let next = upcoming.first.map { LioTripStopRef(name: $0.label, time: $0.startTime) }
                return .today(day: day, next: next, remaining: upcoming.count)
            }
            if case .inChina = phase, let saved = input.hotelSaved { return .backToHotel(saved: saved) }
            return .today(day: day, next: nil, remaining: 0)
        case .ended:
            return .ended(days: stayDays)
        }
    }

    /// A booking that opens within a few days comes first; otherwise the table's order.
    private static func nextTask(_ open: [LioTripTask], now: Date) -> LioTripTask? {
        let soon = now.addingTimeInterval(TimeInterval(urgentDays * 86_400))
        let urgent = open.first { task in
            guard case .booking(_, _, let timing, _) = task.kind else { return false }
            switch timing {
            case .openNow: return true
            case .opensAt(let date): return date <= soon
            case .opensOn(let day): return day.start(in: beijing) <= soon
            default: return false
            }
        }
        return urgent ?? open.first
    }

    private static func clockText(_ date: Date, timeZone: TimeZone) -> String {
        let parts = LioTripDay.gregorian(timeZone).dateComponents([.hour, .minute], from: date)
        return String(format: "%02d:%02d", parts.hour ?? 0, parts.minute ?? 0)
    }

    // MARK: - Day by day

    /// The plan's day for a trip day: the day with that date, else the same day number. The "Now" card and the
    /// day-by-day section both use it, so they always agree on today.
    static func planDay(_ plan: LioPlanSummary?, number: Int, today: LioTripDay, arrival: LioTripDay?) -> LioPlanSummary.Day? {
        guard let plan else { return nil }
        // By date first (the day's own date, else counted from the plan's start), then by day number.
        let start = plan.startDate.flatMap(LioTripDay.init)
        let date = arrival?.tripDay(number) ?? today
        func dayDate(_ day: LioPlanSummary.Day) -> LioTripDay? { day.date.flatMap(LioTripDay.init) ?? start?.tripDay(day.number) }
        if let dated = plan.days.first(where: { dayDate($0) == date }) { return dated }
        // A day with its own date is today only on that date (#1665 review P2-1); undated days go by number.
        return plan.days.first { $0.number == number && dayDate($0) == nil }
    }

    /// Before the trip, the first two days; during it, today and tomorrow; after it, none.
    static func scheduleDays(plan: LioPlanSummary?, arrival: LioTripDay?, today: LioTripDay,
                             phase: LioTripPhase) -> [LioTripScheduleDay] {
        guard let plan else { return [] }
        // Today's plan day is the one the "Now" card uses, so both always show the same day (#1649 review P3-1);
        // when the plan has no day for today, nothing is marked today (#1665 review P2-1).
        let tripNumber: Int
        switch phase {
        case .beforeTrip: tripNumber = 1
        case .arrivalDay: tripNumber = 1
        case .inChina(let day), .departureDay(let day): tripNumber = day
        case .ended: return []
        }
        let todayNumber: Int?
        if case .beforeTrip = phase { todayNumber = nil } else {
            todayNumber = planDay(plan, number: tripNumber, today: today, arrival: arrival)?.number
        }
        let first = todayNumber ?? tripNumber
        // Only dates the plan states; an undated plan's day N is shown as day N of the trip, without a date.
        let start = plan.startDate.flatMap(LioTripDay.init)
        return plan.days.filter { $0.number >= first && $0.number < first + 2 }.map { day in
            let date = day.date.flatMap(LioTripDay.init) ?? start?.tripDay(day.number)
            return LioTripScheduleDay(number: day.number, date: date, isToday: day.number == todayNumber,
                                      stops: day.items.map { LioTripStopRef(name: $0.label, time: $0.startTime) })
        }
    }
}
