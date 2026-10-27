// swift-tools-version: 6.1
import PackageDescription

// Sibling packages and the ios/ root package from this repository (ADR-0004: the commit is the pin).
let modules = ".."
let package = Package(name: "CJCleanupClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJCleanupClient", targets: ["CJCleanupClient"])],
    dependencies: [
        .package(path: "../.."),
        .package(path: "\(modules)/CJMessageClient"),
        .package(path: "\(modules)/CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")],
    targets: [.target(name: "CJCleanupClient", dependencies: [
        .product(name: "CJAPI", package: "ios"),
        .product(name: "CJMessageHTTP", package: "CJMessageClient"),
        .product(name: "CJSession", package: "CJAuth"),
        .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
        .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJCleanupClientTests", dependencies: ["CJCleanupClient"])])
