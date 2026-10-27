// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "G2CDevelopmentConfiguration", platforms: [.macOS(.v14)], targets: [
    .target(name: "G2CDevelopmentConfiguration", path: ".",
        exclude: ["Tests", "CJProbeApp.swift", "DevelopmentTripHost.swift", "Info.plist", "Development.entitlements"],
        sources: ["DevelopmentSessionConfiguration.swift"]),
    .testTarget(name: "G2CDevelopmentConfigurationTests", dependencies: ["G2CDevelopmentConfiguration"], path: "Tests")
])
