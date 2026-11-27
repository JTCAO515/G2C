import Foundation
import Testing
@testable import CJLioUser

/// #1996: the day colours. The three added colours live in their own catalog, so the theme's own colour test
/// (ten swatches, one catalog) is left as it is; this keeps them in step and checks contrast the same way.
struct LioTripMapPaletteTests {
    private static let shell = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private static let catalog = shell.appendingPathComponent("Sources/CJLioUser/Resources/LioTripMapAssets.xcassets")
    private static let paper = LioTheme.swatches.first { $0.name == "paper" }!
    private static let surface = LioTheme.swatches.first { $0.name == "surface" }!
    private static let onVermilion = LioTheme.swatches.first { $0.name == "onVermilion" }!

    private struct ColorSet: Decodable {
        struct Entry: Decodable {
            struct Appearance: Decodable { let appearance: String; let value: String }
            struct Value: Decodable { let components: [String: String] }
            let appearances: [Appearance]?
            let color: Value
        }
        let colors: [Entry]
    }

    private static func hex(_ entry: ColorSet.Entry) throws -> UInt32 {
        try ["red", "green", "blue"].reduce(UInt32(0)) { value, channel in
            let text = try #require(entry.color.components[channel], "\(channel)")
            return value << 8 | (try #require(UInt32(text.dropFirst(2), radix: 16), "\(text)"))
        }
    }

    private static func contrast(_ first: UInt32, _ second: UInt32) -> Double {
        func luminance(_ color: UInt32) -> Double {
            let channels = [color >> 16 & 0xFF, color >> 8 & 0xFF, color & 0xFF].map { channel -> Double in
                let value = Double(channel) / 255
                return value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
            }
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
        }
        let (a, b) = (luminance(first), luminance(second))
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }

    @Test func thereAreSixDistinctDayColours() {
        #expect(LioTripMapPalette.slotCount == 6)
        #expect(Set(LioTripMapPalette.entries.map(\.name)).count == 6)
        #expect(Set(LioTripMapPalette.entries.map(\.light)).count == 6)
        #expect(Set(LioTripMapPalette.entries.map(\.dark)).count == 6)
        #expect(LioTripMapPalette.slot(forDayIndex: 0) == 0 && LioTripMapPalette.slot(forDayIndex: 6) == 0)
    }

    @Test func colourOwnedByTheThemeMatchesTheThemeAndTheRestMatchTheirCatalog() throws {
        let sets = try FileManager.default.contentsOfDirectory(atPath: Self.catalog.path).filter { $0.hasSuffix(".colorset") }
        let own = LioTripMapPalette.entries.filter { $0.themeSwatch == nil }
        #expect(Set(sets) == Set(own.map { $0.asset + ".colorset" }))
        for entry in LioTripMapPalette.entries {
            if let name = entry.themeSwatch {
                let swatch = try #require(LioTheme.swatches.first { $0.name == name }, "\(name)")
                #expect(swatch.light == entry.light && swatch.dark == entry.dark && swatch.asset == entry.asset, "\(entry.name)")
                continue
            }
            let file = Self.catalog.appendingPathComponent("\(entry.asset).colorset/Contents.json")
            let set = try JSONDecoder().decode(ColorSet.self, from: Data(contentsOf: file))
            #expect(set.colors.count == 2, "\(entry.asset)")
            let light = try #require(set.colors.first { $0.appearances == nil }, "\(entry.asset)")
            let dark = try #require(set.colors.first {
                $0.appearances?.count == 1 && $0.appearances?.first?.appearance == "luminosity" && $0.appearances?.first?.value == "dark"
            }, "\(entry.asset)")
            #expect(try Self.hex(light) == entry.light, "\(entry.asset) light")
            #expect(try Self.hex(dark) == entry.dark, "\(entry.asset) dark")
        }
    }

    @Test func numbersOnMarkersAndLinesOnThePageAreReadableInBothAppearances() {
        for entry in LioTripMapPalette.entries {
            // The number on a filled marker is text: 4.5:1. The marker and the line are graphics: 3:1.
            #expect(Self.contrast(Self.onVermilion.light, entry.light) >= 4.5, "\(entry.name) number light")
            #expect(Self.contrast(Self.onVermilion.dark, entry.dark) >= 4.5, "\(entry.name) number dark")
            for page in [Self.paper, Self.surface] {
                #expect(Self.contrast(page.light, entry.light) >= 3, "\(entry.name) on \(page.name) light")
                #expect(Self.contrast(page.dark, entry.dark) >= 3, "\(entry.name) on \(page.name) dark")
            }
        }
    }

    @Test func colourLookupWrapsAnyNumberAndDoesNotCrash() {
        for slot in [-13, -1, 0, 5, 6, 1_000_003, .max, .min] {
            let normalized = LioTripMapPalette.normalized(slot)
            #expect((0..<LioTripMapPalette.slotCount).contains(normalized))
            _ = LioTripMapPalette.color(slot: slot)
        }
    }
}
