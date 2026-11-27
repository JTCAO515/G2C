import Foundation
import Testing
@testable import CJShell

struct LioMemoryCategoryTests {
    @Test func slotsTheServiceWritesTodayLandInTheirGroups() {
        let expected: [(String, LioMemoryCategory)] = [
            ("diet.spicy", .food), ("diet.taste", .food), ("travel.pace", .pace), ("travel.budget", .budget),
            ("lodging.style", .lodging), ("travel.interests", .interests), ("quiet.entrance", .other)
        ]
        for (slot, category) in expected { #expect(LioMemoryCategory(slot: slot) == category, "\(slot)") }
    }

    @Test func plannedGroupsAndUnknownSlotsAreHandledWithoutAnAppChange() {
        #expect(LioMemoryCategory(slot: "companions.group") == .companions)
        #expect(LioMemoryCategory(slot: "travel.companions") == .companions)
        #expect(LioMemoryCategory(slot: "mobility.stairs") == .transport)
        #expect(LioMemoryCategory(slot: "profile.language") == .language)
        #expect(LioMemoryCategory(slot: " Diet.Spicy ") == .food)
        for slot in ["", "unheard.of", "dietary", "fact", ".", "travel.unknown"] {
            #expect(LioMemoryCategory(slot: slot) == .other, "\(slot)")
        }
    }

    @Test func groupsFollowPageOrderKeepArrivalOrderAndDropEmptyOnes() {
        let items = [("a", "travel.budget"), ("b", "diet.spicy"), ("c", "mystery"), ("d", "diet.taste"),
                     ("e", "travel.pace"), ("f", "lodging.style")]
        let groups = LioMemoryGrouping.groups(items) { $0.1 }
        #expect(groups.map(\.category) == [.food, .pace, .budget, .lodging, .other])
        #expect(groups.map { $0.items.map(\.0) } == [["b", "d"], ["e"], ["a"], ["f"], ["c"]])
        #expect(LioMemoryGrouping.groups([String]()) { $0 }.isEmpty)
        #expect(LioMemoryGrouping.groups(["x", "y"]) { _ in "unknown" }.map(\.category) == [.other])
    }

    @Test func everyGroupHasTitlesInBothLanguagesAndASymbol() {
        for category in LioMemoryCategory.allCases {
            #expect(!category.title(.english).isEmpty && !category.title(.chinese).isEmpty)
            #expect(!category.symbol.isEmpty)
        }
        #expect(LioMemoryCategory.other == LioMemoryCategory.order.last)
        #expect(LioMemoryCategory.food.title(.chinese) == "饮食" && LioMemoryCategory.pace.title(.english) == "Travel pace")
        #expect(Set(LioMemoryCategory.allCases.map { $0.title(.english) }).count == LioMemoryCategory.allCases.count)
    }

    /// The sentences are copied from what backend `_FORMS` accepts after the leading "remember" is removed; this
    /// keeps the list short, whole-sentence and free of questions so a later edit cannot add a phrase the
    /// service would never turn into a suggestion.
    @Test func emptyStateExamplesAreShortWholeStatementsThatStartWithRemember() {
        for language in [ShellLanguage.english, .chinese] {
            let examples = LioMemoryCopy.examples(language)
            #expect((2...3).contains(examples.count))
            #expect(Set(examples).count == examples.count)
            let prefix = language == .english ? "Remember I " : "记住我"
            for example in examples {
                #expect(example.hasPrefix(prefix), "\(example)")
                #expect(!example.contains("?") && !example.contains("？") && !example.contains(",") && !example.contains("，"))
                #expect(example.count <= 40)
            }
        }
        #expect(LioMemoryCopy.examples(.chinese).contains("记住我不吃辣"))
    }

    @Test func emptyStateCopyExistsInBothLanguages() {
        for language in [ShellLanguage.english, .chinese] {
            for text in [LioMemoryCopy.pageTitle(language), LioMemoryCopy.pageDescription(language),
                         LioMemoryCopy.usageNote(language), LioMemoryCopy.emptyTitle(language),
                         LioMemoryCopy.emptyDescription(language), LioMemoryCopy.remembersHeading(language),
                         LioMemoryCopy.remembers(language), LioMemoryCopy.examplesHeading(language),
                         LioMemoryCopy.examplesTip(language)] {
                #expect(!text.isEmpty)
            }
        }
        #expect(LioMemoryCopy.emptyTitle(.chinese) == "还没有记忆")
        #expect(LioMemoryCopy.emptyDescription(.chinese).contains("记住"))
        #expect(LioMemoryCopy.usageNote(.chinese).contains("按你记住的"))
        #expect(LioMemoryCopy.pageTitle(.english) == "My memories")
    }

    private func moment(_ iso: String) throws -> Date {
        try #require(ISO8601DateFormatter().date(from: iso))
    }

    @Test func summaryNamesTheSavedDayAndTheSourceInBothLanguages() throws {
        let zone = try #require(TimeZone(identifier: "Asia/Shanghai"))
        let stamp = try moment("2026-11-27T10:30:00Z")
        let zh = LioMemoryCopy.summary(recordedAt: stamp, longTerm: true, language: .chinese, timeZone: zone)
        #expect(zh.hasPrefix("记于") && zh.contains("2026") && zh.contains("27") && zh.hasSuffix("来源：你让 Lio 记住的"))
        let en = LioMemoryCopy.summary(recordedAt: stamp, longTerm: true, language: .english, timeZone: zone)
        #expect(en.hasPrefix("Saved on ") && en.contains("2026") && en.contains("Source: you asked Lio to remember it"))
        let trip = LioMemoryCopy.summary(recordedAt: stamp, longTerm: false, language: .chinese, timeZone: zone)
        #expect(trip.hasSuffix("来源：这次行程的对话"))
        #expect(LioMemoryCopy.summary(recordedAt: stamp, longTerm: false, language: .english, timeZone: zone)
                .hasSuffix("Source: this trip’s chat"))
    }

    @Test func theSavedDayUsesTheGivenTimeZone() throws {
        let shanghai = try #require(TimeZone(identifier: "Asia/Shanghai"))
        let la = try #require(TimeZone(identifier: "America/Los_Angeles"))
        let stamp = try moment("2026-11-27T20:30:00Z")
        let early = LioMemoryCopy.savedOn(stamp, language: .english, timeZone: shanghai)
        let late = LioMemoryCopy.savedOn(stamp, language: .english, timeZone: la)
        #expect(early.contains("28") && late.contains("27"))
    }
}
