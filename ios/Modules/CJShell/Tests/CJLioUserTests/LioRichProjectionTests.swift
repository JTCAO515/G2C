import Foundation
import Testing
import CJTripClient
@testable import CJLioUser

struct LioRichProjectionTests {
    private func content(_ name: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-examples.4.json"))
        let file = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let cases = try #require(file["cases"] as? [String: [String: Any]])
        return try #require(cases[name]?["content"] as? [String: Any])
    }
    private func bytes(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    @Test(arguments: ["unconfirmed", "matched", "dated", "retained_verified", "protected_fixed", "no_default_adjustment"])
    func allFrozenRichValuesProjectWithoutInventingMapsOrAddresses(_ name: String) throws {
        let document = try RichStructuredTripDocument.decode(bytes(content(name)))
        for language in [LioLanguage.english, .chinese] {
            let view = try LioRichItinerary(document, language: language)
            #expect(view.title == document.title)
            #expect(view.days.map(\.number) == [1, 2])
            #expect(view.days.reduce(0) { $0 + $1.stops.count } == document.items.count)
            #expect(view.days.reduce(0) { $0 + $1.legs.count } == document.legs.count)
            #expect(view.hotels.count == document.lodging.recommendations.count)
            #expect(view.undated == (document.calendar == .undated))
            let projected = view.days.flatMap(\.stops)
            for (source, stop) in zip(document.items, projected) {
                #expect(source.place.nameZH == stop.place.nameZH)
                #expect(source.place.nameEN == stop.place.nameEN)
                if let coordinate = source.place.coordinate {
                    #expect(stop.place.mapPoint?.longitude == NSDecimalNumber(decimal: coordinate.longitude.value).doubleValue)
                    #expect(stop.place.mapPoint?.latitude == NSDecimalNumber(decimal: coordinate.latitude.value).doubleValue)
                } else { #expect(stop.place.mapPoint == nil) }
                #expect(stop.place.driverAddress == source.place.address)
                #expect(stop.fixed == source.calendarItem.value.fixed.lioValue)
            }
        }
    }
    @Test func privateServiceTextIsRefusedAtThePublicProjectionBoundary() throws {
        var value = try content("matched")
        value["title"] = "Calling amap tool_call"
        let document = try RichStructuredTripDocument.decode(bytes(value))
        #expect(throws: LioRichProjectionFailure.self) { try LioRichItinerary(document, language: .english) }
    }
    @Test func unrepresentableTravelQuantityDoesNotBecomeZeroOrAnInventedEstimate() throws {
        var value = try content("matched")
        var legs = try #require(value["legs"] as? [[String: Any]])
        legs[0]["duration_seconds"] = 12345
        value["legs"] = legs
        let text = String(decoding: try bytes(value), as: UTF8.self)
        let huge = text.replacingOccurrences(of: "\"duration_seconds\":12345", with: "\"duration_seconds\":" + String(repeating: "9", count: 400))
        let document = try RichStructuredTripDocument.decode(Data(huge.utf8))
        #expect(throws: LioRichProjectionFailure.self) { try LioRichItinerary(document, language: .chinese) }
    }
}
