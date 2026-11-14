import Foundation
import Testing
@testable import CJTripClient

struct RichStructuredTripReadTests {
    private let trace = "00000000-0000-4000-8000-000000000001"
    private func envelope(content: Data, hash: String) -> Data {
        Data(("{\"version\":\"TRIP-structured-read.3\",\"request_id\":\"\(trace)\",\"trip\":{\"trip_id\":\"demo-trip\",\"version\":1,\"content_sha256\":\"\(hash)\",\"content\":" + String(decoding: content, as: UTF8.self) + "}}").utf8)
    }
    @Test(arguments: ["unconfirmed", "matched", "dated", "retained_verified", "protected_fixed", "no_default_adjustment"])
    func richEnvelopeRetainsTheRealFourBytesAndRejectsOldReaders(_ name: String) throws {
        let input = try RichStructuredTripTests().frozenCanonicalContent(name)
        let rich = try RichStructuredTripDocument.decode(input)
        let data = envelope(content: input, hash: rich.contentSHA256)
        let row = try #require(try RichStructuredTripReadV3.detail(data, requestID: trace))
        guard case .rich(let value) = row.content else { Issue.record("actual rich content required"); return }
        #expect(value.originalUTF8 == input)
        #expect(row.content.contentSHA256 == rich.contentSHA256)
        #expect(throws: Error.self) { try CalendarStructuredTripReadV2.detail(data, requestID: trace) }
        #expect(throws: Error.self) { try StructuredTripReadV1.detail(data, requestID: trace) }
    }

    @Test(arguments: ["structured.1 content unchanged", "structured.2 content unchanged", "base detail", "dated detail"])
    func olderContentsRemainTheirActualVersionsInsideTheNewEnvelope(_ name: String) throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let fixture = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-read-examples.2.json"))
        let file = try #require(JSONSerialization.jsonObject(with: fixture) as? [String: Any])
        let examples = try #require(file["positive"] as? [[String: Any]])
        var value = try #require(examples.first { $0["name"] as? String == name }?["value"] as? [String: Any])
        value["version"] = "TRIP-structured-read.3"
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
        let record = try #require(try RichStructuredTripReadV3.detail(data, requestID: trace))
        switch (name, record.content) {
        case ("structured.1 content unchanged", .legacy(let doc)): #expect(doc.version.rawValue == "structured.1")
        case ("structured.2 content unchanged", .legacy(let doc)): #expect(doc.version.rawValue == "structured.2")
        case ("base detail", .calendar(let doc)): #expect(doc.calendar == .undated)
        case ("dated detail", .calendar(let doc)): #expect(doc.calendar == .dated(startDate: "2026-12-01"))
        default: Issue.record("legacy content was relabeled")
        }
    }

    @Test func summaryRetainsExplicitCalendarsLegacyNullAndExactIntegerBounds() throws {
        let hash = String(repeating: "a", count: 64)
        let data = Data("{\"version\":\"TRIP-structured-read.3\",\"request_id\":\"\(trace)\",\"trips\":[{\"trip_id\":\"legacy\",\"version\":1,\"content_version\":\"structured.1\",\"content_sha256\":\"\(hash)\",\"title\":\"Old trip\",\"calendar\":null,\"day_count\":null},{\"trip_id\":\"rich\",\"version\":9223372036854775807,\"content_version\":\"structured.4\",\"content_sha256\":\"\(hash)\",\"title\":\"Rich trip\",\"calendar\":{\"state\":\"undated\"},\"day_count\":2}],\"next_after\":null}".utf8)
        let page = try RichStructuredTripReadV3.page(data, requestID: trace)
        #expect(page.trips[0].calendar == nil && page.trips[0].dayCount == nil)
        #expect(page.trips[1].calendar == .undated && page.trips[1].dayCount == 2)
        #expect(page.trips[1].version == Int.max)
        let overflow = Data(String(decoding: data, as: UTF8.self).replacingOccurrences(of: "9223372036854775807", with: "9223372036854775808").utf8)
        #expect(throws: Error.self) { try RichStructuredTripReadV3.page(overflow, requestID: trace) }
    }

    @Test func readThreeRejectsMismatchedHashTraceVersionAndUnknownKeys() throws {
        let content = try RichStructuredTripTests().frozenCanonicalContent("matched")
        let validHash = try RichStructuredTripDocument.decode(content).contentSHA256
        #expect(throws: Error.self) { try RichStructuredTripReadV3.detail(envelope(content: content, hash: String(repeating: "0", count: 64)), requestID: trace) }
        let data = envelope(content: content, hash: validHash)
        #expect(throws: Error.self) { try RichStructuredTripReadV3.detail(data, requestID: UUID().uuidString) }
        for altered in [String(decoding: data, as: UTF8.self).replacingOccurrences(of: "TRIP-structured-read.3", with: "TRIP-structured-read.2"),
                        String(decoding: data, as: UTF8.self).replacingOccurrences(of: "\"trip_id\":", with: "\"price\":1,\"trip_id\":")] {
            #expect(throws: Error.self) { try RichStructuredTripReadV3.detail(Data(altered.utf8), requestID: trace) }
        }
    }
}
