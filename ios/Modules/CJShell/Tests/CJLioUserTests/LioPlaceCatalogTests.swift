import Foundation
import Testing
@testable import CJLioUser

/// #2004: the Stay tool lists only collected hotels, filtered by price band and star, best first.
struct LioPlaceCatalogTests {
    private func hotel(_ id: String, city: String = "beijing", tier: String = "main", rank: Int? = nil, star: Int? = nil,
                       band: String? = nil, foreigners: Bool? = true, status: String = "approved") -> [String: Any] {
        var row: [String: Any] = [
            "id": id, "city": city, "category": "hotel", "tier": tier, "name_zh": "酒店" + id, "name_en": "Hotel " + id,
            "review": ["status": status],
        ]
        if let rank { row["rank"] = rank }
        if let star { row["star"] = star }
        if let band { row["price_band"] = band }
        if let foreigners { row["accepts_foreigners"] = foreigners }
        return row
    }

    private func data(_ rows: [[String: Any]]) throws -> Data {
        try JSONSerialization.data(withJSONObject: ["places": rows])
    }

    @Test func readsTheFieldsLioPlaceDoesNotKeep() throws {
        let rows = [hotel("pl_bj_a", tier: "backup", rank: 3, star: 4, band: "1000-2000"),
                    hotel("pl_bj_b", rank: 0, star: 9, band: "cheap")]
        let extras = LioPlaceCatalog.extras(in: try data(rows))
        #expect(extras["pl_bj_a"] == .init(isMainTier: false, rank: 3, star: 4, priceBand: .from1000,
                                           acceptsForeigners: true, amapID: nil))
        // A rank of 0, a star of 9 and a band we do not know are left out, not errors.
        #expect(extras["pl_bj_b"] == .init(isMainTier: true, rank: nil, star: nil, priceBand: nil,
                                           acceptsForeigners: true, amapID: nil))
        #expect(LioPlaceCatalog.extras(in: Data("[]".utf8)).isEmpty)
        #expect(LioPlaceCatalog.extras(in: Data("nope".utf8)).isEmpty)
    }

    @Test func filtersByCityBandAndStarAndLeavesOutUnknowns() throws {
        let catalog = LioPlaceCatalog(library: try data([
            hotel("pl_bj_a", star: 5, band: ">2000"),
            hotel("pl_bj_b", star: 3, band: "500-1000"),
            hotel("pl_sh_c", city: "shanghai", star: 4, band: "500-1000"),
            hotel("pl_bj_d"),
        ]))
        func ids(_ filter: LioStayFilter) -> [String] { filter.apply(to: catalog).map(\.id) }
        #expect(ids(LioStayFilter()) == ["pl_bj_a", "pl_bj_b", "pl_bj_d", "pl_sh_c"])
        #expect(ids(LioStayFilter(city: "beijing")) == ["pl_bj_a", "pl_bj_b", "pl_bj_d"])
        #expect(ids(LioStayFilter(band: .from500)) == ["pl_bj_b", "pl_sh_c"])
        #expect(ids(LioStayFilter(city: "shanghai", band: .from500)) == ["pl_sh_c"])
        #expect(ids(LioStayFilter(minimumStar: 4)) == ["pl_bj_a", "pl_sh_c"])
        #expect(ids(LioStayFilter(band: .over2000, minimumStar: 5)) == ["pl_bj_a"])
        #expect(ids(LioStayFilter(band: .under500)).isEmpty)
        #expect(LioStayFilter().isFiltering == false && LioStayFilter(band: .under500).isFiltering)
    }

    @Test func ordersMainBeforeBackupThenByRank() throws {
        let catalog = LioPlaceCatalog(library: try data([
            hotel("pl_bj_a", tier: "backup", rank: 1),
            hotel("pl_bj_b", rank: 2),
            hotel("pl_bj_c", rank: 1),
            hotel("pl_bj_d"),
        ]))
        #expect(LioStayFilter().apply(to: catalog).map(\.id) == ["pl_bj_c", "pl_bj_b", "pl_bj_d", "pl_bj_a"])
    }

    @Test func neverListsAHotelThatDoesNotServeForeignGuests() throws {
        let catalog = LioPlaceCatalog(library: try data([hotel("pl_bj_a", foreigners: false), hotel("pl_bj_b", foreigners: nil)]))
        #expect(LioStayFilter().apply(to: catalog).map(\.id) == ["pl_bj_b"])
    }

    @Test func onlyHotelsAreListedAndAnEmptyLibraryIsEmpty() throws {
        var food = hotel("pl_bj_f"); food["category"] = "food"
        let catalog = LioPlaceCatalog(library: try data([food, hotel("pl_bj_h")]))
        #expect(LioStayFilter().apply(to: catalog).map(\.id) == ["pl_bj_h"])
        let empty = LioPlaceCatalog(library: nil)
        #expect(empty.entries.isEmpty && empty.hotels.isEmpty && !empty.isDevelopment)
        #expect(LioStayFilter().apply(to: empty).isEmpty)
    }

    @Test func starFiltersAreOnlyOfferedWhenSomeHotelHasAStar() throws {
        #expect(!LioStayFilter.offersStars(in: LioPlaceCatalog(library: try data([hotel("pl_bj_a")]))))
        #expect(LioStayFilter.offersStars(in: LioPlaceCatalog(library: try data([hotel("pl_bj_a", star: 4)]))))
    }

    @Test func developmentPlacesAreMarkedAndTheLibraryWinsADuplicate() throws {
        let catalog = LioPlaceCatalog(library: try data([hotel("pl_bj_a")]),
                                      developmentPack: try data([hotel("pl_bj_a", status: "unreviewed"),
                                                                 hotel("pl_bj_b", status: "unreviewed")]))
        #expect(catalog.entries.map(\.id) == ["pl_bj_a", "pl_bj_b"])
        #expect(catalog.entry(id: "pl_bj_a")?.isDevelopment == false)
        #expect(catalog.entry(id: "pl_bj_b")?.isDevelopment == true)
        #expect(catalog.isDevelopment)
        #expect(catalog.repository.place(id: "pl_bj_b")?.nameZH == "酒店pl_bj_b")
    }

    @Test func priceBandsAreTheLibrarysFourAndNamedInBothLanguages() {
        #expect(LioPlaceCatalog.PriceBand.allCases.map(\.rawValue) == ["<500", "500-1000", "1000-2000", ">2000"])
        for band in LioPlaceCatalog.PriceBand.allCases {
            #expect(!band.title(.english).isEmpty && !band.title(.chinese).isEmpty)
        }
        #expect(LioStayFilter.cities.map(\.id) == ["beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "chongqing"])
    }

    @Test func theFeatureIsOffUnlessTheBuildSaysYes() {
        #expect(!LioPlaceToolsFeature.enabled(infoValue: nil))
        #expect(!LioPlaceToolsFeature.enabled(infoValue: "NO"))
        #expect(!LioPlaceToolsFeature.enabled(infoValue: ""))
        #expect(LioPlaceToolsFeature.enabled(infoValue: "YES"))
        #expect(LioPlaceToolsFeature.infoKey == "G2CPlaceToolsEnabled")
    }

    #if DEBUG
    /// The repository's own development pack (unreviewed candidates) reads through the same code.
    @Test func theRealDevelopmentPackHasFilterableHotels() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let pack = root.appendingPathComponent("knowledge/places/dev/places-dev-pack.v1.json")
        guard let bytes = try? Data(contentsOf: pack) else { return }   // the pack is gone once the library has everything
        let catalog = LioPlaceCatalog(library: nil, developmentPack: bytes)
        #expect(catalog.isDevelopment)
        let hotels = catalog.hotels
        #expect(!hotels.isEmpty)
        #expect(hotels.allSatisfy { $0.isDevelopment && $0.extras.acceptsForeigners == true })
        #expect(LioStayFilter(band: .under500).apply(to: catalog).allSatisfy { $0.extras.priceBand == .under500 })
        #expect(Set(hotels.compactMap(\.place.city)).isSubset(of: Set(LioStayFilter.cities.map(\.id))))
    }

    @Test func aPackWithAReviewedEntryIsNotUsed() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("pack-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: file) }
        let body = try JSONSerialization.data(withJSONObject: [
            "version": LioDevPlacesPack.version,
            "places": [hotel("pl_bj_a", status: "approved")],
        ])
        try body.write(to: file)
        #expect(LioPlaceCatalog.developmentPackData(arguments: ["app", "--places-dev-pack", file.path], environment: [:]) == nil)
        #expect(LioPlaceCatalog.developmentPackData(arguments: ["app"], environment: [:]) == nil)
    }
    #endif
}
