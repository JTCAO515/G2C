// swift-tools-version: 6.1
import PackageDescription

// Sibling packages and the ios/ root package from this repository (ADR-0004: the commit is the pin).
let modules = ".."

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    dependencies: [.package(path: "../CJFeasibilityClient"), .package(path: "\(modules)/CJAuth"), .package(path: "\(modules)/CJMemoryClient"), .package(path: "\(modules)/CJTripClient"), .package(path: "\(modules)/CJManualPreviewClient"), .package(path: "\(modules)/CJNeedsClient"), .package(path: "\(modules)/CJFeedbackClient"), .package(path: "\(modules)/CJRunClient"), .package(path: "\(modules)/CJUsageClient"), .package(path: "\(modules)/CJMessageClient"), .package(path: "\(modules)/CJOfflineTrip"), .package(path: "\(modules)/CJCleanupClient"), .package(path: "../..")],
    targets: [
        .target(name: "CJShell", dependencies: [.product(name: "CJFeasibilityClient", package: "CJFeasibilityClient"), .product(name: "CJAuth", package: "CJAuth"), .product(name: "CJMemoryClient", package: "CJMemoryClient"), .product(name: "CJTripClient", package: "CJTripClient"), .product(name: "CJManualPreviewClient", package: "CJManualPreviewClient"), .product(name: "CJNeedsClient", package: "CJNeedsClient"), .product(name: "CJFeedbackClient", package: "CJFeedbackClient"), .product(name: "CJRunClient", package: "CJRunClient"), .product(name: "CJUsageClient", package: "CJUsageClient"), .product(name: "CJOfflineTrip", package: "CJOfflineTrip"), .product(name: "CJCleanupClient", package: "CJCleanupClient"), .product(name: "CJAuthSupabase", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient"), .product(name: "CJMessageHTTP", package: "CJMessageClient"), .product(name: "CJMessageKeyBridge", package: "CJMessageClient"), .product(name: "CJAPI", package: "ios")], resources: [.copy("Resources/BrandAvatar.png")]),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
