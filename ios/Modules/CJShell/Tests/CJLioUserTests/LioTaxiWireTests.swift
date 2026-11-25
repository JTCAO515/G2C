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
        #expect(fare.priceDisplay == "Price after pickup")
    }

    @Test func publishedQuoteUsesTheRangeAndNamesUnknownCategoriesGenerically() throws {
        let response = Data("""
        {"version":"TAXI.1","observed_at":"2026-11-23T00:00:00Z","vehicles":[
          {"category":"1","name":"快车","currency":"CNY","price_display":"约¥35","price_min_minor":3000,"price_max_minor":4200},
          {"category":"201","name":"特惠快车","currency":"CNY","price_display":"¥28起"},
          {"category":"8","name":"专车","currency":"CNY","price_display":"约¥70"},
          {"category":"99","name":"滴滴定制车","currency":"CNY","price_display":"¥52–65"}
        ]}
        """.utf8)
        let fares = try LioTaxiWire.readFares(response)
        #expect(fares.map(\.nameEN) == ["Express", "Discount Express", "Premier", "Other ride option"])
        #expect(fares.map(\.nameZH) == ["快车", "特惠快车", "专车", "滴滴定制车"])
        // A published range wins over the display text; display text that already has a currency is kept.
        #expect(fares.map(\.priceDisplay) == ["¥30–42", "¥28起", "约¥70", "¥52–65"])
    }

    /// #1451: build 54 showed these untranslated and with bare numbers.
    @Test func everyRideOptionGetsAnEnglishNameAndAYuanPrice() throws {
        let response = Data("""
        {"version":"TAXI.1","observed_at":"2026-11-24T00:00:00Z","vehicles":[
          {"category":"314","name":"惊喜特价","currency":"CNY","price_display":"29"},
          {"category":"260","name":"滴滴轻享","currency":"CNY","price_display":"31-36"},
          {"category":"16","name":"六座专车","currency":"CNY","price_display":"88"},
          {"category":"4","name":"豪华车","currency":"CNY","price_display":"126","price_min_minor":12600,"price_max_minor":12600},
          {"category":"77","name":"Taxi","currency":"CNY","price_display":"¥40"}
        ]}
        """.utf8)
        let fares = try LioTaxiWire.readFares(response)
        #expect(fares.map(\.nameEN) == ["Surprise Deal", "DiDi Lite", "6-Seat Premier", "Luxe", "Taxi"])
        #expect(fares.map(\.priceDisplay) == ["¥29", "¥31–36", "¥88", "¥126", "¥40"])
        #expect(LioTaxiFareText.price(display: "35", currency: "CNY", minMinor: 3550, maxMinor: 4800) == "¥35.5–48")
        #expect(LioTaxiFareText.price(display: "", currency: "CNY", minMinor: 3505, maxMinor: 3505) == "¥35.05")
        #expect(LioTaxiFareText.price(display: "", currency: "CNY", minMinor: 99, maxMinor: 120) == "¥0.99–1.2")
        let taxi = try #require(fares.last)
        #expect(taxi.secondaryName(in: .english) == nil && fares.first?.secondaryName(in: .english) == "惊喜特价")
        #expect(fares.first?.secondaryName(in: .chinese) == nil)
        #expect(LioTaxiFareText.price(display: "Price after pickup", currency: "CNY", minMinor: nil, maxMinor: nil)
            == "Price after pickup")
    }

    /// #1451: English screens ask for English names with `locale: "en"`; Chinese requests are unchanged.
    @Test func englishSearchesAskForEnglishNames() throws {
        let english = try JSONSerialization.jsonObject(with: LioTaxiWire.encodeSearch(
            .init(text: "Canton Tower", city: .guangzhou, near: nil, english: true))) as? [String: Any]
        #expect(english?["locale"] as? String == "en")
        let chinese = try LioTaxiWire.encodeSearch(.init(text: "广州塔", city: .guangzhou, near: nil))
        let keys = (try JSONSerialization.jsonObject(with: chinese) as? [String: Any])?.keys.sorted()
        #expect(keys == ["city", "query", "version"])
        #expect(!String(decoding: chinese, as: UTF8.self).contains("locale"))
    }

    /// #1451: English screens lead with name_en / address_en; the driver still gets Chinese.
    @Test func englishPlaceFieldsAreOptionalAndLeadOnEnglishScreens() throws {
        let data = Data("""
        {"version":"TAXI.1","items":[
          {"name_zh":"广州塔","name_en":"Canton Tower","address_zh":"阅江西路222号","address_en":"222 Yuejiang West Rd",
           "city":"广州","lat":23.1065,"lng":113.3245,"coordinate_system":"GCJ-02"},
          {"name_zh":"天河城","address_zh":"天河路208号","city":"广州","lat":23.1322,"lng":113.3226,"coordinate_system":"GCJ-02"}
        ]}
        """.utf8)
        let places = try LioTaxiWire.readPlaces(data)
        let tower = try #require(places.first), mall = try #require(places.last)
        #expect(tower.name(in: .english) == "Canton Tower" && tower.secondaryName(in: .english) == "广州塔")
        #expect(tower.address(in: .english) == "222 Yuejiang West Rd" && tower.address(in: .chinese) == "阅江西路222号")
        #expect(tower.secondaryName(in: .chinese) == nil && tower.addressZH == "阅江西路222号")
        #expect(mall.name(in: .english) == "天河城" && mall.secondaryName(in: .english) == nil)
        #expect(mall.address(in: .english) == "天河路208号" && mall.addressEN == nil)
        // Saved places from before #1451 have no English address and still decode.
        let saved = Data(#"{"nameZH":"外滩","nameEN":"The Bund","addressZH":"中山东一路","coordinate":{"latitude":31.24,"longitude":121.49,"referenceSystem":"gcj02"}}"#.utf8)
        #expect(try JSONDecoder().decode(LioTaxiPlace.self, from: saved).addressEN == nil)
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
