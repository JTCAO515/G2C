#if canImport(ImageIO)
import Foundation
import ImageIO

enum LioTranslationImageEncoder {
    static func jpeg(from data: Data) async throws -> Data {
        let photo = try thumbnail(from: data)
        let bytes = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(bytes as CFMutableData,
                                                                  "public.jpeg" as CFString, 1, nil) else {
            throw LioTranslationMediaFailure.unreadableImage
        }
        CGImageDestinationAddImage(destination, photo, [
            kCGImageDestinationLossyCompressionQuality: 0.8,
        ] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw LioTranslationMediaFailure.unreadableImage }
        return bytes as Data
    }

    private static func thumbnail(from data: Data) throws -> CGImage {
        guard let image = CGImageSourceCreateWithData(data as CFData, nil),
              let photo = CGImageSourceCreateThumbnailAtIndex(image, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 2048,
              ] as CFDictionary) else {
            throw LioTranslationMediaFailure.unreadableImage
        }
        return photo
    }
}
#endif
