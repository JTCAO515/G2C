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

    @Test func laysOutTheTranslatedTextAtTheUploadedImageCoordinates() throws {
        let jpeg = try image(width: 32, height: 16)
        let data = Data(#"{"version":"IMAGE-LAYOUT.1","image_width":32,"image_height":16,"items":[{"source_text":"茶","translated_text":"Tea","location":[2,3,12,3,12,9,2,9]}]}"#.utf8)
        let reply = try LioRelayTranslationResponse.decode(status: 200, body: data, expecting: .image, usesImageLayout: true)
        let photo = try LioPositionedTranslation(image: jpeg, reply: reply)
        let item = try #require(photo.items.first)
        #expect(photo.image == jpeg)
        #expect(item.text == "Tea")
        #expect(item.points.count == 4)
        #expect(item.bounds == CGRect(x: 2, y: 3, width: 10, height: 6))
    }

    @Test(arguments: [[2, 3, 33, 3, 12, 9, 2, 9], [2, 3, 12, 9, 12, 3, 2, 9], [2, 3, 12, 3]])
    func rejectsOutOfBoundsOrInvalidQuadrilaterals(points: [Int]) throws {
        let jpeg = try image(width: 32, height: 16)
        let data = try JSONSerialization.data(withJSONObject: [
            "version": "IMAGE-LAYOUT.1", "image_width": 32, "image_height": 16,
            "items": [["source_text": "茶", "translated_text": "Tea", "location": points]]
        ])
        let reply = try LioRelayTranslationResponse.decode(status: 200, body: data, expecting: .image, usesImageLayout: true)
        #expect(throws: LioTranslationFailure.service) { try LioPositionedTranslation(image: jpeg, reply: reply) }
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
