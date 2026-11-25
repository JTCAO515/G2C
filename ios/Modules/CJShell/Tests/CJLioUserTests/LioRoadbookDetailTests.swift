import Foundation
import PDFKit
import Testing
@testable import CJLioUser

/// #1509 / ROADBOOK.1: the App asks the relay to fill in each place, keeps the answer with the offline copy
/// and prints it in the PDF. Only public place names and the city leave the phone.
@MainActor struct LioRoadbookDetailTests {
    static let reply = """
    {"version":"ROADBOOK.1","places":[
     {"id":"d1s2","status":"ready","poi_id":"B000A8UIN8",
      "content":{"zh":{"summary":"明清两代的皇宫。","why_go":"中轴线上最大的古建筑群。","time_needed":"约 3 小时",
        "hours_booking":"周二至周日 08:30-17:00，需提前实名预约，以官方为准。","tickets":"约 40–60 元，以官方为准。",
        "getting_there":"地铁 1 号线天安门东站。","food_tip":"附近可就餐：四季民福烤鸭店(故宫店)（约 450 米）。","notes":"入口安检，带好护照。"},
       "en":{"summary":"The Ming and Qing imperial palace.","why_go":"The largest old complex on the axis.",
        "time_needed":"About 3 hours","hours_booking":"Tue–Sun 08:30-17:00; book ahead. Check official sources.",
        "tickets":"About 40–60 yuan; check official sources.","getting_there":"Line 1 to Tian'anmen East.",
        "food_tip":"Places to eat nearby: 四季民福烤鸭店(故宫店) (about 450 m).","notes":"Security check; bring your passport."}},
      "metro":[{"name_zh":"天安门东站","distance_m":620}],
      "restaurants":[{"name_zh":"四季民福烤鸭店(故宫店)","address_zh":"东华门大街32号","lat":39.913,"lng":116.403,"distance_m":450}]},
     {"id":"d1s3","status":"limited"},{"id":"d1s4","status":"unavailable"}]}
    """

    static let places = [
        LioRoadbookPlaceQuery(id: "d1s2", nameZH: "故宫博物院", nameEN: "Palace Museum", city: "北京", poiID: nil),
        LioRoadbookPlaceQuery(id: "d1s3", nameZH: "景山公园", nameEN: nil, city: "北京", poiID: "B000A7BGMG"),
        LioRoadbookPlaceQuery(id: "d1s4", nameZH: "某处", nameEN: nil, city: "北京", poiID: nil),
    ]

    @Test func theRequestCarriesOnlyPublicNamesAndTheCity() throws {
        let id = UUID(uuidString: "8F14E45F-CEEA-4E7A-9C3B-2B0D4C1E9A10")!
        let body = try JSONSerialization.jsonObject(with: LioRoadbookWire.encode(Self.places, requestID: id)) as? [String: Any]
        #expect(body?["version"] as? String == "ROADBOOK.1")
        #expect(body?["request_id"] as? String == "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10")
        let sent = try #require(body?["places"] as? [[String: String]])
        #expect(sent[0] == ["id": "d1s2", "name_zh": "故宫博物院", "name_en": "Palace Museum", "city": "北京"])
        #expect(sent[1] == ["id": "d1s3", "name_zh": "景山公园", "city": "北京", "poi_id": "B000A7BGMG"])
        #expect(Set(sent.flatMap(\.keys)).isSubset(of: ["id", "name_zh", "name_en", "city", "poi_id"]))
    }

