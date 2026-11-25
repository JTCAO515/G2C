import Foundation
#if os(iOS)
import CJMessageHTTP
import UIKit
#endif

/// #1510: hotel search for the Tools tab (HOTEL.2 draft, #1508). The Hong Kong relay returns a list of
/// hotels; booking always happens on the partner site through a relay hand-off link. Nothing is booked
/// or paid in the app, and the partner's affiliate ID never reaches the app.

/// Nightly price bands in yuan, matching the search form.
enum LioHotelPriceBand: String, CaseIterable, Identifiable, Sendable {
    case any, under300, from300to600, from600to1000, over1000

    struct Bounds: Equatable, Sendable {
        let min: Int?
        let max: Int?
    }

    var id: String { rawValue }

    var bounds: Bounds? {
        switch self {
        case .any: nil
        case .under300: Bounds(min: nil, max: 300)
        case .from300to600: Bounds(min: 300, max: 600)
        case .from600to1000: Bounds(min: 600, max: 1000)
        case .over1000: Bounds(min: 1000, max: nil)
        }
    }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .any: language.text("Any price", "不限价格")
        case .under300: language.text("Under ¥300", "¥300 以下")
        case .from300to600: "¥300–600"
        case .from600to1000: "¥600–1,000"
        case .over1000: language.text("Over ¥1,000", "¥1,000 以上")
        }
    }
}

/// A validated hotel search: city, an optional landmark or district, dates, guests and price band.
struct LioHotelQuery: Equatable, Sendable {
    enum Problem: Error, Equatable {
        case search(LioHotelSearch.Validation), invalidLandmark, stayTooLong, tooManyGuests, checkInPast

        func message(_ language: LioLanguage) -> String {
            switch self {
            case .search(.cityRequired): language.text("Enter a city to search for hotels.", "请输入城市再查找酒店。")
            case .search(.invalidCity):
                language.text("Enter a city name of up to 100 characters.", "请输入不超过 100 字的城市名称。")
            case .search(.checkoutMustFollowCheckin):
                language.text("Checkout must be after check-in.", "退房日期须晚于入住日期。")
            case .search(.invalidGuestCount): language.text("Enter at least one guest.", "请至少选择一位入住客人。")
            case .invalidLandmark:
                language.text("Enter an area or landmark of up to 100 characters.", "请输入不超过 100 字的区域或地标。")
            case .stayTooLong: language.text("Search for stays of up to 30 nights.", "一次最多搜索 30 晚。")
            case .tooManyGuests: language.text("Search for up to 10 guests.", "一次最多搜索 10 位客人。")
            case .checkInPast: language.text("Choose a check-in date from today on.", "入住日期不能早于今天。")
            }
        }
    }

    static let maximumNights = 30
    static let maximumGuests = 10

    let city: String
    let landmark: String?
    let checkIn: String
    let checkOut: String
    let nights: Int
    let guests: Int
    let price: LioHotelPriceBand
    let language: LioLanguage

    init(city: String, landmark: String?, checkIn: Date, checkOut: Date, guests: Int,
         price: LioHotelPriceBand, language: LioLanguage, today: Date = Date()) throws(Problem) {
        let stay: LioHotelSearch
        do {
            stay = try LioHotelSearch(scope: .city(city), checkIn: checkIn, checkOut: checkOut, guests: guests,
                                      language: language)
        } catch {
            throw .search(error)
        }
        guard guests <= Self.maximumGuests else { throw .tooManyGuests }
        let calendar = LioHotelSearch.calendar
        guard calendar.compare(checkIn, to: today, toGranularity: .day) != .orderedAscending else { throw .checkInPast }
        let nights = calendar.dateComponents([.day], from: calendar.startOfDay(for: checkIn),
                                             to: calendar.startOfDay(for: checkOut)).day ?? 0
        guard nights <= Self.maximumNights else { throw .stayTooLong }
        let trimmed = landmark?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty {
            guard trimmed.unicodeScalars.count <= 100,
                  !trimmed.unicodeScalars.contains(where: { $0.value < 32 }) else { throw .invalidLandmark }
        }
        guard case .city(let cleanCity) = stay.scope else { throw .search(.cityRequired) }
        self.city = cleanCity
        self.landmark = trimmed.isEmpty ? nil : trimmed
        self.checkIn = stay.checkIn
        self.checkOut = stay.checkOut
        self.nights = nights
        self.guests = guests
        self.price = price
        self.language = language
    }
}

