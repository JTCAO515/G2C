// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "CJFoundation",
    platforms: [.iOS(.v17), .macOS(.v14)], // engineering experiment, not product support policy
    products: [.library(name: "CJAPI", targets: ["CJAPI"])],
    dependencies: [
        .package(url: "https://github.com/apple/swift-openapi-generator", exact: "1.14.2"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", exact: "1.3.2")
    ],
    targets: [
        .target(name: "CJAPI", dependencies: [.product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"), .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession")]),
        .testTarget(name: "CJAPITests", dependencies: ["CJAPI"])
    ]
)
