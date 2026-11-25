import Foundation
import Testing
@testable import CJLioUser

/// #1510: hotel search results (HOTEL.2 draft, #1508) — a list of hotels with Chinese and English names,
/// a driver address, price band, rating, nearest metro, whether international guests are accepted,
/// and a booking hand-off through the Hong Kong relay. Nothing is booked or paid in the app.
@MainActor struct LioHotelOffersTests {
    private let base = URL(string: "https://relay.example.invalid")!
    private let requestID = UUID(uuidString: "8F14E45F-CEEA-4E7A-9C3B-2B0D4C1E9A10")!

    private func day(_ text: String) throws -> Date {
        try #require(ISO8601DateFormatter().date(from: text + "T04:00:00Z"))
    }

    private func query(city: String = "北京", landmark: String? = "王府井", nights: Int = 2, guests: Int = 2,
                       price: LioHotelPriceBand = .from300to600) throws -> LioHotelQuery {
        let arrival = try day("2026-12-03")
        let departure = try #require(LioHotelSearch.calendar.date(byAdding: .day, value: nights, to: arrival))
        return try LioHotelQuery(city: city, landmark: landmark, checkIn: arrival, checkOut: departure,
                                 guests: guests, price: price, language: .english, today: arrival)
    }

    private func reply(items: String, version: String = "HOTEL.2", source: String = "Gaode",
                       unapplied: String = #"["check_in","check_out","price"]"#,
                       applied: String = #"["near","guests"]"#, affiliate: String? = "false") -> Data {
        let flag = affiliate.map { #""affiliate_links":\#($0),"# } ?? ""
        return Data("""
        {"version":"\(version)","source":"\(source)",\(flag)"applied_filters":\(applied),
         "unapplied_filters":\(unapplied),"items":[\(items)]}
        """.utf8)
    }

    private let fullItem = """
    {"id":"B000H1","name_zh":"北京王府井希尔顿酒店","name_en":"Hilton Beijing Wangfujing",
     "address_zh":"东城区王府井东街8号","address_en":"8 Wangfujing East Street, Dongcheng",
     "lat":39.9139,"lng":116.4127,"coordinate_system":"GCJ-02","rating":"4.7",
     "price_cny":{"min":980,"max":1460},"price_kind":"reference",
     "metro":{"name_zh":"王府井站","name_en":"Wangfujing Station","distance_m":350},
     "foreign_guests":"accepted",
     "booking_url":"https://relay.example.invalid/v1/tools/hotel/out/handle_aaaaaaaaaaaaaaaaaaaaaa"}
    """

    private func approved(_ url: URL) -> Bool { LioHotelSearchWire.isRelayHandoff(url, relay: base) }

    // MARK: - Query

    @Test func queryTrimsTheLandmarkAndChecksTheStay() throws {
        let built = try query(landmark: "  王府井 ")
        #expect(built.city == "北京")
        #expect(built.landmark == "王府井")
        #expect(built.checkIn == "2026-12-03" && built.checkOut == "2026-12-05")
        #expect(built.nights == 2)
        #expect(try query(landmark: "   ").landmark == nil)
        #expect(try query(landmark: nil).landmark == nil)

        #expect(throws: LioHotelQuery.Problem.invalidLandmark) {
            try query(landmark: String(repeating: "街", count: 101))
        }
        #expect(throws: LioHotelQuery.Problem.invalidLandmark) { try query(landmark: "王府\n井") }
        #expect(throws: LioHotelQuery.Problem.stayTooLong) { try query(nights: 31) }
        #expect(throws: LioHotelQuery.Problem.tooManyGuests) { try query(guests: 11) }
        #expect(throws: LioHotelQuery.Problem.search(.cityRequired)) { try query(city: " ") }
        #expect(throws: LioHotelQuery.Problem.search(.checkoutMustFollowCheckin)) { try query(nights: 0) }
        #expect(throws: LioHotelQuery.Problem.search(.invalidGuestCount)) { try query(guests: 0) }
    }

    @Test func everyQueryProblemHasBilingualAdvice() {
        let problems: [LioHotelQuery.Problem] = [
            .invalidLandmark, .stayTooLong, .tooManyGuests, .search(.cityRequired), .search(.invalidCity),
            .search(.checkoutMustFollowCheckin), .search(.invalidGuestCount), .checkInPast,
        ]
        for problem in problems {
            #expect(!problem.message(.english).isEmpty)
            #expect(problem.message(.chinese) != problem.message(.english))
        }
    }