/// One hotel card. Coordinates are GCJ-02, the driver card always uses the Chinese name and address.
struct LioHotelOffer: Identifiable, Hashable, Sendable {
    enum ForeignGuests: String, Hashable, Sendable {
        case accepted, notAccepted = "not_accepted", unknown

        func label(_ language: LioLanguage) -> String {
            switch self {
            case .accepted: language.text("Accepts international guests", "可接待外国人")
            case .notAccepted: language.text("Doesn’t accept international guests", "不接待外国人")
            case .unknown: language.text("International guests: check on Trip.com", "是否接待外国人：请在 Trip.com 确认")
            }
        }
    }

    struct Price: Hashable, Sendable {
        enum Kind: String, Hashable, Sendable { case live, reference }
        let min: Int
        let max: Int
        let kind: Kind

        func text(_ language: LioLanguage) -> String {
            let range = min == max ? "¥" + Self.yuan(min) : "¥" + Self.yuan(min) + "–" + Self.yuan(max)
            switch kind {
            case .live: return language.text("\(range) a night", "每晚 \(range)")
            case .reference: return language.text("\(range) a night · reference", "参考价 每晚 \(range)")
            }
        }

        private static func yuan(_ value: Int) -> String {
            value.formatted(.number.grouping(.automatic).locale(Locale(identifier: "en_US")))
        }
    }

    struct Metro: Hashable, Sendable {
        let nameZH: String
        let nameEN: String?
        let meters: Int

        func text(_ language: LioLanguage) -> String {
            let name = language == .english ? (nameEN ?? nameZH) : nameZH
            if meters < 1000 {
                return language.text("\(meters) m to \(name)", "距\(name) \(meters) 米")
            }
            let km = String(format: "%.1f", (Double(meters) / 100).rounded() / 10)
            return language.text("\(km) km to \(name)", "距\(name) \(km) 公里")
        }
    }

    let id: String
    let nameZH: String
    let nameEN: String?
    let addressZH: String
    let addressEN: String?
    let coordinate: LioTaxiPlace.Coordinate
    let rating: String?
    let price: Price?
    let metro: Metro?
    let foreignGuests: ForeignGuests
    let booking: URL

    func title(_ language: LioLanguage) -> String {
        language == .english ? (nameEN ?? nameZH) : nameZH
    }

    /// The Chinese name under the English one, so travellers can match the sign at the door.
    func subtitle(_ language: LioLanguage) -> String? {
        language == .english && nameEN != nil ? nameZH : nil
    }

    func address(_ language: LioLanguage) -> String {
        language == .english ? (addressEN ?? addressZH) : addressZH
    }

    func priceText(_ language: LioLanguage) -> String? { price?.text(language) }
    func metroText(_ language: LioLanguage) -> String? { metro?.text(language) }

    var taxiPlace: LioTaxiPlace {
        LioTaxiPlace(nameZH: nameZH, nameEN: nameEN ?? nameZH, addressZH: addressZH, addressEN: addressEN,
                     coordinate: coordinate)
    }
}

struct LioHotelResults: Sendable {
    enum Source: String, Sendable {
        case gaode = "Gaode", tripCom = "Trip.com"

        func credit(_ language: LioLanguage) -> String {
            switch self {
            case .gaode: language.text("Hotel list from Gaode (AMap)", "酒店信息来自高德")
            case .tripCom: language.text("Hotel list from Trip.com", "酒店信息来自 Trip.com")
            }
        }
    }

