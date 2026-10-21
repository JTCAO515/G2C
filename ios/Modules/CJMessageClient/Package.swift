// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "CJMessageClient",
    platforms: [.iOS(.v17), .macOS(.v14)], // Local package baseline, not product support policy.
    products: [.library(name: "CJMessageClient", targets: ["CJMessageClient"])],
    targets: [
        .target(name: "CJMessageClient"),
        .testTarget(name: "CJMessageClientTests", dependencies: ["CJMessageClient"]),
        .executableTarget(name: "CJMessageRecoveryProbe", dependencies: ["CJMessageClient"], path: "Tests/ProcessProbe")
    ]
)
