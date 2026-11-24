import Foundation
import Testing
@testable import CJLioUser

/// #1421 item 3: press and hold the microphone, release to translate.
struct LioHoldToTalkTests {
    private let start = Date(timeIntervalSinceReferenceDate: 1_000)

    @Test func releasingAfterSpeakingTranslates() {
        #expect(LioHoldToTalk.release(recordingStartedAt: start, at: start.addingTimeInterval(1.2),
                                      dragHeight: -10) == .translate)
    }

    @Test func aTapIsTooShortAndExplainsHowToHold() {
        #expect(LioHoldToTalk.release(recordingStartedAt: start, at: start.addingTimeInterval(0.2),
                                      dragHeight: 0) == .tooShort)
        #expect(LioHoldToTalk.release(recordingStartedAt: nil, at: start, dragHeight: 0) == .tooShort)
        #expect(LioHoldToTalk.hint(.tooShort, language: .chinese) == "按住说话，松开即翻译")
        #expect(LioHoldToTalk.hint(.tooShort, language: .english) == "Hold to talk, release to translate")
    }

    @Test func slidingUpCancelsWithoutSending() {
        #expect(LioHoldToTalk.release(recordingStartedAt: start, at: start.addingTimeInterval(3),
                                      dragHeight: -LioHoldToTalk.cancelDistance - 1) == .cancel)
        #expect(LioHoldToTalk.isCancelling(dragHeight: -LioHoldToTalk.cancelDistance - 1))
        #expect(!LioHoldToTalk.isCancelling(dragHeight: -20))
    }

    @Test func recordingPromptChangesWhenReleaseWouldCancel() {
        #expect(LioHoldToTalk.recordingPrompt(cancelling: false, language: .chinese) == "松开翻译，上滑取消")
        #expect(LioHoldToTalk.recordingPrompt(cancelling: true, language: .chinese) == "松开取消")
        #expect(LioHoldToTalk.recordingPrompt(cancelling: false, language: .english) == "Release to translate, slide up to cancel")
    }
}
