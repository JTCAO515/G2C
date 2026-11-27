import Foundation

struct LioNearbyPlace: Identifiable, Equatable {
    enum Category: String, CaseIterable {
        case food, sights, coffee, shopping
        /// Essentials (NEARBY.2, #1621): searched one kind at a time; luggage storage only by name.
        case atm, pharmacy, toilet, luggage
        /// Community services (#2006): like luggage storage, found by a fixed name keyword (社区服务中心), on its own.
        case community

        static let leisure: [Self] = [.food, .sights, .coffee, .shopping]
        /// What the "Convenience" group offers (#2006, formerly "Essentials").
        static let essentials: [Self] = [.atm, .pharmacy, .toilet, .luggage, .community]
        var isEssential: Bool { Self.essentials.contains(self) }
        /// Kinds Gaode has no type code for: searched by a fixed keyword, so only ever on their own.
        var isSearchedByName: Bool { self == .luggage || self == .community }

        /// Short chip label.
        func title(_ language: LioLanguage) -> String {
            switch self {
            case .food: language.text("Food", "美食")
            case .sights: language.text("Sights", "景点")
            case .coffee: language.text("Coffee", "咖啡")
            case .shopping: language.text("Shopping", "购物")
            case .atm: language.text("Bank ATMs", "银行 ATM")
            case .pharmacy: language.text("Pharmacy", "药房")
            case .toilet: language.text("Public toilets", "公共厕所")
            case .luggage: language.text("Luggage storage", "行李寄存")
            case .community: language.text("Community services", "社区服务")
            }
        }

        /// The fixed wording from NEARBY.2 shown with the results. Never say an ATM takes foreign cards.
        func heading(_ language: LioLanguage) -> String {
            switch self {
            case .atm: language.text("Bank ATMs (check the machine's sign for foreign cards)", "银行 ATM（是否支持外卡请看机身标识）")
            case .luggage: language.text("Luggage storage (found by name; some may be missing)", "行李寄存（按名称搜索，结果可能不全）")
            case .community: language.text("Community services (found by name; some may be missing)",
                                           "社区服务（按“社区服务中心”名称搜索，结果可能不全）")
            default: title(language)
            }
        }
    }

    enum Operation: String, CaseIterable, Identifiable {
        var id: Self { self }
        case taxi, directions, showAddress, askLio, addToTrip

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .taxi: language.text("Taxi here", "打车去这里")
            case .directions: language.text("Directions", "导航")
            case .showAddress: language.text("Show the address", "出示中文地址")
            case .askLio: language.text("Ask Lio", "问 Lio")
            case .addToTrip: language.text("Add to trip", "加进行程")
            }
        }
    }

    /// The group's name in the Nearby page (#2006). It was "Essentials" / "必需品".
    static func convenienceTitle(_ language: LioLanguage) -> String {
        language.text("Convenience", "便利")
    }

    /// Essentials (NEARBY.2) appear only when the build enables them (`G2CNearbyEssentialsEnabled`, off by default);
    /// Debug previews can show them with `--lio-nearby-essentials`.
    static var essentialsEnabled: Bool {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--lio-nearby-essentials") { return true }
        #endif
        return Bundle.main.object(forInfoDictionaryKey: "G2CNearbyEssentialsEnabled") as? String == "YES"
    }

    let id: String
    let name: String
    let englishName: String?
    let address: String
    let category: Category
    let meters: Int
    let rating: String?
    let cost: String?
    let isOpen: Bool?

    static func filter(_ places: [Self], categories: Set<Category>, radius: Int, nearest: Bool) -> [Self] {
        let matching = places.filter { categories.contains($0.category) && $0.meters <= radius }
        return nearest ? matching.sorted { $0.meters < $1.meters } : matching
    }
}

#if DEBUG
extension LioNearbyPlace {
    static let fixture: [Self] = [
        .init(id: "food", name: "川味小馆", englishName: "Sichuan Kitchen", address: "示例路 12 号",
              category: .food, meters: 360, rating: "4.6", cost: "¥45", isOpen: true),
        .init(id: "sights", name: "街心公园", englishName: "Neighborhood Park", address: "示例路 20 号",
              category: .sights, meters: 120, rating: nil, cost: nil, isOpen: nil),
        .init(id: "coffee", name: "街角咖啡", englishName: "Corner Coffee", address: "示例路 65 号",
              category: .coffee, meters: 620, rating: "4.5", cost: nil, isOpen: false),
        .init(id: "shopping", name: "小街市场", englishName: nil, address: "示例路 125 号",
              category: .shopping, meters: 1800, rating: nil, cost: nil, isOpen: nil),
    ]
}
#endif
