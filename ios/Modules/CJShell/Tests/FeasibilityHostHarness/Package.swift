// swift-tools-version: 6.1
import PackageDescription
let package = Package(name: "CJShell", platforms: [.iOS(.v17), .macOS(.v14)],
 products: [.library(name: "CJShell", targets: ["CJShell"])],
 dependencies: [.package(path: "../CJNeedsClient"), .package(path: "../CJFeasibilityClient"), .package(path: "../CJAuth")],
 targets: [.target(name: "CJShell", dependencies: [.product(name: "CJNeedsClient", package: "CJNeedsClient"), .product(name: "CJFeasibilityClient", package: "CJFeasibilityClient"), .product(name: "CJSession", package: "CJAuth")]),
 .testTarget(name: "CJShellTests", dependencies: ["CJShell"])])
