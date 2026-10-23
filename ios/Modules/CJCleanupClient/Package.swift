// swift-tools-version: 6.1
import PackageDescription
import Foundation
// Verification-only export stays inside this leased module. Integration uses
// canonical sibling packages, so the host graph cannot acquire duplicate SDKs.
let modules = ProcessInfo.processInfo.environment["CJ_CLEANUP_ISOLATED_DEPS"] == "1"
    ? ".deps/20aa50ed5c8449e6026155a6151f22041dee7fd4/ios/Modules" : ".."
let package = Package(name: "CJCleanupClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJCleanupClient", targets: ["CJCleanupClient"])],
    dependencies: [
        .package(path: "\(modules)/CJMessageClient/.generated/20aa50ed5c8449e6026155a6151f22041dee7fd4/CJFoundation"),
        .package(path: "\(modules)/CJMessageClient"),
        .package(path: "\(modules)/CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")],
    targets: [.target(name: "CJCleanupClient", dependencies: [
        .product(name: "CJAPI", package: "CJFoundation"),
        .product(name: "CJMessageHTTP", package: "CJMessageClient"),
        .product(name: "CJSession", package: "CJAuth"),
        .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
        .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJCleanupClientTests", dependencies: ["CJCleanupClient"])])
