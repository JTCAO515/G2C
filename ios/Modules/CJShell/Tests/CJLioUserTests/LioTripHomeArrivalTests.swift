import Foundation
import Testing
@testable import CJLioUser

/// Trip home T5: entry answers come only from Arrival Mode's bundled, sourced rules, and the checklist ticks are
/// Arrival Mode's own progress.
struct LioTripHomeArrivalTests {
    private static let today = LioArrivalDay("2026-11-26")!

    private static func profile(arrival: String? = "2026-12-08", stayDays: Int? = 7, onward: Bool? = nil) -> LioTripProfile {
        LioTripProfile(arrival: arrival.flatMap(LioTripDay.init), stayDays: stayDays, cityID: "beijing",
                       onwardToThirdCountry: onward, startedAt: Date(timeIntervalSince1970: 1_795_000_000))
    }

    private let rules = try? LioArrivalRules.bundled()

    @Test func aGermanPassportForAWeekInDecemberIsVisaFreeByTheBundledRules() throws {
        let rules = try #require(rules)
        let status = LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(), nationality: "DE", today: Self.today)
        #expect(status == .visaFree(maxDays: 30, checkedOn: rules.policy("unilateral-visa-free-2026")!.checkedAt.description))
    }

    @Test func transitShowsThePolicysOwnWordingAndOtherwiseAVisa() throws {
        let rules = try #require(rules)
        let policy = try #require(rules.policy("transit-240h"))
        let transit = LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(stayDays: 5, onward: true),
                                                          nationality: "US", today: Self.today)
        #expect(transit == .transit(maxDays: policy.maxStayDays, checkedOn: policy.checkedAt.description,
                                    summary: LioTripText(en: policy.summary.en, zh: policy.summary.zh)))
        let visa = LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(stayDays: 5, onward: false),
                                                       nationality: "US", today: Self.today)
        guard case .visaRequired = visa else { Issue.record("\(visa)"); return }
    }

    @Test func missingDetailsClearedSettingsAndLapsedRulesNeverGuess() throws {
        let rules = try #require(rules)
        // The nationality is cleared when the account is deleted (A #1656): the task asks again.
        #expect(LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(), nationality: "", today: Self.today) == .missingDetails)
        #expect(LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(arrival: nil), nationality: "DE", today: Self.today) == .missingDetails)
        #expect(LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(stayDays: nil), nationality: "DE", today: Self.today) == .missingDetails)
        #expect(LioTripHomeArrivalRules.entryStatus(rules: rules, profile: nil, nationality: "DE", today: Self.today) == .missingDetails)
        // No rules file, a trip crossing the policy's end, rules overdue for review: official sources only.
        #expect(LioTripHomeArrivalRules.entryStatus(rules: nil, profile: Self.profile(), nationality: "DE", today: Self.today) == .officialOnly)
        #expect(LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(arrival: "2026-12-28"), nationality: "DE",
                                                    today: Self.today) == .officialOnly)
        #expect(LioTripHomeArrivalRules.entryStatus(rules: rules, profile: Self.profile(), nationality: "DE",
                                                    today: rules.reviewDue.adding(days: 1)) == .officialOnly)
    }

    @Test func checklistTicksAreArrivalModesOwnProgress() {
        #expect(LioTripHomeArrivalRules.checklist(stored: "") == LioTripArrivalChecklist(done: [], total: LioArrivalStep.allCases.count))
        #expect(LioTripHomeArrivalRules.checklist(stored: "internet,taxi,nonsense").done == ["internet", "taxi"])
        var stored = LioTripHomeArrivalRules.setting("internet", done: true, in: "entry")
        #expect(LioTripHomeArrivalRules.checklist(stored: stored).done == ["entry", "internet"])
        stored = LioTripHomeArrivalRules.setting("internet", done: true, in: stored)
        #expect(LioTripHomeArrivalRules.checklist(stored: stored).done == ["entry", "internet"])
        stored = LioTripHomeArrivalRules.setting("entry", done: false, in: stored)
        #expect(stored == LioArrivalProgress(stored: "internet").stored)
        #expect(LioTripHomeArrivalRules.setting("not-a-step", done: true, in: stored) == stored)
    }
}
