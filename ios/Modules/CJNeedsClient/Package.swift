// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "CJNeedsClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJNeedsClient", targets: ["CJNeedsClient"])],
    dependencies: [
        .package(path: "../CJMessageClient/.generated/f87a78a9d8984c59905e385483f17dddd8144d8a/CJFoundation"),
        .package(path: "../CJMessageClient"), .package(path: "../CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")
    ],
    targets: [
        .target(name: "CJNeedsClient", dependencies: [
            .product(name: "CJAPI", package: "CJFoundation"),
            .product(name: "CJMessageHTTP", package: "CJMessageClient"),
            .product(name: "CJSession", package: "CJAuth"),
            .product(name: "CJMessageKeys", package: "CJAuth"),
            .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJNeedsClientTests", dependencies: ["CJNeedsClient"])
    ])
