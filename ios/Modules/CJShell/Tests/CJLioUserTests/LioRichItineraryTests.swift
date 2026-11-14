import Testing
@testable import CJLioUser

struct LioRichItineraryTests {
    private func place(_ name: String, matched: Bool, point: LioItinerary.Point?) -> LioRichItinerary.Place {
        .init(nameZH: name, nameEN: name, address: "示例路 1 号", matched: matched, point: point)
    }

    @Test func missingCoordinatesDoNotRenumberTheRemainingMapStops() {
        let stops = [
            LioRichItinerary.Stop(id: "one", kind: .sight, text: "A", time: nil,
                place: place("A", matched: true, point: .init(latitude: 39.9, longitude: 116.4)), note: nil, tip: nil),
            LioRichItinerary.Stop(id: "two", kind: .meal, text: "B", time: nil,
                place: place("B", matched: false, point: nil), note: nil, tip: nil),
            LioRichItinerary.Stop(id: "three", kind: .hotel, text: "C", time: nil,
                place: place("C", matched: true, point: .init(latitude: 39.91, longitude: 116.41)), note: nil, tip: nil)
        ]
        let day = LioRichItinerary.Day(number: 1, date: nil, theme: "A day", area: "Centre", stops: stops, legs: [])
        #expect(day.mapNumbers == [1, 3])
        #expect(day.mapDay.stops.map(\.id) == ["one", "two", "three"])
        #expect(day.mapDay.stops[1].point == nil)
        #expect(day.mapDay.stops[2].point?.longitude == 116.41)
    }

    @Test func suggestedNamesDoNotGrantADriverAddressOrMapPoint() {
        let candidate = place("A", matched: false, point: .init(latitude: 39.9, longitude: 116.4))
        #expect(candidate.driverAddress == nil)
        #expect(candidate.mapPoint == nil)
        let matched = place("B", matched: true, point: nil)
        #expect(matched.driverAddress == "示例路 1 号")
        #expect(matched.mapPoint == nil)
    }

    @Test func travelLegsDistinguishAnEstimateFromMissingInformation() {
        let leg = LioRichItinerary.Leg(fromID: "one", toID: "two", estimate: .init(mode: .walking, seconds: 61, metres: 1200))
        #expect(leg.description(.english) == "Walk · about 2 min · 1.2 km")
        #expect(leg.description(.chinese) == "步行 · 约 2 分钟 · 1.2 公里")
        #expect(LioRichItinerary.Leg(fromID: "two", toID: "three", estimate: nil).description(.english) == "Travel details not available yet")
    }
}