    /// Search conditions the source could not apply; the screen tells the traveller to check them.
    enum Filter: String, CaseIterable, Decodable, Hashable, Sendable {
        case near, checkIn = "check_in", checkOut = "check_out", guests, price

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .near: language.text("the area", "区域")
            case .checkIn: language.text("the check-in date", "入住日期")
            case .checkOut: language.text("the checkout date", "退房日期")
            case .guests: language.text("the guest count", "人数")
            case .price: language.text("the price range", "价格区间")
            }
        }
    }

    /// Conditions the list could not use, for the traveller to check on the booking site; nil when all applied.
    func notice(_ language: LioLanguage) -> String? {
        guard !unappliedFilters.isEmpty else { return nil }
        let locale = Locale(identifier: language == .chinese ? "zh_CN" : "en_US")
        let list = unappliedFilters.map { $0.title(language) }.formatted(.list(type: .and).locale(locale))
        return language.text("This list doesn’t take \(list) into account yet. Confirm them on Trip.com before you book.",
                             "这份列表还没按\(list)筛选，预订前请在 Trip.com 确认。")
    }

    let source: Source
    let offers: [LioHotelOffer]
    let unappliedFilters: [Filter]
}

enum LioHotelFailure: Error, Equatable {
    case signInRequired, notEnabled, quotaExceeded, rateLimited, timedOut, unavailable

    func message(_ language: LioLanguage) -> String {
        switch self {
        case .signInRequired: language.text("Sign in again, then try again.", "请重新登录后重试。")
        case .notEnabled: language.text("Hotel search isn’t available for this account yet.", "此账号暂未开通酒店搜索。")
        case .quotaExceeded:
            language.text("Hotel search has reached its limit for today. Try again tomorrow.", "今天的酒店搜索次数已用完，请明天再试。")
        case .rateLimited: language.text("Too many searches right now. Try again later.", "搜索太频繁，请稍后再试。")
        case .timedOut: language.text("This took too long. Try again.", "搜索超时，请重试。")
        case .unavailable: language.text("Hotel search isn’t available right now. Try again.", "酒店搜索暂时不可用，请重试。")
        }
    }
}

enum LioHotelSearchWire {
    static let version = "HOTEL.2"
    static let handoffPath = "/v1/tools/hotel/out/"

    private struct Near: Encodable { let query: String }

    private struct PriceRange: Encodable { let min: Int?; let max: Int? }

    private struct Request: Encodable {
        let version: String
        let requestID: String
        let city: String
        let near: Near?
        let checkIn: String
        let checkOut: String
        let guests: Int
        let priceCNY: PriceRange?
        let language: String

        enum CodingKeys: String, CodingKey {
            case version, requestID = "request_id", city, near, checkIn = "check_in", checkOut = "check_out",
                 guests, priceCNY = "price_cny", language
        }
    }

    private struct WirePrice: Decodable { let min: Int; let max: Int }

    private struct WireMetro: Decodable {
        let nameZh: String
        let nameEn: String?
        let distanceM: Int
    }

    private struct Item: Decodable {
        let id: String
        let nameZh: String
        let nameEn: String?
        let addressZh: String
        let addressEn: String?
        let lat: Double
        let lng: Double
        let coordinateSystem: String
        let rating: String?
        let priceCny: WirePrice?
        let priceKind: String?
        let metro: WireMetro?
        let foreignGuests: String?
        let bookingUrl: String

        enum CodingKeys: String, CodingKey {
            case id, nameZh, nameEn, addressZh, addressEn, lat, lng, coordinateSystem, rating, priceCny, priceKind,
                 metro, foreignGuests, bookingUrl
        }

