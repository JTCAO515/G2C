import Foundation

/// The places the Stay and Explore tools offer (#2004, #2005): only what we have collected (the place library),
/// never a web-wide search. It adds to `LioPlace` (#1992) the few fields those tools sort and filter by and
/// `LioPlace` does not keep: tier, rank, hotel star and price band, whether the hotel serves foreign guests, and
/// the AMap id used to match a nearby search result with a place of ours.
///
/// Where the places come from:
/// 1. `LioPlaces.v1.json`, the App's slim copy of the reviewed library. In a release build this is all there is,
///    and until the library has reviewed entries it is empty, so every screen built on this has an empty state.
/// 2. Debug builds only: the development pack named by `--places-dev-pack <path>` (`LioDevPlacesPack`, unreviewed
///    candidates). Its places are marked as development data wherever they are shown.
struct LioPlaceCatalog: Sendable {
    /// Hotel price per night, the library's `price_band`.
    enum PriceBand: String, CaseIterable, Sendable {
        case under500 = "<500"
        case from500 = "500-1000"
        case from1000 = "1000-2000"
        case over2000 = ">2000"

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .under500: language.text("Under ¥500", "¥500 以下")
            case .from500: language.text("¥500–1,000", "¥500–1000")
            case .from1000: language.text("¥1,000–2,000", "¥1000–2000")
            case .over2000: language.text("Over ¥2,000", "¥2000 以上")
            }
        }
    }

    struct Extras: Equatable, Sendable {
        /// `main` places come before `backup` ones.
        let isMainTier: Bool
        let rank: Int?
        /// Hotel star rating (1...5) when the library has one.
        let star: Int?
        let priceBand: PriceBand?
        /// `false` only when the library says the hotel does not serve foreign guests.
        let acceptsForeigners: Bool?
        let amapID: String?
    }

    struct Entry: Identifiable, Equatable, Sendable {
        let place: LioPlace
        let extras: Extras
        /// From the development pack: unreviewed, to be shown as development data.
        let isDevelopment: Bool
        var id: String { place.id }
    }

    let entries: [Entry]

    var isDevelopment: Bool { entries.contains { $0.isDevelopment } }
    var hotels: [Entry] { entries.filter { $0.place.category == .hotel } }

    /// The library places, then the development pack's places that the library does not already have.
    init(library: Data?, developmentPack: Data? = nil) {
        var seen = Set<String>()
        var entries: [Entry] = []
        for (data, isDevelopment) in [(library, false), (developmentPack, true)] {
            guard let data else { continue }
            let extras = Self.extras(in: data)
            for place in LioPlaceRepository.places(in: data) where seen.insert(place.id).inserted {
                entries.append(Entry(place: place, extras: extras[place.id] ?? .none, isDevelopment: isDevelopment))
            }
        }
        self.entries = entries
    }

    init(entries: [Entry]) { self.entries = entries }

    func entry(id: String) -> Entry? { entries.first { $0.id == id } }

    /// A repository over these places, for the place page.
    var repository: LioPlaceRepository { LioPlaceRepository(places: entries.map(\.place)) }

    // MARK: Reading the extra fields

    /// Reads `tier`, `rank`, `star`, `price_band`, `accepts_foreigners` and `location.amap_id` for each id. An
    /// entry or field that is missing or of another type just has no value; nothing here can make a file unreadable.
    static func extras(in data: Data) -> [String: Extras] {
        let object = try? JSONSerialization.jsonObject(with: data)
        let rows: [Any]
        if let document = object as? [String: Any], let places = document["places"] as? [Any] { rows = places }
        else if let bare = object as? [Any] { rows = bare }
        else { return [:] }
        var result: [String: Extras] = [:]
        for case let row as [String: Any] in rows {
            guard let id = row["id"] as? String, !id.isEmpty, result[id] == nil else { continue }
            let star = (row["star"] as? Int).flatMap { (1...5).contains($0) ? $0 : nil }
            let location = row["location"] as? [String: Any]
            result[id] = Extras(
                isMainTier: (row["tier"] as? String) != "backup",
                rank: (row["rank"] as? Int).flatMap { $0 > 0 ? $0 : nil },
                star: star,
                priceBand: (row["price_band"] as? String).flatMap(PriceBand.init(rawValue:)),
                acceptsForeigners: row["accepts_foreigners"] as? Bool,
                amapID: (location?["amap_id"] as? String).flatMap { $0.isEmpty ? nil : $0 })
        }
        return result
    }

    // MARK: This build's catalog

    static let libraryResource = LioPlaceRepository.libraryResource

    /// The catalog this build shows: the library, plus in Debug builds the development pack when one was asked for.
    static let current: LioPlaceCatalog = {
        let library = LioPlaceRepository.resource(libraryResource)
        #if DEBUG
        return LioPlaceCatalog(library: library, developmentPack: developmentPackData())
        #else
        return LioPlaceCatalog(library: library)
        #endif
    }()

    #if DEBUG
    /// The pack's bytes, only when `LioDevPlacesPack` accepts it (right version, nothing marked as reviewed).
    static func developmentPackData(arguments: [String] = ProcessInfo.processInfo.arguments,
                                    environment: [String: String] = ProcessInfo.processInfo.environment) -> Data? {
        guard LioDevPlacesPack.load(arguments: arguments, environment: environment) != nil else { return nil }
        let path: String?
        if let at = arguments.firstIndex(of: LioDevPlacesPack.argument), at + 1 < arguments.count { path = arguments[at + 1] }
        else { path = environment[LioDevPlacesPack.environmentKey] }
        return path.flatMap { try? Data(contentsOf: URL(fileURLWithPath: $0)) }
    }
    #endif
}

