import Foundation
import Testing
@testable import CJLioUser

/// #2005: Explore keeps only the nearby results that are places we have collected, best first.
struct LioExploreGuideTests {
    private func place(_ id: String, _ zh: String, category: String = "food", tier: String = "main", rank: Int? = nil,
                       aliases: [String] = [], amap: String? = nil, lat: Double? = nil, lng: Double? = nil) -> [String: Any] {
        var row: [String: Any] = ["id": id, "city": "beijing", "category": category, "tier": tier, "name_zh": zh, "name_en": id,
                                  "aliases_zh": aliases, "review": ["status": "approved"]]
        if let rank { row["rank"] = rank }
        var location: [String: Any] = [:]
        if let amap { location["amap_id"] = amap }
        if let lat, let lng { location["gcj02"] = ["lat": lat, "lng": lng] }
        if !location.isEmpty { row["location"] = location }
        return row
    }

    private func catalog(_ rows: [[String: Any]]) throws -> LioPlaceCatalog {
        LioPlaceCatalog(library: try JSONSerialization.data(withJSONObject: ["places": rows]))
    }

    private func poi(_ id: String, _ name: String, _ category: LioNearbyPlace.Category, meters: Int? = 100,
                     lat: Double = 39.91, lng: Double = 116.40) -> LioNearbyPOI {
        LioNearbyPOI(id: id, name: name, address: nil, category: category,
                     coordinate: .init(latitude: lat, longitude: lng, referenceSystem: .gcj02),
                     meters: meters, rating: nil, cost: nil, hours: nil, photo: nil)
    }

    private let all = Set(LioExploreGuide.Kind.allCases)

    @Test func keepsOnlyNearbyResultsThatAreInTheLibrary() throws {
        let library = try catalog([place("pl_bj_a", "全聚德烤鸭店"), place("pl_bj_b", "故宫博物院", category: "attraction")])
        let items = LioExploreGuide.intersect([
            poi("1", "全聚德烤鸭店", .food), poi("2", "路边小店", .food), poi("3", "故宫博物院", .sights),
        ], with: library, kinds: all)
        #expect(Set(items.map(\.id)) == ["pl_bj_a", "pl_bj_b"])
    }

    @Test func matchesByAmapIdBeforeName() throws {
        let library = try catalog([place("pl_bj_a", "完全不同的名字", amap: "B0FFF")])
        #expect(LioExploreGuide.match(poi("B0FFF", "别的名字", .food), in: library)?.id == "pl_bj_a")
        #expect(LioExploreGuide.match(poi("B0000", "别的名字", .food), in: library) == nil)
    }

    @Test func matchesNamesWithoutBranchNotesAndAliases() throws {
        let library = try catalog([place("pl_bj_a", "全聚德(前门店)", aliases: ["Quanjude"]),
                                   place("pl_bj_b", "老北京炸酱面馆")])
        #expect(LioExploreGuide.match(poi("1", "全聚德烤鸭店（王府井店）", .food), in: library)?.id == "pl_bj_a")
        #expect(LioExploreGuide.match(poi("2", "老北京炸酱面馆 (簋街店)", .food), in: library)?.id == "pl_bj_b")
        // Too short to trust, and a different place with a similar start.
        #expect(LioExploreGuide.match(poi("3", "全", .food), in: library) == nil)
        #expect(LioExploreGuide.match(poi("4", "老北京", .food), in: library)?.id == "pl_bj_b") // 3 characters, contained
        #expect(LioExploreGuide.match(poi("5", "北京", .food), in: library) == nil)
        #expect(LioExploreGuide.core("全聚德烤鸭店 (前门店)") == "全聚德烤鸭店")
        #expect(LioExploreGuide.core("A·B  C【x】") == "abc")
    }

    @Test func aFarAwayBranchIsNotOurPlace() throws {
        let library = try catalog([place("pl_bj_a", "全聚德烤鸭店", lat: 39.90, lng: 116.40)])
        #expect(LioExploreGuide.match(poi("1", "全聚德烤鸭店", .food, lat: 39.90, lng: 116.401), in: library)?.id == "pl_bj_a")
        #expect(LioExploreGuide.match(poi("2", "全聚德烤鸭店", .food, lat: 39.99, lng: 116.40), in: library) == nil)
    }

