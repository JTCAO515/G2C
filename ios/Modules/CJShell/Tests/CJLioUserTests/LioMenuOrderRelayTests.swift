import Foundation
import Testing
@testable import CJLioUser

/// MENU.1 (#1583): the App sends one photo and reads back checked dishes; anything off-contract is refused.
struct LioMenuWireTests {
    static let jpeg = Data([0xff, 0xd8, 0xff, 0xe0]) + Data(repeating: 0, count: 32)

    static func dish(_ id: String = "l2", _ changes: [String: Any] = [:]) -> [String: Any] {
        var value: [String: Any] = [
            "id": id, "kind": "dish", "name_zh": "宫保鸡丁", "name_en": "Kung Pao Chicken",
            "summary_en": "Chicken with peanuts.", "summary_zh": "鸡丁与花生同炒。",
            "ingredients_en": "Chicken, peanuts", "ingredients_zh": "鸡肉、花生", "method_en": "Stir-fried",
            "method_zh": "爆炒", "portion_en": "About 2 people", "portion_zh": "约 2 人份", "spice": 2,
            "contains": ["poultry": "likely", "peanut": "likely", "tree_nut": "possible", "animal_broth": "possible"],
            "price_text": "¥38",
        ]
        for (key, change) in changes { value[key] = change }
        return value
    }

    static func body(_ items: [[String: Any]], version: String = "MENU.1", truncated: Bool = false,
                     extra: [String: Any] = [:]) -> Data {
        var value: [String: Any] = ["version": version, "truncated": truncated, "items": items]
        for (key, change) in extra { value[key] = change }
        return try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }

    @Test func requestCarriesOnlyVersionIDAndPhoto() throws {
        let id = UUID()
        let body = try LioMenuWire.encode(jpeg: Self.jpeg, requestID: id)
        let value = try #require(try JSONSerialization.jsonObject(with: body) as? [String: String])
        #expect(Set(value.keys) == ["version", "request_id", "media"])
        #expect(value["version"] == "MENU.1")
        #expect(value["request_id"] == id.uuidString.lowercased())
        #expect(Data(base64Encoded: value["media"] ?? "") == Self.jpeg)
        #expect(throws: LioMenuFailure.unreadablePhoto) { try LioMenuWire.encode(jpeg: Data("GIF89a".utf8), requestID: id) }
        #expect(throws: LioMenuFailure.unreadablePhoto) {
            try LioMenuWire.encode(jpeg: Self.jpeg + Data(count: 3 * 1024 * 1024), requestID: id)
        }
    }

    @Test func readsDishesAndUnclearLines() throws {
        let reading = try LioMenuWire.read(Self.body([
            Self.dish(), ["id": "l4", "kind": "unclear", "price_text": NSNull()],
        ], truncated: true))
        #expect(reading.truncated && !reading.isSample)
        let dish = reading.dishes[0]
        #expect(dish.id == "l2" && dish.nameZH == "宫保鸡丁" && dish.spice == .medium && dish.priceText == "¥38")
        #expect(dish.contains == [.poultry: .likely, .peanut: .likely, .treeNut: .possible, .animalBroth: .possible])
        let unclear = reading.dishes[1]
        #expect(!unclear.isLegible && unclear.priceText == nil && unclear.contains.isEmpty && unclear.spice == nil)
    }

    @Test func unknownSpiceIsNotGuessed() throws {
        let reading = try LioMenuWire.read(Self.body([Self.dish("l0", ["spice": NSNull()])]))
        #expect(reading.dishes[0].spice == nil)
    }

    @Test(arguments: [
        body([dish("l1"), dish("l1")]),
        body([dish("x1")]),
        body([dish("l1", ["kind": "dessert"])]),
        body([dish("l1", ["contains": ["msg": "likely"]])]),
        body([dish("l1", ["contains": ["peanut": "maybe"]])]),
        body([dish("l1", ["spice": 4])]),
        body([dish("l1", ["name_zh": " "])]),
        body([dish("l1", ["extra": "field"])]),
        body([["id": "l1", "kind": "unclear", "price_text": NSNull(), "name_zh": "猜的"]]),
        body([dish("l1")], version: "MENU.2"),
        body([dish("l1")], extra: ["user": "someone"]),
        body((0..<51).map { dish("l\($0)") }),
        Data(#"{"version":"MENU.1","version":"MENU.1","truncated":false,"items":[]}"#.utf8),
    ])
    func offContractRepliesAreRefused(_ body: Data) {
        #expect(throws: LioMenuFailure.unavailable) { try LioMenuWire.read(body) }
    }

    @Test(arguments: [(401, LioMenuFailure.signInRequired), (403, .notEnabled), (409, .alreadyUsed),
                      (429, .quota), (500, .unavailable), (502, .unavailable), (418, .unavailable)])
    func statusesBecomeFailures(_ status: Int, _ failure: LioMenuFailure) {
        #expect(LioMenuWire.failure(status: status) == failure)
    }
}

