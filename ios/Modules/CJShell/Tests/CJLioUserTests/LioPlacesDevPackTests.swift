#if DEBUG
import Foundation
import Testing
@testable import CJLioUser

/// The unreviewed development pack is read only from a path given at launch and only when every entry is
/// still marked unreviewed; it is never a bundled resource.
@MainActor struct LioPlacesDevPackTests {
    private func write(_ text: String) throws -> String {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("places-dev-" + UUID().uuidString + ".json")
        try text.write(to: url, atomically: true, encoding: .utf8)
        return url.path
    }

    private func pack(status: String = "unreviewed", version: String = "g2c-places-dev.1") -> String {
        """
        {"version": "\(version)", "warning": "x", "generated_on": "2026-11-27", "places": [
          {"id": "pl_bj_gugong", "city": "beijing", "category": "attraction", "tier": "main", "name_zh": "故宫博物院",
           "name_en": "The Palace Museum", "aliases_zh": ["故宫"], "aliases_en": ["Forbidden City"], "address_zh": null,
           "district_zh": "东城区", "intro_short_zh": "皇宫", "intro_short_en": "Palace", "intro_long_zh": null,
           "intro_long_en": null, "hours_zh": null, "rank": null, "sources": ["https://www.dpm.org.cn/"],
           "location": {"gcj02": {"lat": 39.917839, "lng": 116.397029}, "amap_id": "B000A8UIN8", "amap_name": "故宫",
                        "method": "amap-poi-search", "geocoded_on": "2026-11-27"},
           "review": {"status": "\(status)", "reviewer": null, "reviewed_on": null, "note": null}},
          {"id": "pl_sh_waitan", "city": "shanghai", "category": "attraction", "tier": "main", "name_zh": "外滩",
           "name_en": "The Bund", "aliases_zh": [], "aliases_en": [], "location": null,
           "review": {"status": "\(status)", "reviewer": null, "reviewed_on": null, "note": null}}
        ]}
        """
    }

    @Test func nothingIsReadUnlessAPathIsGiven() {
        #expect(LioDevPlacesPack.load(arguments: ["app"], environment: [:]) == nil)
        #expect(LioDevPlacesPack.load(arguments: ["app", "--places-dev-pack"], environment: [:]) == nil)
        #expect(LioDevPlacesPack.load(arguments: ["app", "--places-dev-pack", "/nowhere/pack.json"], environment: [:]) == nil)
    }

    @Test func aPackIsReadFromTheArgumentOrTheEnvironment() throws {
        let path = try write(pack())
        let fromArgument = try #require(LioDevPlacesPack.load(arguments: ["app", "--places-dev-pack", path], environment: [:]))
        let fromEnvironment = try #require(LioDevPlacesPack.load(arguments: ["app"], environment: [LioDevPlacesPack.environmentKey: path]))
        #expect(fromArgument == fromEnvironment && fromArgument.places.count == 2)
        #expect(fromArgument.places[0].location?.amapID == "B000A8UIN8" && fromArgument.places[1].location == nil)
    }

    @Test func namesAndAliasesMatchExactlyAndCityNarrowsTheSearch() throws {
        let pack = try #require(LioDevPlacesPack.load(arguments: ["a", "--places-dev-pack", try write(pack())], environment: [:]))
        #expect(pack.match(name: "forbidden city")?.id == "pl_bj_gugong")
        #expect(pack.match(name: "故宫", city: "beijing")?.id == "pl_bj_gugong")
        #expect(pack.match(name: "故宫", city: "shanghai") == nil)
        #expect(pack.match(name: "Forbidden") == nil)
        #expect(pack.place(id: "pl_sh_waitan")?.nameEN == "The Bund")
    }

    @Test func aPackWithAReviewedEntryOrAnotherVersionIsRefused() throws {
        #expect(LioDevPlacesPack.load(arguments: ["a", "--places-dev-pack", try write(pack(status: "approved"))], environment: [:]) == nil)
        #expect(LioDevPlacesPack.load(arguments: ["a", "--places-dev-pack", try write(pack(version: "g2c-places-dev.2"))], environment: [:]) == nil)
        #expect(LioDevPlacesPack.load(arguments: ["a", "--places-dev-pack", try write("{oops")], environment: [:]) == nil)
    }

    /// The committed pack itself decodes: every entry the generator wrote is readable by this model.
    @Test func theCommittedPackDecodes() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let path = root.appendingPathComponent("knowledge/places/dev/places-dev-pack.v1.json").path
        guard FileManager.default.fileExists(atPath: path) else { return }   // no candidates yet: no pack
        let pack = try #require(LioDevPlacesPack.load(arguments: ["a", "--places-dev-pack", path], environment: [:]))
        #expect(pack.places.count > 100 && Set(pack.places.map(\.id)).count == pack.places.count)
        #expect(pack.places.allSatisfy { !$0.nameZH.isEmpty && !$0.nameEN.isEmpty })
    }
}
#endif
