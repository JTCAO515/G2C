import Foundation

/// Which station is next to which curated place (#2008). A key station (天安门西, 王府井, 天坛东门) can show the place's
/// picture and a short introduction from the places library; the library owns the place and its images, this file
/// owns only the pairing. The pictures arrive with the library (#1987, #1988): until then the list is empty and the
/// station card is unchanged.
struct LioMetroStationPlaces: Equatable, Sendable {
    struct Link: Equatable, Sendable {
        let city: String
        let station: String
        /// Library place id, `pl_<city abbreviation>_<name>` (knowledge/places/README.md).
        let place: String
    }

    static let schema = "lio.metro.places.v1"

    let links: [Link]

    /// The library place next to a station, if one is linked.
    func place(city: String, station: String) -> String? {
        links.first { $0.city == city && $0.station == station }?.place
    }

    enum Failure: Error, Equatable { case unreadable, invalid(String) }

    private struct File: Decodable {
        struct Item: Decodable { let city, station, place: String }
        let schema: String
        let links: [Item]
    }

    /// Checks the file at the boundary: the schema, a place id in the library's shape, and one place per station.
    static func read(_ data: Data) throws -> LioMetroStationPlaces {
        guard let file = try? JSONDecoder().decode(File.self, from: data) else { throw Failure.unreadable }
        guard file.schema == schema else { throw Failure.invalid("schema") }
        var seen = Set<String>()
        var links: [Link] = []
        for item in file.links {
            guard !item.city.isEmpty, !item.station.isEmpty, isPlaceID(item.place),
                  seen.insert(item.city + "/" + item.station).inserted else { throw Failure.invalid(item.station) }
            links.append(Link(city: item.city, station: item.station, place: item.place))
        }
        return LioMetroStationPlaces(links: links)
    }

    static func isPlaceID(_ value: String) -> Bool {
        value.range(of: #"^pl_[a-z]{2,3}_[a-z0-9_]+$"#, options: .regularExpression) != nil
    }

    /// The bundled pairing. A missing or unreadable file means no links, never a broken map.
    static let bundled: LioMetroStationPlaces = {
        guard let url = Bundle.module.url(forResource: "LioMetroStationPlaces.v1", withExtension: "json", subdirectory: "Metro"),
              let data = try? Data(contentsOf: url), let places = try? read(data) else {
            return LioMetroStationPlaces(links: [])
        }
        return places
    }()
}

#if os(iOS)
import SwiftUI

/// Draws a library place's picture and short introduction for a station card (#2008). The places library (#1992 PlacePage,
/// #1987 images) supplies this; without it the station card simply has no landmark section. The picture is
/// an illustration and says so ("示意图").
typealias LioMetroLandmarkCard = @MainActor (_ placeID: String, _ language: LioLanguage) -> AnyView?

private struct LioMetroLandmarkCardKey: EnvironmentKey {
    static let defaultValue: LioMetroLandmarkCard? = nil
}

extension EnvironmentValues {
    var lioMetroLandmarkCard: LioMetroLandmarkCard? {
        get { self[LioMetroLandmarkCardKey.self] }
        set { self[LioMetroLandmarkCardKey.self] = newValue }
    }
}
#endif
