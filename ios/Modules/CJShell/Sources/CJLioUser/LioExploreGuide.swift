import Foundation

/// Explore (#2005): what is near the traveller *and* in our place library, best first. The nearby search is AMap's
/// (the same relay as Nearby); its results are kept only when they are a place we have collected, so the list is
/// our recommendations, not every shop around. Nothing here talks to the network.
enum LioExploreGuide {
    /// The three kinds the tool offers. Coffee counts as food and drink.
    enum Kind: CaseIterable, Hashable, Sendable {
        case food, sights, shopping

        var nearbyCategories: [LioNearbyPlace.Category] {
            switch self {
            case .food: [.food, .coffee]
            case .sights: [.sights]
            case .shopping: [.shopping]
            }
        }

        init?(_ category: LioPlace.Category) {
            switch category {
            case .food: self = .food
            case .attraction: self = .sights
            case .shopping: self = .shopping
            case .hotel, .hub, .other: return nil
            }
        }

        init?(_ category: LioNearbyPlace.Category?) {
            switch category {
            case .food?, .coffee?: self = .food
            case .sights?: self = .sights
            case .shopping?: self = .shopping
            default: return nil
            }
        }

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .food: language.text("Food & drink", "吃喝")
            case .sights: language.text("Sights", "景点")
            case .shopping: language.text("Shopping", "购物")
            }
        }

        var identifier: String {
            switch self {
            case .food: "food"
            case .sights: "sights"
            case .shopping: "shopping"
            }
        }
    }

    /// A place of ours that the nearby search also found.
    struct Item: Identifiable, Equatable, Sendable {
        let entry: LioPlaceCatalog.Entry
        let kind: Kind
        /// Distance from the traveller as AMap reports it, in metres.
        let metres: Int?
        var id: String { entry.id }
    }

    /// The nearby search to run for these kinds.
    static func query(center: LioTaxiPlace.Coordinate, kinds: Set<Kind>, radius: Int) -> LioNearbyQuery {
        let categories = Set(kinds.flatMap(\.nearbyCategories))
        return LioNearbyQuery(center: center, categories: categories, radius: radius, nearest: false)
    }

    /// Our places among `results`, main tier first, then library rank, then nearest. A place found twice keeps its
    /// nearest result.
    static func intersect(_ results: [LioNearbyPOI], with catalog: LioPlaceCatalog, kinds: Set<Kind>) -> [Item] {
        var best: [String: Item] = [:]
        for poi in results {
            guard let entry = match(poi, in: catalog), let kind = Kind(entry.place.category), kinds.contains(kind),
                  Kind(poi.category).map({ $0 == kind }) ?? true else { continue }
            let item = Item(entry: entry, kind: kind, metres: poi.meters)
            if let known = best[entry.id], (known.metres ?? .max) <= (item.metres ?? .max) { continue }
            best[entry.id] = item
        }
        return best.values.sorted { lhs, rhs in
            (lhs.entry.extras.isMainTier ? 0 : 1, lhs.entry.extras.rank ?? .max, lhs.metres ?? .max, lhs.id)
                < (rhs.entry.extras.isMainTier ? 0 : 1, rhs.entry.extras.rank ?? .max, rhs.metres ?? .max, rhs.id)
        }
    }

    /// The catalog entry a search result is, or nil. By AMap id when the library has one; otherwise by name, and
    /// when both have a coordinate they must be within 500 m (a chain's other branch is not our place).
    static func match(_ poi: LioNearbyPOI, in catalog: LioPlaceCatalog) -> LioPlaceCatalog.Entry? {
        if let id = catalog.entries.first(where: { $0.extras.amapID == poi.id }) { return id }
        let name = core(poi.name)
        guard name.count >= 2 else { return nil }
        return catalog.entries.first { entry in
            guard entry.place.category != .hotel, entry.place.category != .hub else { return false }
            if let point = entry.place.point,
               LioPlaceRepository.metres(from: point, to: .init(latitude: poi.coordinate.latitude,
                                                                longitude: poi.coordinate.longitude)) > 500 {
                return false
            }
            return ([entry.place.nameZH] + entry.place.aliasesZH).map(core).contains { candidate in
                candidate.count >= 2 && (candidate == name
                    || (min(candidate.count, name.count) >= 3 && (candidate.contains(name) || name.contains(candidate))))
            }
        }
    }

    /// A name without branch notes and spacing: "全聚德烤鸭店 (前门店)" → "全聚德烤鸭店".
    static func core(_ name: String) -> String {
        var text = name
        for (open, close) in [("(", ")"), ("（", "）"), ("[", "]"), ("【", "】")] {
            while let start = text.range(of: open), let end = text.range(of: close, range: start.upperBound..<text.endIndex) {
                text.removeSubrange(start.lowerBound..<end.upperBound)
            }
        }
        return text.filter { !$0.isWhitespace && $0 != "·" && $0 != "-" }.lowercased()
    }
}
