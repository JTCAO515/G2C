#if canImport(Vision)
import Foundation
import ImageIO
import Vision

enum LioVisionTextReader {
    static func lines(from data: Data) async throws -> [String] {
        let photo = try thumbnail(from: data)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        let supported = try request.supportedRecognitionLanguages()
        request.recognitionLanguages = ["zh-Hans", "en-US"].filter { supported.contains($0) }
        try VNImageRequestHandler(cgImage: photo).perform([request])
        let observations = (request.results ?? []).sorted {
            if $0.boundingBox.midY == $1.boundingBox.midY { return $0.boundingBox.minX < $1.boundingBox.minX }
            return $0.boundingBox.midY > $1.boundingBox.midY
        }
        let text = observations.compactMap { $0.topCandidates(1).first?.string }
        guard !text.isEmpty else { throw LioTranslationMediaFailure.noText }
        return text
    }

    static func relayJPEG(from data: Data) async throws -> Data {
        let photo = try thumbnail(from: data)
        let bytes = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(bytes as CFMutableData,
                                                                  "public.jpeg" as CFString, 1, nil) else {
            throw LioTranslationMediaFailure.unreadableImage
        }
        CGImageDestinationAddImage(destination, photo, [
            kCGImageDestinationLossyCompressionQuality: 0.82,
        ] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw LioTranslationMediaFailure.unreadableImage }
        return bytes as Data
    }

    private static func thumbnail(from data: Data) throws -> CGImage {
        guard let image = CGImageSourceCreateWithData(data as CFData, nil),
              let photo = CGImageSourceCreateThumbnailAtIndex(image, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 4096,
              ] as CFDictionary) else {
            throw LioTranslationMediaFailure.unreadableImage
        }
        return photo
    }
}
#endif
