import Testing
@testable import CJLioUser

struct LioStopEndingTests {
    @Test func explicitUndatedOvernightDayRemainsReadable() {
        let stop = LioItinerary.Stop(id: "overnight", name: "Overnight journey", time: "22:00", point: nil,
                                    fixed: nil, endTime: "02:00", endDayNumber: 2)
        #expect(stop.endingText(.english) == "Day 2 02:00")
        #expect(stop.endingText(.chinese) == "第 2 天 02:00")
    }
    @Test func legacyCalendarAndUnknownEndingsKeepTheirActualValues() {
        let dated = LioItinerary.Stop(id: "dated", name: "Journey", time: "22:00", point: nil,
                                     fixed: nil, endTime: "02:00", endDate: "2026-12-02")
        #expect(dated.endingText(.english) == "2026-12-02 02:00")
        #expect(dated.endingText(.chinese) == "2026-12-02 02:00")
        let unknown = LioItinerary.Stop(id: "unknown", name: "Journey", time: nil, point: nil, fixed: nil)
        #expect(unknown.endingText(.english).isEmpty)
        #expect(unknown.endDayNumber == nil)
    }
}
