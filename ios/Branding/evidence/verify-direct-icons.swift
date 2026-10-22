import Foundation
import CoreGraphics
import ImageIO

enum CheckError: Error { case decode(String), mismatch(String) }
func pixels(_ path: String) throws -> Data {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
          let context = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: image.width * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { throw CheckError.decode(path) }
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    guard let data = context.data else { throw CheckError.decode(path) }
    return Data(bytes: data, count: image.width * image.height * 4)
}
let directory = "ios/Branding/Assets"
for name in try FileManager.default.contentsOfDirectory(atPath: directory).filter({ $0.hasPrefix("AppIcon") }).sorted() {
    let expected = try pixels(directory + "/" + name)
    let actual = try pixels(".local/DirectDerivedData/Build/Products/Debug-iphonesimulator/CJProbeApp.app/" + name)
    guard expected == actual else { throw CheckError.mismatch(name) }
    print("PASS decoded RGBA pixels: \(name)")
}
