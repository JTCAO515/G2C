// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "CJTripClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJTripClient", targets: ["CJTripClient"])],
    dependencies: [
        .package(path: "../CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation"),
        .package(path: "../CJMessageClient"), .package(path: "../CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")
    ],
    targets: [
        .target(name: "CJTripClient", dependencies: [
            .product(name: "CJAPI", package: "CJFoundation"),
            .product(name: "CJMessageHTTP", package: "CJMessageClient"),
            .product(name: "CJSession", package: "CJAuth"),
            .product(name: "CJMessageKeys", package: "CJAuth"),
            .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJTripClientTests", dependencies: ["CJTripClient"], resources: [.copy("Fixtures")])
    ])
