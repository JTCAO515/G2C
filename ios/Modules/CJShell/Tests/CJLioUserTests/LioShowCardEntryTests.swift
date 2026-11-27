import Foundation
import Testing
@testable import CJLioUser

/// #1574: the Back to Hotel card stays hidden unless the build sets `G2CShowCardEnabled = YES`; when shown it
/// comes first so travellers find it quickly.
struct LioShowCardEntryTests {
    @Test func hiddenByDefault() {
        #expect(!LioToolCatalog.visible(.init()).contains(.returnHotel))
        #expect(!LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true, roadbook: true,
                                              transport: true)).contains(.returnHotel))
    }

    @Test func isRouteOnlyWhenEnabled() {
        // #1980: Back to Hotel moved to the trip day page; the route still opens it, the Tools tab has no card.
        var availability = LioToolCatalog.Availability()
        availability.returnHotel = true
        #expect(LioToolCatalog.visible(availability).contains(.returnHotel))
        #expect(!LioToolCatalog.cards(availability).contains(.returnHotel))
    }

    @Test func cardCopy() {
        #expect(LioTool.returnHotel.identifier == "lio.tools.return-hotel")
        #expect(LioTool.returnHotel.name(.chinese) == "回酒店")
        #expect(LioTool.returnHotel.name(.english) == "Back to Hotel")
        #expect(LioTool.returnHotel.summary(.chinese) == "打车回酒店、出示卡")
        #expect(LioTool.returnHotel.summary(.english) == "Taxi back, show cards for locals")
        #expect(LioTool.returnHotel.symbol == "house.and.flag")
    }

    @Test func infoPlistDefaultsTheFlagToABuildSettingThatIsUnset() throws {
        let plist = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("App/Info.plist")
        let text = try String(contentsOf: plist, encoding: .utf8)
        #expect(text.contains("<key>G2CShowCardEnabled</key><string>$(G2C_SHOW_CARD_ENABLED)</string>"))
        let project = plist.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj")
        #expect(!(try String(contentsOf: project, encoding: .utf8)).contains("G2C_SHOW_CARD_ENABLED"),
                "the flag stays off: no build configuration sets it")
    }
}
