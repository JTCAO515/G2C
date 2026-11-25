import Foundation

/// A place around a metro station (#1450 station surroundings, METRO-NEARBY.1). Names come from Gaode;
/// the English ones are the server's best-effort translation and may be missing.
struct LioMetroNearbyPlace: Identifiable, Hashable, Sendable {
    let id: String
    let nameZH: String
    let nameEN: String?
    let addressZH: String?
    let addressEN: String?
    let category: LioNearbyPlace.Category?
    let coordinate: LioTaxiPlace.Coordinate
    let meters: Int?
    let rating: String?

    func name(in language: LioLanguage) -> String { language == .english ? (nameEN ?? nameZH) : nameZH }

    /// About 80 metres a minute on foot; never under one minute.
    var walkingMinutes: Int? { meters.map { max(1, Int(($0 + 79) / 80)) } }

    /// For the taxi page: the Chinese name and address are what the driver needs.
    var taxiPlace: LioTaxiPlace {
        LioTaxiPlace(nameZH: nameZH, nameEN: nameEN ?? nameZH, addressZH: addressZH, addressEN: addressEN,
                     coordinate: coordinate)
    }
}

/// The wire format of METRO-NEARBY.1 (contracts/api/METRO-NEARBY.1.md). The request names a station only:
/// it never carries a position, the traveller's or any other.
enum LioMetroNearbyWire {
    static let version = "METRO-NEARBY.1"

    private struct Request: Encodable {
        let version: String
        let requestID: String
        let cityID: String
        let stationID: String
        let categories: [String]
        let language: String

        enum CodingKeys: String, CodingKey {
            case version, requestID = "request_id", cityID = "city_id", stationID = "station_id", categories, language
        }
    }

    private struct Item: Decodable {
        let id: String
        let nameZh: String
        let nameEn: String?
        let addressZh: String?
        let addressEn: String?
        let typeCode: String
        let lat: Double
        let lng: Double
        let coordinateSystem: String
        let distanceM: Int?
        let rating: String?
    }

    private struct Reply: Decodable {
        let version: String
        let source: String
        let cityId: String
        let stationId: String
        let items: [Item]
    }

    static func encode(city: String, station: String, categories: Set<LioNearbyPlace.Category>,
                       language: LioLanguage, requestID: UUID) throws -> Data {
        guard !categories.isEmpty else { throw LioNearbyFailure.unavailable }
        let ordered = LioNearbyPlace.Category.allCases.filter(categories.contains).map(\.rawValue)
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try encoder.encode(Request(version: version, requestID: requestID.uuidString.lowercased(),
                                          cityID: city, stationID: station, categories: ordered,
                                          language: language == .english ? "en" : "zh"))
    }

    static func read(_ data: Data, city: String, station: String) throws -> [LioMetroNearbyPlace] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let reply = try decoder.decode(Reply.self, from: data)
        guard reply.version == version, reply.source == "Gaode", reply.cityId == city, reply.stationId == station,
              reply.items.count <= 25, Set(reply.items.map(\.id)).count == reply.items.count else {
            throw LioNearbyFailure.unavailable
        }
        return try reply.items.map { item in
            guard let name = text(item.nameZh), !item.id.isEmpty, item.coordinateSystem == "GCJ-02",
                  (-90...90).contains(item.lat), (-180...180).contains(item.lng) else {
                throw LioNearbyFailure.unavailable
            }
            return LioMetroNearbyPlace(
                id: item.id, nameZH: name, nameEN: text(item.nameEn), addressZH: text(item.addressZh),
                addressEN: text(item.addressEn), category: LioNearbyPOI.category(typeCode: item.typeCode),
                coordinate: .init(latitude: item.lat, longitude: item.lng, referenceSystem: .gcj02),
                meters: item.distanceM.flatMap { $0 >= 0 ? $0 : nil }, rating: text(item.rating))
        }
    }

    private static func text(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        return value
    }
}

/// Station surroundings for the metro map. Present only when the build enables it and the relay is signed in.
struct LioMetroNearbyService: Sendable {
    let search: @MainActor @Sendable (_ city: String, _ station: String, _ categories: Set<LioNearbyPlace.Category>,
                                      _ language: LioLanguage) async throws -> [LioMetroNearbyPlace]
}

extension LioMetroNearbyService {
    /// Internal testers only, when the build sets `G2CMetroNearbyEnabled` (off by default, M4 entry 12 item 5)
    /// on top of the Nearby relay; the server decides per account.
    @MainActor static func internalBeta(relay: LioNearbyRelayClient,
                                        bundle: Bundle = .main) -> Self? {
        guard bundle.object(forInfoDictionaryKey: "G2CMetroNearbyEnabled") as? String == "YES" else { return nil }
        return LioMetroNearbyService { city, station, categories, language in
            let body = try LioMetroNearbyWire.encode(city: city, station: station, categories: categories,
                                                     language: language, requestID: UUID())
            return try LioMetroNearbyWire.read(try await relay.metroNearby(body), city: city, station: station)
        }
    }

    #if DEBUG
    /// Sample places for the simulator (`--lio-metro-nearby-preview`), marked as samples in their names.
    @MainActor static var previewFromArguments: Self? {
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("--lio-metro-nearby-preview-closed") {
            // An account the server has not opened surroundings for (403 not_enabled).
            return LioMetroNearbyService { _, _, _, _ in throw LioNearbyFailure.notEnabled }
        }
        guard arguments.contains("--lio-metro-nearby-preview") else { return nil }
        return LioMetroNearbyService { _, station, categories, _ in
            let all: [(LioNearbyPlace.Category, String, String, Int, String?)] = [
                (.sights, "示例公园", "Sample Park", 240, "4.7"),
                (.sights, "示例博物馆", "Sample Museum", 610, "4.8"),
                (.shopping, "示例购物中心", "Sample Shopping Centre", 180, "4.5"),
                (.shopping, "示例商业街", "Sample Shopping Street", 520, nil),
                (.food, "示例粤菜馆", "Sample Cantonese Restaurant", 150, "4.6"),
                (.food, "示例面馆", "Sample Noodle House", 330, "4.4"),
                (.coffee, "示例咖啡馆", "Sample Café", 90, "4.3"),
            ]
            return all.enumerated().filter { categories.contains($0.element.0) }.map { index, row in
                LioMetroNearbyPlace(id: "\(station)-\(index)", nameZH: row.1, nameEN: row.2, addressZH: "示例地址\(index + 1)号",
                                    addressEN: nil, category: row.0,
                                    coordinate: .init(latitude: 23.1325, longitude: 113.3227, referenceSystem: .gcj02),
                                    meters: row.3, rating: row.4)
            }
        }
    }
    #endif
}

#if canImport(SwiftUI)
import SwiftUI

private struct LioMetroNearbyServiceKey: EnvironmentKey {
    static let defaultValue: LioMetroNearbyService? = nil
}

extension EnvironmentValues {
    var lioMetroNearby: LioMetroNearbyService? {
        get { self[LioMetroNearbyServiceKey.self] }
        set { self[LioMetroNearbyServiceKey.self] = newValue }
    }
}
#endif
