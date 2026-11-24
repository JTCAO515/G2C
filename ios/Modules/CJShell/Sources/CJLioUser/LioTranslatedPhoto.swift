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

    static func pixelSize(_ data: Data) -> CGSize? {
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

struct LioPositionedTranslation {
    struct Item {
        let text: String
        let points: [CGPoint]
        let bounds: CGRect
    }

    let image: Data
    let size: CGSize
    let items: [Item]

    init(image: Data, reply: LioRelayTranslationResponse) throws {
        guard let width = reply.imageWidth, let height = reply.imageHeight,
              let size = LioTranslatedPhoto.pixelSize(image),
              size.width == CGFloat(width), size.height == CGFloat(height) else {
            throw LioTranslationFailure.service
        }

        self.image = image
        self.size = size
        items = try reply.items.map { item in
            guard let values = item.location, values.count == 8 else { throw LioTranslationFailure.service }
            let points = stride(from: 0, to: values.count, by: 2).map {
                CGPoint(x: values[$0], y: values[$0 + 1])
            }
            guard points.allSatisfy({ (0...size.width).contains($0.x) && (0...size.height).contains($0.y) }),
                  points.indices.allSatisfy({ index in
                      let a = points[index], b = points[(index + 1) % 4], c = points[(index + 2) % 4]
                      return (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x) > 0
                  }),
                  let minX = points.map(\.x).min(), let maxX = points.map(\.x).max(),
                  let minY = points.map(\.y).min(), let maxY = points.map(\.y).max() else {
                throw LioTranslationFailure.service
            }
            return Item(text: item.translatedText, points: points,
                        bounds: CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY))
        }
    }
}
