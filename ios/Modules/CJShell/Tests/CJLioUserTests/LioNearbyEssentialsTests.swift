import Foundation
import Testing
@testable import CJLioUser

/// NEARBY.2 essentials (#1621): ATMs, pharmacies, public toilets and luggage storage found by name.
@MainActor struct LioNearbyEssentialsTests {
    private let base = URL(string: "https://example.invalid")!
    private let center = LioTaxiPlace.Coordinate(latitude: 39.9087, longitude: 116.3975, referenceSystem: .wgs84)
    private let requestID = UUID(uuidString: "8F14E45F-CEEA-4E7A-9C3B-2B0D4C1E9A10")!

    private func reply(_ version: String, _ codes: [String]) -> Data {
        let rows = codes.enumerated().map { index, code in
            #"{"id":"B\#(index)","name_zh":"地点\#(index)","address_zh":"示例路","type_code":"\#(code)","lat":39.91,"lng":116.40,"coordinate_system":"GCJ-02","distance_m":\#(100 * (index + 1))}"#
        }
        return Data(#"{"version":"\#(version)","source":"Gaode","items":[\#(rows.joined(separator: ","))]}"#.utf8)
    }

    private func body(_ categories: Set<LioNearbyPlace.Category>) throws -> [String: Any] {
        let data = try LioNearbyWire.encodeSearch(.init(center: center, categories: categories, radius: 1000, nearest: true),
                                                  requestID: requestID)
        return try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @Test func essentialsUseNearby2AndLeisureStaysOnNearby1() throws {
        #expect(try body([.atm])["version"] as? String == "NEARBY.2")
        #expect(try body([.atm])["categories"] as? [String] == ["atm"])
        #expect(try body([.pharmacy, .toilet])["categories"] as? [String] == ["pharmacy", "toilet"])
        #expect(try body([.luggage])["categories"] as? [String] == ["luggage"])
        // Leisure searches keep the frozen NEARBY.1 request, byte for byte as before.
        let leisure = try body([.food, .coffee])
        #expect(leisure["version"] as? String == "NEARBY.1")
        #expect(Set(leisure.keys) == ["version", "request_id", "center", "categories", "radius_m", "sort"])
    }

    @Test func luggageIsNeverRequestedWithOtherKinds() {
        for others in [[LioNearbyPlace.Category.toilet], [.food], [.atm, .pharmacy]] {
            #expect(throws: LioNearbyFailure.unavailable) { _ = try body(Set(others + [.luggage])) }
        }
        #expect(throws: LioNearbyFailure.unavailable) { _ = try body([.food, .sights, .coffee, .shopping, .atm]) }
    }

    @Test func oneEssentialLabelsEveryPlaceWithTheRequestedKind() throws {
        // Luggage storage is found by name: its places carry their own codes (a hotel, a shop) but are luggage storage.
        let luggage = try LioNearbyWire.readPlaces(reply("NEARBY.2", ["100105", "061000"]), requested: [.luggage])
        #expect(luggage.map(\.category) == [.luggage, .luggage])
        let atm = try LioNearbyWire.readPlaces(reply("NEARBY.2", ["160301"]), requested: [.atm])
        #expect(atm.first?.category == .atm)
        // Several essentials are told apart by code.
        let mixed = try LioNearbyWire.readPlaces(reply("NEARBY.2", ["090601", "200300", "160301"]), requested: [.pharmacy, .toilet])
        #expect(mixed.map(\.category) == [.pharmacy, .toilet, .atm])
        // A leisure search with one kind still reads each place's own code, as before.
        let food = try LioNearbyWire.readPlaces(reply("NEARBY.1", ["050101", "050500"]), requested: [.food])
        #expect(food.map(\.category) == [.food, .coffee])
    }

    @Test func aReplyFromTheOtherVersionIsRefused() {
        #expect(throws: LioNearbyFailure.unavailable) { _ = try LioNearbyWire.readPlaces(reply("NEARBY.1", ["160301"]), requested: [.atm]) }
        #expect(throws: LioNearbyFailure.unavailable) { _ = try LioNearbyWire.readPlaces(reply("NEARBY.2", ["050101"]), requested: [.food]) }
    }

    @Test func quotaAndMixedRequestErrorsKeepTheirMeaning() {
        #expect(LioNearbyWire.failure(status: 429, body: Data(#"{"error":"quota_exceeded"}"#.utf8)) == .quotaExceeded)
        #expect(LioNearbyWire.failure(status: 400, body: Data(#"{"error":"invalid_request"}"#.utf8)) == .unavailable)
    }

    @Test func fixedWordingNeverSaysAnATMTakesForeignCards() {
        #expect(LioNearbyPlace.Category.atm.heading(.chinese) == "银行 ATM（是否支持外卡请看机身标识）")
        #expect(LioNearbyPlace.Category.atm.heading(.english) == "Bank ATMs (check the machine's sign for foreign cards)")
        #expect(LioNearbyPlace.Category.luggage.heading(.chinese) == "行李寄存（按名称搜索，结果可能不全）")
        #expect(LioNearbyPlace.Category.luggage.heading(.english) == "Luggage storage (found by name; some may be missing)")
        #expect(LioNearbyPlace.Category.pharmacy.heading(.chinese) == "药房" && LioNearbyPlace.Category.toilet.heading(.english) == "Public toilets")
        for category in LioNearbyPlace.Category.essentials {
            for language in [LioLanguage.english, .chinese] {
                let text = category.heading(language) + category.title(language)
                #expect(!text.contains("支持外卡") || text.contains("是否支持外卡"))
                #expect(!text.lowercased().contains("accepts foreign"))
            }
        }
        #expect(LioNearbyPlace.Category.leisure.allSatisfy { !$0.isEssential })
        #expect(LioNearbyPlace.Category.essentials.allSatisfy { $0.isEssential })
    }

    @Test func essentialsStayOffUnlessTheBuildEnablesThem() {
        // Host tests run without the Info.plist key or the Debug launch argument.
        #expect(!LioNearbyPlace.essentialsEnabled)
    }
}
