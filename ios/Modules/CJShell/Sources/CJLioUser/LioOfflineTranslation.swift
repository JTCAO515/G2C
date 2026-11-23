#if os(iOS)
import Foundation
import Translation
import Vision

enum LioOfflineTranslation {
    static func readPhoto(_ data: Data, language: LioTranslationLanguage) async throws -> [String] {
        let photo = try LioTranslationImageEncoder.thumbnail(from: data)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        let identifier = language == .chinese ? "zh-Hans" : "en-US"
        guard try request.supportedRecognitionLanguages().contains(identifier) else {
            throw LioTranslationFailure.unreadableImage
        }
        request.recognitionLanguages = [identifier]
        try VNImageRequestHandler(cgImage: photo).perform([request])
        let observations = (request.results ?? []).sorted {
            if $0.boundingBox.midY == $1.boundingBox.midY { return $0.boundingBox.minX < $1.boundingBox.minX }
            return $0.boundingBox.midY > $1.boundingBox.midY
        }
        let text = observations.compactMap { $0.topCandidates(1).first?.string }
        guard !text.isEmpty else { throw LioTranslationFailure.noRecognizedText(.photo) }
        return text
    }

    @available(iOS 18.0, *)
    static func translate(_ request: LioTranslationRequest, using session: TranslationSession) async throws
        -> [String] {
        let source = Locale.Language(identifier: request.source.rawValue)
        let target = Locale.Language(identifier: request.target.rawValue)
        switch await LanguageAvailability().status(from: source, to: target) {
        case .unsupported: throw LioTranslationFailure.unsupportedOffline
        case .supported: try await session.prepareTranslation()
        case .installed: break
        @unknown default: throw LioTranslationFailure.unavailableOffline
        }
        var translated: [String] = []
        for line in request.text {
            try Task.checkCancellation()
            translated.append(try await session.translate(line).targetText)
        }
        return translated
    }
}
#endif
