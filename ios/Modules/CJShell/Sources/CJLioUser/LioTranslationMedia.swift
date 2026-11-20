import Foundation

enum LioTranslationMediaFailure: Error, Equatable {
    case noText, unreadableImage, mismatchedLines, cameraDenied, cameraUnavailable
    case microphoneDenied, recordingUnavailable, emptyRecording
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
struct LioMediaPermissionGate {
    let isCurrent: () -> Bool

    func request(_ permission: () async -> Bool) async throws -> Bool {
        try requireCurrent()
        let granted = await permission()
        try requireCurrent()
        return granted
    }

    private func requireCurrent() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }
}
