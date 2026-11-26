import Foundation
import Testing
@testable import CJLioUser

/// #1753 (W4-9): the AI line under answers is off unless the build says YES, and reads the approved wording.
struct LioAIDisclosureTests {
    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioAIDisclosureFeature.infoKey == "G2CAIDisclosureEnabled")
        #expect(!LioAIDisclosureFeature.enabled(infoValue: nil))
        #expect(!LioAIDisclosureFeature.enabled(infoValue: "NO"))
        #expect(LioAIDisclosureFeature.enabled(infoValue: "YES"))
        #expect(!LioAIDisclosureFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CAIDisclosureEnabled</key><string>$(G2C_AI_DISCLOSURE_ENABLED)</string>"))
        #expect(!project.contains("G2C_AI_DISCLOSURE_ENABLED"), "off unless a release turns it on")
    }

    @Test func wordingIsTheApprovedLineInBothLanguages() {
        #expect(LioAIDisclosureFeature.text(.english) == "AI-generated and may be wrong. Double-check anything important.")
        #expect(LioAIDisclosureFeature.text(.chinese) == "由 AI 生成，可能有误，重要信息请自行确认。")
    }
}
