#if canImport(Vision)
import CoreGraphics
import CoreText
import Foundation
import ImageIO
import Testing
@testable import CJLioUser

struct LioVisionTextReaderTests {
    @Test func readsThePrintedLinesInVisualOrder() async throws {
        let context = try #require(CGContext(data: nil, width: 800, height: 420, bitsPerComponent: 8,
                                             bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                             bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(CGColor(gray: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 800, height: 420))
        let font = CTFontCreateWithName("Helvetica" as CFString, 96, nil)
        let attributes: [NSAttributedString.Key: Any] = [
            NSAttributedString.Key(kCTFontAttributeName as String): font,
            NSAttributedString.Key(kCTForegroundColorAttributeName as String): CGColor(gray: 0, alpha: 1)
        ]
        for (text, y) in [("Tea", 260.0), ("Coffee", 100.0)] {
            let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: attributes) as CFAttributedString)
            context.textPosition = CGPoint(x: 64, y: y)
            CTLineDraw(line, context)
        }
        let image = try #require(context.makeImage())
        let bytes = NSMutableData()
        let destination = try #require(CGImageDestinationCreateWithData(bytes as CFMutableData, "public.png" as CFString, 1, nil))
        CGImageDestinationAddImage(destination, image, nil)
        try #require(CGImageDestinationFinalize(destination))

        #expect(try await LioVisionTextReader.lines(from: bytes as Data) == ["Tea", "Coffee"])
        let encoded = try await LioVisionTextReader.relayJPEG(from: bytes as Data)
        #expect(encoded.starts(with: [0xff, 0xd8, 0xff]))
        #expect(try await LioVisionTextReader.lines(from: encoded) == ["Tea", "Coffee"])

    }

    @Test func rejectsDataThatIsNotAnImage() async {
        await #expect(throws: LioTranslationMediaFailure.unreadableImage) {
            _ = try await LioVisionTextReader.lines(from: Data("bad image".utf8))
        }
    }
}
#endif
