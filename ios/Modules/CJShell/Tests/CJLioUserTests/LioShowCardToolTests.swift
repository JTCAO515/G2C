import Foundation
import Testing
@testable import CJLioUser

/// #1742: Show Cards is a tool of its own; phrases and help cards are part of it, and there is one
/// "show it to someone" screen.
struct LioShowCardToolTests {
    @Test func showCardsTakesThePhraseCardsSlotAndIsAlwaysShown() {
        #expect(LioToolCatalog.cards(.init()).first == .showCards, "#1980: first card, in JT's order")
        #expect(!LioTool.allCases.map(\.rawValue).contains("phrase-cards"), "phrases are part of Show Cards now")
        #expect(LioTool.showCards.identifier == "lio.tools.show-cards")
        #expect(LioTool.showCards.name(.english) == "Show Cards")
        #expect(LioTool.showCards.name(.chinese) == "出示卡")
        #expect(LioTool.showCards.summary(.english) == "Phrases and help cards in large Chinese")
        #expect(LioTool.showCards.summary(.chinese) == "常用语和求助，给对方看")
        #expect(LioTool.showCards.symbol == "person.text.rectangle")
        // #1765: only `section` (the Business section for the trip home's meeting item).
        #expect(LioToolRegistry.entry(for: .showCards)?.parameters == ["section"])
    }

    @Test func theCardsWithTravellerDetailsStillFollowTheirOwnSwitch() {
        // Show Cards is shown without any switch, but Back to Hotel (and with it the detail scenes) stays off.
        #expect(!LioToolCatalog.visible(.init()).contains(.returnHotel))
        #expect(LioShowCardFeature.enabled(infoValue: nil) == false)
        #expect(LioShowCardFeature.enabled(infoValue: "NO") == false)
        #expect(LioShowCardFeature.enabled(infoValue: "YES"))
    }

    @Test func helpCardsKeepTheirWordingInBothLanguages() {
        #expect(LioShowCardHelp.allCases == [.assistance, .interpreter, .medical, .police])
        #expect(LioShowCardHelp.assistance.content
                == LioShowCardContent(mainZH: "我需要帮助，可以帮我一下吗？",
                                      english: ["I need help. Could you assist me, please?"]))
        #expect(LioShowCardHelp.interpreter.content.mainZH == "我不会说中文，可以帮我找一位会说英语的人吗？")
        #expect(LioShowCardHelp.medical.content.english == ["I need to see a doctor. Could you show me where to go?"])
        #expect(LioShowCardHelp.police.content.mainZH == "我需要帮助，可以帮我联系警方吗？")
        #expect(LioShowCardHelp.interpreter.title(.english) == "Language help")
        #expect(LioShowCardHelp.interpreter.title(.chinese) == "语言协助")
        let identifiers = LioShowCardHelp.allCases.map(\.identifier)
        #expect(Set(identifiers).count == identifiers.count)
        #expect(identifiers.allSatisfy { $0.hasPrefix("lio.support.help-card.message.") })
    }

    @Test func aPhraseIsShownChineseFirstWithItsEnglish() {
        let phrase = LioTravelPhrase("dining-menu", "请问，有英文菜单吗？", "Is there a menu in English?")
        #expect(LioShowCardContent.phrase(phrase)
                == LioShowCardContent(mainZH: "请问，有英文菜单吗？", english: ["Is there a menu in English?"]))
        for category in LioPhraseCategory.allCases {
            for phrase in category.phrases {
                let card = LioShowCardContent.phrase(phrase)
                #expect(!card.mainZH.isEmpty && card.english.count == 1)
            }
        }
    }

    /// The show-card sheet is the only screen that keeps the display awake for someone else to read; a second
    /// full-screen "show" view would need its own and is caught here.
    @Test func onlyTheShowCardSheetKeepsTheScreenAwake() throws {
        let sources = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/CJLioUser")
        let enumerator = try #require(FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil))
        let files = enumerator.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
        #expect(files.count >= 10)
        let awake = try files.filter { try String(contentsOf: $0, encoding: .utf8).contains("isIdleTimerDisabled") }
        #expect(awake.map(\.lastPathComponent) == ["LioShowCard.swift"])
        for removed in ["LioPhraseCardsView.swift", "LioLocalHelpCardView.swift"] {
            #expect(!files.map(\.lastPathComponent).contains(removed))
        }
    }
}
