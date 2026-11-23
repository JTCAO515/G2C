import Foundation
import ImageIO

struct LioTranslatedPhoto {
    let original: Data
    let translated: Data

    init?(original: Data, translated: Data) {
        guard let source = Self.pixelSize(original),
              let result = Self.pixelSize(translated),
              source == result else { return nil }
        self.original = original
        self.translated = translated
    }

    private static func pixelSize(_ data: Data) -> CGSize? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) == 1,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int,
              (1...2048).contains(width), (1...2048).contains(height)
        else { return nil }
        let orientation = properties[kCGImagePropertyOrientation] as? Int ?? 1
        return (5...8).contains(orientation)
            ? CGSize(width: height, height: width)
            : CGSize(width: width, height: height)
    }
}
