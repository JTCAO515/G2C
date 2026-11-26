import Testing
@testable import CJLioUser

/// #1421 item 1: "插件" becomes "工具 / Tools", shown as a two-column card grid.
struct LioToolCatalogTests {
    @Test func tabAndPageAreCalledToolsInBothLanguages() {
        #expect(LioToolCatalog.title(.chinese) == "工具")
        #expect(LioToolCatalog.title(.english) == "Tools")
    }

    @Test func everyCardHasAnIconNameAndOneSentenceInBothLanguages() {
        for tool in LioTool.allCases {
            #expect(!tool.symbol.isEmpty)
            #expect(tool.identifier.hasPrefix("lio.tools."))
            for language in [LioLanguage.english, .chinese] {
                let name = tool.name(language)
                let summary = tool.summary(language)
                #expect(!name.isEmpty && !summary.isEmpty)
                #expect(summary.count <= (language == .chinese ? 11 : 44), "\(tool) summary should fit the card at the default size")
                #expect(!summary.contains("插件") && !summary.localizedStandardContains("plugin"))
            }
        }
        #expect(Set(LioTool.allCases.map(\.identifier)).count == LioTool.allCases.count)
    }

    @Test func hiddenToolsAreLeftOut() {
        let none = LioToolCatalog.visible(.init())
        #expect(none == [.localSupport, .metro, .payment, .translation, .showCards])
        #expect(!none.contains(.taxi) && !none.contains(.currency) && !none.contains(.hotels) && !none.contains(.nearby))

        let all = LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true))
        #expect(all == [.localSupport, .taxi, .hotels, .nearby, .currency, .metro, .payment, .translation, .showCards])

        #expect(!none.contains(.transport))
        let transport = LioToolCatalog.visible(.init(taxi: true, roadbook: true, transport: true))
        #expect(transport == [.localSupport, .taxi, .roadbook, .transport, .metro, .payment, .translation, .showCards])
    }

    @Test func existingIdentifiersStayStableForAcceptanceScripts() {
        #expect(LioTool.localSupport.identifier == "lio.tools.local-support")
        #expect(LioTool.taxi.identifier == "lio.tools.taxi")
        #expect(LioTool.currency.identifier == "lio.tools.currency")
        #expect(LioTool.metro.identifier == "lio.tools.metro-guide")
        #expect(LioTool.payment.identifier == "lio.tools.payment-guide")
        #expect(LioTool.translation.identifier == "lio.tools.translation")
        #expect(LioTool.showCards.identifier == "lio.tools.show-cards")
        #expect(LioTool.hotels.identifier == "lio.tools.hotels")
        #expect(LioTool.transport.identifier == "lio.tools.transport")
    }

    @Test func accessibilityLabelReadsNameThenSummary() {
        #expect(LioTool.taxi.accessibilityLabel(.chinese) == "打车，" + LioTool.taxi.summary(.chinese))
        #expect(LioTool.taxi.accessibilityLabel(.english) == "Taxi, " + LioTool.taxi.summary(.english))
    }
}
