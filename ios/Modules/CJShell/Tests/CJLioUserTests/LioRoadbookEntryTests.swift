import Testing
@testable import CJLioUser

/// #1515: the Roadbook tool card stays hidden unless the build sets `G2CRoadbookEnabled = YES`.
struct LioRoadbookEntryTests {
    @Test func roadbookIsHiddenByDefault() {
        #expect(!LioToolCatalog.visible(.init()).contains(.roadbook))
        #expect(!LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true)).contains(.roadbook))
    }

    @Test func roadbookCardFollowsHotelsWhenEnabled() {
        #expect(LioToolCatalog.visible(.init(roadbook: true)) == [.localSupport, .roadbook, .metro, .payment, .translation, .phrases])
        let all = LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true, roadbook: true))
        #expect(all == [.localSupport, .taxi, .hotels, .roadbook, .nearby, .currency, .metro, .payment, .translation, .phrases])
    }

    @Test func roadbookCardCopy() {
        #expect(LioTool.roadbook.identifier == "lio.tools.roadbook")
        #expect(LioTool.roadbook.name(.chinese) == "路书")
        #expect(LioTool.roadbook.name(.english) == "Roadbook")
        #expect(LioTool.roadbook.summary(.chinese) == "按天离线看的旅行手册")
        #expect(LioTool.roadbook.summary(.english) == "Your trip day by day, offline")
        #expect(LioTool.roadbook.symbol == "book.closed")
    }

    @Test func onlyAnExplicitYesTurnsTheBuildFlagOn() {
        #expect(LioRoadbookFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "$(G2C_ROADBOOK_ENABLED)", true, 1] {
            #expect(!LioRoadbookFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
    }
}
