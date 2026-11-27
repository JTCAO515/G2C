import Foundation
import Testing
@testable import CJLioUser

/// #1997 / #2033 follow-up: the trip canvas finds places in the reviewed library, and in a Debug build launched with a
/// development pack in the pack as well; a name two places share is a miss; the hand-written samples are never used.
struct LioPlaceLookupTests {
    private static let libraryJSON = """
    {"version": "g2c-places-app.1", "places": [
      {"id": "pl_bj_gugong", "city": "beijing", "category": "attraction", "kind": "museum", "name_zh": "故宫博物院",
       "name_en": "The Palace Museum", "aliases_zh": ["故宫"], "aliases_en": ["Forbidden City"], "lat": 39.9165, "lng": 116.3971},
      {"id": "pl_bj_nocoord", "city": "beijing", "category": "food", "name_zh": "无坐标馆", "name_en": "No Coordinate"},
      {"id": "pl_bj_bad", "city": "beijing", "category": "food", "name_zh": "坏坐标", "name_en": "Bad Point", "lat": 0, "lng": 0},
      {"id": "pl_bj_dup_a", "city": "beijing", "category": "food", "name_zh": "老店", "name_en": "Old Shop A", "lat": 39.9, "lng": 116.4},
      {"id": "pl_bj_dup_b", "city": "beijing", "category": "food", "name_zh": "老店", "name_en": "Old Shop B", "lat": 39.91, "lng": 116.41},
      {"id": "pl_sh_dup_c", "city": "shanghai", "category": "food", "name_zh": "老店", "name_en": "Old Shop C", "lat": 31.2, "lng": 121.4}]}
    """

    private func lookup(library: String? = libraryJSON, arguments: [String] = ["app"],
                        environment: [String: String] = [:]) -> LioRepositoryPlaceLookup {
        LioRepositoryPlaceLookup(repository: LioPlaceLookups.canvasRepository(
            library: library.map { Data($0.utf8) }, arguments: arguments, environment: environment))
    }

    @Test func aNameOrAliasInEitherLanguageFindsThePlaceAndItsPoint() {
        let lookup = lookup()
        let expected = LioPlaceMatch(placeID: "pl_bj_gugong", coordinate: .init(latitude: 39.9165, longitude: 116.3971))
        for name in ["故宫博物院", "故宫", "the palace museum", " Forbidden City "] {
            #expect(lookup.match(name: name, city: "beijing") == expected, "\(name)")
            #expect(lookup.match(name: name, city: nil) == expected)
        }
        #expect(lookup.match(name: "故宫", city: "shanghai") == nil)         // another city's library does not answer
        #expect(lookup.match(name: "颐和园", city: "beijing") == nil)
        #expect(lookup.match(name: "  ", city: nil) == nil)
    }

    @Test func aPlaceWithoutAUsablePointKeepsItsIdAndHasNoCoordinate() {
        #expect(lookup().match(name: "无坐标馆", city: "beijing") == LioPlaceMatch(placeID: "pl_bj_nocoord", coordinate: nil))
        #expect(lookup().match(name: "坏坐标", city: "beijing") == LioPlaceMatch(placeID: "pl_bj_bad", coordinate: nil))
    }

    @Test func aNameTwoPlacesShareIsAMissUnlessTheCityTellsThemApart() {
        let lookup = lookup()
        #expect(lookup.match(name: "老店", city: "beijing") == nil)
        #expect(lookup.match(name: "老店", city: nil) == nil)
        #expect(lookup.match(name: "老店", city: "shanghai")?.placeID == "pl_sh_dup_c")
    }

    @Test func withoutALibraryNothingMatchesAndTheSamplesAreNotUsed() {
        #expect(lookup(library: nil).match(name: "故宫", city: nil) == nil)
        #expect(LioPlaceLookups.canvasRepository(library: nil).places.isEmpty)
        #expect(lookup(library: "not json").match(name: "故宫", city: nil) == nil)
    }

    #if DEBUG
    private static let packJSON = """
    {"version": "g2c-places-dev.1", "warning": "x", "generated_on": "2026-11-27", "places": [
      {"id": "pl_sh_waitan", "city": "shanghai", "category": "attraction", "tier": "main", "name_zh": "外滩",
       "name_en": "The Bund", "aliases_zh": [], "aliases_en": [], "location": {"gcj02": {"lat": 31.24, "lng": 121.49},
       "amap_id": null, "method": "manual"}, "rank": null, "review": {"status": "unreviewed"}},
      {"id": "pl_bj_gugong", "city": "beijing", "category": "attraction", "tier": "main", "name_zh": "故宫博物院",
       "name_en": "Palace Museum (dev)", "aliases_zh": [], "aliases_en": [], "location": null, "rank": null,
       "review": {"status": "unreviewed"}}]}
    """

    private func withPack<T>(_ body: (String) throws -> T) throws -> T {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("places-lookup-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appendingPathComponent("pack.json")
        try Self.packJSON.write(to: url, atomically: true, encoding: .utf8)
        return try body(url.path)
    }

    @Test func aDevelopmentPackAddsItsPlacesInADebugBuildAndTheLibraryWinsADuplicate() throws {
        try withPack { path in
            let lookup = lookup(arguments: ["app", LioDevPlacesPack.argument, path])
            #expect(lookup.match(name: "The Bund", city: "shanghai") ==
                    LioPlaceMatch(placeID: "pl_sh_waitan", coordinate: .init(latitude: 31.24, longitude: 121.49)))
            // pl_bj_gugong is in both: the reviewed library's entry (with its point) is the one found.
            #expect(lookup.match(name: "故宫博物院", city: "beijing")?.coordinate == .init(latitude: 39.9165, longitude: 116.3971))
            #expect(lookup.match(name: "Palace Museum (dev)", city: "beijing") == nil)   // the duplicate id's pack entry is dropped
            // same through the environment
            let viaEnvironment = self.lookup(environment: [LioDevPlacesPack.environmentKey: path])
            #expect(viaEnvironment.match(name: "外滩", city: "shanghai")?.placeID == "pl_sh_waitan")
        }
    }

    @Test func withoutAskingForAPackItsPlacesAreNotFound() throws {
        try withPack { _ in
            #expect(lookup().match(name: "外滩", city: "shanghai") == nil)
        }
    }

    @Test func aBadPackIsIgnored() {
        #expect(lookup(arguments: ["app", LioDevPlacesPack.argument, "/no/such/file.json"]).match(name: "外滩", city: nil) == nil)
    }
    #endif
}
