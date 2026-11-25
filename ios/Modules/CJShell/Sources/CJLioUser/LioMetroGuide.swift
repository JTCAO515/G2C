import Foundation

/// A mainland city with a metro (#1421, #1450). The list is the bundled maps themselves; every listed city
/// opens straight into its interactive map.
struct LioMetroCity: Hashable, Identifiable, Sendable {
    let id: String
    let nameZH: String
    let nameEN: String
    let provinceZH: String

    var rawValue: String { id }

    func name(in language: LioLanguage) -> String { language.text(nameEN, nameZH) }

    /// The city's Chinese name, shown on its card in both languages so travellers can match signs.
    var nativeName: String { nameZH }

    var identifier: String { "lio.metro.city." + id }

    /// The bundled interactive map in `Resources/Metro`.
    var mapResource: String? { "LioMetroMap.\(id).v1" }

    /// Taxi place search covers only some cities; elsewhere the station sheet offers directions only.
    var taxiCity: LioTaxiCity? { LioTaxiCity(rawValue: id) }

    /// The card's second line: the Chinese name to match signs, or the province for Chinese readers.
    func detail(in language: LioLanguage) -> String { language == .english ? nameZH : provinceZH }
}

extension LioMetroCity {
    /// Every city in the bundled catalogue: the best-known first, then the rest by pinyin (JT 2026-11-25).
    static let allCases: [LioMetroCity] = catalogue()

    static func named(_ id: String) -> LioMetroCity? { allCases.first { $0.id == id } }

    /// The bundled source notice for the maps (`Resources/Metro/NOTICE.md`).
    static var noticeURL: URL? { Bundle.module.url(forResource: "NOTICE", withExtension: "md", subdirectory: "Metro") }

    static func cities(matching query: String = "") -> [LioMetroCity] {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return allCases.filter { city in
            text.isEmpty || city.nameZH.localizedStandardContains(text) || city.nameEN.localizedStandardContains(text)
                || city.provinceZH.localizedStandardContains(text) || city.id.localizedStandardContains(text)
        }
    }

    /// The catalogue is whatever maps are bundled: each map file carries its city's entry, so removing a
    /// city means deleting its one file and regenerating `Resources/Metro/NOTICE.md`, with no code change.
    /// A file whose entry does not read is left out rather than emptying the list; the data tests fail on it.
    static func catalogue() -> [LioMetroCity] {
        let entries = mapFiles.compactMap { try? read(entry: Data(contentsOf: $0)) }
        // One entry per city: a second file naming the same city is ignored instead of crashing the list.
        let featured = Dictionary(entries.compactMap { entry in entry.featured.map { (entry.city.id, $0) } },
                                  uniquingKeysWith: { first, _ in first })
        var seen = Set<String>()
        return sorted(entries.map(\.city).filter { seen.insert($0.id).inserted }, featured: featured)
    }

    /// The bundled map files, one per city, in file-name order.
    static var mapFiles: [URL] {
        (Bundle.module.urls(forResourcesWithExtension: "json", subdirectory: "Metro") ?? [])
            .filter { $0.lastPathComponent.hasPrefix("LioMetroMap.") }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    private struct Header: Decodable {
        struct Info: Decodable {
            let nameZH, nameEN, provinceZH: String
            let featured: Int?
        }
        let city: String
        let cityInfo: Info
    }

    /// Checks one map file's city entry at the boundary: an id, names in both languages and the province.
    /// `featured` (optional) puts a well-known city near the top of the list.
    static func read(entry data: Data) throws -> (city: LioMetroCity, featured: Int?) {
        guard let header = try? JSONDecoder().decode(Header.self, from: data) else { throw LioMetroMapFailure.unreadable }
        let info = header.cityInfo
        guard !header.city.isEmpty, !info.nameZH.isEmpty, !info.nameEN.isEmpty, !info.provinceZH.isEmpty else {
            throw LioMetroMapFailure.invalid("city entry")
        }
        if let rank = info.featured, rank < 1 { throw LioMetroMapFailure.invalid("city entry") }
        return (.init(id: header.city, nameZH: info.nameZH, nameEN: info.nameEN, provinceZH: info.provinceZH), info.featured)
    }

    /// Featured cities by their rank, then every other city by pinyin (the file id is the city's pinyin).
    static func sorted(_ cities: [LioMetroCity], featured: [String: Int]) -> [LioMetroCity] {
        cities.sorted { (featured[$0.id] ?? .max, $0.id) < (featured[$1.id] ?? .max, $1.id) }
    }
}
