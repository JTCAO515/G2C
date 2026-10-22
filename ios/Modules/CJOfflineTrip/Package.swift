// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "CJOfflineTrip", platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJOfflineTrip", targets: ["CJOfflineTrip"])],
    dependencies: [
        .package(path: "../CJAuth"), .package(path: "../CJTripClient"), .package(path: "../CJMessageClient"),
        .package(path: "../CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")
    ],
    targets: [
        .target(name: "CJOfflineTrip", dependencies: [
            .product(name: "CJAPI", package: "CJFoundation"), .product(name: "CJTripClient", package: "CJTripClient"),
            .product(name: "CJMessageKeys", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth")]),
        .testTarget(name: "CJOfflineTripTests", dependencies: [
            "CJOfflineTrip", .product(name: "CJTripClient", package: "CJTripClient"),
            .product(name: "CJMessageHTTP", package: "CJMessageClient"),
            .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            .product(name: "HTTPTypes", package: "swift-http-types"),
            .product(name: "CJMessageKeys", package: "CJAuth"), .product(name: "CJSession", package: "CJAuth")])
    ])
