import Foundation
#if os(iOS)
import CJMessageHTTP
#endif

/// A place returned by the Hong Kong NEARBY.1 relay (Gaode around search). Coordinates are GCJ-02.
struct LioNearbyPOI: Identifiable, Hashable, Sendable {
    let id: String
    let name: String
    let address: String?
    let category: LioNearbyPlace.Category?
    let coordinate: LioTaxiPlace.Coordinate
    let meters: Int?
    let rating: String?
    let cost: String?
    let hours: String?
    let photo: URL?

    /// Gaode type codes: 0505 coffee and tea houses, 05 food, 11 scenic spots, 06 shopping;
    /// 1603 ATMs, 090601 pharmacies, 2003 public toilets. Luggage storage has no code: it is found by name.
    static func category(typeCode: String) -> LioNearbyPlace.Category? {
        if typeCode.hasPrefix("1603") { return .atm }
        if typeCode.hasPrefix("090601") { return .pharmacy }
        if typeCode.hasPrefix("2003") { return .toilet }
        if typeCode.hasPrefix("0505") { return .coffee }
        if typeCode.hasPrefix("05") { return .food }
        if typeCode.hasPrefix("11") { return .sights }
        if typeCode.hasPrefix("06") { return .shopping }
        return nil
    }

    var taxiPlace: LioTaxiPlace {
        LioTaxiPlace(nameZH: name, nameEN: name, addressZH: address, coordinate: coordinate)
    }
}

struct LioNearbyQuery: Equatable, Sendable {
    static let radii = [500, 1000, 3000]

    let center: LioTaxiPlace.Coordinate
    let categories: Set<LioNearbyPlace.Category>
    let radius: Int
    let nearest: Bool
}

enum LioNearbyFailure: Error, Equatable {
    case locationDenied, signInRequired, notEnabled, quotaExceeded, rateLimited, timedOut, unavailable
    /// #1748: the in-app location choice has not been made (or was turned off).
    case consentNeeded
}

enum LioNearbyWire {
    private static let version = "NEARBY.1"
    /// NEARBY.2 adds the essentials. Leisure searches stay on NEARBY.1, which the relay keeps accepting unchanged.
    private static let essentialsVersion = "NEARBY.2"

    static func version(for categories: Set<LioNearbyPlace.Category>) -> String {
        categories.contains(where: \.isEssential) ? essentialsVersion : version
    }

    private struct Center: Encodable {
        let lat: Double
        let lng: Double
        let coordinateSystem: String

        enum CodingKeys: String, CodingKey { case lat, lng, coordinateSystem = "coordinate_system" }

        init(_ point: LioTaxiPlace.Coordinate) throws {
            guard (-90...90).contains(point.latitude), (-180...180).contains(point.longitude) else {
                throw LioNearbyFailure.unavailable
            }
            lat = point.latitude
            lng = point.longitude
            coordinateSystem = point.referenceSystem == .wgs84 ? "WGS-84" : "GCJ-02"
        }
    }

    private struct SearchRequest: Encodable {
        let version: String
        let requestID: String
        let center: Center
        let categories: [String]
        let radiusM: Int
        let sort: String

        enum CodingKeys: String, CodingKey {
            case version, requestID = "request_id", center, categories, radiusM = "radius_m", sort
        }
    }

    private struct ReverseRequest: Encodable {
        let version: String
        let requestID: String
        let center: Center

        enum CodingKeys: String, CodingKey { case version, requestID = "request_id", center }
    }

    private struct Item: Decodable {
        let id: String
        let nameZh: String
        let addressZh: String?
        let typeCode: String
        let lat: Double
        let lng: Double
        let coordinateSystem: String
        let distanceM: Int?
        let rating: String?
        let costCny: String?
        let openingHours: String?
        let photoUrl: String?

        enum CodingKeys: String, CodingKey {
            case id, nameZh, addressZh, typeCode, lat, lng, coordinateSystem, distanceM, rating, costCny,
                 openingHours, photoUrl
        }

        init(from decoder: Decoder) throws {
            let row = try decoder.container(keyedBy: CodingKeys.self)
            id = try row.decode(String.self, forKey: .id)
            nameZh = try row.decode(String.self, forKey: .nameZh)
            addressZh = try row.decodeIfPresent(String.self, forKey: .addressZh)
            typeCode = try row.decode(String.self, forKey: .typeCode)
            lat = try row.decode(Double.self, forKey: .lat)
            lng = try row.decode(Double.self, forKey: .lng)
            coordinateSystem = try row.decode(String.self, forKey: .coordinateSystem)
            // Optional display fields never invalidate a place; an unexpected type is simply left out.
            distanceM = try? row.decodeIfPresent(Int.self, forKey: .distanceM)
            rating = try? row.decodeIfPresent(String.self, forKey: .rating)
            costCny = try? row.decodeIfPresent(String.self, forKey: .costCny)
            openingHours = try? row.decodeIfPresent(String.self, forKey: .openingHours)
            photoUrl = try? row.decodeIfPresent(String.self, forKey: .photoUrl)
        }
    }

    private struct SearchReply: Decodable {
        let version: String
        let source: String
        let items: [Item]
    }

    private struct ReverseReply: Decodable {
        let version: String
        let source: String
        let addressZh: String?
    }

