// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "CJOfflineTrip", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJOfflineTrip", targets: ["CJOfflineTrip"])],
    dependencies: [.package(path: "../CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation")],
    targets: [.target(name: "CJOfflineTrip", dependencies: [.product(name: "CJAPI", package: "CJFoundation")]),
              .testTarget(name: "CJOfflineTripTests", dependencies: ["CJOfflineTrip"])])
