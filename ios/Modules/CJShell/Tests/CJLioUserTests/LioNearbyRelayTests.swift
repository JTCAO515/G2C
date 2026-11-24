import Foundation
import Testing
@testable import CJLioUser

/// #1421 item 5 / #1428: Nearby uses the Hong Kong NEARBY.1 relay (Gaode around search, reverse address).
@MainActor struct LioNearbyRelayTests {
    private let base = URL(string: "https://example.invalid")!
    private let center = LioTaxiPlace.Coordinate(latitude: 39.9087, longitude: 116.3975, referenceSystem: .wgs84)
    private let requestID = UUID(uuidString: "8F14E45F-CEEA-4E7A-9C3B-2B0D4C1E9A10")!

    private func response(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
    }

    private let items = Data("""
    {"version":"NEARBY.1","source":"Gaode","items":[
      {"id":"B000A1","name_zh":"四季民福烤鸭店","address_zh":"东华门大街","type_code":"050101","lat":39.9142,"lng":116.4035,
       "coordinate_system":"GCJ-02","distance_m":"ignored","rating":"4.7","cost_cny":"180","opening_hours":"10:30-22:00",
       "photo_url":"https://store.is.autonavi.com/showpic/a.jpg"},
      {"id":"B000A2","name_zh":"街角咖啡","address_zh":null,"type_code":"050500","lat":39.9100,"lng":116.4000,
       "coordinate_system":"GCJ-02","distance_m":320,"rating":null,"cost_cny":null,"opening_hours":null,"photo_url":null},
      {"id":"B000A3","name_zh":"故宫博物院","address_zh":"景山前街4号","type_code":"110201","lat":39.9163,"lng":116.3972,
       "coordinate_system":"GCJ-02","distance_m":850}
    ]}
    """.utf8)

