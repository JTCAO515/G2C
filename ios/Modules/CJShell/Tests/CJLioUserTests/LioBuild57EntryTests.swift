import Foundation
import Testing
@testable import CJLioUser

/// #1606: build 57's entries. Every new card and the trip home stay hidden unless the build sets its flag to YES,
/// and no build configuration in the project sets one (the release script passes them for build 57 only).
struct LioBuild57EntryTests {
    @Test func arrivalCardStaysHiddenUntilTheFlagIsOnAndThenComesFirst() {
        #expect(LioTool.arrival.identifier == "lio.tools.arrival")
        #expect(!LioToolCatalog.visible(.init()).contains(.arrival))
        var on = LioToolCatalog.Availability()
        on.arrival = true
        #expect(LioToolCatalog.visible(on) == [.arrival, .localSupport, .metro, .payment, .translation, .phrases])
        #expect(LioTool.arrival.name(.chinese) == "落地模式")
        #expect(LioTool.arrival.name(.english) == "Arrival Mode")
        #expect(LioTool.arrival.summary(.chinese) == "落地首日要做的事")
        #expect(LioTool.arrival.symbol == "airplane.arrival")
    }

    @Test func attractionBookingCardIsHiddenUnlessTheBuildEnablesIt() {
        #expect(!LioToolCatalog.visible(.init()).contains(.attractionBooking))
        #expect(!LioToolCatalog.visible(.init(taxi: true, hotels: true, roadbook: true, transport: true)).contains(.attractionBooking))
        #expect(LioToolCatalog.visible(.init(attractionBooking: true)).contains(.attractionBooking))
        #expect(LioTool.attractionBooking.identifier == "lio.tools.attraction-booking")
        #expect(LioTool.attractionBooking.name(.chinese) == "景点预约")
        #expect(LioTool.attractionBooking.name(.english) == "Sight Bookings")
        #expect(LioTool.attractionBooking.summary(.chinese) == "预约规则与放票提醒")
    }

    @Test func turningNewCardsOnKeepsTheOtherToolsInTheirOrder() {
        let before = LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true, roadbook: true,
                                                  transport: true))
        let after = LioToolCatalog.visible(.init(taxi: true, currency: true, hotels: true, nearby: true, roadbook: true,
                                                 transport: true, arrival: true, attractionBooking: true))
        #expect(after.filter { $0 != .arrival && $0 != .attractionBooking } == before)
        #expect(after.firstIndex(of: .attractionBooking) == after.firstIndex(of: .transport).map { $0 + 1 })
    }

    @Test func flagValuesOtherThanYESKeepEverythingOff() {
        for value: Any? in [nil, "", "NO", "yes", "$(G2C_ARRIVAL_MODE_ENABLED)", true, 1] {
            #expect(!LioArrivalFeature.enabled(infoValue: value))
            #expect(!LioAttractionBookingFeature.enabled(infoValue: value))
            #expect(!LioTripHomeFeature.enabled(infoValue: value))
        }
        #expect(LioArrivalFeature.enabled(infoValue: "YES"))
        #expect(LioAttractionBookingFeature.enabled(infoValue: "YES"))
        #expect(LioTripHomeFeature.enabled(infoValue: "YES"))
        #expect(!LioTripHomeFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsEveryFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        let flags = [
            ("G2CTransportEnabled", "G2C_TRANSPORT_ENABLED"),
            ("G2CMetroNearbyEnabled", "G2C_METRO_NEARBY_ENABLED"),
            ("G2CNearbyEssentialsEnabled", "G2C_NEARBY_ESSENTIALS_ENABLED"),
            ("G2CArrivalModeEnabled", "G2C_ARRIVAL_MODE_ENABLED"),
            ("G2CAttractionBookingEnabled", "G2C_ATTRACTION_BOOKING_ENABLED"),
            ("G2CShowCardEnabled", "G2C_SHOW_CARD_ENABLED"),
            ("G2CMenuOrderEnabled", "G2C_MENU_ORDER_ENABLED"),
            ("G2CTripHomeEnabled", "G2C_TRIP_HOME_ENABLED"),
        ]
        for (key, setting) in flags {
            #expect(plist.contains("<key>\(key)</key><string>$(\(setting))</string>"), "\(key)")
            #expect(!project.contains(setting), "\(setting) stays unset in the project")
        }
        #expect(LioArrivalFeature.infoKey == "G2CArrivalModeEnabled")
        #expect(LioAttractionBookingFeature.infoKey == "G2CAttractionBookingEnabled")
        #expect(LioTripHomeFeature.infoKey == "G2CTripHomeEnabled")
    }
}