    @Test func readyPlacesBecomeDetailsAndOthersKeepTheirStatus() throws {
        let result = try LioRoadbookWire.read(Data(Self.reply.utf8), asked: Self.places.map(\.id))
        let detail = try #require(result["d1s2"]?.detail)
        #expect(detail.poiID == "B000A8UIN8")
        #expect(detail.field(.tickets, .chinese) == "约 40–60 元，以官方为准。")
        #expect(detail.field(.whyGo, .english) == "The largest old complex on the axis.")
        #expect(detail.metro == [.init(nameZH: "天安门东站", distanceMetres: 620)])
        let restaurant = try #require(detail.restaurants.first)
        #expect(restaurant.taxiPlace.nameZH == "四季民福烤鸭店(故宫店)")
        #expect(restaurant.taxiPlace.addressZH == "东华门大街32号")
        #expect(restaurant.taxiPlace.coordinate.referenceSystem == .gcj02)
        #expect(result["d1s3"] == .limited && result["d1s4"] == .unavailable)
    }

    @Test func malformedOrUnaskedRepliesAreRefused() {
        let unasked = Self.reply.replacingOccurrences(of: "\"d1s4\"", with: "\"other\"")
        #expect(throws: LioRoadbookFailure.unavailable) {
            try LioRoadbookWire.read(Data(unasked.utf8), asked: Self.places.map(\.id))
        }
        let missingField = Self.reply.replacingOccurrences(of: "\"notes\":\"入口安检，带好护照。\"", with: "\"x\":\"y\"")
        #expect(throws: LioRoadbookFailure.unavailable) {
            try LioRoadbookWire.read(Data(missingField.utf8), asked: Self.places.map(\.id))
        }
        #expect(throws: LioRoadbookFailure.unavailable) {
            try LioRoadbookWire.read(Data("{}".utf8), asked: ["d1s2"])
        }
    }

    @Test func relayErrorsMapToPlainOutcomes() {
        func code(_ status: Int, _ error: String) -> LioRoadbookFailure {
            LioRoadbookWire.failure(status: status, body: Data("{\"error\":\"\(error)\"}".utf8))
        }
        #expect(code(401, "sign_in_required") == .signInRequired)
        #expect(code(403, "not_enabled") == .notEnabled)
        #expect(code(409, "request_already_used") == .unavailable)
        #expect(code(429, "quota_exceeded") == .limited)
        #expect(code(503, "unavailable") == .unavailable)
        for failure in [LioRoadbookFailure.signInRequired, .notEnabled, .limited, .unavailable, .timedOut] {
            #expect(!failure.message(.english).isEmpty && !failure.message(.chinese).isEmpty)
        }
    }

    @Test func theRelayClientPostsWithTheCurrentSessionOnly() async throws {
        var sent: URLRequest?
        let base = URL(string: "https://relay.example.invalid/")!
        let client = LioRoadbookRelayClient(baseURL: base, isCurrent: { true }, bearer: { "token" },
                                            newRequestID: { UUID() }) { request in
            sent = request
            return (Data(Self.reply.utf8), HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
        let result = try await client.enrich(Self.places)
        #expect(sent?.url?.absoluteString == "https://relay.example.invalid/v1/tools/roadbook/places")
        #expect(sent?.httpMethod == "POST" && sent?.value(forHTTPHeaderField: "Authorization") == "Bearer token")
        #expect(result["d1s2"]?.detail != nil)

        let signedOut = LioRoadbookRelayClient(baseURL: base, isCurrent: { false }, bearer: { "token" }) { _ in
            Issue.record("must not send"); throw URLError(.cancelled)
        }
        await #expect(throws: LioRoadbookFailure.signInRequired) { try await signedOut.enrich(Self.places) }
    }

    @Test func atMostEightPlacesGoInOneRequest() {
        let many = (1...19).map { LioRoadbookPlaceQuery(id: "s\($0)", nameZH: "地点\($0)", nameEN: nil, city: "北京", poiID: nil) }
        #expect(LioRoadbookWire.batches(many).map(\.count) == [8, 8, 3])
    }

    @Test func detailsTravelWithTheOfflineCopyAndOlderCopiesStillOpen() throws {
        let detail = try #require(try LioRoadbookWire.read(Data(Self.reply.utf8), asked: Self.places.map(\.id))["d1s2"]?.detail)
        let base = LioRoadbookTests.roadbook()
        let stopID = base.itinerary.days[0].stops[0].id
        let book = base.with(details: [stopID: detail])
        let restored = try LioRoadbookArchive(book).roadbook()
        #expect(restored.details[stopID] == detail)
        #expect(throws: LioRoadbookArchive.Failure.self) {
            try LioRoadbookArchive(base.with(details: ["no-such-stop": detail])).roadbook()
        }

        var json = try #require(String(data: JSONEncoder().encode(LioRoadbookArchive(LioRoadbookTests.roadbook())), encoding: .utf8))
        json = json.replacingOccurrences(of: ",\"details\":[]", with: "").replacingOccurrences(of: "\"details\":[],", with: "")
        #expect(!json.contains("details"))
        #expect(try JSONDecoder().decode(LioRoadbookArchive.self, from: Data(json.utf8)).roadbook().details.isEmpty)
    }

    @Test func thePdfPrintsTheFilledInFields() throws {
        let detail = try #require(try LioRoadbookWire.read(Data(Self.reply.utf8), asked: Self.places.map(\.id))["d1s2"]?.detail)
        let itinerary = LioRoadbookTests.itinerary(dates: [nil], stopsPerDay: 1)
        let stopID = itinerary.days[0].stops[0].id
        let book = LioRoadbookTests.roadbook(itinerary).with(details: [stopID: detail])
        let text = try #require(PDFDocument(data: LioRoadbookPDF.data(for: book, language: .chinese))?.string)
        for expected in ["为什么值得去", "中轴线上最大的古建筑群", "约 40–60 元", "天安门东站", "四季民福烤鸭店(故宫店)"] {
            #expect(text.contains(expected), "\(expected)")
        }
    }

    @Test func placesThatCanBeFilledInNeedACityAndAreSightsOrFood() {
        let book = LioRoadbookTests.roadbook()
        let queries = book.placesToFillIn()
        #expect(queries.count == 6 && queries.allSatisfy { $0.city == "北京" })
        let noCity = LioRoadbook(id: "x", source: .saved, city: nil, createdAt: .now, itinerary: LioRoadbookTests.itinerary())
        #expect(noCity.placesToFillIn().isEmpty)
        let detail = try? LioRoadbookWire.read(Data(Self.reply.utf8), asked: Self.places.map(\.id))["d1s2"]?.detail
        let partly = book.with(details: [book.itinerary.days[0].stops[0].id: detail!])
        #expect(partly.placesToFillIn().count == 5, "filled places are not asked again")
    }
}

