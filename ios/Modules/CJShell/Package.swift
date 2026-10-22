// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    dependencies: [.package(path: "../CJAuth"), .package(path: "../CJMessageClient"), .package(path: "../CJMessageClient/.generated/9dc67ced50a0cb7611a84b4adf97ab0b43c88bea/CJFoundation")],
    targets: [
        .target(name: "CJShell", dependencies: [.product(name: "CJAuth", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient"), .product(name: "CJMessageHTTP", package: "CJMessageClient"), .product(name: "CJAPI", package: "CJFoundation")], resources: [.copy("Resources/BrandAvatar.png")]),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
