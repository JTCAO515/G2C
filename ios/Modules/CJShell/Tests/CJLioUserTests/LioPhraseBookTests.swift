import Testing
@testable import CJLioUser

struct LioPhraseBookTests {
    @Test func eachTravelScenarioHasBilingualPhrasesWithStableIdentities() {
        let categories = LioPhraseCategory.allCases
        #expect(categories == [.dining, .directions, .taxi, .shopping, .healthcare])
        let phrases = categories.flatMap(\.phrases)
        #expect(categories.allSatisfy { $0.phrases.count >= 4 })
        #expect(Set(phrases.map(\.id)).count == phrases.count)
        #expect(phrases.allSatisfy { !$0.chinese.isEmpty && !$0.english.isEmpty })
        #expect(phrases.allSatisfy { $0.text(in: .chinese) == $0.chinese && $0.text(in: .english) == $0.english })
    }
}
