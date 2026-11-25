import Foundation
import Testing
@testable import CJLioUser

/// #1450 station surroundings (METRO-NEARBY.1, M4 entry 12 item 5): the App names a station, never a position.
@MainActor struct LioMetroNearbyTests {
    private let base = URL(string: "https://example.invalid")!
    private let requestID = UUID(uuidString: "8F14E45F-CEEA-4E7A-9C3B-2B0D4C1E9A10")!

    private func response(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
    }

    private let reply = Data("""
    {"version":"METRO-NEARBY.1","source":"Gaode","city_id":"guangzhou","station_id":"gz012","radius_m":800,"items":[
      {"id":"B001","name_zh":"天河城","name_en":"Teemall","address_zh":"天河路208号","address_en":"208 Tianhe Road",
       "type_code":"060101","lat":23.1325,"lng":113.3227,"coordinate_system":"GCJ-02","distance_m":312,"rating":"4.6",
       "cost_cny":null,"opening_hours":null,"photo_url":null},
      {"id":"B002","name_zh":"正佳广场","address_zh":null,"type_code":"060100","lat":23.1330,"lng":113.3260,
       "coordinate_system":"GCJ-02","distance_m":null,"rating":null}
    ]}
    """.utf8)

    @Test func theRequestNamesTheStationOnly() throws {
        let body = try LioMetroNearbyWire.encode(city: "guangzhou", station: "gz012", categories: [.shopping, .sights],
                                                 language: .english, requestID: requestID)
        let object = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(Set(object.keys) == ["version", "request_id", "city_id", "station_id", "categories", "language"])
        #expect(object["version"] as? String == "METRO-NEARBY.1")
        #expect(object["request_id"] as? String == "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10")
        #expect(object["city_id"] as? String == "guangzhou" && object["station_id"] as? String == "gz012")
        #expect(object["categories"] as? [String] == ["sights", "shopping"])
        #expect(object["language"] as? String == "en")
        #expect(throws: LioNearbyFailure.unavailable) {
            try LioMetroNearbyWire.encode(city: "guangzhou", station: "gz012", categories: [], language: .chinese,
                                          requestID: requestID)
        }
    }

    @Test func readsPlacesForTheStationAskedAbout() throws {
        let places = try LioMetroNearbyWire.read(reply, city: "guangzhou", station: "gz012")
        #expect(places.map(\.id) == ["B001", "B002"])
        let mall = try #require(places.first)
        #expect(mall.name(in: .english) == "Teemall" && mall.name(in: .chinese) == "天河城")
        #expect(mall.category == .shopping && mall.meters == 312 && mall.walkingMinutes == 4 && mall.rating == "4.6")
        #expect(mall.coordinate == .init(latitude: 23.1325, longitude: 113.3227, referenceSystem: .gcj02))
        #expect(mall.taxiPlace.nameZH == "天河城" && mall.taxiPlace.addressZH == "天河路208号")
        // No English name: the Chinese one stands in.
        #expect(places[1].name(in: .english) == "正佳广场" && places[1].walkingMinutes == nil)
        // An answer about another station, or with repeated places, is not shown.
        #expect(throws: LioNearbyFailure.unavailable) { try LioMetroNearbyWire.read(reply, city: "guangzhou", station: "gz013") }
        let repeated = Data(String(decoding: reply, as: UTF8.self).replacingOccurrences(of: "\"B002\"", with: "\"B001\"").utf8)
        #expect(throws: LioNearbyFailure.unavailable) { try LioMetroNearbyWire.read(repeated, city: "guangzhou", station: "gz012") }
    }

    @Test func theRelayPostsToTheStationRouteAndMapsRefusals() async throws {
        // One mutable script the exchange reads; a class, so the closure captures a reference, not a var.
        final class Script { var paths = [String](); var status = 200; var answer = Data() }
        let script = Script()
        script.answer = reply
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                         newRequestID: { requestID }) { request in
            let url = try #require(request.url)
            script.paths.append(url.path)
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-only")
            return (script.answer, response(url, status: script.status))
        }
        let body = try LioMetroNearbyWire.encode(city: "guangzhou", station: "gz012", categories: [.shopping],
                                                 language: .chinese, requestID: requestID)
        #expect(try LioMetroNearbyWire.read(try await relay.metroNearby(body), city: "guangzhou", station: "gz012").count == 2)
        #expect(script.paths == ["/v1/tools/metro/nearby"])
        for (code, body, failure) in [(429, #"{"error":"quota_exceeded"}"#, LioNearbyFailure.quotaExceeded),
                                      (403, #"{"error":"not_enabled"}"#, .notEnabled),
                                      (404, #"{"error":"station_not_found"}"#, .unavailable)] {
            script.status = code
            script.answer = Data(body.utf8)
            await #expect(throws: failure) { try await relay.metroNearby(Data()) }
        }
    }

    @Test func offUnlessTheBuildEnablesIt() {
        let relay = LioNearbyRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { _ in
            throw LioNearbyFailure.unavailable
        }
        // The test bundle has no G2CMetroNearbyEnabled: the service is absent and the station sheet shows no section.
        #expect(LioMetroNearbyService.internalBeta(relay: relay, bundle: Bundle(for: BundleMarker.self)) == nil)
    }
}

private final class BundleMarker {}
