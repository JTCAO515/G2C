// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CJShell",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "CJShell", targets: ["CJShell"])],
    targets: [
        .target(name: "CJShell"),
        .testTarget(name: "CJShellTests", dependencies: ["CJShell"])
    ]
)
