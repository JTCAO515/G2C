import Foundation
import CoreGraphics
import ImageIO
import Testing
@testable import CJLioUser

struct LioTranslatedPhotoTests {
    @Test func keepsOnlyImagesWithMatchingSupportedDisplayDimensions() throws {
        let original = try image(width: 32, height: 16)
        let matching = try image(width: 16, height: 32, orientation: 6)
        let wrongSize = try image(width: 16, height: 32)
        let oversized = try image(width: 2049, height: 16)
        let result = try #require(LioTranslatedPhoto(original: original, translated: matching))
        #expect(result.original == original)
        #expect(result.translated == matching)
        #expect(LioTranslatedPhoto(original: original, translated: wrongSize) == nil)
        #expect(LioTranslatedPhoto(original: original, translated: Data()) == nil)
        #expect(LioTranslatedPhoto(original: oversized, translated: oversized) == nil)
    }

    private func image(width: Int, height: Int, orientation: Int = 1) throws -> Data {
        let renderer = try #require(CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                                               bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                               bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        let bitmap = try #require(renderer.makeImage())
        let data = NSMutableData()
        let destination = try #require(CGImageDestinationCreateWithData(data, "public.jpeg" as CFString, 1, nil))
        CGImageDestinationAddImage(destination, bitmap, [kCGImagePropertyOrientation: orientation] as CFDictionary)
        try #require(CGImageDestinationFinalize(destination))
        return data as Data
    }
}
