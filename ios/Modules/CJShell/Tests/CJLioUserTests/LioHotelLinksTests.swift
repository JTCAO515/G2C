import Foundation
import Testing
@testable import CJLioUser

struct LioHotelLinksTests {
    @Test func editingHotelSearchRetiresAnEarlierHandoff() throws {
        var form = LioHotelFormState()
        let link = try #require(URL(string: "https://hotel.example.invalid/out"))
        form.start(.open(link))
        let original = try #require(form.pending)
        #expect(form.accepts(original))
        _ = form.edit(\.city, to: "北京")
        #expect(!form.accepts(original))
        #expect(form.pending == nil)
        _ = form.edit(\.city, to: "")
        form.start(.open(link))
        let second = try #require(form.pending)
        #expect(!form.accepts(original))
        #expect(form.accepts(second))
        form.retire()
        #expect(!form.accepts(second))
    }

    @Test func hotelDatesUseTheCalendarAtTheDestination() throws {
        let iso = ISO8601DateFormatter()
        let arrival = try #require(iso.date(from: "2026-11-21T16:00:00Z"))
        let departure = try #require(iso.date(from: "2026-11-22T16:00:00Z"))
        let query = try LioHotelSearch(scope: .city(" 北京 "), checkIn: arrival, checkOut: departure,
                                       guests: 2, language: .chinese)
        #expect(query.scope == .city("北京"))
        #expect(query.checkIn == "2026-11-22")
        #expect(query.checkOut == "2026-11-23")
        #expect(query.guests == 2)
        let cityBody = try #require(JSONSerialization.jsonObject(with: LioHotelWire.encode(query)) as? [String: Any])
        #expect(cityBody["city"] as? String == "北京")
        #expect(cityBody["location"] == nil)
        #expect(cityBody["language"] as? String == "zh")

        #expect(throws: LioHotelSearch.Validation.cityRequired) {
            try LioHotelSearch(scope: .city(" "), checkIn: arrival, checkOut: departure, guests: 2, language: .chinese)
        }
        #expect(throws: LioHotelSearch.Validation.checkoutMustFollowCheckin) {
            try LioHotelSearch(scope: .city("北京"), checkIn: arrival, checkOut: arrival, guests: 2, language: .chinese)
        }
        #expect(throws: LioHotelSearch.Validation.invalidGuestCount) {
            try LioHotelSearch(scope: .city("北京"), checkIn: arrival, checkOut: departure, guests: 0, language: .chinese)
        }
    }

    @Test func hotelAreaMustUseWGS84WithoutRelabelingGCJ02() throws {
        let area = LioHotelArea(nameZH: "测试片区", nameEN: "Example area",
                               center: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .gcj02),
                               radiusMetres: 1000)
        let arrival = try #require(LioHotelSearch.calendar.date(from: DateComponents(year: 2026, month: 11, day: 23)))
        let departure = try #require(LioHotelSearch.calendar.date(byAdding: .day, value: 1, to: arrival))
        let query = try LioHotelSearch(scope: .area(area), checkIn: arrival, checkOut: departure,
                                       guests: 1, language: .english)
        #expect(throws: LioHotelWire.Failure.invalidLocation) { try LioHotelWire.encode(query) }
    }

    @Test func hotelLinkRejectsConflictingFiltersAndUnapprovedDestinations() {
        let conflict = Data("""
        {"version":"HOTEL.1","url":"https://hotel.example.invalid/out",
         "applied_filters":["check_in"],"unapplied_filters":["check_in"]}
        """.utf8)
        #expect(throws: LioHotelWire.Failure.unavailable) { try LioHotelWire.readLink(conflict) { _ in true } }
        let external = Data("""
        {"version":"HOTEL.1","url":"https://unknown.example.invalid/out",
         "applied_filters":["city"],"unapplied_filters":[]}
        """.utf8)
        #expect(throws: LioHotelWire.Failure.unavailable) {
            try LioHotelWire.readLink(external) { $0.host == "hotel.example.invalid" }
        }
    }

    #if DEBUG
    @MainActor @Test func hotelFixtureKeepsDateGuestAndAreaInputsWithoutOpeningAService() async throws {
        let service = LioHotelService.preview(unapplied: [.guests])
        let area = LioHotelService.previewArea
        let arrival = try #require(LioHotelSearch.calendar.date(from: DateComponents(year: 2026, month: 11, day: 23)))
        let departure = try #require(LioHotelSearch.calendar.date(byAdding: .day, value: 1, to: arrival))
        let query = try LioHotelSearch(scope: .area(area), checkIn: arrival, checkOut: departure,
                                       guests: 3, language: .english)
        let body = try #require(JSONSerialization.jsonObject(with: LioHotelWire.encode(query)) as? [String: Any])
        let location = try #require(body["location"] as? [String: Any])
        #expect(body["version"] as? String == "HOTEL.1")
        #expect(body["city"] == nil)
        #expect(location["lat"] as? Double == 39.9289)
        #expect(location["lng"] as? Double == 116.4165)
        #expect(location["radius_m"] as? Int == 2_000)
        #expect(body["check_in"] as? String == "2026-11-23")
        #expect(body["check_out"] as? String == "2026-11-24")
        #expect(body["guests"] as? Int == 3)
        let reply = try await service.link(query)
        let parts = try #require(URLComponents(url: reply.destination, resolvingAgainstBaseURL: false))
        #expect(parts.host == "hotel.example.invalid")
        #expect(parts.path == "/v1/tools/hotel/out/fixture_handle_aaaaaaaaaaaa")
        #expect(parts.queryItems == nil)
        #expect(reply.unappliedFilters.map { $0.title(.english) } == ["guests"])
        #expect(await service.open(reply.destination))
    }
    #endif
}