        init(from decoder: Decoder) throws {
            let row = try decoder.container(keyedBy: CodingKeys.self)
            id = try row.decode(String.self, forKey: .id)
            nameZh = try row.decode(String.self, forKey: .nameZh)
            addressZh = try row.decode(String.self, forKey: .addressZh)
            lat = try row.decode(Double.self, forKey: .lat)
            lng = try row.decode(Double.self, forKey: .lng)
            coordinateSystem = try row.decode(String.self, forKey: .coordinateSystem)
            bookingUrl = try row.decode(String.self, forKey: .bookingUrl)
            // Display extras never invalidate a hotel; an unexpected shape is simply left out.
            nameEn = try? row.decodeIfPresent(String.self, forKey: .nameEn)
            addressEn = try? row.decodeIfPresent(String.self, forKey: .addressEn)
            rating = try? row.decodeIfPresent(String.self, forKey: .rating)
            priceCny = try? row.decodeIfPresent(WirePrice.self, forKey: .priceCny)
            priceKind = try? row.decodeIfPresent(String.self, forKey: .priceKind)
            metro = try? row.decodeIfPresent(WireMetro.self, forKey: .metro)
            foreignGuests = try? row.decodeIfPresent(String.self, forKey: .foreignGuests)
        }
    }

    private struct Reply: Decodable {
        let version: String
        let source: String
        let appliedFilters: [LioHotelResults.Filter]
        let unappliedFilters: [LioHotelResults.Filter]
        let items: [Item]
    }

    private struct ErrorBody: Decodable { let error: String }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func encode(_ query: LioHotelQuery, requestID: UUID) throws -> Data {
        let request = Request(
            version: version, requestID: requestID.uuidString.lowercased(), city: query.city,
            near: query.landmark.map(Near.init), checkIn: query.checkIn, checkOut: query.checkOut,
            guests: query.guests, priceCNY: query.price.bounds.map { PriceRange(min: $0.min, max: $0.max) },
            language: query.language == .chinese ? "zh" : "en")
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try encoder.encode(request)
    }

    /// Booking links must be the relay's own hand-off path, so the affiliate redirect stays server-side.
    /// Booking links must be one opaque handle on the relay's own hand-off path (no `..`, extra segments,
    /// query or fragment), so the affiliate redirect stays server-side.
    static func isRelayHandoff(_ url: URL, relay: URL) -> Bool {
        guard url.scheme == "https", url.host != nil, url.host == relay.host, url.port == relay.port,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              let raw = URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath,
              raw.hasPrefix(handoffPath) else { return false }
        let handle = raw.dropFirst(handoffPath.count)
        return (16...128).contains(handle.count)
            && handle.unicodeScalars.allSatisfy { ($0.isASCII && CharacterSet.alphanumerics.contains($0)) || $0 == "_" || $0 == "-" }
    }

