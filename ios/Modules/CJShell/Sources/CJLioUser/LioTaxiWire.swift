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
            let nameEN = switch quote.category {
            case "1": "Express"
            case "201": "Discount Express"
            case "8": "Premier"
            default: quote.name
            }
            return LioTaxiFare(id: quote.category, nameZH: quote.name, nameEN: nameEN,
                              priceDisplay: quote.priceDisplay)
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

    static func failure(status: Int, body: Data) -> LioTaxiFailure {
        let code = (try? decoder.decode(ErrorBody.self, from: body))?.error
        return switch (status, code) {
        case (401, "sign_in_required"): .signInRequired
        case (403, "not_enabled"): .notEnabled
        case (422, "out_of_service_area"): .outOfService
        case (422, "coordinate_unverified"): .coordinateUnverified
        case (429, "quota_exceeded"): .quotaExceeded
        case (429, "rate_limited"): .rateLimited
        default: .unavailable
        }
    }
}
