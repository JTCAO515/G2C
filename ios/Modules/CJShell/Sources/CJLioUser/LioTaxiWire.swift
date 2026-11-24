import Foundation

enum LioTaxiWire {
    enum LinkType: String, Decodable {
        case https, appScheme = "app_scheme"
    }

    private static let version = "TAXI.1"

    private struct Point: Encodable {
        let lat: Double
        let lng: Double
        let coordinateSystem: String
        let name: String

        enum CodingKeys: String, CodingKey {
            case lat, lng, coordinateSystem = "coordinate_system", name
        }

        init(place: LioTaxiPlace) throws {
            let coordinate = place.coordinate
            guard (-90...90).contains(coordinate.latitude),
                  (-180...180).contains(coordinate.longitude) else {
                throw LioTaxiFailure.coordinateUnverified
            }
            lat = coordinate.latitude
            lng = coordinate.longitude
            coordinateSystem = coordinate.referenceSystem == .wgs84 ? "WGS-84" : "GCJ-02"
            name = place.nameZH
        }
    }

    private struct Request: Encodable {
        let version: String
        let origin: Point
        let destination: Point
    }

    private struct Estimate: Decodable {
        struct Vehicle: Decodable {
            let category: String
            let name: String
            let currency: String
            let priceDisplay: String
            let priceMinMinor: Int?
            let priceMaxMinor: Int?
        }

        let version: String
        let vehicles: [Vehicle]
        let observedAt: String
    }

    private struct Link: Decodable {
        let version: String
        let url: String
        let linkType: LinkType
    }

    private struct NearPoint: Encodable {
        let lat: Double
        let lng: Double
        let coordinateSystem: String

        enum CodingKeys: String, CodingKey {
            case lat, lng, coordinateSystem = "coordinate_system"
        }
    }

    private struct SearchRequest: Encodable {
        let version: String
        let query: String
        let city: String
        let near: NearPoint?
    }

    private struct SearchResult: Decodable {
        struct Item: Decodable {
            let nameZh: String
            let nameEn: String?
            let addressZh: String?
            let addressEn: String?
            let city: String?
            let lat: Double
            let lng: Double
            let coordinateSystem: String
        }

        let version: String
        let items: [Item]
    }

    private struct ErrorBody: Decodable {
        let error: String
    }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func encode(_ route: LioTaxiRoute) throws -> Data {
        let body = try Request(version: version, origin: Point(place: route.pickup),
                               destination: Point(place: route.destination))
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let data = try encoder.encode(body)
        guard data.count <= 4_096 else { throw LioTaxiFailure.unavailable }
        return data
    }

