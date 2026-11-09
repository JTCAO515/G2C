import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

@MainActor
struct LioSavedTripTests {
    @Test func displaysTheSavedCardInChatAndTripsWithoutGuessingMissingDetails() async throws {
        let data = Data("""
            {
              "version":"LIO-timeline.1",
              "conversation_id":"lio-dialogue-0123456789abcdef0123456789abcdef",
              "messages":[
                {"message_id":"planning-question","text":"Plan two days in Beijing.","answer":"","status":"completed",
                 "failure":null,"activity":null,"sources":[],"memory":null,
                 "trip":{"trip_id":"beijing-trip","title":"Beijing trip","days":[
                   {"date":"2026-11-10","items":[
                     {"item_id":"museum","label":"Museum","start_time":"09:00","end_time":"11:00","fixed":true}]},
                   {"date":null,"items":[
                     {"item_id":"walk","label":"Walk","start_time":null,"end_time":null,"fixed":null}]}
                 ]}},
                {"message_id":"follow-up","text":"What about tea?","answer":"A tea house is an option.",
                 "status":"completed","failure":null,"activity":null,"sources":[],"trip":null,"memory":null}
              ],
              "next_before":null
            }
            """.utf8)
        let service = LioService.timeline(
            send: { _ in Issue.record("Displaying a saved trip must not send another question"); return .uncertain },
            read: { id, _ in try LioTimelineWire.decodePage(data, for: id) })
        let model = LioConversation(service: service)

        await model.refreshTimeline()

        let trip = try #require(model.turns.first?.itinerary)
        #expect(model.itineraries == [trip])
        #expect(trip.days[0].date == "2026-11-10")
        #expect(trip.days[0].stops.first?.time == "09:00")
        #expect(trip.days[0].stops.first?.endTime == "11:00")
        #expect(trip.days[0].stops.first?.fixed == true)
        #expect(trip.days[1].datePending)
        #expect(trip.days[1].stops.first?.time == nil)
        #expect(trip.days[1].stops.first?.fixed == nil)
        #expect(trip.days.allSatisfy { $0.stops.allSatisfy { $0.point == nil } })
        #expect(model.turns.last?.itinerary == nil)
    }
}
