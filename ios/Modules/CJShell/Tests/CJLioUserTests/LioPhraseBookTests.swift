import Testing
@testable import CJLioUser

struct LioPhraseBookTests {
    @Test func eachTravelScenarioHasBilingualPhrasesWithStableIdentities() {
        let categories = LioPhraseCategory.allCases
        #expect(categories == [.dining, .directions, .taxi, .shopping, .healthcare, .business])
        let phrases = categories.flatMap(\.phrases)
        #expect(categories.allSatisfy { $0.phrases.count >= 4 })
        #expect(Set(phrases.map(\.id)).count == phrases.count)
        #expect(phrases.allSatisfy { !$0.chinese.isEmpty && !$0.english.isEmpty })
        #expect(phrases.allSatisfy { $0.text(in: .chinese) == $0.chinese && $0.text(in: .english) == $0.english })
    }

    @Test func businessPhrasesCoverQuoteMinimumOrderLeadTimeSampleAndPayment() {
        let ids = LioPhraseCategory.business.phrases.map(\.id)
        #expect(ids == ["business-quote", "business-moq", "business-lead-time", "business-sample", "business-payment"])
        #expect(LioPhraseCategory.business.title(in: .english) == "Business")
        #expect(LioPhraseCategory.business.title(in: .chinese) == "商务")
        #expect(LioPhraseCategory.business.icon == "briefcase")
    }
}
