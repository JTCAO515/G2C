import Foundation
import Testing

/// #1832: the system location prompt and the privacy manifest say what the app does with location: Taxi and
/// Nearby use it, it goes to our service and to the map and taxi providers, and it is declared as precise
/// location for app functionality, not tracking (outbound data register #1743).
struct LioLocationDisclosureTests {
    private static let app = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("App")

    @Test func locationPurposeNamesBothUsesAndWhereItGoesInBothLanguages() throws {
        let plist = try String(contentsOf: Self.app.appendingPathComponent("Info.plist"), encoding: .utf8)
        let key = "<key>NSLocationWhenInUseUsageDescription</key><string>"
        #expect(plist.components(separatedBy: key).count == 2, "one location purpose string")
        let start = try #require(plist.range(of: key))
        let end = try #require(plist.range(of: "</string>", range: start.upperBound..<plist.endIndex))
        let purpose = String(plist[start.upperBound..<end.lowerBound])
        let parts = purpose.components(separatedBy: " / ")
        #expect(parts.count == 2, "English, then Chinese")
        let english = parts.first ?? "", chinese = parts.last ?? ""
        for word in ["Taxi", "Nearby", "our service", "Amap", "DiDi"] { #expect(english.contains(word), "\(word)") }
        for word in ["打车", "附近", "我们的服务", "高德", "滴滴"] { #expect(chinese.contains(word), "\(word)") }
    }

    @Test func privacyManifestDeclaresPreciseLocationForAppFunctionalityOnly() throws {
        let data = try Data(contentsOf: Self.app.appendingPathComponent("PrivacyInfo.xcprivacy"))
        let manifest = try #require(try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any])
        #expect(manifest["NSPrivacyTracking"] as? Bool != true)
        let collected = try #require(manifest["NSPrivacyCollectedDataTypes"] as? [[String: Any]])
        let location = collected.filter {
            ($0["NSPrivacyCollectedDataType"] as? String)?.hasSuffix("Location") == true
        }
        #expect(location.count == 1, "only precise location is declared; the device sends precise coordinates")
        let precise = try #require(location.first)
        #expect(precise["NSPrivacyCollectedDataType"] as? String == "NSPrivacyCollectedDataTypePreciseLocation")
        #expect(precise["NSPrivacyCollectedDataTypeLinked"] as? Bool == true)
        #expect(precise["NSPrivacyCollectedDataTypeTracking"] as? Bool == false)
        #expect(precise["NSPrivacyCollectedDataTypePurposes"] as? [String] == ["NSPrivacyCollectedDataTypePurposeAppFunctionality"])
    }
}
