import Testing
@testable import CJLioUser

@MainActor
struct LioTranslationMediaTests {
    @Test func refusesMicrophoneDenialBeforeRequestingSpeechPermission() async {
        let admission = LioVoiceAuthorization(onDeviceAvailable: true, microphone: { false }, speech: {
            Issue.record("Speech permission must not be requested after microphone denial")
            return true
        })
        await #expect(throws: LioTranslationMediaFailure.microphoneDenied) { try await admission.check() }
    }

    @Test func refusesSpeechDenialAndUnavailableLocalRecognition() async {
        let denied = LioVoiceAuthorization(onDeviceAvailable: true, microphone: { true }, speech: { false })
        await #expect(throws: LioTranslationMediaFailure.speechDenied) { try await denied.check() }
        let offlineUnavailable = LioVoiceAuthorization(onDeviceAvailable: false, microphone: {
            Issue.record("An unavailable local recognizer must not request permission")
            return true
        }, speech: { true })
        await #expect(throws: LioTranslationMediaFailure.speechUnavailable) { try await offlineUnavailable.check() }
    }

    @Test func preservesDuplicateImageLinesAndTheirOrder() throws {
        let rows = try LioImageTranslationLine.pair(["茶", "茶", "咖啡"], with: ["Tea", "Tea", "Coffee"])
        #expect(rows.map(\.id) == [0, 1, 2])
        #expect(rows.map(\.original) == ["茶", "茶", "咖啡"])
        #expect(rows.map(\.translated) == ["Tea", "Tea", "Coffee"])
    }

    @Test func refusesMissingOrMismatchedImageText() {
        #expect(throws: LioTranslationMediaFailure.noText) {
            try LioImageTranslationLine.pair([], with: [])
        }
        #expect(throws: LioTranslationMediaFailure.mismatchedLines) {
            try LioImageTranslationLine.pair(["茶", "咖啡"], with: ["Tea"])
        }
    }
}
