import Foundation
import Testing
@testable import CJLioUser

struct LioArrivalRulesTests {
    private static func day(_ text: String) -> LioArrivalDay { LioArrivalDay(text)! }
    private static let today = day("2026-11-25")

    private func trip(_ code: String, arrive: String = "2026-12-01", days: Int = 7, onward: Bool = false)
        -> LioArrivalTrip {
        LioArrivalTrip(countryCode: code, arrival: Self.day(arrive), stayDays: days, onwardToThirdCountry: onward)
    }

    // MARK: - Every rule carries an official source and a check date

    @Test func everyBundledRuleHasAnOfficialSourceAndACheckDate() throws {
        let rules = try LioArrivalRules.bundled()
        #expect(rules.countries.count >= 13)
        for code in ["US", "GB", "DE", "FR", "AU", "JP", "KR", "SG"] {
            #expect(rules.country(code) != nil, "\(code)")
        }
        for policy in rules.policies {
            #expect(!policy.sources.isEmpty, "\(policy.id)")
            #expect(policy.checkedAt <= Self.today, "\(policy.id)")
            #expect(!policy.summary.zh.isEmpty && !policy.summary.en.isEmpty)
            #expect(!policy.notCovered.zh.isEmpty && !policy.notCovered.en.isEmpty)
            for source in policy.sources {
                #expect(LioArrivalRules.isOfficial(source.url), "\(source.url)")
                #expect(!source.publisher.zh.isEmpty && !source.publisher.en.isEmpty)
            }
        }
        for country in rules.countries {
            #expect(country.checkedAt <= Self.today, "\(country.code)")
            #expect(!country.sources(in: rules).isEmpty, "\(country.code)")
        }
        #expect(!rules.officialFallback.isEmpty)
        #expect(rules.officialFallback.allSatisfy { LioArrivalRules.isOfficial($0.url) })
        #expect(!rules.arrivalCard.sources.isEmpty)
        #expect(rules.arrivalCard.sources.allSatisfy { LioArrivalRules.isOfficial($0.url) })
    }

    @Test(arguments: [
        "https://www.nia.gov.cn/x", "https://s.nia.gov.cn/x", "https://cs.mfa.gov.cn/", "https://www.fmprc.gov.cn/x",
        "https://au.china-embassy.gov.cn/x", "https://vancouver.china-consulate.gov.cn/x",
    ])
    func officialHostsAreAccepted(_ text: String) {
        #expect(LioArrivalRules.isOfficial(URL(string: text)!))
    }

    @Test(arguments: [
        "http://www.nia.gov.cn/x", "https://nia.gov.cn.example.com/x", "https://china-visa-online.com/x",
        "https://www.visaforchina.cn/x", "https://gov.cn@example.com/x", "https://examplegov.cn/x",
    ])
    func unofficialHostsAreRejected(_ text: String) {
        #expect(!LioArrivalRules.isOfficial(URL(string: text)!))
    }