    static func read(_ data: Data, allowing approvedTarget: (URL) -> Bool) throws -> LioHotelResults {
        guard let reply = try? decoder.decode(Reply.self, from: data), reply.version == version,
              let source = LioHotelResults.Source(rawValue: reply.source) else { throw LioHotelFailure.unavailable }
        let applied = Set(reply.appliedFilters)
        let unapplied = Set(reply.unappliedFilters)
        guard applied.count == reply.appliedFilters.count, unapplied.count == reply.unappliedFilters.count,
              applied.isDisjoint(with: unapplied),
              applied.union(unapplied) == Set(LioHotelResults.Filter.allCases) else { throw LioHotelFailure.unavailable }

        var seen = Set<String>()
        let offers = try reply.items.map { item -> LioHotelOffer in
            let name = item.nameZh.trimmingCharacters(in: .whitespacesAndNewlines)
            let address = item.addressZh.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !item.id.isEmpty, seen.insert(item.id).inserted, !name.isEmpty, !address.isEmpty,
                  item.coordinateSystem == "GCJ-02", (-90...90).contains(item.lat), (-180...180).contains(item.lng),
                  let booking = URL(string: item.bookingUrl), approvedTarget(booking) else {
                throw LioHotelFailure.unavailable
            }
            let price = item.priceCny.flatMap { range -> LioHotelOffer.Price? in
                guard range.min > 0, range.min <= range.max else { return nil }
                let kind = item.priceKind.flatMap(LioHotelOffer.Price.Kind.init(rawValue:)) ?? .reference
                return LioHotelOffer.Price(min: range.min, max: range.max, kind: kind)
            }
            let metro = item.metro.flatMap { station -> LioHotelOffer.Metro? in
                guard let stationName = nonEmpty(station.nameZh), station.distanceM >= 0 else { return nil }
                return LioHotelOffer.Metro(nameZH: stationName, nameEN: nonEmpty(station.nameEn),
                                           meters: station.distanceM)
            }
            return LioHotelOffer(
                id: item.id, nameZH: name, nameEN: nonEmpty(item.nameEn), addressZH: address,
                addressEN: nonEmpty(item.addressEn),
                coordinate: .init(latitude: item.lat, longitude: item.lng, referenceSystem: .gcj02),
                rating: nonEmpty(item.rating), price: price, metro: metro,
                // Gaode has no foreign-guest data (#1508 step one): never show a policy it cannot know.
                foreignGuests: source == .gaode ? .unknown
                    : item.foreignGuests.flatMap(LioHotelOffer.ForeignGuests.init(rawValue:)) ?? .unknown,
                booking: booking)
        }
        return LioHotelResults(source: source, offers: offers,
                               unappliedFilters: LioHotelResults.Filter.allCases.filter(unapplied.contains))
    }

    static func failure(status: Int, body: Data) -> LioHotelFailure {
        let code = (try? decoder.decode(ErrorBody.self, from: body))?.error
        return switch (status, code) {
        case (401, _): .signInRequired
        case (403, "not_enabled"): .notEnabled
        case (429, "quota_exceeded"): .quotaExceeded
        case (429, _): .rateLimited
        case (504, _): .timedOut
        default: .unavailable
        }
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        return value
    }
}

/// What the hotel screen needs: a search and a way to open a booking hand-off outside the app.
struct LioHotelFinder: Sendable {
    let search: @MainActor @Sendable (LioHotelQuery) async throws -> LioHotelResults
    let open: @MainActor @Sendable (URL) async -> Bool
}

@MainActor public struct LioHotelRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)

    private let baseURL: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let newRequestID: @MainActor () -> UUID
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool, bearer: @escaping @MainActor () -> String?,
         newRequestID: @escaping @MainActor () -> UUID = { UUID() }, exchange: @escaping Exchange) {
        self.baseURL = baseURL
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.newRequestID = newRequestID
        self.exchange = exchange
    }

    func search(_ query: LioHotelQuery) async throws -> LioHotelResults {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else { throw LioHotelFailure.signInRequired }
        let url = baseURL.appending(path: "v1/tools/hotel/search")
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try LioHotelSearchWire.encode(query, requestID: newRequestID())

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await exchange(request)
        } catch {
            try requireCurrentSession()
            if (error as? URLError)?.code == .timedOut { throw LioHotelFailure.timedOut }
            throw error
        }
        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url else { throw LioHotelFailure.unavailable }
        guard http.statusCode == 200 else { throw LioHotelSearchWire.failure(status: http.statusCode, body: data) }
        let relay = baseURL
        return try LioHotelSearchWire.read(data) { LioHotelSearchWire.isRelayHandoff($0, relay: relay) }
    }

    private func requireCurrentSession() throws {
        guard isCurrent() else { throw CancellationError() }
        try Task.checkCancellation()
    }
}

