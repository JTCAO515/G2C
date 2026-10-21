// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "CJMessageClient",
    platforms: [.iOS(.v17), .macOS(.v14)], // Local package baseline, not product support policy.
    products: [.library(name: "CJMessageClient", targets: ["CJMessageClient"]),
               .library(name: "CJMessageHTTP", targets: ["CJMessageHTTP"]),
               .library(name: "CJMessageKeyBridge", targets: ["CJMessageKeyBridge"])],
    dependencies: [
        .package(path: ".generated/312a69caf0bd97ed65679cfd8ff049972c212cef/CJFoundation"),
        .package(path: ".generated/CJMessageKeysInterface"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", exact: "1.3.2"),
        .package(url: "https://github.com/apple/swift-http-types", exact: "1.8.0")
    ],
    targets: [
        .target(name: "CJMessageClient"),
        .target(name: "CJMessageKeyBridge", dependencies: ["CJMessageClient", .product(name: "CJMessageKeys", package: "CJMessageKeysInterface")]),
        .target(name: "CJMessageHTTP", dependencies: ["CJMessageClient", .product(name: "CJAPI", package: "CJFoundation"),
            .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
            .product(name: "HTTPTypes", package: "swift-http-types")]),
        .testTarget(name: "CJMessageHTTPTests", dependencies: ["CJMessageHTTP"]),
        .testTarget(name: "CJMessageClientTests", dependencies: ["CJMessageClient", "CJMessageKeyBridge"]),
        .executableTarget(name: "CJMessageRecoveryProbe", dependencies: ["CJMessageClient"], path: "Tests/ProcessProbe")
    ]
)