    @Test func neverMatchesHotelsOrHubs() throws {
        let library = try catalog([place("pl_bj_h", "北京示例酒店", category: "hotel"), place("pl_bj_x", "首都机场", category: "hub")])
        #expect(LioExploreGuide.match(poi("1", "北京示例酒店", .food), in: library) == nil)
        #expect(LioExploreGuide.match(poi("2", "首都机场", .sights), in: library) == nil)
    }

    @Test func respectsTheChosenKindsAndTheResultsOwnKind() throws {
        let library = try catalog([place("pl_bj_a", "全聚德烤鸭店"), place("pl_bj_b", "故宫博物院", category: "attraction"),
                                   place("pl_bj_c", "王府井百货", category: "shopping")])
        let results = [poi("1", "全聚德烤鸭店", .food), poi("2", "故宫博物院", .sights), poi("3", "王府井百货", .shopping)]
        #expect(Set(LioExploreGuide.intersect(results, with: library, kinds: [.food]).map(\.id)) == ["pl_bj_a"])
        #expect(Set(LioExploreGuide.intersect(results, with: library, kinds: [.sights, .shopping]).map(\.id)) == ["pl_bj_b", "pl_bj_c"])
        #expect(LioExploreGuide.intersect(results, with: library, kinds: []).isEmpty)
        // A result AMap files as shopping is not our restaurant of the same name.
        #expect(LioExploreGuide.intersect([poi("9", "全聚德烤鸭店", .shopping)], with: library, kinds: all).isEmpty)
    }

    @Test func ordersMainTierThenRankThenNearest() throws {
        let library = try catalog([place("pl_bj_a", "甲餐厅", tier: "backup", rank: 1), place("pl_bj_b", "乙餐厅", rank: 2),
                                   place("pl_bj_c", "丙餐厅", rank: 1), place("pl_bj_d", "丁餐厅"), place("pl_bj_e", "戊餐厅")])
        let results = [poi("1", "甲餐厅", .food, meters: 10), poi("2", "乙餐厅", .food, meters: 50),
                       poi("3", "丙餐厅", .food, meters: 900), poi("4", "丁餐厅", .food, meters: 300),
                       poi("5", "戊餐厅", .food, meters: 100)]
        #expect(LioExploreGuide.intersect(results, with: library, kinds: all).map(\.id)
                == ["pl_bj_c", "pl_bj_b", "pl_bj_e", "pl_bj_d", "pl_bj_a"])
    }

    @Test func aPlaceFoundTwiceKeepsItsNearestResult() throws {
        let library = try catalog([place("pl_bj_a", "全聚德烤鸭店")])
        let items = LioExploreGuide.intersect([poi("1", "全聚德烤鸭店", .food, meters: 700), poi("2", "全聚德烤鸭店", .food, meters: 200)],
                                              with: library, kinds: all)
        #expect(items.map(\.metres) == [200])
    }

    @Test func anEmptyLibraryOrNoResultsGivesNothing() throws {
        #expect(LioExploreGuide.intersect([poi("1", "全聚德烤鸭店", .food)], with: LioPlaceCatalog(library: nil), kinds: all).isEmpty)
        let library = try catalog([place("pl_bj_a", "全聚德烤鸭店")])
        #expect(LioExploreGuide.intersect([], with: library, kinds: all).isEmpty)
    }

    @Test func theQueryAsksAMapForTheChosenKinds() {
        let center = LioTaxiPlace.Coordinate(latitude: 39.9, longitude: 116.4, referenceSystem: .wgs84)
        let query = LioExploreGuide.query(center: center, kinds: [.food, .shopping], radius: 1000)
        #expect(query.categories == [.food, .coffee, .shopping])
        #expect(query.radius == 1000 && !query.nearest)
        // Leisure kinds only: the search stays on the frozen NEARBY.1 request.
        #expect(!query.categories.contains { $0.isEssential })
        #expect(LioNearbyWire.version(for: query.categories) == "NEARBY.1")
        #expect(Set(LioExploreGuide.Kind.allCases.flatMap(\.nearbyCategories)).count == 4)
    }
}
