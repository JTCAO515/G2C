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

    @Test func wordingIsTheApprovedLineInBothLanguages() {
        #expect(LioAIDisclosureFeature.text(.english) == "AI-generated and may be wrong. Double-check anything important.")
        #expect(LioAIDisclosureFeature.text(.chinese) == "由 AI 生成，可能有误，重要信息请自行确认。")
    }
}
