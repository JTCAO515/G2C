import CJMessageHTTP
import CJTripClient
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

    @Test func persistedTripCanBeShownWithoutAChatMessage() throws {
        let trace = "B35279D6-8B42-466D-A55D-8A16B64BB270"
        let content = """
            {"content_version":"structured.1","items":[{"evidence":[],"fixed":{"state":"unknown"},"id":"item-1","schedule":{"end":{"date":{"state":"unknown"},"time":{"state":"unknown"},"timezone":{"state":"unknown"},"utc_offset":{"state":"unknown"}},"start":{"date":{"state":"unknown"},"time":{"state":"unknown"},"timezone":{"state":"unknown"},"utc_offset":{"state":"unknown"}}},"source_category":"user_provided","source_refs":[],"text":"Tomorrow 09:00 is free text only","verification":"pending"}],"sources":[],"title":"明确标题 / explicit title"}
            """
        let data = Data("""
            {"version":"TRIP-structured-read.1","request_id":"\(trace)","trip":{"trip_id":"trip:1","version":1,
              "content_sha256":"61414a3ce8a395cfe416242284fc254443ae6368ba84d931bf5f38cb0fed9e41","content":\(content)}}
            """.utf8)
        let saved = try StructuredTripReadV1.detail(data, requestID: trace)
        let record = try #require(saved)
        let itinerary = LioItinerary(record)
        let stop = try #require(itinerary.days.first?.stops.first)

        #expect(itinerary.id == "trip:1")
        #expect(itinerary.title == "明确标题 / explicit title")
        #expect(itinerary.days.first?.datePending == true)
        #expect(stop.name.contains("Tomorrow 09:00"))
        #expect(stop.time == nil && stop.endTime == nil && stop.fixed == nil && stop.point == nil)
    }

}