    private struct ErrorBody: Decodable { let error: String }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return encoder
    }

    static func encodeSearch(_ query: LioNearbyQuery, requestID: UUID) throws -> Data {
        guard LioNearbyQuery.radii.contains(query.radius), !query.categories.isEmpty, query.categories.count <= 4,
              // Luggage storage and community services are searched by name and only on their own.
              !query.categories.contains(where: \.isSearchedByName) || query.categories.count == 1 else {
            throw LioNearbyFailure.unavailable
        }
        let ordered = LioNearbyPlace.Category.allCases.filter(query.categories.contains).map(\.rawValue)
        return try encoder.encode(SearchRequest(version: version(for: query.categories), requestID: requestID.uuidString.lowercased(),
                                                center: Center(query.center), categories: ordered,
                                                radiusM: query.radius, sort: query.nearest ? "distance" : "relevance"))
    }

    static func encodeReverse(_ center: LioTaxiPlace.Coordinate, requestID: UUID) throws -> Data {
        try encoder.encode(ReverseRequest(version: version, requestID: requestID.uuidString.lowercased(),
                                          center: Center(center)))
    }

    /// `requested` groups the results: an essentials search (one kind at a time) labels every place with that kind,
    /// since luggage storage is found by name and its places carry their own type codes; leisure kinds are told
    /// apart by type code as before.
    static func readPlaces(_ data: Data, requested: Set<LioNearbyPlace.Category> = Set(LioNearbyPlace.Category.leisure)) throws -> [LioNearbyPOI] {
        let reply = try decoder.decode(SearchReply.self, from: data)
        guard reply.version == version(for: requested), reply.source == "Gaode" else { throw LioNearbyFailure.unavailable }
        let only = requested.count == 1 ? requested.first.flatMap { $0.isEssential ? $0 : nil } : nil
        return try reply.items.map { item in
            let name = item.nameZh.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !item.id.isEmpty, !name.isEmpty, item.coordinateSystem == "GCJ-02",
                  (-90...90).contains(item.lat), (-180...180).contains(item.lng) else {
                throw LioNearbyFailure.unavailable
            }
            return LioNearbyPOI(
                id: item.id, name: name, address: nonEmpty(item.addressZh),
                category: only ?? LioNearbyPOI.category(typeCode: item.typeCode),
                coordinate: .init(latitude: item.lat, longitude: item.lng, referenceSystem: .gcj02),
                meters: item.distanceM.flatMap { $0 >= 0 ? $0 : nil },
                rating: nonEmpty(item.rating), cost: nonEmpty(item.costCny).map { "¥" + $0 },
                hours: nonEmpty(item.openingHours), photo: trustedPhoto(item.photoUrl))
        }
    }

    static func readAddress(_ data: Data) throws -> String? {
        let reply = try decoder.decode(ReverseReply.self, from: data)
        guard reply.version == version, reply.source == "Gaode" else { throw LioNearbyFailure.unavailable }
        return nonEmpty(reply.addressZh)
    }

    static func failure(status: Int, body: Data) -> LioNearbyFailure {
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

    /// The relay already limits photos to Gaode hosts; the app checks again before loading one.
    private static func trustedPhoto(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value), url.scheme == "https", let host = url.host,
              host.hasSuffix(".autonavi.com") || host.hasSuffix(".amap.com"), url.user == nil else { return nil }
        return url
    }
}

@MainActor public struct LioNearbyRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)
    private enum Operation: String { case search, reverse }

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

    var permitsLocalAccess: Bool { isCurrent() }

    func requireCurrentSession() throws {
        guard isCurrent() else { throw CancellationError() }
        try Task.checkCancellation()
    }

    func search(_ query: LioNearbyQuery) async throws -> [LioNearbyPOI] {
        guard !query.categories.isEmpty else { return [] }
        let body = try LioNearbyWire.encodeSearch(query, requestID: newRequestID())
        return try LioNearbyWire.readPlaces(try await post(.search, body: body), requested: query.categories)
    }

    func reverse(_ center: LioTaxiPlace.Coordinate) async throws -> String? {
        let body = try LioNearbyWire.encodeReverse(center, requestID: newRequestID())
        return try LioNearbyWire.readAddress(try await post(.reverse, body: body))
    }

    /// Metro station surroundings (METRO-NEARBY.1, #1450): the same signed-in relay and limits, its own route.
    func metroNearby(_ body: Data) async throws -> Data {
        try await send(to: baseURL.appending(path: "v1/tools/metro/nearby"), body: body)
    }

    private func post(_ operation: Operation, body: Data) async throws -> Data {
        try await send(to: baseURL.appending(path: "v1/tools/nearby").appending(path: operation.rawValue), body: body)
    }

    private func send(to url: URL, body: Data) async throws -> Data {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else { throw LioNearbyFailure.signInRequired }
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = body

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await exchange(request)
        } catch {
            try requireCurrentSession()
            if (error as? URLError)?.code == .timedOut { throw LioNearbyFailure.timedOut }
            throw error
        }
        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url else { throw LioNearbyFailure.unavailable }
        guard http.statusCode == 200 else { throw LioNearbyWire.failure(status: http.statusCode, body: data) }
        return data
    }
}

#if os(iOS)
extension LioNearbyRelayClient {
    /// Internal testers only, when the build enables Nearby (`G2CNearbyEnabled`); the relay decides per account.
    public static func internalBeta(endpoint: MessageEndpoint, isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioNearbyRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CNearbyEnabled") as? String == "YES" else { return nil }
        return LioNearbyRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
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
            guard response.expectedContentLength <= limit else { throw LioNearbyFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioNearbyFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}
#endif
