import Foundation
import Testing
@testable import CJLioUser

/// #1591: the Tools tab shows 景点预约 only when the build sets `G2CAttractionBookingEnabled` to YES.
struct LioAttractionBookingEntryTests {
    @Test func cardIsHiddenUnlessTheBuildEnablesIt() {
        #expect(!LioToolCatalog.visible(.init()).contains(.attractionBooking))
        #expect(!LioToolCatalog.visible(.init(taxi: true, hotels: true, roadbook: true, transport: true)).contains(.attractionBooking))
        #expect(LioToolCatalog.visible(.init(attractionBooking: true)).contains(.attractionBooking))
    }

    @Test func enablingItKeepsTheOtherToolsInTheirOrder() {
        let before = LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true))
        let after = LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true, attractionBooking: true))
        #expect(after.filter { $0 != .attractionBooking } == before)
    }

    @Test func cardHasAStableIdentifierAndShortCopy() {
        #expect(LioTool.attractionBooking.identifier == "lio.tools.attraction-booking")
        #expect(LioTool.attractionBooking.name(.chinese) == "景点预约")
        #expect(LioTool.attractionBooking.name(.english) == "Sight Bookings")
        #expect(LioTool.attractionBooking.summary(.chinese) == "预约规则与放票提醒")
    }

    @Test func buildValueOtherThanYESKeepsItOff() {
        for value: Any? in [nil, "", "NO", "yes", "$(G2C_ATTRACTION_BOOKING_ENABLED)", true, 1] {
            #expect(!LioAttractionBookingFeature.enabled(infoValue: value))
        }
        #expect(LioAttractionBookingFeature.enabled(infoValue: "YES"))
    }
}
