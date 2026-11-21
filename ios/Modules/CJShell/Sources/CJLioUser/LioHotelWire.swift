import Foundation

enum LioHotelWire {
    enum Failure: Error, Equatable {
        case invalidLocation, unavailable
    }

    private static let version = "HOTEL.1"

    private struct Location: Encodable {
        let lat: Double
        let lng: Double
        let radiusMetres: Int

        enum CodingKeys: String, CodingKey {
            case lat, lng, radiusMetres = "radius_m"
        }

        init(area: LioHotelArea) throws {
            guard area.center.referenceSystem == .wgs84,
                  (-90...90).contains(area.center.latitude),
                  (-180...180).contains(area.center.longitude),
                  area.radiusMetres > 0 else { throw Failure.invalidLocation }
            lat = area.center.latitude
            lng = area.center.longitude
            radiusMetres = area.radiusMetres
        }
    }

    private struct Request: Encodable {
        let version: String
        let city: String?
        let location: Location?
        let checkIn: String
        let checkOut: String
        let guests: Int
        let language: String

        enum CodingKeys: String, CodingKey {
            case version, city, location, checkIn = "check_in", checkOut = "check_out", guests, language
        }
    }

    private struct Response: Decodable {
        let version: String
        let url: String
        let appliedFilters: [LioHotelLink.Filter]
        let unappliedFilters: [LioHotelLink.Filter]
    }

    static func encode(_ search: LioHotelSearch) throws -> Data {
        let city: String?
        let location: Location?
        switch search.scope {
        case .city(let value):
            city = value
            location = nil
        case .area(let area):
            city = nil
            location = try Location(area: area)
        }
        let request = Request(version: version, city: city, location: location, checkIn: search.checkIn,
                              checkOut: search.checkOut, guests: search.guests,
                              language: search.language == .chinese ? "zh" : "en")
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try encoder.encode(request)
    }

    static func readLink(_ data: Data, allowing approvedTarget: (URL) -> Bool) throws -> LioHotelLink {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let link = try decoder.decode(Response.self, from: data)
        let applied = Set(link.appliedFilters)
        let unapplied = Set(link.unappliedFilters)
        guard link.version == version, applied.isDisjoint(with: unapplied),
              applied.count == link.appliedFilters.count, unapplied.count == link.unappliedFilters.count,
              let url = URL(string: link.url), url.scheme == "https", let host = url.host, !host.isEmpty,
              url.user == nil, url.password == nil, approvedTarget(url) else {
            throw Failure.unavailable
        }
        return LioHotelLink(destination: url, unappliedFilters: link.unappliedFilters)
    }
}
