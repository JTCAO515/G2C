import Testing
@testable import CJLioUser

struct LioQuestionDraftTests {
    private let history = LioQuestionOption(id: "interests.history", displayText: "History", sendText: "Interests: History")
    private let food = LioQuestionOption(id: "interests.food", displayText: "Food", sendText: "Interests: Food")
    private let nature = LioQuestionOption(id: "interests.nature", displayText: "Nature", sendText: "Interests: Nature")
    private let slow = LioQuestionOption(id: "pace.slow", displayText: "Slow", sendText: "Pace: Slow")
    private let balanced = LioQuestionOption(id: "pace.balanced", displayText: "Balanced", sendText: "Pace: Balanced")
    private let active = LioQuestionOption(id: "pace.active", displayText: "Active", sendText: "Pace: Active")

    private var interests: LioQuestionGroup {
        LioQuestionGroup(id: "interests", question: "What sounds interesting?", multiple: true, options: [history, food, nature])
    }
    private var pace: LioQuestionGroup {
        LioQuestionGroup(id: "pace", question: "What pace suits you?", multiple: false, options: [slow, balanced, active])
    }

    @Test func partialAnswersJoinInQuestionAndOptionOrderWithOneNewline() {
        var draft = LioQuestionDraft(messageID: "one", questions: [interests, pace])
        #expect(draft.jointReply.isEmpty)
        draft.toggle(food, in: interests)
        #expect(draft.jointReply == "Interests: Food")
        draft.toggle(active, in: pace)
        draft.toggle(history, in: interests)
        #expect(draft.jointReply == "Interests: History\nInterests: Food\nPace: Active")
        draft.toggle(food, in: interests)
        #expect(draft.jointReply == "Interests: History\nPace: Active")
    }

    @Test func singleChoiceReplacesAndCanBeDeselected() {
        var draft = LioQuestionDraft(messageID: "one", questions: [interests, pace])
        draft.toggle(slow, in: pace)
        draft.toggle(balanced, in: pace)
        #expect(!draft.isSelected(slow, in: pace))
        #expect(draft.isSelected(balanced, in: pace))
        #expect(draft.jointReply == "Pace: Balanced")
        draft.toggle(balanced, in: pace)
        #expect(draft.jointReply.isEmpty)
    }

    @Test func unchangedSnapshotAndValueRestorationKeepChoices() {
        var draft = LioQuestionDraft(messageID: "one", questions: [interests, pace])
        draft.toggle(history, in: interests)
        draft.toggle(slow, in: pace)
        var restored = draft
        restored.apply(messageID: "one", questions: [interests, pace])
        #expect(restored == draft)
    }

    @Test func changedGroupClearsItsSelectionsButKeepsTheOtherGroup() {
        var draft = LioQuestionDraft(messageID: "one", questions: [interests, pace])
        draft.toggle(history, in: interests)
        draft.toggle(slow, in: pace)
        let revised = LioQuestionGroup(id: "interests", question: interests.question, multiple: true,
                                  options: [history, nature, food])
        draft.apply(messageID: "one", questions: [revised, pace])
        #expect(draft.jointReply == "Pace: Slow")
        #expect(!draft.isSelected(history, in: revised))
    }

    @Test func removedGroupDoesNotRestoreOldChoicesWhenItReturns() {
        var draft = LioQuestionDraft(messageID: "one", questions: [interests, pace])
        draft.toggle(food, in: interests)
        draft.toggle(active, in: pace)
        draft.apply(messageID: "one", questions: [pace])
        draft.apply(messageID: "one", questions: [interests, pace])
        #expect(draft.jointReply == "Pace: Active")
    }

    @Test func aNewMessageStartsWithNoSelectionsEvenWithIdenticalGroups() {
        var draft = LioQuestionDraft(messageID: "one", questions: [interests, pace])
        draft.toggle(food, in: interests)
        draft.apply(messageID: "two", questions: [interests, pace])
        #expect(draft.messageID == "two")
        #expect(draft.jointReply.isEmpty)
    }
}
