import Foundation
import Testing
@testable import CJLioUser

/// #1421 P0: build 53 only filtered local trip places, so typed names never found anything.
@MainActor struct LioTaxiSearchTests {
    private let base = URL(string: "https://example.invalid")!
    private let near = LioTaxiPlace.Coordinate(latitude: 30.66, longitude: 104.06, referenceSystem: .wgs84)

    private func response(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
    }

    private let items = Data("""
    {"version":"TAXI.1","items":[
      {"name_zh":"宽窄巷子","address_zh":"四川省成都市青羊区长顺街附近","city":"成都","lat":30.6638,"lng":104.0537,
       "coordinate_system":"GCJ-02"},
      {"name_zh":"宽窄巷子-东门","address_zh":null,"city":"成都","lat":30.6640,"lng":104.0560,
       "coordinate_system":"GCJ-02"}
    ]}
    """.utf8)

    @Test func searchPostsTheTypedNameCityAndPickupToTheRelay() async throws {
        var bodies = [[String: Any]]()
        var paths = [String]()
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
            let url = try #require(request.url)
            paths.append(url.path)
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-only")
            #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
            let body = try #require(request.httpBody)
            bodies.append(try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any]))
            return (items, response(url, status: 200))
        }

        let places = try await relay.search(.init(text: "  宽窄巷子 ", city: .chengdu, near: near))

        #expect(paths == ["/v1/tools/taxi/search"])
        let body = try #require(bodies.first)
        #expect(body["query"] as? String == "宽窄巷子")
        #expect(body["city"] as? String == "成都")
        #expect(body["version"] as? String == "TAXI.1")
        let point = try #require(body["near"] as? [String: Any])
        #expect(point["lat"] as? Double == 30.66)
        #expect(point["lng"] as? Double == 104.06)
        #expect(point["coordinate_system"] as? String == "WGS-84")
        #expect(Set(body.keys) == ["version", "query", "city", "near"])

        #expect(places.count == 2)
        let first = try #require(places.first)
        #expect(first.nameZH == "宽窄巷子")
        #expect(first.addressZH == "四川省成都市青羊区长顺街附近")
        #expect(first.coordinate == .init(latitude: 30.6638, longitude: 104.0537, referenceSystem: .gcj02))
        #expect(places[1].addressZH == nil)
    }

    @Test func searchWithoutAPickupOmitsNear() throws {
        let data = try LioTaxiWire.encodeSearch(.init(text: "外滩", city: .shanghai, near: nil))
        let body = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(Set(body.keys) == ["version", "query", "city"])
        #expect(String(decoding: data, as: UTF8.self).contains("外滩"))
    }

    @Test func blankOrOversizedQueriesAreNotSent() async throws {
        var sends = 0
        let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
            sends += 1
            return (items, response(try #require(request.url), status: 200))
        }
        #expect(try await relay.search(.init(text: "   ", city: .beijing, near: nil)).isEmpty)
        await #expect(throws: LioTaxiFailure.queryTooLong) {
            try await relay.search(.init(text: String(repeating: "天", count: 81), city: .beijing, near: nil))
        }
        #expect(sends == 0)
    }

    @Test func anEmptyResultIsNotAFailure() throws {
        #expect(try LioTaxiWire.readPlaces(Data(#"{"version":"TAXI.1","items":[]}"#.utf8)).isEmpty)
    }

    @Test func malformedPlacesAreRejected() {
        for body in [
            #"{"version":"TAXI.2","items":[]}"#,
            #"{"version":"TAXI.1"}"#,
            #"{"version":"TAXI.1","items":[{"name_zh":"","city":"成都","lat":30.6,"lng":104.0,"coordinate_system":"GCJ-02"}]}"#,
            #"{"version":"TAXI.1","items":[{"name_zh":"A","city":"成都","lat":91,"lng":104.0,"coordinate_system":"GCJ-02"}]}"#,
            #"{"version":"TAXI.1","items":[{"name_zh":"A","city":"成都","lat":30.6,"lng":104.0,"coordinate_system":"BD-09"}]}"#,
        ] {
            #expect(throws: (any Error).self) { try LioTaxiWire.readPlaces(Data(body.utf8)) }
        }
    }

    @Test func searchFailuresKeepTheirMeaning() async throws {
        for (status, code, failure) in [
            (403, "not_enabled", LioTaxiFailure.notEnabled),
            (429, "quota_exceeded", .quotaExceeded),
            (504, "supplier_timeout", .timedOut),
            (404, "not_found", .unavailable),
        ] {
            let relay = LioTaxiRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
                (Data(#"{"error":"\#(code)"}"#.utf8), response(try #require(request.url), status: status))
            }
            await #expect(throws: failure) {
                try await relay.search(.init(text: "天安门", city: .beijing, near: nil))
            }
        }
    }

    @Test func pickupCoordinatesChooseTheNearestSupportedCity() {
        #expect(LioTaxiCity.nearest(to: .init(latitude: 39.90, longitude: 116.40, referenceSystem: .wgs84)) == .beijing)
        #expect(LioTaxiCity.nearest(to: .init(latitude: 31.23, longitude: 121.47, referenceSystem: .gcj02)) == .shanghai)
        #expect(LioTaxiCity.nearest(to: near) == .chengdu)
        #expect(LioTaxiCity.nearest(to: .init(latitude: 29.65, longitude: 91.10, referenceSystem: .wgs84)) == nil)
    }

    @Test func everyCityHasBothNamesAndACommonExample() {
        #expect(Set(LioTaxiCity.allCases.map(\.nameZH)).count == LioTaxiCity.allCases.count)
        for city in LioTaxiCity.allCases {
            #expect(!city.nameEN.isEmpty)
            #expect(!city.exampleZH.isEmpty)
        }
    }

    @Test func noResultNoticeNamesTheQueryAndCityAndSuggestsWhatToTry() {
        let query = LioTaxiSearchQuery(text: "外摊", city: .shanghai, near: nil)
        let zh = LioTaxiSearchNotice.noMatches(for: query, language: .chinese)
        #expect(zh.contains("外摊") && zh.contains("上海") && zh.contains("外滩"))
        let en = LioTaxiSearchNotice.noMatches(for: query, language: .english)
        #expect(en.contains("外摊") && en.contains("Shanghai"))
    }

    @Test func failureNoticesDistinguishAccountLimitAndOutage() {
        let notices = [LioTaxiFailure.notEnabled, .quotaExceeded, .signInRequired, .timedOut, .unavailable,
                       .queryTooLong].map { LioTaxiSearchNotice.failure($0, language: .chinese) }
        #expect(Set(notices).count == notices.count)
        #expect(LioTaxiSearchNotice.failure(URLError(.notConnectedToInternet), language: .english)
            .localizedStandardContains("offline"))
    }

    #if DEBUG
    @Test func previewSearchFindsTheThreeCityAcceptancePlaces() async throws {
        let service = LioTaxiService.preview()
        for (text, city) in [("天安门", LioTaxiCity.beijing), ("外滩", .shanghai), ("宽窄巷子", .chengdu)] {
            let places = try await service.search(.init(text: text, city: city, near: nil))
            #expect(places.first?.nameZH.contains(text) == true)
        }
    }
    #endif
}
