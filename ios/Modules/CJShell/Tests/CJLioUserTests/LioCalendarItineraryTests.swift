import Foundation
import Testing
import CJMessageHTTP
import CJTripClient
@testable import CJLioUser

struct LioCalendarItineraryTests {
    private func itinerary(_ name: String) throws -> LioItinerary {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/message/trip-send-examples.2.json"))
        let examples = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let values = try #require(examples["positive"] as? [[String: Any]])
        let value = try #require(values.first { $0["name"] as? String == name }?["value"])
        return try LioItinerary(LioCalendarTripCard.decode(JSONSerialization.data(withJSONObject: value)))
    }

    @Test(arguments: ["base detail", "dated detail"])
    func protectedDetailRetainsEveryCalendarDayAndFixedTime(_ name: String) throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-read-examples.2.json"))
        let file = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let values = try #require(file["positive"] as? [[String: Any]])
        let value = try #require(values.first { $0["name"] as? String == name }?["value"])
        let record = try #require(try CalendarStructuredTripReadV2.detail(JSONSerialization.data(withJSONObject: value),
            requestID: "00000000-0000-4000-8000-000000000001"))
        let plan = LioItinerary(record)
        #expect(plan.days.map(\.number) == [1, 2, 3])
        #expect(plan.days.map { $0.stops.count } == [1, 0, 0])
        #expect(plan.days[0].stops[0].time == "09:00")
        #expect(plan.days[0].stops[0].fixed == true)
        if name == "base detail" {
            #expect(plan.calendar == .undated)
            #expect(plan.days[2].title(.chinese, calendar: plan.calendar) == "第 3 天")
        } else {
            #expect(plan.calendar == .dated(startDate: "2026-12-01"))
            #expect(plan.days[2].date == "2026-12-03")
        }
    }

    @Test func undatedIncludesEmptyRestDaysWithBilingualOrdinals() throws {
        let plan = try itinerary("undated card all3 days incl empty")
        #expect(plan.calendar == .undated)
        #expect(plan.days.map { $0.title(.english, calendar: plan.calendar) } == ["Day 1", "Day 2", "Day 3"])
        #expect(plan.days.map { $0.title(.chinese, calendar: plan.calendar) } == ["第 1 天", "第 2 天", "第 3 天"])
        #expect(plan.days.map { $0.stops.count } == [1, 0, 0])
        #expect(plan.days[0].stops[0].time == "09:00")
        #expect(plan.days[0].stops[0].fixed == true)
        #expect(plan.days.allSatisfy { $0.date == nil })
    }

    @Test func dateConversionAndRestoredUndatedProjectionRemainDistinct() throws {
        let before = try itinerary("undated card all3 days incl empty")
        let dated = try itinerary("dated card same trip new version")
        let restored = try itinerary("undated card all3 days incl empty")
        #expect(before.id == dated.id && dated.id == restored.id)
        #expect(before != dated)
        #expect(dated.calendar == .dated(startDate: "2026-12-01"))
        #expect(dated.days.map { $0.title(.english, calendar: dated.calendar) } == ["2026-12-01", "2026-12-02", "2026-12-03"])
        #expect(restored == before)
    }

    @Test(arguments: ["structured.1", "structured.2"])
    func legacyUnknownDatesDoNotBecomeExplicitlyUndated(_ version: String) throws {
        let plan = try itinerary("legacy \(version) card not normalized")
        #expect(plan.calendar == nil)
        #expect(plan.days[0].title(.english, calendar: plan.calendar) == "Date to be decided")
        #expect(plan.days[0].title(.chinese, calendar: plan.calendar) == "日期待定")
        #expect(plan.days[0].stops[0].time == "09:00:00")
    }
}
