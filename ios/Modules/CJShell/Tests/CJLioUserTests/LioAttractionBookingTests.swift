import Foundation
import Testing
@testable import CJLioUser

/// Attraction booking rules (工具：景点预约与放票提醒): every rule is sourced, dated and marked
/// "check the official channel"; unknown values stay unknown instead of being guessed.
struct LioAttractionBookingTests {
    private let rules = LioAttractionBookingRule.all

    @Test func tableCoversTenToTwentyPopularSights() {
        #expect((10...20).contains(rules.count))
        #expect(Set(rules.map(\.id)).count == rules.count)
        for id in ["beijing.palace-museum", "beijing.national-museum", "beijing.mao-mausoleum",
                   "xian.qin-mausoleum-museum"] {
            #expect(rules.contains { $0.id == id }, "\(id) is one of the sights named in the task")
        }
    }

    @Test func everyRuleHasHttpsSourcesACheckDateAndBothLanguages() throws {
        for rule in rules {
            #expect(!rule.sources.isEmpty, "\(rule.id) needs a source")
            for source in rule.sources {
                #expect(source.scheme == "https" || source.scheme == "http", "\(rule.id): \(source)")
                #expect(source.host?.isEmpty == false)
            }
            #expect(rule.officialChannel.url.scheme?.hasPrefix("http") == true)
            let checked = try #require(LioAttractionBookingRule.day(rule.checkedOn), "\(rule.id) check date")
            #expect(checked <= LioAttractionBookingRule.day("2026-11-25")!)
            for language in [LioLanguage.english, .chinese] {
                #expect(!rule.name(language).isEmpty)
                #expect(!rule.city(language).isEmpty)
                #expect(!rule.officialChannel.name(language).isEmpty)
                for line in rule.limits(language) + rule.notes(language) { #expect(!line.isEmpty) }
            }
            #expect(rule.limitsEN.count == rule.limitsZH.count && rule.notesEN.count == rule.notesZH.count)
        }
    }

    @Test func numbersAreOnlyGivenWhereTheSourceStatesThem() {
        for rule in rules {
            if let window = rule.windowDays { #expect((1...60).contains(window), "\(rule.id)") }
            if let release = rule.releaseTime {
                #expect(rule.windowDays != nil, "\(rule.id): a release time needs the day it applies to")
                #expect((0..<24).contains(release.hour) && (0..<60).contains(release.minute))
            }
            if rule.requirement == .notRequired { #expect(rule.releaseTime == nil) }
        }
        // Spot-check the values read from the official pages on 2026-11-25.
        let palace = rule("beijing.palace-museum")
        #expect(palace.requirement == .required && palace.windowDays == 7)
        #expect(palace.releaseTime == .init(hour: 20, minute: 0))
        #expect(palace.passport == .accepted && palace.closedWeekdays == [2] && palace.openOnPublicHolidays)
        #expect(palace.partnerLinks == false, "the Palace Museum says it authorises no third-party ticket agents")
        let mao = rule("beijing.mao-mausoleum")
        #expect(mao.windowDays == 6 && mao.releaseTime == nil && mao.passport == .notStated)
        let qin = rule("xian.qin-mausoleum-museum")
        #expect(qin.requirement == .required && qin.windowDays == nil && qin.releaseTime == nil)
        #expect(rule("shanghai.museum-east").requirement == .notRequired)
    }

    @Test func everyRuleSaysToCheckTheOfficialChannel() {
        for language in [LioLanguage.english, .chinese] {
            let footer = LioAttractionBookingRule.officialFirst(language)
            #expect(footer.contains(language == .chinese ? "以官方为准" : "official"))
        }
    }

    @Test func summaryNeverInventsAMissingNumber() {
        let checked = LioAttractionBookingRule.day("2026-11-25")!
        let qin = rule("xian.qin-mausoleum-museum")
        let qinLine = qin.summary(.english, on: checked)
        let hasDigit = qinLine.contains { $0.isNumber }
        #expect(!hasDigit)
        #expect(qin.summary(.chinese, on: checked).contains("实名预约"))
        let palace = rule("beijing.palace-museum")
        #expect(palace.summary(.chinese, on: checked) == "需实名预约 · 提前 7 天 20:00 放票")
        #expect(palace.summary(.english, on: checked) == "Booking required · opens 7 days ahead at 20:00")
        let mao = rule("beijing.mao-mausoleum")
        #expect(mao.summary(.chinese, on: checked) == "需实名预约 · 最多提前 6 天")
        #expect(rule("shanghai.museum-east").summary(.chinese, on: checked) == "常设展免预约")
    }

    @Test func itineraryPlacesMatchByChineseOrEnglishName() {
        #expect(LioAttractionBookingRule.match(nameZH: "故宫博物院", nameEN: "")?.id == "beijing.palace-museum")
        #expect(LioAttractionBookingRule.match(nameZH: "故宫", nameEN: "Forbidden City")?.id == "beijing.palace-museum")
        #expect(LioAttractionBookingRule.match(nameZH: "", nameEN: "the forbidden city")?.id == "beijing.palace-museum")
        #expect(LioAttractionBookingRule.match(nameZH: "兵马俑", nameEN: "")?.id == "xian.qin-mausoleum-museum")
        #expect(LioAttractionBookingRule.match(nameZH: "成都大熊猫繁育研究基地", nameEN: "")?.id == "chengdu.panda-base")
        // Near misses do not borrow another venue's rules.
        #expect(LioAttractionBookingRule.match(nameZH: "故宫角楼咖啡", nameEN: "") == nil)
        #expect(LioAttractionBookingRule.match(nameZH: "上海博物馆东馆", nameEN: "")?.id == "shanghai.museum-east")
        #expect(LioAttractionBookingRule.match(nameZH: "上海博物馆", nameEN: "")?.id == "shanghai.museum-peoples-square")
        #expect(LioAttractionBookingRule.match(nameZH: "南锣鼓巷", nameEN: "Nanluoguxiang") == nil)
    }

    @Test func staleRulesHideTheirNumbers() {
        let palace = rule("beijing.palace-museum")
        let checked = LioAttractionBookingRule.day(palace.checkedOn)!
        #expect(!palace.isStale(on: checked))
        let later = LioAttractionBookingRule.calendar.date(byAdding: .day, value: LioAttractionBookingRule.reviewDays + 1, to: checked)!
        #expect(palace.isStale(on: later))
        #expect(palace.summary(.chinese, on: later) == "规则可能已变化，请查官方渠道")
    }

    @Test func featureFlagIsOffUnlessTheBuildSaysYES() {
        #expect(!LioAttractionBookingFeature.enabled(infoValue: nil))
        #expect(!LioAttractionBookingFeature.enabled(infoValue: ""))
        #expect(!LioAttractionBookingFeature.enabled(infoValue: "NO"))
        #expect(!LioAttractionBookingFeature.enabled(infoValue: true))
        #expect(LioAttractionBookingFeature.enabled(infoValue: "YES"))
        #expect(LioAttractionBookingFeature.infoKey == "G2CAttractionBookingEnabled")
    }

    @Test func partnerLinksAreOnlyMarkedWhereTheVenueAllowsThirdParties() {
        // Third-party ticket links wait for JT's approval; the data only records where they could go.
        #expect(!rule("beijing.palace-museum").partnerLinks)
        #expect(!rule("beijing.mao-mausoleum").partnerLinks && !rule("beijing.tiananmen-rostrum").partnerLinks)
        #expect(rule("shanghai.museum-peoples-square").partnerLinks, "the museum names Trip.com for international visitors")
    }

    private func rule(_ id: String) -> LioAttractionBookingRule {
        rules.first { $0.id == id }!
    }
}
