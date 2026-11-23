import Foundation

struct LioNearbyPlace: Identifiable, Equatable {
    enum Category: String, CaseIterable {
        case food, sights, coffee, shopping

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .food: language.text("Food", "美食")
            case .sights: language.text("Sights", "景点")
            case .coffee: language.text("Coffee", "咖啡")
            case .shopping: language.text("Shopping", "购物")
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
