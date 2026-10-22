// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    dependencies: [.package(path: "../CJAuth"), .package(path: "../CJMemoryClient"), .package(path: "../CJTripClient"), .package(path: "../CJNeedsClient"), .package(path: "../CJFeedbackClient"), .package(path: "../CJRunClient"), .package(path: "../CJMessageClient"), .package(path: "../CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation")],
    targets: [
        .target(name: "CJShell", dependencies: [.product(name: "CJAuth", package: "CJAuth"), .product(name: "CJMemoryClient", package: "CJMemoryClient"), .product(name: "CJTripClient", package: "CJTripClient"), .product(name: "CJNeedsClient", package: "CJNeedsClient"), .product(name: "CJFeedbackClient", package: "CJFeedbackClient"), .product(name: "CJRunClient", package: "CJRunClient"), .product(name: "CJAuthSupabase", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient"), .product(name: "CJMessageHTTP", package: "CJMessageClient"), .product(name: "CJAPI", package: "CJFoundation")], resources: [.copy("Resources/BrandAvatar.png")]),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