#if os(iOS)
extension LioHotelRelayClient {
    /// Internal testers only, when the build enables hotel search (`G2CHotelEnabled`, off by default);
    /// the relay decides per account.
    public static func internalBeta(endpoint: MessageEndpoint, isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioHotelRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CHotelEnabled") as? String == "YES" else { return nil }
        return LioHotelRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 30
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }
            let (stream, response) = try await session.bytes(for: request)
            let limit = endpoint.maximumResponseBytes
            guard response.expectedContentLength <= limit else { throw LioHotelFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioHotelFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}

extension LioHotelFinder {
    @MainActor static func internalBeta(relay: LioHotelRelayClient) -> Self {
        LioHotelFinder(search: { query in try await relay.search(query) },
                       open: { url in await UIApplication.shared.open(url) })
    }
}
#endif

#if DEBUG
extension LioHotelFinder {
    static let previewHost = "hotel.example.invalid"

    /// Four Beijing hotels around Wangfujing for screenshots and UI tests, shaped like the Trip.com list of
    /// #1508 step two (with foreign-guest answers); links never leave the fixture host.
    static let preview = LioHotelFinder(search: { query in
        try LioHotelSearchWire.read(previewReply(language: query.language)) {
            LioHotelSearchWire.isRelayHandoff($0, relay: URL(string: "https://\(previewHost)")!)
        }
    }, open: { _ in true })

    static func previewReply(language: LioLanguage) -> Data {
        func link(_ suffix: String) -> String { "https://\(previewHost)\(LioHotelSearchWire.handoffPath)fixture_\(suffix)" }
        let items: [[String: Any]] = [
            ["id": "fixture-h1", "name_zh": "北京王府井希尔顿酒店", "name_en": "Hilton Beijing Wangfujing",
             "address_zh": "东城区王府井东街8号", "address_en": "8 Wangfujing East Street, Dongcheng",
             "lat": 39.9139, "lng": 116.4127, "coordinate_system": "GCJ-02", "rating": "4.7",
             "price_cny": ["min": 980, "max": 1460], "price_kind": "reference",
             "metro": ["name_zh": "王府井站", "name_en": "Wangfujing Station", "distance_m": 350],
             "foreign_guests": "accepted", "booking_url": link("hilton_aaaaaaaaaaaa")],
            ["id": "fixture-h2", "name_zh": "全季酒店（北京东单店）", "name_en": "JI Hotel Beijing Dongdan",
             "address_zh": "东城区东单北大街甲98号", "address_en": "98A Dongdan North Street, Dongcheng",
             "lat": 39.9157, "lng": 116.4180, "coordinate_system": "GCJ-02", "rating": "4.6",
             "price_cny": ["min": 420, "max": 560], "price_kind": "reference",
             "metro": ["name_zh": "东单站", "name_en": "Dongdan Station", "distance_m": 620],
             "booking_url": link("jihotel_aaaaaaaaaaa")],
            ["id": "fixture-h3", "name_zh": "菊儿人家胡同客栈",
             "address_zh": "东城区菊儿胡同3号", "lat": 39.9399, "lng": 116.4012, "coordinate_system": "GCJ-02",
             "rating": "4.3", "price_cny": ["min": 260, "max": 260], "price_kind": "reference",
             "metro": ["name_zh": "南锣鼓巷站", "distance_m": 1250],
             "foreign_guests": "not_accepted", "booking_url": link("hutong_aaaaaaaaaaa")],
            ["id": "fixture-h4", "name_zh": "北京饭店", "name_en": "Beijing Hotel",
             "address_zh": "东城区东长安街33号", "address_en": "33 East Chang’an Avenue, Dongcheng",
             "lat": 39.9087, "lng": 116.4108, "coordinate_system": "GCJ-02",
             "foreign_guests": "accepted", "booking_url": link("bjhotel_aaaaaaaaaaa")],
        ]
        let reply: [String: Any] = [
            "version": LioHotelSearchWire.version, "source": "Trip.com",
            "applied_filters": ["near", "guests"], "unapplied_filters": ["check_in", "check_out", "price"],
            "items": items,
        ]
        return (try? JSONSerialization.data(withJSONObject: reply)) ?? Data()
    }
}
#endif
