// swift-tools-version: 6.1
import PackageDescription
import Foundation

// Author verification uses byte-exact fixed exports inside this module. Normal
// integration resolves canonical sibling packages; it never falls back to exports.
let modules = ProcessInfo.processInfo.environment["CJ_SHELL_ISOLATED_DEPS"] == "1"
    ? ".deps/f87a78a9d8984c59905e385483f17dddd8144d8a/ios/Modules" : ".."

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    dependencies: [.package(path: "../CJFeasibilityClient"), .package(path: "\(modules)/CJAuth"), .package(path: "\(modules)/CJMemoryClient"), .package(path: "\(modules)/CJTripClient"), .package(path: "\(modules)/CJManualPreviewClient"), .package(path: "\(modules)/CJNeedsClient"), .package(path: "\(modules)/CJFeedbackClient"), .package(path: "\(modules)/CJRunClient"), .package(path: "\(modules)/CJUsageClient"), .package(path: "\(modules)/CJMessageClient"), .package(path: "\(modules)/CJOfflineTrip"), .package(path: "\(modules)/CJCleanupClient"), .package(path: "\(modules)/CJMessageClient/.generated/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/CJFoundation")],
    targets: [
        .target(name: "CJShell", dependencies: [.product(name: "CJFeasibilityClient", package: "CJFeasibilityClient"), .product(name: "CJAuth", package: "CJAuth"), .product(name: "CJMemoryClient", package: "CJMemoryClient"), .product(name: "CJTripClient", package: "CJTripClient"), .product(name: "CJManualPreviewClient", package: "CJManualPreviewClient"), .product(name: "CJNeedsClient", package: "CJNeedsClient"), .product(name: "CJFeedbackClient", package: "CJFeedbackClient"), .product(name: "CJRunClient", package: "CJRunClient"), .product(name: "CJUsageClient", package: "CJUsageClient"), .product(name: "CJOfflineTrip", package: "CJOfflineTrip"), .product(name: "CJCleanupClient", package: "CJCleanupClient"), .product(name: "CJAuthSupabase", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient"), .product(name: "CJMessageHTTP", package: "CJMessageClient"), .product(name: "CJAPI", package: "CJFoundation")], resources: [.copy("Resources/BrandAvatar.png")]),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