    @Test func priceBandsMapToYuanBounds() {
        #expect(LioHotelPriceBand.any.bounds == nil)
        #expect(LioHotelPriceBand.under300.bounds == LioHotelPriceBand.Bounds(min: nil, max: 300))
        #expect(LioHotelPriceBand.from300to600.bounds == LioHotelPriceBand.Bounds(min: 300, max: 600))
        #expect(LioHotelPriceBand.from600to1000.bounds == LioHotelPriceBand.Bounds(min: 600, max: 1000))
        #expect(LioHotelPriceBand.over1000.bounds == LioHotelPriceBand.Bounds(min: 1000, max: nil))
        for band in [LioHotelPriceBand.any, .under300, .over1000] {
            #expect(band.title(.english) != band.title(.chinese))
        }
        #expect(LioHotelPriceBand.from300to600.title(.english) == "¥300–600")
    }

    // MARK: - Wire

    @Test func searchBodyCarriesOnlyTheContractFields() throws {
        let body = try #require(JSONSerialization.jsonObject(
            with: LioHotelSearchWire.encode(try query(), requestID: requestID)) as? [String: Any])
        #expect(Set(body.keys) == ["version", "request_id", "city", "near", "check_in", "check_out", "guests",
                                   "price_cny", "language"])
        #expect(body["version"] as? String == "HOTEL.2")
        #expect(body["request_id"] as? String == "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10")
        #expect(body["city"] as? String == "北京")
        #expect((body["near"] as? [String: Any])?["query"] as? String == "王府井")
        #expect(body["check_in"] as? String == "2026-12-03")
        #expect(body["check_out"] as? String == "2026-12-05")
        #expect(body["guests"] as? Int == 2)
        let price = try #require(body["price_cny"] as? [String: Any])
        #expect(price["min"] as? Int == 300 && price["max"] as? Int == 600)
        #expect(body["language"] as? String == "en")

        let open = try #require(JSONSerialization.jsonObject(
            with: LioHotelSearchWire.encode(try query(landmark: nil, price: .any), requestID: requestID)) as? [String: Any])
        #expect(open["near"] == nil)
        #expect(open["price_cny"] == nil)
        let cheap = try #require(JSONSerialization.jsonObject(
            with: LioHotelSearchWire.encode(try query(price: .under300), requestID: requestID)) as? [String: Any])
        #expect(Set(try #require(cheap["price_cny"] as? [String: Any]).keys) == ["max"])
    }

    @Test func fullResultReadsEveryCardField() throws {
        let results = try LioHotelSearchWire.read(reply(items: fullItem, source: "Trip.com"), allowing: approved)
        #expect(results.source == .tripCom)
        #expect(results.unappliedFilters == [.checkIn, .checkOut, .price])
        #expect(results.notice(.english) ==
                "This list doesn’t take the check-in date, the checkout date, and the price range into account yet. Confirm them on Trip.com before you book.")
        #expect(results.notice(.chinese) == "这份列表还没按入住日期、退房日期和价格区间筛选，预订前请在 Trip.com 确认。")
        let hotel = try #require(results.offers.first)
        #expect(hotel.id == "B000H1")
        #expect(hotel.nameZH == "北京王府井希尔顿酒店")
        #expect(hotel.title(.english) == "Hilton Beijing Wangfujing")
        #expect(hotel.title(.chinese) == "北京王府井希尔顿酒店")
        #expect(hotel.subtitle(.english) == "北京王府井希尔顿酒店")
        #expect(hotel.subtitle(.chinese) == nil)
        #expect(hotel.address(.english) == "8 Wangfujing East Street, Dongcheng")
        #expect(hotel.address(.chinese) == "东城区王府井东街8号")
        #expect(hotel.coordinate == .init(latitude: 39.9139, longitude: 116.4127, referenceSystem: .gcj02))
        #expect(hotel.rating == "4.7")
        #expect(hotel.price == LioHotelOffer.Price(min: 980, max: 1460, kind: .reference))
        #expect(hotel.metro == LioHotelOffer.Metro(nameZH: "王府井站", nameEN: "Wangfujing Station", meters: 350))
        #expect(hotel.foreignGuests == .accepted)
        #expect(hotel.booking.path == "/v1/tools/hotel/out/handle_aaaaaaaaaaaaaaaaaaaaaa")

        let driver = hotel.taxiPlace
        #expect(driver.nameZH == "北京王府井希尔顿酒店")
        #expect(driver.addressZH == "东城区王府井东街8号")
        #expect(driver.coordinate.referenceSystem == .gcj02)
    }

    @Test func missingOptionalFieldsStayHonest() throws {
        let sparse = """
        {"id":"B000H2","name_zh":"王府井胡同客栈","address_zh":"东城区菊儿胡同3号","lat":39.94,"lng":116.40,
         "coordinate_system":"GCJ-02","rating":4.2,"price_cny":{"min":700,"max":300},"metro":{"name_zh":"","distance_m":-5},
         "foreign_guests":"maybe","booking_url":"https://relay.example.invalid/v1/tools/hotel/out/handle_bbbbbbbbbbbbbbbbbbbbbb"}
        """
        let hotel = try #require(try LioHotelSearchWire.read(reply(items: sparse, source: "Trip.com"), allowing: approved).offers.first)
        #expect(hotel.title(.english) == "王府井胡同客栈")
        #expect(hotel.subtitle(.english) == nil)
        #expect(hotel.address(.english) == "东城区菊儿胡同3号")
        #expect(hotel.rating == nil)
        #expect(hotel.price == nil)
        #expect(hotel.metro == nil)
        // An unrecognised answer never becomes "accepted".
        #expect(hotel.foreignGuests == .unknown)

        let refused = fullItem.replacingOccurrences(of: #""accepted""#, with: #""not_accepted""#)
        #expect(try LioHotelSearchWire.read(reply(items: refused, source: "Trip.com"), allowing: approved).offers.first?.foreignGuests == .notAccepted)
        let live = fullItem.replacingOccurrences(of: #""reference""#, with: #""live""#)
        #expect(try LioHotelSearchWire.read(reply(items: live), allowing: approved).offers.first?.price?.kind == .live)
        let noKind = fullItem.replacingOccurrences(of: #""price_kind":"reference","#, with: "")
        #expect(try LioHotelSearchWire.read(reply(items: noKind), allowing: approved).offers.first?.price?.kind == .reference)
    }

    @Test func untrustedRepliesAreRejected() throws {
        let foreignHost = fullItem.replacingOccurrences(of: "relay.example.invalid", with: "trip.example.invalid")
        let plainHTTP = fullItem.replacingOccurrences(of: "https://", with: "http://")
        let otherPath = fullItem.replacingOccurrences(of: "/v1/tools/hotel/out/", with: "/v1/other/")
        let withUser = fullItem.replacingOccurrences(of: "https://relay", with: "https://u:p@relay")
        let wgs = fullItem.replacingOccurrences(of: "GCJ-02", with: "WGS-84")
        let unnamed = fullItem.replacingOccurrences(of: #""北京王府井希尔顿酒店""#, with: #"" ""#)
        let badLat = fullItem.replacingOccurrences(of: "39.9139", with: "139.9")
        for item in [foreignHost, plainHTTP, otherPath, withUser, wgs, unnamed, badLat] {
            #expect(throws: LioHotelFailure.unavailable) { try LioHotelSearchWire.read(reply(items: item), allowing: approved) }
        }
        #expect(throws: LioHotelFailure.unavailable) {
            try LioHotelSearchWire.read(reply(items: fullItem, version: "HOTEL.1"), allowing: approved)
        }
        #expect(throws: LioHotelFailure.unavailable) {
            try LioHotelSearchWire.read(reply(items: fullItem, source: "Elsewhere"), allowing: approved)
        }
        // The filter partition must be complete and disjoint, as in HOTEL.1.
        #expect(throws: LioHotelFailure.unavailable) {
            try LioHotelSearchWire.read(reply(items: fullItem, unapplied: #"["price"]"#), allowing: approved)
        }
        #expect(throws: LioHotelFailure.unavailable) {
            try LioHotelSearchWire.read(reply(items: fullItem, unapplied: #"["price","guests","check_in","check_out"]"#),
                                   allowing: approved)
        }
        let duplicate = fullItem + "," + fullItem
        #expect(throws: LioHotelFailure.unavailable) { try LioHotelSearchWire.read(reply(items: duplicate), allowing: approved) }
        #expect(try LioHotelSearchWire.read(reply(items: ""), allowing: approved).offers.isEmpty)
    }

    @Test func handoffLinksAreOneOpaqueSegmentOnTheRelay() throws {
        func ok(_ text: String) throws -> Bool { LioHotelSearchWire.isRelayHandoff(try #require(URL(string: text)), relay: base) }
        #expect(try ok("https://relay.example.invalid/v1/tools/hotel/out/AbC_def-1234567890xyz"))
        #expect(try !ok("https://relay.example.invalid/v1/tools/hotel/out/../../v1/tools/taxi/link"))
        #expect(try !ok("https://relay.example.invalid/v1/tools/hotel/out/abcdefghijklmnop/extra"))
        #expect(try !ok("https://relay.example.invalid/v1/tools/hotel/out/short"))
        #expect(try !ok("https://relay.example.invalid/v1/tools/hotel/out/abcdefghijklmnopqrstuv?next=x"))
        #expect(try !ok("https://relay.example.invalid/v1/tools/hotel/out/abcdefghijklmnopqrstuv#frag"))
        #expect(try !ok("https://relay.example.invalid/v1/tools/hotel/out/abcdefghij%2Fklmnopqrstuv"))
    }

    @Test func gaodeListsNeverClaimInternationalGuestPolicy() throws {
        // Step one of #1508: Gaode has no foreign-guest data, so the app shows "check on Trip.com" whatever arrives.
        let gaode = try #require(try LioHotelSearchWire.read(reply(items: fullItem, source: "Gaode"), allowing: approved).offers.first)
        #expect(gaode.foreignGuests == .unknown)
        let trip = try #require(try LioHotelSearchWire.read(reply(items: fullItem, source: "Trip.com"), allowing: approved).offers.first)
        #expect(trip.foreignGuests == .accepted)
    }

    @Test func checkInCannotBeInThePast() throws {
        let today = try day("2026-12-03")
        let yesterday = try #require(LioHotelSearch.calendar.date(byAdding: .day, value: -1, to: today))
        let tomorrow = try #require(LioHotelSearch.calendar.date(byAdding: .day, value: 1, to: today))
        #expect(throws: LioHotelQuery.Problem.checkInPast) {
            try LioHotelQuery(city: "北京", landmark: nil, checkIn: yesterday, checkOut: tomorrow, guests: 1,
                              price: .any, language: .english, today: today)
        }
        #expect(try LioHotelQuery(city: "北京", landmark: nil, checkIn: today, checkOut: tomorrow, guests: 1,
                                  price: .any, language: .english, today: today).checkIn == "2026-12-03")
        #expect(LioHotelQuery.Problem.checkInPast.message(.english) != LioHotelQuery.Problem.checkInPast.message(.chinese))
    }

    @Test func affiliateDisclosureFollowsTheReply() throws {
        // #225: the disclosure appears only when the hand-off really carries an affiliate ID.
        #expect(try LioHotelSearchWire.read(reply(items: fullItem, affiliate: "false"), allowing: approved).affiliateLinks == false)
        #expect(try LioHotelSearchWire.read(reply(items: fullItem, affiliate: "true"), allowing: approved).affiliateLinks == true)
        // A reply that does not say is treated as affiliate, so the disclosure is never missing.
        #expect(try LioHotelSearchWire.read(reply(items: fullItem, affiliate: nil), allowing: approved).affiliateLinks == true)
        #expect(throws: LioHotelFailure.unavailable) {
            try LioHotelSearchWire.read(reply(items: fullItem, affiliate: #""yes""#), allowing: approved)
        }
        #expect(LioHotelResults.disclosure(.english).contains("affiliate"))
        #expect(LioHotelResults.disclosure(.chinese).contains("推广链接"))
    }

    @Test func gaodeReferencePricesNeverShowAnAcceptedBadge() throws {
        // Step one: a Gaode list with reference prices claims nothing about international guests.
        let item = fullItem.replacingOccurrences(of: #""foreign_guests":"accepted""#,
                                                 with: #""foreign_guests":"unknown""#)
        let hotel = try #require(try LioHotelSearchWire.read(reply(items: item, source: "Gaode"), allowing: approved).offers.first)
        #expect(hotel.price?.kind == .reference)
        #expect(hotel.foreignGuests == .unknown)
        #expect(!hotel.foreignGuests.isConfirmed)
        #expect(hotel.foreignGuests.label(.english) == "International guests: check on Trip.com")
        #expect(LioHotelOffer.ForeignGuests.accepted.isConfirmed)
    }

    @Test func relayErrorsMapToTravellerProblems() {
        func body(_ code: String) -> Data { Data(#"{"error":"\#(code)"}"#.utf8) }
        #expect(LioHotelSearchWire.failure(status: 401, body: Data()) == .signInRequired)
        #expect(LioHotelSearchWire.failure(status: 403, body: body("not_enabled")) == .notEnabled)
        #expect(LioHotelSearchWire.failure(status: 429, body: body("quota_exceeded")) == .quotaExceeded)
        #expect(LioHotelSearchWire.failure(status: 429, body: body("rate_limited")) == .rateLimited)
        #expect(LioHotelSearchWire.failure(status: 504, body: body("supplier_timeout")) == .timedOut)
        #expect(LioHotelSearchWire.failure(status: 502, body: body("supplier_unavailable")) == .unavailable)
        for failure in [LioHotelFailure.signInRequired, .notEnabled, .quotaExceeded, .rateLimited, .timedOut, .unavailable] {
            #expect(failure.message(.english) != failure.message(.chinese))
        }
    }

    // MARK: - Card text

    @Test func cardTextIsBilingual() throws {
        let hotel = try #require(try LioHotelSearchWire.read(reply(items: fullItem, source: "Trip.com"), allowing: approved).offers.first)
        #expect(hotel.priceText(.english) == "¥980–1,460 a night · reference")
        #expect(hotel.priceText(.chinese) == "参考价 每晚 ¥980–1,460")
        #expect(hotel.metroText(.english) == "350 m to Wangfujing Station")
        #expect(hotel.metroText(.chinese) == "距王府井站 350 米")
        #expect(LioHotelOffer.ForeignGuests.accepted.label(.english) == "Accepts international guests")
        #expect(LioHotelOffer.ForeignGuests.accepted.label(.chinese) == "可接待外国人")
        #expect(LioHotelOffer.ForeignGuests.notAccepted.label(.chinese) == "不接待外国人")
        #expect(LioHotelOffer.ForeignGuests.unknown.label(.english) == "International guests: check on Trip.com")

        let far = LioHotelOffer.Metro(nameZH: "东直门站", nameEN: nil, meters: 1250)
        #expect(far.text(.english) == "1.3 km to 东直门站")
        #expect(far.text(.chinese) == "距东直门站 1.3 公里")
        let single = LioHotelOffer.Price(min: 420, max: 420, kind: .live)
        #expect(single.text(.english) == "¥420 a night")
        #expect(single.text(.chinese) == "每晚 ¥420")
    }

    // MARK: - Relay

    @Test func relayPostsWithTheBearerAndKeepsOnlyRelayHandoffs() async throws {
        var paths = [String]()
        let relay = LioHotelRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" },
                                        newRequestID: { requestID }) { request in
            let url = try #require(request.url)
            paths.append(url.path)
            #expect(request.httpMethod == "POST")
            #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-only")
            #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
            return (reply(items: fullItem), HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!)
        }
        let results = try await relay.search(try query())
        #expect(paths == ["/v1/tools/hotel/search"])
        #expect(results.offers.map(\.id) == ["B000H1"])
    }

    @Test func relayNeedsACurrentSignedInSession() async throws {
        var calls = 0
        let signedOut = LioHotelRelayClient(baseURL: base, isCurrent: { true }, bearer: { nil }) { _ in
            calls += 1
            throw URLError(.badServerResponse)
        }
        await #expect(throws: LioHotelFailure.signInRequired) { try await signedOut.search(try query()) }

        let refused = LioHotelRelayClient(baseURL: base, isCurrent: { true }, bearer: { "fixture-only" }) { request in
            calls += 1
            let url = try #require(request.url)
            return (Data(#"{"error":"not_enabled"}"#.utf8),
                    HTTPURLResponse(url: url, statusCode: 403, httpVersion: nil, headerFields: nil)!)
        }
        await #expect(throws: LioHotelFailure.notEnabled) { try await refused.search(try query()) }
        #expect(calls == 1)
    }

    #if DEBUG
    @Test func previewFinderServesTheBeijingFixture() async throws {
        let results = try await LioHotelFinder.preview.search(try query())
        #expect(results.offers.count >= 3)
        #expect(Set(results.offers.map(\.foreignGuests)) == [.accepted, .notAccepted, .unknown])
        #expect(results.offers.allSatisfy { $0.booking.host == "hotel.example.invalid" })
    }
    #endif
}
