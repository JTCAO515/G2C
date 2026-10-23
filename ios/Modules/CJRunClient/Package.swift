// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "CJRunClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJRunClient", targets: ["CJRunClient"])],
    dependencies: [
        .package(path: "../CJMessageClient/.generated/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/CJFoundation"),
        .package(path: "../CJMessageClient"), .package(path: "../CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")],
    targets: [.target(name: "CJRunClient", dependencies: [
        .product(name: "CJAPI", package: "CJFoundation"), .product(name: "CJMessageHTTP", package: "CJMessageClient"),
        .product(name: "CJSession", package: "CJAuth"),
        .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"), .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJRunClientTests", dependencies: ["CJRunClient"])])
