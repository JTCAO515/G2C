// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    dependencies: [.package(path: "../CJAuth"), .package(path: "../CJMemoryClient"), .package(path: "../CJTripClient"), .package(path: "../CJManualPreviewClient"), .package(path: "../CJNeedsClient"), .package(path: "../CJFeedbackClient"), .package(path: "../CJRunClient"), .package(path: "../CJMessageClient"), .package(path: "../CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation")],
    targets: [
        .target(name: "CJShell", dependencies: [.product(name: "CJAuth", package: "CJAuth"), .product(name: "CJMemoryClient", package: "CJMemoryClient"), .product(name: "CJTripClient", package: "CJTripClient"), .product(name: "CJManualPreviewClient", package: "CJManualPreviewClient"), .product(name: "CJNeedsClient", package: "CJNeedsClient"), .product(name: "CJFeedbackClient", package: "CJFeedbackClient"), .product(name: "CJRunClient", package: "CJRunClient"), .product(name: "CJAuthSupabase", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient"), .product(name: "CJMessageHTTP", package: "CJMessageClient"), .product(name: "CJAPI", package: "CJFoundation")], resources: [.copy("Resources/BrandAvatar.png")]),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
