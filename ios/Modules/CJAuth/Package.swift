// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CJAuth",
    platforms: [.iOS(.v17), .macOS(.v14)], // local experiment, not product minimum OS
    products: [.library(name: "CJAuth", targets: ["CJAuth"])],
    targets: [.target(name: "CJAuth"), .testTarget(name: "CJAuthTests", dependencies: ["CJAuth"])]
)
