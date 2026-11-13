import Foundation
import Testing
import CJMessageHTTP

struct LioCalendarTripCardTests {
    private func example(_ name: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let file = root.appendingPathComponent("contracts/message/trip-send-examples.2.json")
        let values = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
        let examples = try #require(values["positive"] as? [[String: Any]])
        let row = try #require(examples.first { $0["name"] as? String == name })
        return try #require(row["value"] as? [String: Any])
    }
    private func bytes(_ value: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    private func undated() throws -> [String: Any] { try example("undated card all3 days incl empty") }
    private func dated() throws -> [String: Any] { try example("dated card same trip new version") }

    @Test func frozenUndatedCardKeepsEveryDayAndExactBytes() throws {
        let data = try bytes(undated())
        let card = try LioCalendarTripCard.decode(data)
        #expect(card.calendar == .undated)
        #expect(card.contentVersion == .calendar)
        #expect(card.days.map(\.index) == [1, 2, 3])
        #expect(card.days.map { $0.items.count } == [1, 0, 0])
        #expect(card.days.allSatisfy { $0.date == nil })
        #expect(card.days[0].items[0].startTime == "09:00")
        #expect(card.days[0].items[0].fixed == true)
        #expect(card.dateChecks?.allSatisfy { $0.state == .notChecked } == true)
        #expect(card.inputUTF8 == data)
    }

    @Test func datedConversionKeepsIdentityAndChangesVersionWithoutInventingChecks() throws {
        let first = try LioCalendarTripCard.decode(bytes(undated()))
        let second = try LioCalendarTripCard.decode(bytes(dated()))
        #expect(first.id == second.id)
        #expect(second.tripVersion == first.tripVersion + 1)
        #expect(first.contentSHA256 != second.contentSHA256)
        #expect(second.calendar == .dated(startDate: "2026-12-01"))
        #expect(second.days.map(\.date) == ["2026-12-01", "2026-12-02", "2026-12-03"])
        #expect(second.dateChecks?.allSatisfy { $0.state == .unknown } == true)
    }

    @Test(arguments: ["structured.1", "structured.2"])
    func oldContentRemainsLegacyWithNoInferredCalendar(_ version: String) throws {
        let value = try example("legacy \(version) card not normalized")
        let card = try LioCalendarTripCard.decode(bytes(value))
        #expect(card.contentVersion.rawValue == version)
        #expect(card.calendar == nil)
        #expect(card.dateChecks == nil)
        #expect(card.days[0].index == nil)
        #expect(card.days[0].date == nil)
        #expect(card.days[0].items[0].startTime == "09:00:00")
    }

    @Test func lexicalVersionIntegersNeverRoundOrAcceptBooleans() throws {
        var value = try undated()
        value["trip_version"] = Int64.max
        #expect(try LioCalendarTripCard.decode(bytes(value)).tripVersion == Int64.max)
        let original = String(decoding: try bytes(undated()), as: UTF8.self)
        for token in ["true", "1.0", "1e0", "0", "-1", "9223372036854775808"] {
            let changed = original.replacingOccurrences(of: #""trip_version":1"#, with: #""trip_version":"# + token)
            #expect(changed != original)
            #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(Data(changed.utf8)) }
        }
    }

    @Test func rejectsMixedCalendarModesAndMissingOrExtraFields() throws {
        let original = try undated()
        let changes: [[String: Any]] = [
            ["version": "LIO-trip-card.3"], ["content_version": "structured.4"],
            ["calendar": NSNull()], ["date_checks": NSNull()], ["price": 100],
            ["booking_status": "confirmed"], ["content_sha256": "bad-hash"]
        ]
        for change in changes {
            let value = original.merging(change) { _, new in new }
            #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(bytes(value)) }
        }
        var value = original
        value.removeValue(forKey: "calendar")
        #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(bytes(value)) }
        value = original
        var days = try #require(value["days"] as? [[String: Any]])
        days[0]["date"] = "2026-12-01"
        value["days"] = days
        #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(bytes(value)) }
    }

    @Test func rejectsGapsBadTimesNumericBooleansAndDuplicatedItems() throws {
        for mutation in 0..<5 {
            var value = try undated()
            var days = try #require(value["days"] as? [[String: Any]])
            var items = try #require(days[0]["items"] as? [[String: Any]])
            switch mutation {
            case 0: days[1]["day_index"] = 3
            case 1: items[0]["start_time"] = "24:00"; days[0]["items"] = items
            case 2: items[0]["fixed"] = 1; days[0]["items"] = items
            case 3: days[1]["items"] = items
            default: items[0].removeValue(forKey: "end_time"); days[0]["items"] = items
            }
            value["days"] = days
            #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(bytes(value)) }
        }
    }

    @Test func rejectsUnobservedClearAndForeignCheckReferences() throws {
        for mutation in 0..<4 {
            var value = try dated()
            var checks = try #require(value["date_checks"] as? [[String: Any]])
            switch mutation {
            case 0: checks[0]["state"] = "clear"
            case 1: checks[0]["day_indices"] = [4]
            case 2: checks[0]["item_ids"] = ["another-trip-item"]
            default: checks[1]["kind"] = checks[0]["kind"]
            }
            value["date_checks"] = checks
            #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(bytes(value)) }
        }
    }

    @Test func usesGregorianLeapAndYearBoundariesWithoutTheDeviceClock() throws {
        for dates in [["2028-02-28", "2028-02-29", "2028-03-01"],
                      ["1900-02-28", "1900-03-01", "1900-03-02"],
                      ["2026-12-31", "2027-01-01", "2027-01-02"]] {
            var value = try dated()
            value["calendar"] = ["state": "dated", "start_date": dates[0]]
            var days = try #require(value["days"] as? [[String: Any]])
            for index in days.indices { days[index]["date"] = dates[index] }
            value["days"] = days
            #expect(try LioCalendarTripCard.decode(bytes(value)).days.map(\.date) == dates.map(Optional.some))
        }
    }

    @Test func rejectsDuplicateJSONKeysBeforeProjection() throws {
        let original = String(decoding: try bytes(undated()), as: UTF8.self)
        let changed = original.replacingOccurrences(of: #""trip_id":"demo-trip""#,
                                                    with: #""trip_id":"demo-trip","trip_id":"other-trip""#)
        #expect(changed != original)
        #expect(throws: MessageHTTPFailure.self) { try LioCalendarTripCard.decode(Data(changed.utf8)) }
    }
}
