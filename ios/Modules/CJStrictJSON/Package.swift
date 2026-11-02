// swift-tools-version: 6.0
import PackageDescription

// Leaf package: no dependencies, so every client module can share one JSON boundary.
let package = Package(name: "CJStrictJSON", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJStrictJSON", targets: ["CJStrictJSON"])],
    targets: [.target(name: "CJStrictJSON"),
              .testTarget(name: "CJStrictJSONTests", dependencies: ["CJStrictJSON"])])
