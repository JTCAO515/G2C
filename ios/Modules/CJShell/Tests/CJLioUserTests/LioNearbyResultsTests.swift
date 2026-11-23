import Testing
@testable import CJLioUser

struct LioNearbyResultsTests {
    @Test func filtersCategoryAndRangeBeforeChangingTheSort() {
        let allowed: Set<LioNearbyPlace.Category> = [.food, .sights, .coffee]
        let source: [LioNearbyPlace] = [
            place("food", .food, meters: 360),
            place("sights", .sights, meters: 120),
            place("coffee", .coffee, meters: 620),
        ]
        #expect(LioNearbyPlace.filter(source, categories: allowed, radius: 500, nearest: false).map(\.id)
                == ["food", "sights"])
        #expect(LioNearbyPlace.filter(source, categories: allowed, radius: 500, nearest: true).map(\.id)
                == ["sights", "food"])
        #expect(LioNearbyPlace.filter(source, categories: [], radius: 3000, nearest: true).isEmpty)
    }

    private func place(_ id: String, _ category: LioNearbyPlace.Category, meters: Int) -> LioNearbyPlace {
        LioNearbyPlace(id: id, name: id, englishName: nil, address: "", category: category,
                       meters: meters, rating: nil, cost: nil, isOpen: nil)
    }
}