/// #1616 review P1: filling in, then keeping offline, must keep the details.
@MainActor struct LioRoadbookKeepDetailsTests {
    @Test func keepingAFilledInRoadbookKeepsItsDetails() throws {
        let detail = try #require(try LioRoadbookWire.read(Data(LioRoadbookDetailTests.reply.utf8),
                                                         asked: LioRoadbookDetailTests.places.map(\.id))["d1s2"]?.detail)
        let base = LioRoadbookTests.roadbook()
        let stopID = base.itinerary.days[0].stops[0].id
        let kept = base.with(details: [stopID: detail]).kept(at: Date(timeIntervalSince1970: 7))
        #expect(kept.details[stopID] == detail && kept.createdAt == Date(timeIntervalSince1970: 7))

        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("roadbook-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioRoadbookStore(directory: directory)
        try store.save(kept)
        #expect(store.load().first?.details[stopID] == detail)
        #expect(store.load().first?.placesToFillIn().contains { $0.id == stopID } == false, "not asked (or paid for) again")
    }
}

/// #1616 review P2: covering the screen does not cancel a fill-in; releasing the screen does.
@MainActor struct LioRoadbookFillTaskTests {
    @Test func releasingTheHolderCancelsTheTask() async {
        var holder: LioRoadbookFillTask? = LioRoadbookFillTask()
        let task = Task<Void, Never> { try? await Task.sleep(for: .seconds(60)) }
        holder?.task = task
        #expect(!task.isCancelled)
        holder = nil
        #expect(task.isCancelled)
    }
}
