import Foundation
import Testing
@testable import CJLioUser

/// #1740: the taxi, driver card, directions and booking buttons under a trip place.
struct LioPlaceActionsTests {
    private static let palace = LioRichItinerary.Place(nameZH: "故宫博物院", nameEN: "Palace Museum",
                                                       address: "北京市东城区景山前街4号", matched: true,
                                                       point: .init(latitude: 39.9163, longitude: 116.3972))

    private static func stop(_ place: LioRichItinerary.Place, kind: LioRichItinerary.Kind, id: String = "s1") -> LioRichItinerary.Stop {
        .init(id: id, kind: kind, text: "", time: "09:00", place: place, note: nil, tip: nil)
    }

    private static func actions(_ stop: LioRichItinerary.Stop, available: Set<LioTool> = [.taxi, .attractionBooking]) -> LioPlaceActions {
        LioPlaceActions(stop: stop) { available.contains($0) }
    }

    @Test func aCheckedSightHasAllFourButtons() throws {
        let actions = Self.actions(Self.stop(Self.palace, kind: .sight))
        #expect(actions.actions == [.taxi, .driver, .navigate, .book])

        let taxi = try #require(actions.taxi)
        #expect(taxi.tool == .taxi)
        #expect(taxi.parameters == ["destination": "故宫博物院", "destinationEN": "Palace Museum",
                                    "address": "北京市东城区景山前街4号", "lat": "39.9163", "lng": "116.3972"])
        // The taxi page gets the same destination "Take a taxi here" always used.
        #expect(LioTaxiPlace(route: taxi) == LioRoadbook.taxiDestination(Self.palace))

        let booking = try #require(actions.booking)
        #expect(booking.tool == .attractionBooking)
        #expect(booking.parameters == ["sight": "beijing.palace-museum"])
        #expect(LioAttractionBookingRule.rule(route: booking)?.id == "beijing.palace-museum")

        let driver = try #require(actions.driver)
        #expect(driver.mainZH == "故宫博物院" && driver.detailsZH == ["北京市东城区景山前街4号"])
        #expect(driver.leadZH == "请送我到这里" && driver.noteZH == nil)

        let navigation = try #require(actions.navigation)
        #expect(navigation.point == Self.palace.point)
        let urls = navigation.urls
        #expect(urls.first?.scheme == "iosamap" && urls.first?.absoluteString.contains("dlat=39.9163") == true)
        #expect(urls.last?.host == "maps.apple.com")
    }

    @Test func aCheckedRestaurantHasNoBooking() {
        let place = LioRichItinerary.Place(nameZH: "四季民福烤鸭店", nameEN: "Siji Minfu", address: "北京市东城区灯市口西街32号",
                                           matched: true, point: .init(latitude: 39.9155, longitude: 116.4107))
        let actions = Self.actions(Self.stop(place, kind: .meal))
        #expect(actions.actions == [.taxi, .driver, .navigate])
        #expect(actions.booking == nil)
    }

    @Test func anUncheckedPlaceOnlyShowsTheDriverMarkedUnconfirmedAndASearch() throws {
        // A chat plan's place: no kind, not checked, no coordinate.
        let place = LioRichItinerary.Place(nameZH: "四季民福烤鸭店", nameEN: "Siji Minfu", address: "北京某路",
                                           matched: false, point: .init(latitude: 39.9, longitude: 116.4))
        let actions = Self.actions(Self.stop(place, kind: .unspecified))
        #expect(actions.actions == [.driver, .navigate])
        #expect(actions.taxi == nil, "no checked coordinate, no ride")

        let driver = try #require(actions.driver)
        #expect(driver.detailsZH.isEmpty, "an unchecked address is not shown to the driver")
        #expect(driver.noteZH == "地址未确认" && driver.noteEN == "Address not confirmed")

        let navigation = try #require(actions.navigation)
        #expect(navigation.point == nil && navigation.query == "四季民福烤鸭店")
        #expect(navigation.urls.first?.absoluteString.hasPrefix("iosamap://poi") == true)
    }

    @Test func freeTimeAndTravelWithoutACoordinateHaveNoDirections() {
        for kind in [LioRichItinerary.Kind.freeTime, .transport] {
            let place = LioRichItinerary.Place(nameZH: "随便逛逛", nameEN: "Wander", address: nil, matched: false, point: nil)
            #expect(Self.actions(Self.stop(place, kind: kind)).actions == [.driver], "\(kind)")
        }
    }

    @Test func aCheckedPlaceWithoutACoordinateSearchesItsAddress() {
        let place = LioRichItinerary.Place(nameZH: "四季民福烤鸭店", nameEN: "Siji Minfu", address: "北京市东城区灯市口西街32号",
                                           matched: true, point: nil)
        let actions = Self.actions(Self.stop(place, kind: .meal))
        #expect(actions.actions == [.driver, .navigate])
        #expect(actions.navigation?.query == "北京市东城区灯市口西街32号")
    }

    @Test func bookingFollowsTheSightKindOrABookingRule() throws {
        // A chat place without a kind is still bookable when its name matches a rule; the route carries the rule.
        let chat = LioRichItinerary.Place(nameZH: "故宫", nameEN: "Forbidden City", address: nil, matched: false, point: nil)
        let matched = Self.actions(Self.stop(chat, kind: .unspecified))
        #expect(matched.actions == [.driver, .navigate, .book])
        #expect(matched.booking?.parameters == ["sight": "beijing.palace-museum"])

        // A sight with no rule opens the booking tool with its name, which then shows the list.
        let park = LioRichItinerary.Place(nameZH: "景山公园", nameEN: "Jingshan Park", address: "北京市西城区景山西街44号",
                                          matched: true, point: .init(latitude: 39.92, longitude: 116.39))
        let sight = try #require(Self.actions(Self.stop(park, kind: .sight)).booking)
        #expect(sight.parameters == ["sight": "景山公园"])
        #expect(LioAttractionBookingRule.rule(route: sight) == nil)

        // Neither a sight nor a rule: no booking.
        let shop = LioRichItinerary.Place(nameZH: "某商场", nameEN: "Mall", address: nil, matched: false, point: nil)
        #expect(Self.actions(Self.stop(shop, kind: .meal)).booking == nil)
    }

    @Test func toolsThatCannotOpenHereAreNotShown() {
        let actions = Self.actions(Self.stop(Self.palace, kind: .sight), available: [])
        #expect(actions.actions == [.driver, .navigate])
    }

    @Test func taxiRoutesSurviveTheLinkFormAndBadCoordinatesAreDropped() throws {
        let route = try #require(Self.actions(Self.stop(Self.palace, kind: .sight)).taxi)
        let url = try #require(route.url)
        let reopened = try #require(LioRoute(url: url))
        #expect(LioTaxiPlace(route: reopened) == LioRoadbook.taxiDestination(Self.palace))

        for (lat, lng) in [("91", "116.4"), ("39.9", "-181"), ("nan", "116.4"), ("abc", "116.4")] {
            let bad = try #require(LioRoute(tool: .taxi, parameters: ["destination": "故宫", "lat": lat, "lng": lng]))
            #expect(LioTaxiPlace(route: bad) == nil, "\(lat),\(lng)")
        }
        let noName = try #require(LioRoute(tool: .taxi, parameters: ["lat": "39.9", "lng": "116.4"]))
        #expect(LioTaxiPlace(route: noName) == nil)
    }

    /// The Beijing three-day template: every place is checked, so each has taxi, driver card and directions;
    /// sights (and only places a rule or the sight kind covers) also have booking.
    @Test func beijingTemplateFollowsTheRules() throws {
        let book = LioRoadbookTemplates.beijing(.chinese)
        let stops = book.itinerary.days.flatMap(\.stops)
        #expect(stops.count >= 10)
        for stop in stops {
            let actions = Self.actions(stop)
            let bookable = stop.kind == .sight
                || LioAttractionBookingRule.match(nameZH: stop.place.nameZH, nameEN: stop.place.nameEN) != nil
            #expect(actions.actions == [.taxi, .driver, .navigate] + (bookable ? [.book] : []), "\(stop.id)")
            #expect(actions.driver?.noteZH == nil, "\(stop.id) is checked")
            #expect(LioTaxiPlace(route: try #require(actions.taxi)) == LioRoadbook.taxiDestination(stop.place), "\(stop.id)")
        }
        let byID = Dictionary(uniqueKeysWithValues: stops.map { ($0.id, Self.actions($0)) })
        #expect(byID["bj-002"]?.booking?.parameters == ["sight": "beijing.palace-museum"])
        #expect(byID["bj-005"]?.booking?.parameters == ["sight": "beijing.mutianyu"])
        #expect(byID["bj-004"]?.booking == nil, "a food street has no booking")
        #expect(byID["bj-006"]?.booking == nil)
    }
}
