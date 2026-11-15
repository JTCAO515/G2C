import Foundation
import Testing
@testable import CJTripClient

struct RichStructuredTripTests {
    private func fixture() throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-examples.4.json"))
        return try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
    }
    private func bytes(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    private func content(_ name: String) throws -> [String: Any] {
        let cases = try #require(try fixture()["cases"] as? [String: [String: Any]])
        return try #require(cases[name]?["content"] as? [String: Any])
    }
    func frozenCanonicalContent(_ name: String) throws -> Data {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let input = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-examples.4.json"))
        var parser = StrictTripJSON(bytes: Array(input))
        let file = try parser.document().object()
        let cases = try file.required("cases").object()
        let example = try cases.required(name).object()
        return try tripCanonicalJSON(example.required("content"))
    }
    @Test(arguments: ["unconfirmed", "matched", "dated", "retained_verified", "protected_fixed", "no_default_adjustment"])
    func frozenRichContentRetainsItsRealVersionAndEveryField(_ name: String) throws {
        let input = try frozenCanonicalContent(name), value = try RichStructuredTripDocument.decode(input)
        #expect(value.originalUTF8 == input)
        let expected = [
            "unconfirmed": "668ac87d86c756e191b7281649b49148f892aecffe8c4b409921170c5ae8c4ed",
            "matched": "0ed945a7a8efeb7ce368e0a6051893091a504b16922c645af65ea673a6537e29",
            "dated": "451dba99ff9a63c5da6d8aca8cac3da72a5a9be00e2338a5c83f520b5682c44b",
            "retained_verified": "88b811cc6de88933a67a018382df52c9eca3da1a8d8ec7cf223b0e1599a8357e",
            "protected_fixed": "958bb50b59a3cefbdc9cf57997a964cff8e12400807433de895845ea6d494815",
            "no_default_adjustment": "668ac87d86c756e191b7281649b49148f892aecffe8c4b409921170c5ae8c4ed",
        ]
        #expect(value.contentSHA256 == expected[name])
        #expect(value.days.count == 2)
        #expect(value.items.count == 8)
        #expect(value.legs.count == 6)
        #expect((2...3).contains(value.lodging.recommendations.count))
        #expect(value.days.allSatisfy { !$0.theme.isEmpty && !$0.area.isEmpty })
        #expect(throws: TripFailure.self) { try CalendarStructuredTripDocument.decode(input) }
        #expect(throws: TripFailure.self) { try StructuredTripDocument.decode(input) }
    }
    private func change(_ root: Any, path: [Any], value: Any) throws -> Any {
        if path.isEmpty { return value }
        var rest = path; let key = rest.removeFirst()
        if let index = key as? Int {
            var list = try #require(root as? [Any]);list[index] = try change(list[index], path: rest, value: value);return list
        }
        var object = try #require(root as? [String: Any]);let name = try #require(key as? String)
        object[name] = try change(object[name] ?? NSNull(), path: rest, value: value);return object
    }
    @Test func rejectsFrozenShapeCalendarAdjacencyAndHotelNegatives() throws {
        let rows = try #require(try fixture()["reject"] as? [[String: Any]])
        let structural = Set(["hotel-price", "hotel-booking", "coordinate-conversion-tag", "nonadjacent-leg",
                              "unconfirmed-place-with-provider-id", "unconfirmed-route-with-estimate", "missing-lodging-area",
                              "three-days-as-two", "legacy-version-cannot-carry-rich-fields"])
        var checked = Set<String>()
        for row in rows {
            let name = try #require(row["name"] as? String)
            guard structural.contains(name) else { continue }
            var altered: Any = try content(#require(row["case"] as? String))
            let changes = [row] + ((row["also"] as? [[String: Any]]) ?? [])
            for changeRow in changes {
                altered = try change(altered, path: #require(changeRow["path"] as? [Any]), value: #require(changeRow["value"]))
            }
            #expect(throws: Error.self) { try RichStructuredTripDocument.decode(bytes(altered)) }
            checked.insert(name)
        }
        #expect(checked == structural)
        // Actual-original/eligible-registry/profile source negatives require the protected producer.
        // This display codec cannot establish those private inputs or authorize a write.
    }

    @Test func quantitiesKeepLargeIntegersAndRejectNonfiniteNegativeAndBooleanValues() throws {
        let base = try content("matched")
        let path: [Any] = ["legs", 0, "duration_seconds"]
        for bad: Any in [-1, true, "10"] {
            #expect(throws: Error.self) { try RichStructuredTripDocument.decode(bytes(change(base, path: path, value: bad))) }
        }
        let ordinary = try bytes(change(base, path: path, value: 12345))
        let text = String(decoding: ordinary, as: UTF8.self)
        let large = String(repeating: "9", count: 400)
        let input = Data(text.replacingOccurrences(of: "\"duration_seconds\":12345", with: "\"duration_seconds\":" + large).utf8)
        let decoded = try RichStructuredTripDocument.decode(input)
        #expect(decoded.legs[0].estimate?.duration.token == large)
        #expect(decoded.originalUTF8 == input)
        let infinity = Data(text.replacingOccurrences(of: "\"duration_seconds\":12345", with: "\"duration_seconds\":1e999").utf8)
        #expect(throws: Error.self) { try RichStructuredTripDocument.decode(infinity) }
    }
}