extension LioPlaceCatalog.Extras {
    static let none = LioPlaceCatalog.Extras(isMainTier: true, rank: nil, star: nil, priceBand: nil,
                                             acceptsForeigners: nil, amapID: nil)
}

/// The tools built on the catalog (#2004, #2005) are off unless the build turns them on.
enum LioPlaceToolsFeature {
    static let infoKey = "G2CPlaceToolsEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains(LioDevPlacesPack.argument)
            || ProcessInfo.processInfo.arguments.contains("--lio-place-tools-preview")
        #else
        return false
        #endif
    }
}

// MARK: - Stay (#2004)

/// The Stay tool's filters. A hotel with no value for a filter that is set is left out (a "500–1000" search should
/// not list hotels whose price we do not know).
struct LioStayFilter: Equatable, Sendable {
    /// The six cities the library covers, in the order the chips show them.
    static let cities: [(id: String, zh: String, en: String)] = [
        ("beijing", "北京", "Beijing"), ("shanghai", "上海", "Shanghai"), ("guangzhou", "广州", "Guangzhou"),
        ("shenzhen", "深圳", "Shenzhen"), ("chengdu", "成都", "Chengdu"), ("chongqing", "重庆", "Chongqing"),
    ]

    var city: String?
    var band: LioPlaceCatalog.PriceBand?
    /// At least this many stars.
    var minimumStar: Int?

    var isFiltering: Bool { city != nil || band != nil || minimumStar != nil }

    /// Hotels that serve foreign guests and match, best first: main tier before backup, then library rank,
    /// then id so the order never jumps.
    func apply(to catalog: LioPlaceCatalog) -> [LioPlaceCatalog.Entry] {
        catalog.hotels.filter { entry in
            entry.extras.acceptsForeigners != false
                && (city == nil || entry.place.city == city)
                && (band == nil || entry.extras.priceBand == band)
                && (minimumStar == nil || (entry.extras.star ?? 0) >= minimumStar!)
        }
        .sorted { lhs, rhs in
            (lhs.extras.isMainTier ? 0 : 1, lhs.extras.rank ?? .max, lhs.id)
                < (rhs.extras.isMainTier ? 0 : 1, rhs.extras.rank ?? .max, rhs.id)
        }
    }

    /// Star filters only make sense when some hotel has a star rating.
    static func offersStars(in catalog: LioPlaceCatalog) -> Bool {
        catalog.hotels.contains { $0.extras.star != nil }
    }
}
