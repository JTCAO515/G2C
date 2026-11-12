import Foundation
import Testing
@testable import CJLioUser

struct LioThemeTests {
    private static let shell = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private static let assets = shell.appendingPathComponent("Sources/CJLioUser/Resources/LioAssets.xcassets")

    private struct ColorSet: Decodable {
        struct Entry: Decodable {
            struct Appearance: Decodable { let appearance: String; let value: String }
            struct Value: Decodable {
                let colorSpace: String
                let components: [String: String]
                enum CodingKeys: String, CodingKey { case colorSpace = "color-space", components }
            }
            let appearances: [Appearance]?
            let color: Value
            let idiom: String
        }
        let colors: [Entry]
    }

    private static func swatch(_ name: String) throws -> LioTheme.Swatch {
        try #require(LioTheme.swatches.first { $0.name == name }, "\(name)")
    }

    private static func hex(_ entry: ColorSet.Entry) throws -> UInt32 {
        #expect(entry.color.colorSpace == "srgb")
        #expect(entry.color.components["alpha"] == "1.000")
        var value: UInt32 = 0
        for channel in ["red", "green", "blue"] {
            let text = try #require(entry.color.components[channel], "\(channel)")
            #expect(text.hasPrefix("0x") && text.count == 4, "\(text)")
            value = value << 8 | (try #require(UInt32(text.dropFirst(2), radix: 16), "\(text)"))
        }
        return value
    }

    /// WCAG 2.x relative luminance and contrast ratio.
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

    @Test func colorSetsMatchTheSwiftTable() throws {
        #expect(LioTheme.swatches.count == 10)
        #expect(Set(LioTheme.swatches.map(\.name)).count == 10)
        let sets = try FileManager.default.contentsOfDirectory(atPath: Self.assets.path)
            .filter { $0.hasSuffix(".colorset") }
        #expect(Set(sets) == Set(LioTheme.swatches.map { $0.asset + ".colorset" }))
        for swatch in LioTheme.swatches {
            let file = Self.assets.appendingPathComponent("\(swatch.asset).colorset/Contents.json")
            let set = try JSONDecoder().decode(ColorSet.self, from: Data(contentsOf: file))
            #expect(set.colors.count == 2, "\(swatch.asset)")
            let light = try #require(set.colors.first { $0.appearances == nil }, "\(swatch.asset)")
            let dark = try #require(set.colors.first {
                $0.appearances?.count == 1 && $0.appearances?.first?.appearance == "luminosity"
                    && $0.appearances?.first?.value == "dark"
            }, "\(swatch.asset)")
            #expect(light.idiom == "universal" && dark.idiom == "universal")
            #expect(try Self.hex(light) == swatch.light, "\(swatch.asset) light")
            #expect(try Self.hex(dark) == swatch.dark, "\(swatch.asset) dark")
        }
    }

    @Test func textColorsMeetFourAndAHalfToOneInBothAppearances() throws {
        let backgrounds = try ["paper", "surface", "surfaceSunken"].map(Self.swatch)
        let texts = try ["ink", "inkSecondary", "vermilion", "jade", "gold"].map(Self.swatch)
        for text in texts {
            for background in backgrounds {
                let light = Self.contrast(text.light, background.light)
                let dark = Self.contrast(text.dark, background.dark)
                #expect(light >= 4.5, "\(text.name) on \(background.name) light \(light)")
                #expect(dark >= 4.5, "\(text.name) on \(background.name) dark \(dark)")
            }
        }
        let vermilion = try Self.swatch("vermilion")
        let onVermilion = try Self.swatch("onVermilion")
        #expect(Self.contrast(onVermilion.light, vermilion.light) >= 4.5)
        #expect(Self.contrast(onVermilion.dark, vermilion.dark) >= 4.5)
    }

    @Test func contrastMatchesKnownWCAGValues() {
        #expect(abs(Self.contrast(0x000000, 0xFFFFFF) - 21) < 0.001)
        #expect(abs(Self.contrast(0x777777, 0xFFFFFF) - 4.478) < 0.01)
        #expect(Self.contrast(0xFFFFFF, 0xE86655) < 4.5)
    }

    @Test func lioShellUsesThemeTokensInsteadOfSystemColorsAndFixedRadii() throws {
        let sources = Self.shell.appendingPathComponent("Sources")
        let enumerator = try #require(FileManager.default.enumerator(at: sources.appendingPathComponent("CJLioUser"),
                                                                     includingPropertiesForKeys: nil))
        let lioFiles = enumerator.compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" && $0.lastPathComponent != "LioTheme.swift" }
        #expect(lioFiles.count >= 10)
        let app = Self.shell.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("App")
        let files = lioFiles + [sources.appendingPathComponent("CJShell/LioSavedMemoryView.swift"),
                               app.appendingPathComponent("DemoBetaApp.swift")]
        let forbidden = try NSRegularExpression(
            pattern: #"systemBackground|SystemBackground|accentColor|[Rr]adius\s*[:(]\s*[0-9]"#)
        let hits = try files.flatMap { file -> [String] in
            let text = try String(contentsOf: file, encoding: .utf8)
            return forbidden.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap { match in
                guard let span = Range(match.range, in: text) else { return nil }
                let line = text[..<span.lowerBound].filter { $0 == "\n" }.count + 1
                return "\(file.lastPathComponent):\(line): \(text[span])"
            }
        }
        #expect(hits.isEmpty, "Use LioTheme instead: \(hits.joined(separator: "\n"))")
        for sample in ["Color(uiColor: .systemBackground)", ".secondarySystemBackground", "Color.accentColor",
                       "RoundedRectangle(cornerRadius: 16)", "topLeadingRadius: 7", ".cornerRadius(8)"] {
            #expect(forbidden.firstMatch(in: sample, range: NSRange(sample.startIndex..., in: sample)) != nil, "\(sample)")
        }
    }
}
