import Foundation
import Testing
@testable import CJLioUser

/// #1980: the Tools tab shows nine cards. The tools that left it keep their ids, so routes, links and the answer
/// buttons' tool ids (`payment-guide`, `taxi`) still open them.
struct LioToolsNineTests {
    private static let everything = LioToolCatalog.Availability(
        taxi: true, currency: true, hotels: true, nearby: true, roadbook: true, transport: true, arrival: true,
        attractionBooking: true, menuOrder: true, returnHotel: true, convenience: true)

    @Test func nineCardsInTheOrderJTGave() {
        #expect(LioToolCatalog.cards(Self.everything) == [.showCards, .translation, .taxi, .metro, .transport, .hotels,
                                                          .eatPlay, .convenience, .money])
        #expect(LioToolCatalog.cards(Self.everything).count == 9)
        let names = LioToolCatalog.cards(Self.everything).map { $0.name(.chinese) }
        #expect(names == ["出示卡", "翻译", "打车", "地铁", "大交通", "住", "吃喝玩", "附近便利", "钱"])
    }

    @Test func everyToolThatLeftTheGridStillOpensByRoute() {
        let moved: [LioTool] = [.returnHotel, .arrival, .roadbook, .localSupport, .nearby, .attractionBooking,
                                .menuOrder, .payment, .currency]
        let visible = LioToolCatalog.visible(Self.everything)
        for tool in moved {
            #expect(!LioToolCatalog.cards(Self.everything).contains(tool), "\(tool.rawValue) is no card")
            #expect(visible.contains(tool), "\(tool.rawValue) stays routable")
            #expect(LioRoute(tool: tool) != nil)
        }
        // The fixed table of answer buttons (#1727) names these two.
        #expect(LioRoute(tool: LioTool("payment-guide")) != nil)
        #expect(LioRoute(tool: LioTool("taxi"), parameters: ["destination": "故宫"])?["destination"] == "故宫")
        #expect(LioRoute(url: URL(string: "go2china://tool/payment-guide")!)?.tool == .payment)
    }

    @Test func movedToolsKeepTheirIdentifiers() {
        #expect(LioTool.nearby.identifier == "lio.tools.nearby")
        #expect(LioTool.currency.identifier == "lio.tools.currency")
        #expect(LioTool.payment.identifier == "lio.tools.payment-guide")
        #expect(LioTool.menuOrder.identifier == "lio.tools.menu-order")
        #expect(LioTool.attractionBooking.identifier == "lio.tools.attraction-booking")
        #expect(LioTool.eatPlay.identifier == "lio.tools.eat-play")
        #expect(LioTool.convenience.identifier == "lio.tools.convenience")
        #expect(LioTool.money.identifier == "lio.tools.money")
    }

    @Test func hubsAppearOnlyWhenOneOfTheirToolsIs() {
        // Money always has the payment guide; Eat & Play needs nearby, sight bookings or the menu helper.
        #expect(LioToolCatalog.cards(.init()).contains(.money))
        #expect(!LioToolCatalog.cards(.init()).contains(.eatPlay))
        for on in [LioToolCatalog.Availability(nearby: true), .init(attractionBooking: true), .init(menuOrder: true)] {
            #expect(LioToolCatalog.cards(on).contains(.eatPlay))
        }
        #expect(!LioToolCatalog.cards(.init(nearby: true)).contains(.convenience), "essentials need their own flag")
        #expect(LioToolCatalog.cards(.init(nearby: true, convenience: true)).contains(.convenience))
    }

    @Test func hubAndConvenienceCopyFitsTheCard() {
        for tool in [LioTool.eatPlay, .convenience, .money] {
            #expect(tool.summary(.chinese).count <= 11, "\(tool.rawValue)")
            #expect(tool.summary(.english).count <= 44, "\(tool.rawValue)")
        }
        #expect(LioTool.hotels.name(.chinese) == "住")
        #expect(LioTool.transport.name(.chinese) == "大交通")
    }
}
