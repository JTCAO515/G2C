// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "CJIOSSpike", platforms: [.iOS(.v18), .macOS(.v15)],
    products: [.library(name: "SpikeUI", targets: ["SpikeUI"])],
    dependencies: [
        .package(url: "https://github.com/supabase/supabase-swift", exact: "2.55.4"),
        .package(url: "https://github.com/apple/swift-openapi-generator", exact: "1.14.2"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", exact: "1.13.3"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", exact: "1.3.2"),
        .package(url: "https://github.com/gonzalezreal/textual", exact: "0.5.0")
    ],
    targets: [
        .target(name: "SpikeClient", dependencies: [
            .product(name: "Auth", package: "supabase-swift"),
            .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession")
        ], plugins: [.plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")]),
        .target(name: "SpikeUI", dependencies: ["SpikeClient", .product(name: "Textual", package: "textual")]),
        .testTarget(name: "SpikeClientTests", dependencies: ["SpikeClient"])
    ]
)
