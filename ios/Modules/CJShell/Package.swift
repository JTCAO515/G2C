// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    dependencies: [.package(path: "../CJAuth"), .package(path: "../CJMessageClient"), .package(path: "../CJMessageClient/.generated/2f8be7c3e2dd298457488412b3a5e3b2ca59ca93/CJFoundation")],
    targets: [
        .target(name: "CJShell", dependencies: [.product(name: "CJAuth", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient"), .product(name: "CJMessageHTTP", package: "CJMessageClient"), .product(name: "CJAPI", package: "CJFoundation")]),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
