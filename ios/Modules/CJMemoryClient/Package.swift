// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "CJMemoryClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJMemoryClient", targets: ["CJMemoryClient"])],
    dependencies: [
        .package(path: "../CJMessageClient/.generated/33cec5ba71d74820cb0acd3c89ecbe39ba125590/CJFoundation"),
        .package(path: "../CJMessageClient"), .package(path: "../CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")],
    targets: [.target(name: "CJMemoryClient", dependencies: [
        .product(name: "CJAPI", package: "CJFoundation"), .product(name: "CJMessageHTTP", package: "CJMessageClient"),
        .product(name: "CJMessageKeys", package: "CJAuth"),
        .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"), .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJMemoryClientTests", dependencies: ["CJMemoryClient"])])
