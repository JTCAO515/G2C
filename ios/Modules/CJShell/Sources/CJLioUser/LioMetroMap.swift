import Foundation

/// Interactive metro map data (#1454), bundled JSON produced by S (`METRO.1`, proposal in
/// `docs/design/lio-metro-map.md`). Decoded once and validated here; the view trusts the result.
struct LioMetroMap: Equatable, Sendable {
    struct Line: Equatable, Identifiable, Sendable {
        let id: String
        let nameZH: String
        let nameEN: String
        /// "#RRGGBB"
        let color: String
        /// Station IDs in running order. A loop line repeats its first station at the end.
        let stations: [String]
    }

    struct Station: Equatable, Identifiable, Sendable {
        let id: String
        let nameZH: String
        let nameEN: String
        let latitude: Double
        let longitude: Double
        let referenceSystem: LioTaxiPlace.Coordinate.ReferenceSystem
        /// Schematic position in 0...1 when the data has one; otherwise projected from the coordinate.
        let x: Double
        let y: Double
        let lines: [String]

        var isInterchange: Bool { lines.count > 1 }
    }

    struct Source: Equatable, Sendable {
        let name: String
        let license: String
        let url: URL
    }

    let city: String
    let dataVersion: String
    let source: Source
    let lines: [Line]
    let stations: [Station]

    func station(_ id: String) -> Station? { stations.first { $0.id == id } }
    func line(_ id: String) -> Line? { lines.first { $0.id == id } }

    /// The station nearest to a point in map space (0...1), if any lies within `radius`.
    func station(near x: Double, _ y: Double, radius: Double) -> Station? {
        stations
            .map { ($0, hypot($0.x - x, $0.y - y)) }
            .filter { $0.1 <= radius }
            .min { $0.1 < $1.1 }?.0
    }

    /// Lines through a station, in the order the data lists the lines.
    func lines(at station: Station) -> [Line] { lines.filter { station.lines.contains($0.id) } }
}

enum LioMetroMapFailure: Error, Equatable { case unreadable, invalid(String) }

enum LioMetroMapWire {
    static let version = "METRO.1"

    private struct File: Decodable {
        struct Source: Decodable { let name: String; let license: String; let url: String }
        struct Line: Decodable {
            let id: String; let nameZh: String; let nameEn: String; let color: String; let stations: [String]
        }
        struct Station: Decodable {
            let id: String; let nameZh: String; let nameEn: String
            let lat: Double; let lng: Double; let coordinateSystem: String
            let x: Double?; let y: Double?
        }
        let version: String
        let city: String
        let dataVersion: String
        let source: Source
        let lines: [Line]
        let stations: [Station]
    }

    static func read(_ data: Data) throws -> LioMetroMap {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let file = try? decoder.decode(File.self, from: data) else { throw LioMetroMapFailure.unreadable }
        guard file.version == version else { throw LioMetroMapFailure.invalid("version") }
        guard !file.lines.isEmpty, !file.stations.isEmpty else { throw LioMetroMapFailure.invalid("empty") }
        guard let url = URL(string: file.source.url), url.scheme == "https", !file.source.name.isEmpty,
              !file.source.license.isEmpty else { throw LioMetroMapFailure.invalid("source") }

        let stationIDs = file.stations.map(\.id)
        guard Set(stationIDs).count == stationIDs.count else { throw LioMetroMapFailure.invalid("duplicate station") }
        guard Set(file.lines.map(\.id)).count == file.lines.count else { throw LioMetroMapFailure.invalid("duplicate line") }
        let known = Set(stationIDs)
        for line in file.lines {
            guard line.stations.count >= 2, line.stations.allSatisfy(known.contains),
                  isHexColor(line.color), !line.nameZh.isEmpty, !line.nameEn.isEmpty else {
                throw LioMetroMapFailure.invalid("line \(line.id)")
            }
        }
        for station in file.stations {
            guard !station.nameZh.isEmpty, !station.nameEn.isEmpty,
                  (-90...90).contains(station.lat), (-180...180).contains(station.lng),
                  ["WGS-84", "GCJ-02"].contains(station.coordinateSystem),
                  (station.x == nil) == (station.y == nil),
                  [station.x, station.y].allSatisfy({ $0.map { (0...1).contains($0) } ?? true }) else {
                throw LioMetroMapFailure.invalid("station \(station.id)")
            }
        }

        // Without a schematic layout, fit the coordinates into the unit square keeping their aspect.
        let schematic = file.stations.allSatisfy { $0.x != nil }
        let lats = file.stations.map(\.lat), lngs = file.stations.map(\.lng)
        let midLat = ((lats.min() ?? 0) + (lats.max() ?? 0)) / 2
        let xs = lngs.map { $0 * cos(midLat * .pi / 180) }
        let minX = xs.min() ?? 0, maxY = lats.max() ?? 0
        let span = max((xs.max() ?? 0) - minX, maxY - (lats.min() ?? 0), .leastNonzeroMagnitude)

        let membership = Dictionary(grouping: file.lines.flatMap { line in line.stations.map { ($0, line.id) } },
                                    by: \.0).mapValues { Array(Set($0.map(\.1))).sorted() }
        let stations = file.stations.enumerated().map { index, item in
            LioMetroMap.Station(id: item.id, nameZH: item.nameZh, nameEN: item.nameEn,
                                latitude: item.lat, longitude: item.lng,
                                referenceSystem: item.coordinateSystem == "GCJ-02" ? .gcj02 : .wgs84,
                                x: schematic ? item.x! : (xs[index] - minX) / span,
                                y: schematic ? item.y! : (maxY - item.lat) / span,
                                lines: membership[item.id] ?? [])
        }
        return LioMetroMap(city: file.city, dataVersion: file.dataVersion,
                           source: .init(name: file.source.name, license: file.source.license, url: url),
                           lines: file.lines.map { .init(id: $0.id, nameZH: $0.nameZh, nameEN: $0.nameEn,
                                                         color: $0.color, stations: $0.stations) },
                           stations: stations)
    }

    private static func isHexColor(_ value: String) -> Bool {
        value.count == 7 && value.first == "#" && value.dropFirst().allSatisfy(\.isHexDigit)
    }
}
