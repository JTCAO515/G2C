#if canImport(Vision)
import Foundation
import ImageIO
import Vision

enum LioVisionTextReader {
    static func lines(from data: Data, language: LioTranslationLanguage) async throws -> [String] {
        guard let image = CGImageSourceCreateWithData(data as CFData, nil),
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(image, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 4096,
              ] as CFDictionary) else {
            throw LioTranslationMediaFailure.unreadableImage
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        let recognitionLanguage = language == .chinese ? "zh-Hans" : "en-US"
        guard try request.supportedRecognitionLanguages().contains(recognitionLanguage) else {
            throw LioTranslationMediaFailure.unreadableImage
        }
        request.recognitionLanguages = [recognitionLanguage]
        try VNImageRequestHandler(cgImage: thumbnail).perform([request])
        let observations = (request.results ?? []).sorted {
            if $0.boundingBox.midY == $1.boundingBox.midY { return $0.boundingBox.minX < $1.boundingBox.minX }
            return $0.boundingBox.midY > $1.boundingBox.midY
        }
        let text = observations.compactMap { $0.topCandidates(1).first?.string }
        guard !text.isEmpty else { throw LioTranslationMediaFailure.noText }
        return text
    }
}
#endif
