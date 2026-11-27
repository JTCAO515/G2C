import Foundation
import Testing
@testable import CJLioUser

/// #1979: tapping a 「去办」 chip sends its sentence to Lio through the chat's own send path. The view and the host are
/// not compiled on macOS, so the rule is tested here with a stand-in for that path.
struct LioTodoChipAskTests {
    @Test func aTappedChipIsSentAsItIsInEachLanguage() throws {
        let content = try #require(LioTodoContent.bundled())
        for language in [LioLanguage.english, .chinese] {
            for chip in content.steps.flatMap(\.chips) {
                let sentence = chip.text.text(language)
                var sent: [String] = []
                let outcome = LioTodoChipAsk.run(sentence, currentDraft: "") { sent.append($0); return true }
                #expect(outcome == .sent, "\(sentence)")
                #expect(sent == [sentence], "\(sentence)")
            }
        }
    }

    @Test func aChipTheChatRefusesWaitsInAnEmptyMessageBox() {
        var tried = 0
        let outcome = LioTodoChipAsk.run("去哪查入境规定？", currentDraft: "  ") { _ in tried += 1; return false }
        #expect(tried == 1)
        #expect(outcome == .draft("去哪查入境规定？"))
    }

    @Test func aRefusedChipNeverOverwritesWhatTheTravellerTyped() {
        let outcome = LioTodoChipAsk.run("Link to entry rules?", currentDraft: "Best noodles near me") { _ in false }
        #expect(outcome == .kept)
    }

    @Test func anAcceptedChipLeavesTheMessageBoxToTheChat() {
        // The chat clears or keeps the box itself; the typed text is not this rule's to touch.
        #expect(LioTodoChipAsk.run("Link to entry rules?", currentDraft: "half a thought") { _ in true } == .sent)
    }

    @Test func anEmptySentenceIsNeverSent() {
        var tried = 0
        #expect(LioTodoChipAsk.run("  \n", currentDraft: "") { _ in tried += 1; return true } == .kept)
        #expect(tried == 0)
    }

    @Test func theSentenceIsTrimmedBeforeItIsSent() {
        var sent: [String] = []
        _ = LioTodoChipAsk.run(" 入境卡去哪填？ ", currentDraft: "") { sent.append($0); return true }
        #expect(sent == ["入境卡去哪填？"])
    }
}
