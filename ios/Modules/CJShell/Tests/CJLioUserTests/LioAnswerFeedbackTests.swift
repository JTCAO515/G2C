import Foundation
import Testing
@testable import CJLioUser

/// #1753 (W4-9): "Not helpful" under answers is off unless the build says YES, reads the approved wording,
/// and keeps details within 500 characters and 6000 UTF-8 bytes.
struct LioAnswerFeedbackTests {
    @Test func flagIsOffUnlessTheBuildSaysYes() {
        #expect(LioAnswerFeedbackFeature.infoKey == "G2CAnswerFeedbackEnabled")
        #expect(!LioAnswerFeedbackFeature.enabled(infoValue: nil))
        #expect(!LioAnswerFeedbackFeature.enabled(infoValue: "NO"))
        #expect(!LioAnswerFeedbackFeature.enabled(infoValue: true))
        #expect(LioAnswerFeedbackFeature.enabled(infoValue: "YES"))
        #expect(!LioAnswerFeedbackFeature.enabledInBuild, "the test bundle sets no flag")
    }

    @Test func infoPlistReadsTheFlagFromABuildSettingThatNoConfigurationSets() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(plist.contains("<key>G2CAnswerFeedbackEnabled</key><string>$(G2C_ANSWER_FEEDBACK_ENABLED)</string>"))
        #expect(!project.contains("G2C_ANSWER_FEEDBACK_ENABLED"), "off unless a release turns it on")
    }

    @Test func wordingIsTheApprovedCopyInBothLanguages() {
        typealias Copy = LioAnswerFeedbackFeature.Copy
        #expect(Copy.notHelpful(.english) == "Not helpful" && Copy.notHelpful(.chinese) == "没帮上")
        #expect(LioAnswerFeedbackFeature.problem(.english) == "This answer didn't help.")
        #expect(LioAnswerFeedbackFeature.problem(.chinese) == "这条回答没帮上忙。")
        #expect(Copy.thanks(.english) == "Thanks, we got it." && Copy.thanks(.chinese) == "已收到，谢谢。")
        #expect(Copy.addDetails(.english) == "Add details" && Copy.addDetails(.chinese) == "补充说明")
        #expect(Copy.detailsPrompt(.english) == "What went wrong? Don't include personal details.")
        #expect(Copy.detailsPrompt(.chinese) == "哪里不对？请不要填写个人信息。")
        #expect(Copy.notSent(.english) == "Not sent. Tap to try again." && Copy.notSent(.chinese) == "没发出去，点此重试。")
        #expect(Copy.full(.english) == "Feedback is full for now." && Copy.full(.chinese) == "反馈已满，暂不能提交。")
    }

    @Test func detailsStayWithinCharactersAndBytes() {
        #expect(LioAnswerFeedbackFeature.limitedDetails("short") == "short")
        let latin = String(repeating: "a", count: 700)
        #expect(LioAnswerFeedbackFeature.limitedDetails(latin).count == 500)
        let chinese = String(repeating: "错", count: 600)
        let limitedChinese = LioAnswerFeedbackFeature.limitedDetails(chinese)
        #expect(limitedChinese.count == 500 && limitedChinese.utf8.count == 1500)
        // One family emoji is a single character of 25 UTF-8 bytes: the byte limit comes first.
        let family = String(repeating: "👨‍👩‍👧‍👦", count: 300)
        let limitedFamily = LioAnswerFeedbackFeature.limitedDetails(family)
        #expect(limitedFamily.utf8.count <= 6000 && limitedFamily.count == 6000 / "👨‍👩‍👧‍👦".utf8.count)
    }

    @Test func outcomesBecomeThePhaseShownUnderTheAnswer() {
        #expect(LioAnswerFeedbackPhase(.sent, after: .notHelpful) == .sent)
        #expect(LioAnswerFeedbackPhase(.sent, after: .details) == .detailsSent)
        #expect(LioAnswerFeedbackPhase(.notSent, after: .details) == .notSent(.details))
        #expect(LioAnswerFeedbackPhase(.unavailable, after: .notHelpful) == .notSent(.notHelpful))
        #expect(LioAnswerFeedbackPhase(.full, after: .notHelpful) == .full)
        #expect(LioAnswerFeedbackPhase.sending(.details).isSending && !LioAnswerFeedbackPhase.sent.isSending)
    }
}
