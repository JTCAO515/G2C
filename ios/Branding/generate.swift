import Foundation
import CoreGraphics
import ImageIO
import CryptoKit
import UniformTypeIdentifiers

enum GenerationError: Error { case invalidSource, renderingFailed, encodingFailed }
let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
let source = root.appendingPathComponent("digital-assets/ios-avatar/2026-10-21/roamlion-symbol-original.png")
let bytes = try Data(contentsOf: source)
let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
guard digest == "cc1460d9ae4e46424289b5fd18c79d37361c2f536686090ae5774988b05670b1",
      let imageSource = CGImageSourceCreateWithData(bytes as CFData, nil),
      let original = CGImageSourceCreateImageAtIndex(imageSource, 0, nil),
      original.width == 2048, original.height == 2048 else { throw GenerationError.invalidSource }
let output = root.appendingPathComponent("ios/Branding/Assets")
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
// Full square source, no cropping or redesign. Only system icons flatten transparency.
for (name, size, opaque) in [("BrandAvatar", 192, false), ("AppIcon60x60@2x", 120, true), ("AppIcon60x60@3x", 180, true), ("AppIcon76x76", 76, true), ("AppIcon76x76@2x", 152, true), ("AppIcon83.5x83.5@2x", 167, true), ("AppIcon1024", 1024, true)] {
    let alpha = opaque ? CGImageAlphaInfo.noneSkipLast : CGImageAlphaInfo.premultipliedLast
    guard let context = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: size * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: alpha.rawValue) else { throw GenerationError.renderingFailed }
    let rect = CGRect(x: 0, y: 0, width: size, height: size)
    if opaque { context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(rect) }
    context.interpolationQuality = .high
    context.draw(original, in: rect)
    guard let scaled = context.makeImage(), let destination = CGImageDestinationCreateWithURL(output.appendingPathComponent(name + ".png") as CFURL, UTType.png.identifier as CFString, 1, nil) else { throw GenerationError.encodingFailed }
    CGImageDestinationAddImage(destination, scaled, nil)
    guard CGImageDestinationFinalize(destination) else { throw GenerationError.encodingFailed }
    print("\(name).png \(size)x\(size) opaque=\(opaque)")
}
