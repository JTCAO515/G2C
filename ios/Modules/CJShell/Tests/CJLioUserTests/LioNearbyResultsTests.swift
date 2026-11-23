import Testing
@testable import CJLioUser

struct LioNearbyResultsTests {
    @Test func filtersCategoryAndRangeBeforeChangingTheSort() {
        let allowed: Set<LioNearbyPlace.Category> = [.food, .sights, .coffee]
        let source = LioNearbyPlace.fixture
        #expect(LioNearbyPlace.filter(source, categories: allowed, radius: 500, nearest: false).map(\.id)
                == ["food", "sights"])
        #expect(LioNearbyPlace.filter(source, categories: allowed, radius: 500, nearest: true).map(\.id)
                == ["sights", "food"])
        #expect(LioNearbyPlace.filter(source, categories: [], radius: 3000, nearest: true).isEmpty)
    }
}
