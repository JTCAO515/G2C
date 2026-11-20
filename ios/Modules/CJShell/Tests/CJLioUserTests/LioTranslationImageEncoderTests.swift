import CoreGraphics
import Foundation
import ImageIO
import Testing
@testable import CJLioUser

struct LioTranslationImageEncoderTests {
    @Test func resizesLargeImagesForUploadAndPreservesAspectRatio() async throws {
        let context = try #require(CGContext(data: nil, width: 3072, height: 768, bitsPerComponent: 8,
                                             bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                             bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(red: 0.2, green: 0.5, blue: 0.7, alpha: 1)
        context.fill(CGRect(x: 0, y: 0, width: 3072, height: 768))
        let image = try #require(context.makeImage())
        let png = NSMutableData()
        let destination = try #require(CGImageDestinationCreateWithData(png, "public.png" as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil)
        try #require(CGImageDestinationFinalize(destination))
        let jpeg = try await LioTranslationImageEncoder.jpeg(from: png as Data)
        #expect(jpeg.prefix(3) == Data([0xff, 0xd8, 0xff]))
        let source = try #require(CGImageSourceCreateWithData(jpeg as CFData, nil))
        let decoded = try #require(CGImageSourceCreateImageAtIndex(source, 0, nil))
        #expect(decoded.width == 2048)
        #expect(decoded.height == 512)
    }
}
