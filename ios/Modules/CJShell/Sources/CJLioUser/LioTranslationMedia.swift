import Foundation

enum LioTranslationMediaFailure: Error, Equatable {
    case noText, unreadableImage, mismatchedLines, cameraDenied, cameraUnavailable
    case microphoneDenied, speechDenied, speechUnavailable, unrecognizedSpeech
}

struct LioImageTranslationLine: Identifiable, Equatable {
    let id: Int
    let original: String
    let translated: String

    static func pair(_ originals: [String], with translations: [String]) throws -> [Self] {
        guard !originals.isEmpty else { throw LioTranslationMediaFailure.noText }
        guard originals.count == translations.count else { throw LioTranslationMediaFailure.mismatchedLines }
        return zip(originals, translations).enumerated().map { index, texts in
            Self(id: index, original: texts.0, translated: texts.1)
        }
    }
}

@MainActor
struct LioVoiceAuthorization {
    let onDeviceAvailable: Bool
    let microphone: () async -> Bool
    let speech: () async -> Bool

    func check() async throws {
        guard onDeviceAvailable else { throw LioTranslationMediaFailure.speechUnavailable }
        guard await microphone() else { throw LioTranslationMediaFailure.microphoneDenied }
        try Task.checkCancellation()
        guard await speech() else { throw LioTranslationMediaFailure.speechDenied }
        try Task.checkCancellation()
    }
}
