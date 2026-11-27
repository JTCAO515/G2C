#if DEBUG
import Foundation

/// UNREVIEWED development place data (`knowledge/places/dev/places-dev-pack.v1.json`): the candidates Codex
/// drafted that nobody on the team has reviewed yet. It exists only so the place page, entity links and the
/// trip canvas can be built before the real library (`LioPlaces.v1.json`) has entries.
///
/// Debug builds only: this whole file is compiled out of Release and Beta builds, and the pack is **not** a
/// bundled resource (a test checks `Package.swift`). It is read from a path given at launch:
/// `--places-dev-pack <path>` or the environment variable `G2C_PLACES_DEV_PACK`. Nothing shows these places
/// to a traveler; a place from here must be shown as development data wherever it appears.
struct LioDevPlace: Decodable, Equatable, Sendable {
    struct Point: Decodable, Equatable, Sendable { let lat: Double; let lng: Double }
    struct Location: Decodable, Equatable, Sendable {
        let gcj02: Point
        let amapID: String?
        enum CodingKeys: String, CodingKey { case gcj02; case amapID = "amap_id" }
    }
    struct Review: Decodable, Equatable, Sendable { let status: String }

    let id: String
    let city: String
    let category: String
    let tier: String
    let nameZH: String
    let nameEN: String
    let aliasesZH: [String]?
    let aliasesEN: [String]?
    let addressZH: String?
    let districtZH: String?
    let introShortZH: String?
    let introShortEN: String?
    let introLongZH: String?
    let introLongEN: String?
    let hoursZH: String?
    let location: Location?
    let review: Review

    enum CodingKeys: String, CodingKey {
        case id, city, category, tier, location, review
        case nameZH = "name_zh", nameEN = "name_en", aliasesZH = "aliases_zh", aliasesEN = "aliases_en"
        case addressZH = "address_zh", districtZH = "district_zh"
        case introShortZH = "intro_short_zh", introShortEN = "intro_short_en"
        case introLongZH = "intro_long_zh", introLongEN = "intro_long_en", hoursZH = "hours_zh"
    }

    /// Every name this place answers to, for exact (case-folded) matching.
    var names: [String] { [nameZH, nameEN] + (aliasesZH ?? []) + (aliasesEN ?? []) }
}

struct LioDevPlacesPack: Equatable, Sendable {
    static let version = "g2c-places-dev.1"
    static let argument = "--places-dev-pack"
    static let environmentKey = "G2C_PLACES_DEV_PACK"

    let places: [LioDevPlace]

    private struct Document: Decodable { let version: String; let places: [LioDevPlace] }

    /// Nil when no pack was asked for, the file is missing or malformed, or any entry claims to be reviewed
    /// (a reviewed entry belongs in the real library, so a pack that has one is not this pack).
    static func load(arguments: [String] = ProcessInfo.processInfo.arguments,
                     environment: [String: String] = ProcessInfo.processInfo.environment) -> LioDevPlacesPack? {
        let path: String?
        if let at = arguments.firstIndex(of: argument), at + 1 < arguments.count { path = arguments[at + 1] }
        else { path = environment[environmentKey] }
        guard let path, !path.isEmpty, let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
              let document = try? JSONDecoder().decode(Document.self, from: data), document.version == version,
              document.places.allSatisfy({ $0.review.status == "unreviewed" }) else { return nil }
        return LioDevPlacesPack(places: document.places)
    }

    func place(id: String) -> LioDevPlace? { places.first { $0.id == id } }

    /// The place whose name or alias equals `name` (case-folded), optionally within one city.
    func match(name: String, city: String? = nil) -> LioDevPlace? {
        let key = name.lowercased()
        return places.first { place in
            (city == nil || place.city == city) && place.names.contains { $0.lowercased() == key }
        }
    }
}
#endif