    @Test func searchPostsTheContractFieldsAndReadsGCJPlaces() async throws {
        var bodies = [[String: Any]]()
        var paths = [String]()
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { request in
            let url = try #require(request.url)
            paths.append(url.path)
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-only")
            let raw = try #require(request.httpBody)
            bodies.append(try #require(try JSONSerialization.jsonObject(with: raw) as? [String: Any]))
            return (items, response(url, status: 200))
        }

        let places = try await relay.search(.init(center: center, categories: [.food, .coffee], radius: 1000, nearest: true))

        #expect(paths == ["/v1/tools/nearby/search"])
        let body = try #require(bodies.first)
        #expect(Set(body.keys) == ["version", "request_id", "center", "categories", "radius_m", "sort"])
        #expect(body["version"] as? String == "NEARBY.1")
        #expect(body["request_id"] as? String == "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10")
        #expect(body["categories"] as? [String] == ["food", "coffee"])
        #expect(body["radius_m"] as? Int == 1000)
        #expect(body["sort"] as? String == "distance")
        let point = try #require(body["center"] as? [String: Any])
        #expect(point["coordinate_system"] as? String == "WGS-84")
        #expect(Set(point.keys) == ["lat", "lng", "coordinate_system"])

        #expect(places.map(\.id) == ["B000A1", "B000A2", "B000A3"])
        let duck = try #require(places.first)
        #expect(duck.name == "四季民福烤鸭店")
        #expect(duck.coordinate == .init(latitude: 39.9142, longitude: 116.4035, referenceSystem: .gcj02))
        #expect(duck.category == .food && places[1].category == .coffee && places[2].category == .sights)
        #expect(duck.rating == "4.7" && duck.cost == "¥180" && duck.hours == "10:30-22:00")
        #expect(duck.meters == nil, "a non-integer distance is dropped, not invented")
        #expect(places[1].meters == 320 && places[1].address == nil)
        #expect(duck.photo?.host == "store.is.autonavi.com")
    }

    @Test func recommendedSortAndOrderedUniqueCategories() throws {
        let data = try LioNearbyWire.encodeSearch(.init(center: center, categories: [.shopping, .food, .sights],
                                                        radius: 500, nearest: false), requestID: requestID)
        let body = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(body["sort"] as? String == "relevance")
        #expect(body["categories"] as? [String] == ["food", "sights", "shopping"])
    }

    @Test func emptyCategoriesOrUnsupportedRadiusAreNotSent() async throws {
        var sends = 0
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { request in
            sends += 1
            return (items, response(try #require(request.url), status: 200))
        }
        #expect(try await relay.search(.init(center: center, categories: [], radius: 500, nearest: false)).isEmpty)
        await #expect(throws: LioNearbyFailure.unavailable) {
            try await relay.search(.init(center: center, categories: [.food], radius: 700, nearest: false))
        }
        #expect(sends == 0)
    }

    @Test func reverseReadsTheChineseAddress() async throws {
        var paths = [String]()
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { request in
            let url = try #require(request.url)
            paths.append(url.path)
            let raw = try #require(request.httpBody)
            let body = try #require(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
            #expect(Set(body.keys) == ["version", "request_id", "center"])
            return (Data(#"{"version":"NEARBY.1","source":"Gaode","address_zh":"北京市东城区东华门街道"}"#.utf8),
                    response(url, status: 200))
        }
        #expect(try await relay.reverse(center) == "北京市东城区东华门街道")
        #expect(paths == ["/v1/tools/nearby/reverse"])
    }

    @Test func malformedRepliesAreRejected() throws {
        for body in [
            #"{"version":"NEARBY.2","source":"Gaode","items":[]}"#,
            #"{"version":"NEARBY.1","source":"Other","items":[]}"#,
            #"{"version":"NEARBY.1","source":"Gaode","items":[{"id":"x","name_zh":"A","type_code":"050101","lat":95,"lng":116,"coordinate_system":"GCJ-02"}]}"#,
            #"{"version":"NEARBY.1","source":"Gaode","items":[{"id":"x","name_zh":"A","type_code":"050101","lat":39,"lng":116,"coordinate_system":"WGS-84"}]}"#,
            #"{"version":"NEARBY.1","source":"Gaode","items":[{"id":"","name_zh":"A","type_code":"050101","lat":39,"lng":116,"coordinate_system":"GCJ-02"}]}"#,
        ] {
            #expect(throws: (any Error).self) { try LioNearbyWire.readPlaces(Data(body.utf8)) }
        }
        #expect(try LioNearbyWire.readPlaces(Data(#"{"version":"NEARBY.1","source":"Gaode","items":[]}"#.utf8)).isEmpty)
    }

    @Test func untrustedPhotoLinksAreDropped() throws {
        let body = #"{"version":"NEARBY.1","source":"Gaode","items":[{"id":"x","name_zh":"A","type_code":"050101","lat":39,"lng":116,"coordinate_system":"GCJ-02","photo_url":"https://evil.example/a.jpg"}]}"#
        #expect(try LioNearbyWire.readPlaces(Data(body.utf8)).first?.photo == nil)
    }

    @Test func failuresKeepTheirMeaningAndTheSessionGate() async throws {
        for (status, code, failure) in [
            (401, "sign_in_required", LioNearbyFailure.signInRequired),
            (403, "not_enabled", .notEnabled),
            (429, "quota_exceeded", .quotaExceeded),
            (429, "rate_limited", .rateLimited),
            (504, "supplier_timeout", .timedOut),
            (502, "supplier_unavailable", .unavailable),
        ] {
            let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                             newRequestID: { requestID }) { request in
                (Data(#"{"error":"\#(code)"}"#.utf8), response(try #require(request.url), status: status))
            }
            await #expect(throws: failure) { try await relay.reverse(center) }
        }
        var sends = 0
        let signedOut = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { nil },
                                             newRequestID: { requestID }) { request in
            sends += 1
            return (items, response(try #require(request.url), status: 200))
        }
        await #expect(throws: LioNearbyFailure.signInRequired) { try await signedOut.reverse(center) }
        #expect(sends == 0)
    }

    @Test func lateRepliesAfterASessionChangeAreDiscarded() async throws {
        var current = true
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { current }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { request in
            current = false
            return (items, response(try #require(request.url), status: 200))
        }
        await #expect(throws: CancellationError.self) {
            try await relay.search(.init(center: center, categories: [.food], radius: 500, nearest: false))
        }
    }

    @Test func aRetiredSessionSendsNothing() async throws {
        var sends = 0
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { false }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { request in
            sends += 1
            return (items, response(try #require(request.url), status: 200))
        }
        await #expect(throws: LioNearbyFailure.signInRequired) { try await relay.reverse(center) }
        #expect(sends == 0)
    }

    @Test func aReplyFromAnotherOriginIsRejected() async throws {
        let foreign = URL(string: "https://other.example.invalid/v1/tools/nearby/search")!
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { _ in (items, response(foreign, status: 200)) }
        await #expect(throws: LioNearbyFailure.unavailable) {
            try await relay.search(.init(center: center, categories: [.food], radius: 500, nearest: false))
        }
    }
}
