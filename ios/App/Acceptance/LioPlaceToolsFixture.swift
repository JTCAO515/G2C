// Generated simulator project only. Sample places in the library's shape, marked as development data; nothing
// is fetched or sent.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private enum LioPlaceToolsSamples {
    static func hotel(_ id: String, _ city: String, _ zh: String, _ en: String, star: Int?, band: String, rank: Int,
                      intro: String) -> [String: Any] {
        var row: [String: Any] = [
            "id": id, "city": city, "category": "hotel", "tier": "main", "rank": rank, "name_zh": zh, "name_en": en,
            "intro_short_zh": intro, "intro_short_en": intro, "price_band": band, "accepts_foreigners": true,
            "review": ["status": "unreviewed"],
        ]
        if let star { row["star"] = star }
        return row
    }

    static var pack: Data {
        let rows: [[String: Any]] = [
            hotel("pl_bj_a", "beijing", "北京示例国际酒店", "Sample Beijing International", star: 5, band: ">2000", rank: 1,
                  intro: "Near Wangfujing, English-speaking front desk."),
            hotel("pl_bj_b", "beijing", "北京示例中档酒店", "Sample Beijing Midscale", star: 4, band: "500-1000", rank: 2,
                  intro: "Two stops from the Forbidden City."),
            hotel("pl_bj_c", "beijing", "北京示例经济酒店", "Sample Beijing Budget", star: 3, band: "<500", rank: 3,
                  intro: "Simple rooms by the metro."),
            hotel("pl_sh_a", "shanghai", "上海示例酒店", "Sample Shanghai Hotel", star: 4, band: "1000-2000", rank: 1,
                  intro: "On the Bund side of People's Square."),
        ]
        return try! JSONSerialization.data(withJSONObject: ["version": "g2c-places-dev.1", "places": rows])
    }
}

private struct LioPlaceToolsFixture: View {
    let chinese: Bool
    let dark: Bool

    var body: some View {
        NavigationStack {
            LioStayView(language: chinese ? .chinese : .english,
                        catalog: LioPlaceCatalog(library: nil, developmentPack: LioPlaceToolsSamples.pack))
        }
        .environment(\.lioAddPlaceToTrip, { _ in true })
        .preferredColorScheme(dark ? .dark : .light)
    }
}

private enum LioExploreSamples {
    static func place(_ id: String, _ category: String, _ zh: String, _ en: String, rank: Int, intro: String) -> [String: Any] {
        ["id": id, "city": "beijing", "category": category, "tier": "main", "rank": rank, "name_zh": zh, "name_en": en,
         "intro_short_zh": intro, "intro_short_en": intro, "review": ["status": "unreviewed"]]
    }

    static var pack: Data {
        let rows: [[String: Any]] = [
            place("pl_bj_quanjude", "food", "全聚德烤鸭店", "Quanjude Roast Duck", rank: 2, intro: "Classic Peking duck near Wangfujing."),
            place("pl_bj_gugong", "attraction", "故宫博物院", "The Palace Museum", rank: 1, intro: "The imperial palace; book ahead."),
            place("pl_bj_wangfujing", "shopping", "王府井百货大楼", "Wangfujing Department Store", rank: 1, intro: "Long-running department store."),
        ]
        return try! JSONSerialization.data(withJSONObject: ["version": "g2c-places-dev.1", "places": rows])
    }

    static func poi(_ id: String, _ name: String, _ category: LioNearbyPlace.Category, _ meters: Int) -> LioNearbyPOI {
        LioNearbyPOI(id: id, name: name, address: nil, category: category,
                     coordinate: .init(latitude: 39.91, longitude: 116.41, referenceSystem: .gcj02),
                     meters: meters, rating: nil, cost: nil, hours: nil, photo: nil)
    }

    /// What AMap finds around: three of ours and two places that are not in the library.
    static let service = LioNearbyService(currentLocation: {
        .init(nameZH: "王府井", nameEN: "Wangfujing", addressZH: "北京市东城区王府井大街",
              coordinate: .init(latitude: 39.9110, longitude: 116.4102, referenceSystem: .wgs84))
    }, search: { query in
        let all = [poi("1", "全聚德烤鸭店(王府井店)", .food, 420), poi("2", "路边小吃摊", .food, 80),
                   poi("3", "故宫博物院", .sights, 1250), poi("4", "王府井百货大楼", .shopping, 350),
                   poi("5", "街角便利店", .shopping, 120)]
        return all.filter { ($0.category).map(query.categories.contains) ?? false && ($0.meters ?? 0) <= query.radius }
    }, reverse: { _ in "北京市东城区王府井大街" })
}

private struct LioExploreFixture: View {
    let chinese: Bool
    let dark: Bool
    let emptyLibrary: Bool

    var body: some View {
        NavigationStack {
            LioExploreView(language: chinese ? .chinese : .english, service: LioExploreSamples.service,
                           catalog: emptyLibrary ? LioPlaceCatalog(library: nil)
                                                 : LioPlaceCatalog(library: nil, developmentPack: LioExploreSamples.pack))
        }
        .environment(\.lioAddPlaceToTrip, { _ in true })
        .preferredColorScheme(dark ? .dark : .light)
    }
}
#endif