    static func encodeSearch(_ query: LioTaxiSearchQuery) throws -> Data {
        guard query.text.count <= LioTaxiSearchQuery.maximumLength else { throw LioTaxiFailure.queryTooLong }
        let near = try query.near.map { point -> NearPoint in
            guard (-90...90).contains(point.latitude), (-180...180).contains(point.longitude) else {
                throw LioTaxiFailure.coordinateUnverified
            }
            return NearPoint(lat: point.latitude, lng: point.longitude,
                             coordinateSystem: point.referenceSystem == .wgs84 ? "WGS-84" : "GCJ-02")
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let data = try encoder.encode(SearchRequest(version: version, query: query.text,
                                                    city: query.city.nameZH, near: near))
        guard data.count <= 4_096 else { throw LioTaxiFailure.queryTooLong }
        return data
    }

    static func readPlaces(_ data: Data) throws -> [LioTaxiPlace] {
        let result = try decoder.decode(SearchResult.self, from: data)
        guard result.version == version else { throw LioTaxiFailure.unavailable }
        return try result.items.map { item in
            let system: LioTaxiPlace.Coordinate.ReferenceSystem
            switch item.coordinateSystem {
            case "GCJ-02": system = .gcj02
            case "WGS-84": system = .wgs84
            default: throw LioTaxiFailure.unavailable
            }
            let name = item.nameZh.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, (-90...90).contains(item.lat), (-180...180).contains(item.lng) else {
                throw LioTaxiFailure.unavailable
            }
            let address = item.addressZh?.trimmingCharacters(in: .whitespacesAndNewlines)
            let english = item.nameEn?.trimmingCharacters(in: .whitespacesAndNewlines)
            let addressEnglish = item.addressEn?.trimmingCharacters(in: .whitespacesAndNewlines)
            // name_en / address_en are optional (#1451): without them English screens show the Chinese text.
            return LioTaxiPlace(nameZH: name, nameEN: english?.isEmpty == false ? english! : name,
                                addressZH: address?.isEmpty == false ? address : nil,
                                addressEN: addressEnglish?.isEmpty == false ? addressEnglish : nil,
                                coordinate: .init(latitude: item.lat, longitude: item.lng, referenceSystem: system))
        }
    }

    static func readFares(_ data: Data) throws -> [LioTaxiFare] {
        let estimate = try decoder.decode(Estimate.self, from: data)
        let formatter = ISO8601DateFormatter()
        let standardDate = formatter.date(from: estimate.observedAt)
        formatter.formatOptions.insert(.withFractionalSeconds)
        guard estimate.version == version, standardDate != nil || formatter.date(from: estimate.observedAt) != nil,
              Set(estimate.vehicles.map(\.category)).count == estimate.vehicles.count else {
            throw LioTaxiFailure.unavailable
        }
        return try estimate.vehicles.map { quote in
            guard !quote.category.isEmpty, !quote.name.isEmpty, !quote.priceDisplay.isEmpty else {
                throw LioTaxiFailure.unavailable
            }
            return LioTaxiFare(id: quote.category, nameZH: quote.name,
                               nameEN: LioTaxiFareText.englishName(category: quote.category, chinese: quote.name),
                               priceDisplay: LioTaxiFareText.price(display: quote.priceDisplay, currency: quote.currency,
                                                                   minMinor: quote.priceMinMinor,
                                                                   maxMinor: quote.priceMaxMinor))
        }
    }

    static func readLink(_ data: Data, allowing approvedTarget: (LinkType, URL) -> Bool) throws -> URL {
        let link = try decoder.decode(Link.self, from: data)
        guard link.version == version, let url = URL(string: link.url), let scheme = url.scheme,
              url.user == nil, url.password == nil else { throw LioTaxiFailure.unavailable }
        switch link.linkType {
        case .https:
            guard scheme == "https", let host = url.host, !host.isEmpty else { throw LioTaxiFailure.unavailable }
        case .appScheme:
            guard scheme != "http", scheme != "https" else { throw LioTaxiFailure.unavailable }
        }
        guard approvedTarget(link.linkType, url) else { throw LioTaxiFailure.unavailable }
        return url
    }

    static func approvesDiDiTarget(_ type: LinkType, _ url: URL) -> Bool {
        guard type == .https, let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              parts.host == "v.didi.cn", parts.port == nil, parts.fragment == nil,
              parts.percentEncodedPath == "/XvYQEWe", let coordinates = parts.queryItems,
              coordinates.count == 4,
              Set(coordinates.map(\.name)) == ["slat", "slng", "dlat", "dlng"] else { return false }
        return coordinates.allSatisfy { item in
            guard let value = item.value, let coordinate = Double(value) else { return false }
            let limit = item.name.hasSuffix("lat") ? 90.0 : 180.0
            return (-limit...limit).contains(coordinate)
        }
    }

    static func failure(status: Int, body: Data) -> LioTaxiFailure {
        let code = (try? decoder.decode(ErrorBody.self, from: body))?.error
        return switch (status, code) {
        case (401, "sign_in_required"): .signInRequired
        case (403, "not_enabled"): .notEnabled
        case (422, "out_of_service_area"): .outOfService
        case (422, "coordinate_unverified"): .coordinateUnverified
        case (429, "quota_exceeded"): .quotaExceeded
        case (429, "rate_limited"): .rateLimited
        case (504, "supplier_timeout"): .timedOut
        default: .unavailable
        }
    }
}
