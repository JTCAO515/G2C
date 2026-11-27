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
#endif
