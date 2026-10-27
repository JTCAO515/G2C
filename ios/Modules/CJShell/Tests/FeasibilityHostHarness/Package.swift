// swift-tools-version: 6.1
import PackageDescription

// Run the historical host assertions against the current repository modules.
let package = Package(
    name: "FeasibilityHostHarness",
    platforms: [.iOS(.v17), .macOS(.v14)],
    dependencies: [
        .package(path: "../.."),
        .package(path: "../../../CJNeedsClient"),
        .package(path: "../../../CJFeasibilityClient"),
        .package(path: "../../../CJAuth"),
        .package(path: "../../../CJMessageClient")
    ],
    targets: [.testTarget(
        name: "FeasibilityHostHarnessTests",
        dependencies: [
            .product(name: "CJShell", package: "CJShell"),
            .product(name: "CJNeedsClient", package: "CJNeedsClient"),
            .product(name: "CJFeasibilityClient", package: "CJFeasibilityClient"),
            .product(name: "CJSession", package: "CJAuth"),
            .product(name: "CJMessageHTTP", package: "CJMessageClient")
        ],
        path: ".",
        exclude: ["ShellFacts.swift"],
        sources: ["FeasibilityHostTests.swift"]
    )]
)
