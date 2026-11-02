import Testing
@testable import CJShell

struct TypedMemoryQuestionTests {
    @Test func preservesEveryExplicitScopeForEachQuestion() {
        let food = TypedMemoryManualOption(label:"Food long",subject:"self",slot:"food",kind:.preference,scope:.longTerm)
        let travel = TypedMemoryManualOption(label:"Food travel",subject:"self",slot:"food",kind:.preference,scope:.selectedTravel)
        let pace = TypedMemoryManualOption(label:"Pace",subject:"self",slot:"pace",kind:.preference,scope:.longTerm)
        let first = TypedMemoryQuestion.choices([food,travel,pace])
        let second = TypedMemoryQuestion.choices([food,travel,pace])
        #expect(first.count == 2 && first[0].optionIDs == [food.id,travel.id] && first[1].optionIDs == [pace.id])
        #expect(first.map(\.id) == second.map(\.id))
        #expect(first[0].options[0].subject == "self" && first[0].options[0].slot == "food")
    }
    @Test func prioritizesRecordedKindsAndLimitsToThreeWithoutInferencePromotion() {
        let p = TypedMemoryManualOption(label:"Preference",subject:"self",slot:"food",kind:.preference,scope:.longTerm)
        let p2 = TypedMemoryManualOption(label:"Other preference",subject:"self",slot:"pace",kind:.preference,scope:.longTerm)
        let f = TypedMemoryManualOption(label:"Fact",subject:"self",slot:"fact",kind:.fact,scope:.longTerm)
        let e = TypedMemoryManualOption(label:"Experience",subject:"self",slot:"experience",kind:.experience,scope:.longTerm)
        let i = TypedMemoryManualOption(label:"Inference",subject:"self",slot:"inference",kind:.inference,scope:.longTerm)
        let questions = TypedMemoryQuestion.choices([p,p2,i,f,e])
        #expect(questions.count == 3 && questions.map(\.kind) == ["preference","fact","experience"])
        #expect(!questions.flatMap(\.options).contains { $0.id == i.id || $0.id == p2.id })
    }
    @Test func unavailableOptionsNeverInventWriterChoices() {
        #expect(TypedMemoryQuestion.choices([]).isEmpty)
        let i = TypedMemoryManualOption(label:"Inference",subject:"self",slot:"inference",kind:.inference,scope:.longTerm)
        #expect(TypedMemoryQuestion.choices([i]).isEmpty)
    }
}
