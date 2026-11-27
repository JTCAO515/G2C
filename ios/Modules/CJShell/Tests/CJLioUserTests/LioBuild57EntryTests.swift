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
        #expect(LioToolCatalog.visible(on) == [.arrival, .localSupport, .metro, .payment, .translation, .showCards])
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
                                                 transport: true, arrival: true, attractionBooking: true, menuOrder: true,
                                                 returnHotel: true))
        let added: Set<LioTool> = [.arrival, .attractionBooking, .menuOrder, .returnHotel]
        #expect(after.filter { !added.contains($0) } == before)
        #expect(Array(after.prefix(2)) == [.returnHotel, .arrival])
        #expect(after.firstIndex(of: .attractionBooking) == after.firstIndex(of: .transport).map { $0 + 1 })
    }

    @Test func menuCardShowsOnlyWithAServiceAndFitsTheCard() {
        #expect(!LioToolCatalog.visible(.init()).contains(.menuOrder))
        #expect(LioToolCatalog.visible(.init(menuOrder: true)).contains(.menuOrder))
        let all = LioToolCatalog.visible(.init(transport: true, attractionBooking: true, menuOrder: true))
        #expect(all.firstIndex(of: .menuOrder) == all.firstIndex(of: .attractionBooking).map { $0 + 1 })
        #expect(LioTool.menuOrder.identifier == "lio.tools.menu-order")
        #expect(LioTool.menuOrder.symbol == "fork.knife")
        #expect(LioTool.menuOrder.name(.chinese) == "点餐")
        #expect(LioTool.menuOrder.name(.english) == "Menu Helper")
        #expect(LioTool.menuOrder.summary(.chinese) == "拍菜单，用中文点菜")
        #expect(LioTool.menuOrder.summary(.english) == "Snap a menu, order in Chinese")
        #expect(LioMenuService.fromBuild(arguments: [], info: [:], relay: nil) == nil)
        #expect(LioMenuService.fromBuild(arguments: [], info: ["G2CMenuOrderEnabled": "NO"], relay: .preview) == nil)
    }

    @Test func arrivalStartsFromTheEarliestUpcomingTripNotTheLastSaved() throws {
        func plan(_ id: String, _ start: String?) -> LioPlanSummary {
            LioPlanSummary(tripID: id, tripVersion: 1, title: id, startDate: start, undated: start == nil, days: [])
        }
        let today = try #require(LioArrivalDay("2026-12-01"))
        // Newest first, as the saved list keeps them.
        let plans = [plan("later", "2026-12-20"), plan("past", "2026-11-20"), plan("undated", nil), plan("sooner", "2026-12-05")]
        #expect(LioToolCatalog.arrivalPlan(plans, today: today)?.tripID == "sooner")
        #expect(LioToolCatalog.arrivalPlan([plan("past", "2026-11-20"), plan("undated", nil)], today: today)?.tripID == "past")
        #expect(LioToolCatalog.arrivalPlan([plan("today", "2026-12-01")], today: today)?.tripID == "today")
        #expect(LioToolCatalog.arrivalPlan([], today: today) == nil)
        // Same first day: the one saved most recently (listed first).
        let tie = [plan("newer", "2026-12-05"), plan("older", "2026-12-05")]
        #expect(LioToolCatalog.arrivalPlan(tie, today: today)?.tripID == "newer")
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
            ("G2CPlaceToolsEnabled", "G2C_PLACE_TOOLS_ENABLED"),
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