    @Test func loaderRejectsRulesWithoutSourcesDatesOrWithUnofficialLinks() throws {
        let valid = try Data(contentsOf: #require(LioArrivalRules.bundledURL))
        _ = try LioArrivalRules.decode(valid)
        typealias Object = [String: Any]
        func policies(_ root: inout Object, _ edit: (inout Object) -> Void) {
            var list = root["policies"] as! [Object]
            edit(&list[2])
            root["policies"] = list
        }
        func countries(_ root: inout Object, _ edit: (inout Object) -> Void) {
            var list = root["countries"] as! [Object]
            edit(&list[0])
            root["countries"] = list
        }
        let broken: [String: (inout Object) -> Void] = [
            "no sources": { root in policies(&root) { $0.removeValue(forKey: "sources") } },
            "empty sources": { root in policies(&root) { $0["sources"] = [Object]() } },
            "no rule date": { root in policies(&root) { $0.removeValue(forKey: "checked_at") } },
            "no country date": { root in countries(&root) { $0.removeValue(forKey: "checked_at") } },
            "bad date": { root in policies(&root) { $0["valid_until"] = "2026-13-41" } },
            "unknown kind": { root in policies(&root) { $0["kind"] = "visa_on_arrival" } },
            "unofficial link": { root in policies(&root) {
                $0["sources"] = [["url": "https://nia-gov.example.com/x", "publisher": ["zh": "x", "en": "x"]]]
            } },
            "unknown policy": { root in countries(&root) { $0["policies"] = ["transit-999h"] } },
            "no policy and no fallback": { root in countries(&root) {
                $0["policies"] = [String](); $0["otherwise"] = "visa_required"
            } },
            "duplicate country": { root in
                var list = root["countries"] as! [Object]; list.append(list[0]); root["countries"] = list
            },
            "no overall date": { root in root.removeValue(forKey: "checked_at") },
            "unofficial arrival card source": { root in
                var card = root["arrival_card"] as! Object
                card["sources"] = [["url": "https://china-arrival-card.example.com/", "publisher": ["zh": "x", "en": "x"]]]
                root["arrival_card"] = card
            },
        ]
        for (name, edit) in broken {
            var root = try #require(try JSONSerialization.jsonObject(with: valid) as? Object)
            edit(&root)
            let data = try JSONSerialization.data(withJSONObject: root)
            let decoded = try? LioArrivalRules.decode(data)
            #expect(decoded == nil, "\(name) should be rejected")
        }
    }

    // MARK: - Decisions

    @Test func germanShortStayInTheWindowIsVisaFreeWithSources() throws {
        let rules = try LioArrivalRules.bundled()
        let result = rules.evaluate(trip("DE"), today: Self.today)
        guard case .visaFree(let policy) = result.outcome else { Issue.record("\(result.outcome)"); return }
        #expect(policy.id == "unilateral-visa-free-2026")
        #expect(policy.maxStayDays == 30)
        #expect(result.sources == policy.sources)
        #expect(result.checkedAt == Self.day("2026-11-25"))
    }

    @Test func ukAndCanadaUseTheirOwnNotice() throws {
        let rules = try LioArrivalRules.bundled()
        for code in ["GB", "CA"] {
            guard case .visaFree(let policy) = rules.evaluate(trip(code), today: Self.today).outcome else {
                Issue.record("\(code)"); continue
            }
            #expect(policy.id == "uk-canada-visa-free-2026")
            #expect(policy.validFrom == Self.day("2026-02-17"))
        }
    }

    @Test func aTripThatEndsAfterThePolicyEndsSaysCheckOfficial() throws {
        let rules = try LioArrivalRules.bundled()
        let crossing = rules.evaluate(trip("FR", arrive: "2026-12-28", days: 7), today: Self.today)
        #expect(crossing.outcome == .checkOfficial(.policyMayEndDuringTrip))
        let after = rules.evaluate(trip("FR", arrive: "2027-01-05", days: 7), today: Self.today)
        #expect(after.outcome == .checkOfficial(.policyEnded))
        // The last day itself is still inside the published window.
        let lastDay = rules.evaluate(trip("FR", arrive: "2026-12-25", days: 6), today: Self.today)
        guard case .visaFree = lastDay.outcome else { Issue.record("\(lastDay.outcome)"); return }
    }

    @Test func americanTransitNeedsAThirdCountryAndTenDaysOrLess() throws {
        let rules = try LioArrivalRules.bundled()
        guard case .transit(let policy) = rules.evaluate(trip("US", days: 10, onward: true), today: Self.today).outcome
        else { Issue.record("transit"); return }
        #expect(policy.id == "transit-240h")
        #expect(rules.evaluate(trip("US", days: 7), today: Self.today).outcome == .visaRequired)
        #expect(rules.evaluate(trip("US", days: 11, onward: true), today: Self.today).outcome == .visaRequired)
    }

    @Test func longStaysFallBackToTransitOrVisa() throws {
        let rules = try LioArrivalRules.bundled()
        #expect(rules.evaluate(trip("JP", days: 31), today: Self.today).outcome == .visaRequired)
        guard case .transit = rules.evaluate(trip("JP", arrive: "2027-02-01", days: 5, onward: true),
                                             today: Self.today).outcome
        else { Issue.record("an open-ended transit rule still applies"); return }
    }

    @Test func unverifiedOrUnlistedNationalitiesAreSentToOfficialSources() throws {
        let rules = try LioArrivalRules.bundled()
        let singapore = rules.evaluate(trip("SG", days: 7), today: Self.today)
        #expect(singapore.outcome == .checkOfficial(.notVerified))
        #expect(!singapore.sources.isEmpty)
        let unlisted = rules.evaluate(trip("ZZ"), today: Self.today)
        #expect(unlisted.outcome == .checkOfficial(.notCovered))
        #expect(unlisted.sources.map(\.url) == rules.officialFallback.map(\.url))
    }

    @Test func overdueRulesAreNotShownAsAnswers() throws {
        let rules = try LioArrivalRules.bundled()
        #expect(rules.reviewDue == Self.day("2026-12-25"))
        #expect(!rules.isOverdue(today: Self.day("2026-12-25")))
        let late = Self.day("2026-12-26")
        #expect(rules.isOverdue(today: late))
        #expect(rules.evaluate(trip("DE"), today: late).outcome == .checkOfficial(.overdueForReview))
    }

    @Test func daysParseStrictlyAndCountForward() throws {
        #expect(LioArrivalDay("2026-02-30") == nil)
        #expect(LioArrivalDay("2026-2-3") == nil)
        #expect(Self.day("2026-12-25").adding(days: 7) == Self.day("2027-01-01"))
        #expect(Self.day("2026-12-31") > Self.day("2026-12-30"))
    }

    // MARK: - Arrival card: official channel only

    @Test func arrivalCardOpensOnlyTheImmigrationAdministrationsPage() {
        let url = LioArrivalCard.officialURL
        #expect(url.absoluteString == "https://s.nia.gov.cn/ArrivalCardFillingPC/")
        #expect(url.scheme == "https")
        #expect(url.host == "s.nia.gov.cn")
        #expect(url.user == nil && url.port == nil && url.query == nil)
        #expect(LioArrivalCard.isOfficial(url))
    }

    @Test(arguments: [
        "http://s.nia.gov.cn/ArrivalCardFillingPC/", "https://s.nia.gov.cn.example.com/ArrivalCardFillingPC/",
        "https://china-arrival-card.example.com/", "https://www.nia.gov.cn/ArrivalCardFillingPC/",
        "https://s.nia.gov.cn@example.com/ArrivalCardFillingPC/", "https://s.nia.gov.cn/ArrivalCardFillingPC/?pay=1",
    ])
    func arrivalCardRejectsLookalikes(_ text: String) {
        #expect(!LioArrivalCard.isOfficial(URL(string: text)!))
    }
}