@MainActor struct LioMenuRelayClientTests {
    private let base = URL(string: "https://api.example.invalid/")!

    @Test func postsThePhotoWithTheBearer() async throws {
        var sent: URLRequest?
        let client = LioMenuRelayClient(baseURL: base, isCurrent: { true }, bearer: { "token" }) { request in
            sent = request
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (LioMenuWireTests.body([LioMenuWireTests.dish()]), response)
        }
        let reading = try await client.read(LioMenuWireTests.jpeg)
        #expect(reading.dishes.count == 1)
        #expect(sent?.url?.absoluteString == "https://api.example.invalid/v1/tools/menu/explain")
        #expect(sent?.httpMethod == "POST")
        #expect(sent?.value(forHTTPHeaderField: "Authorization") == "Bearer token")
    }

    @Test func signedOutSendsNothing() async {
        var calls = 0
        let client = LioMenuRelayClient(baseURL: base, isCurrent: { true }, bearer: { nil }) { request in
            calls += 1
            return (Data(), URLResponse())
        }
        await #expect(throws: LioMenuFailure.signInRequired) { try await client.read(LioMenuWireTests.jpeg) }
        #expect(calls == 0)
    }

    @Test func answersFromAnotherURLAreRefused() async {
        let client = LioMenuRelayClient(baseURL: base, isCurrent: { true }, bearer: { "token" }) { _ in
            let other = URL(string: "https://elsewhere.example.invalid/v1/tools/menu/explain")!
            return (LioMenuWireTests.body([]), HTTPURLResponse(url: other, statusCode: 200, httpVersion: nil,
                                                                 headerFields: nil)!)
        }
        await #expect(throws: LioMenuFailure.unavailable) { try await client.read(LioMenuWireTests.jpeg) }
    }

    @Test func quotaAnswersSaySo() async {
        let client = LioMenuRelayClient(baseURL: base, isCurrent: { true }, bearer: { "token" }) { request in
            (Data(#"{"code":"quota_exceeded"}"#.utf8),
             HTTPURLResponse(url: request.url!, statusCode: 429, httpVersion: nil, headerFields: nil)!)
        }
        await #expect(throws: LioMenuFailure.quota) { try await client.read(LioMenuWireTests.jpeg) }
    }

    @Test func theBuildSwitchTurnsTheRelayOn() async throws {
        let client = LioMenuRelayClient(baseURL: base, isCurrent: { true }, bearer: { "token" }) { request in
            (LioMenuWireTests.body([]), HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                                        headerFields: nil)!)
        }
        let relay = LioMenuService.relay(client)
        #expect(LioMenuService.fromBuild(arguments: [], info: [:], relay: relay) == nil)
        let service = try #require(LioMenuService.fromBuild(arguments: [], info: ["G2CMenuOrderEnabled": "YES"],
                                                            relay: relay))
        #expect(try await service.read(LioMenuWireTests.jpeg).dishes.isEmpty)
    }
}
