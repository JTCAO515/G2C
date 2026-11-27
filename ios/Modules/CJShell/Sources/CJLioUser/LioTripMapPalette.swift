import SwiftUI

/// #1996: one colour per day on the trip map. Three slots reuse theme colours (vermilion, jade, gold); three are
/// added for the map (lapis, plum, slate) in `LioTripMapAssets.xcassets`, each with a light and a dark value.
/// Every slot keeps 4.5:1 with `onVermilion` (the number on the marker) and 3:1 with `paper` and `surface`
/// (the line and marker against the page) in both appearances; `LioTripMapPaletteTests` checks that.
/// Day 7 starts the palette again; the number on the marker and the day legend still tell days apart.
enum LioTripMapPalette {
    struct Entry: Sendable {
        let name: String
        /// A colour the theme already has (`LioTheme.swatches`), or nil when the slot has its own asset.
        let themeSwatch: String?
        let asset: String
        let light: UInt32
        let dark: UInt32
    }

    static let entries: [Entry] = [
        Entry(name: "vermilion", themeSwatch: "vermilion", asset: "LioVermilion", light: 0xC0352B, dark: 0xE86655),
        Entry(name: "lapis", themeSwatch: nil, asset: "LioMapLapis", light: 0x2B5EA7, dark: 0x7FA8E8),
        Entry(name: "jade", themeSwatch: "jade", asset: "LioJade", light: 0x1D7556, dark: 0x4FB893),
        Entry(name: "plum", themeSwatch: nil, asset: "LioMapPlum", light: 0x8A3F8F, dark: 0xC58BCB),
        Entry(name: "gold", themeSwatch: "gold", asset: "LioGold", light: 0x866116, dark: 0xD4AE5C),
        Entry(name: "slate", themeSwatch: nil, asset: "LioMapSlate", light: 0x4F6272, dark: 0x9DB1C2)
    ]

    static var slotCount: Int { entries.count }

    /// Any integer (a day index, a caller's own number) to a slot in `0..<slotCount`; negatives wrap too.
    static func normalized(_ slot: Int) -> Int {
        let remainder = slot % slotCount
        return remainder < 0 ? remainder + slotCount : remainder
    }

    /// The slot for the day at this position of the trip (day 1 is index 0).
    static func slot(forDayIndex index: Int) -> Int { normalized(index) }

    static func color(slot: Int) -> Color { colors[normalized(slot)] }

    private static let colors: [Color] = [
        LioTheme.vermilion,
        Color("LioMapLapis", bundle: .module),
        LioTheme.jade,
        Color("LioMapPlum", bundle: .module),
        LioTheme.gold,
        Color("LioMapSlate", bundle: .module)
    ]
}
