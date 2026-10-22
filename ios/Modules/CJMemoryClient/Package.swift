// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "CJMemoryClient", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJMemoryClient", targets: ["CJMemoryClient"])],
    dependencies: [
        .package(path: "../CJMessageClient/.generated/57336d501e5691302a3d5e9770f07666d1c57d4a/CJFoundation"),
        .package(path: "../CJMessageClient"), .package(path: "../CJAuth"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")],
    targets: [.target(name: "CJMemoryClient", dependencies: [
        .product(name: "CJAPI", package: "CJFoundation"), .product(name: "CJMessageHTTP", package: "CJMessageClient"),
        .product(name: "CJMessageKeys", package: "CJAuth"),
        .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"), .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJMemoryClientTests", dependencies: ["CJMemoryClient"])])
