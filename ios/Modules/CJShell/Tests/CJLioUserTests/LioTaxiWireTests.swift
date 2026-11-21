import Foundation
import Testing
@testable import CJLioUser

struct LioTaxiWireTests {
    @Test func requestContainsOnlyTheContractFieldsAndKeepsCoordinateSystems() throws {
        let pickup = LioTaxiPlace(nameZH: "示例起点", nameEN: "Pickup", addressZH: "不发送此地址",
                                  coordinate: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .wgs84))
        let destination = LioTaxiPlace(nameZH: "示例终点", nameEN: "Destination", addressZH: nil,
                                       coordinate: .init(latitude: 40.05, longitude: 116.3, referenceSystem: .gcj02))
        let bytes = try LioTaxiWire.encode(.init(pickup: pickup, destination: destination))
        let body = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let origin = try #require(body["origin"] as? [String: Any])
        let end = try #require(body["destination"] as? [String: Any])
        #expect(Set(body.keys) == ["version", "origin", "destination"])
        #expect(body["version"] as? String == "TAXI.1")
        #expect(Set(origin.keys) == ["lat", "lng", "coordinate_system", "name"])
        #expect(origin["coordinate_system"] as? String == "WGS-84")
        #expect(end["coordinate_system"] as? String == "GCJ-02")
        #expect(end["lat"] as? Double == 40.05)
    }

    @Test func displayOnlyQuoteKeepsTheProviderPriceText() throws {
        let data = Data("""
        {"version":"TAXI.1","observed_at":"2026-11-21T00:00:00.123Z","vehicles":[
          {"category":"standard","name":"Standard","currency":"CNY","price_display":"Price after pickup"}
        ]}
        """.utf8)
        let fare = try #require(LioTaxiWire.readFares(data).first)
        if case .description(let text) = fare.price {
            #expect(text == "Price after pickup")
        } else {
            Issue.record("A price range was invented from a text quote")
        }
    }

    @Test func linksRequireATargetAllowedByTheCaller() throws {
        let data = Data(#"{"version":"TAXI.1","url":"https://example.invalid/ride-preview","link_type":"https"}"#.utf8)
        #expect(throws: LioTaxiFailure.unavailable) { try LioTaxiWire.readLink(data) { _, _ in false } }
        let accepted = try LioTaxiWire.readLink(data) { type, url in
            type == .https && url.host == "example.invalid" && url.path == "/ride-preview"
        }
        #expect(accepted.host == "example.invalid")
        let mismatch = Data(#"{"version":"TAXI.1","url":"http://example.invalid/ride-preview","link_type":"https"}"#.utf8)
        #expect(throws: LioTaxiFailure.unavailable) { try LioTaxiWire.readLink(mismatch) { _, _ in true } }
        let wrongVersion = Data(#"{"version":"TAXI.2","url":"https://example.invalid/ride-preview","link_type":"https"}"#.utf8)
        #expect(throws: LioTaxiFailure.unavailable) { try LioTaxiWire.readLink(wrongVersion) { _, _ in true } }
    }

    @Test func matchedErrorStatusDistinguishesQuotaFromThrottling() {
        let quota = Data(#"{"error":"quota_exceeded"}"#.utf8)
        let throttle = Data(#"{"error":"rate_limited"}"#.utf8)
        let disabled = Data(#"{"error":"not_enabled"}"#.utf8)
        #expect(LioTaxiWire.failure(status: 429, body: quota) == .quotaExceeded)
        #expect(LioTaxiWire.failure(status: 429, body: throttle) == .rateLimited)
        #expect(LioTaxiWire.failure(status: 403, body: disabled) == .notEnabled)
        #expect(LioTaxiWire.failure(status: 502, body: throttle) == .unavailable)
    }
}
