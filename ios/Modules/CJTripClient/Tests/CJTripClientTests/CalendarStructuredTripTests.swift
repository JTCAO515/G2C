import Foundation
import Testing
@testable import CJTripClient

struct CalendarStructuredTripTests {
    private let requestID = "00000000-0000-4000-8000-000000000001"
    private func fixture(_ file: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return try #require(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("contracts/trip/" + file))) as? [String: Any])
    }
    private func example(_ name: String) throws -> [String: Any] {
        let rows = try #require(fixture("structured-read-examples.2.json")["positive"] as? [[String: Any]])
        return try #require(rows.first { $0["name"] as? String == name }?["value"] as? [String: Any])
    }
    private func bytes(_ value: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    private func canonical(_ value: [String: Any]) throws -> Data {
        var parser = StrictTripJSON(bytes: Array(try bytes(value)))
        return try tripCanonicalJSON(parser.document())
    }

    @Test func undatedCanonicalContentKeepsOriginalHashAndAllOrdinals() throws {
        let example = try example("base detail")
        let record = try #require(example["trip"] as? [String: Any])
        let content = try #require(record["content"] as? [String: Any])
        let input = try canonical(content)
        let document = try CalendarStructuredTripDocument.decode(input)
        #expect(document.calendar == .undated)
        #expect(document.days.map(\.index) == [1, 2, 3])
        #expect(document.days.allSatisfy { $0.date == nil })
        #expect(document.items[0].startDayIndex == 1)
        #expect(document.items[0].value.start.date == .unknown)
        #expect(document.items[0].value.start.time == .known("09:00"))
        #expect(document.originalUTF8 == input)
        #expect(document.contentSHA256 == record["content_sha256"] as? String)
        #expect(throws: TripFailure.self) { try StructuredTripDocument.decode(input) }
    }

    @Test func datedReadBindsTheActualThreeContentHash() throws {
        let input = try bytes(example("dated detail"))
        let record = try #require(try CalendarStructuredTripReadV2.detail(input, requestID: requestID))
        guard case .calendar(let document) = record.content else { Issue.record("calendar content required"); return }
        #expect(document.calendar == .dated(startDate: "2026-12-01"))
        #expect(document.days.map(\.date) == ["2026-12-01", "2026-12-02", "2026-12-03"])
        #expect(document.items[0].value.start.date == .known("2026-12-01"))
        #expect(document.dateChecks.allSatisfy { $0.state == .unknown })
    }

    @Test(arguments: ["structured.1", "structured.2"])
    func readTwoKeepsLegacyContentWithoutCreatingAnUndatedCalendar(_ version: String) throws {
        let record = try #require(try CalendarStructuredTripReadV2.detail(bytes(example("\(version) content unchanged")), requestID: requestID))
        guard case .legacy(let document) = record.content else { Issue.record("legacy content required"); return }
        #expect(document.version.rawValue == version)
        let page = try CalendarStructuredTripReadV2.page(bytes(example("\(version) summary not relabeled undated")), requestID: requestID)
        #expect(page.trips[0].calendar == nil)
        #expect(page.trips[0].dayCount == nil)
    }

    @Test func rejectsHashTraceAndVersionMismatchWithoutOldReadFallback() throws {
        let original = try example("base detail")
        for mutation in 0..<3 {
            var value = original
            switch mutation {
            case 0:
                var trip = try #require(value["trip"] as? [String: Any])
                trip["content_sha256"] = String(repeating: "0", count: 64)
                value["trip"] = trip
            case 1: value["request_id"] = UUID().uuidString
            default: value["version"] = "TRIP-structured-read.1"
            }
            #expect(throws: TripFailure.self) { try CalendarStructuredTripReadV2.detail(bytes(value), requestID: requestID) }
        }
    }

    @Test func summaryCountIsDataAndDoesNotCauseAnUnboundedDateLoop() throws {
        var value = try example("dated list")
        var trips = try #require(value["trips"] as? [[String: Any]])
        trips[0]["day_count"] = Int64.max
        value["trips"] = trips
        #expect(try CalendarStructuredTripReadV2.page(bytes(value), requestID: requestID).trips[0].dayCount == Int.max)
    }

    @Test func rejectsMalformedCalendarScheduleAndUnsupportedDateClaims() throws {
        let file = try fixture("structured-examples.3.json")
        for mutation in 0..<5 {
            var content = try #require(file["base"] as? [String: Any])
            switch mutation {
            case 0:
                var days = try #require(content["days"] as? [[String: Any]])
                days[1]["day_index"] = 3
                content["days"] = days
            case 1:
                var items = try #require(content["items"] as? [[String: Any]])
                var schedule = try #require(items[0]["schedule"] as? [String: Any])
                var start = try #require(schedule["start"] as? [String: Any])
                start["day_index"] = 4
                schedule["start"] = start; items[0]["schedule"] = schedule; content["items"] = items
            case 2:
                var items = try #require(content["items"] as? [[String: Any]])
                var schedule = try #require(items[0]["schedule"] as? [String: Any])
                var start = try #require(schedule["start"] as? [String: Any])
                start["utc_offset"] = ["state": "known", "value": "+08:00"]
                schedule["start"] = start; items[0]["schedule"] = schedule; content["items"] = items
            case 3:
                var checks = try #require(content["date_checks"] as? [[String: Any]])
                checks[0]["state"] = "clear"; content["date_checks"] = checks
            default: content["price"] = 100
            }
            #expect(throws: Error.self) { try CalendarStructuredTripDocument.decode(canonical(content)) }
        }
    }
}
