// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "G2CDevelopmentConfiguration", platforms: [.macOS(.v14)], targets: [
    .target(name: "G2CDevelopmentConfiguration", path: ".",
        exclude: ["Acceptance", "Tests", "CJProbeApp.swift", "DevelopmentTripHost.swift", "DemoBetaApp.swift", "Info.plist", "Development.entitlements", "Beta.entitlements", "PrivacyInfo.xcprivacy"],
        sources: ["DevelopmentSessionConfiguration.swift", "DemoBetaConfiguration.swift"]),
    .testTarget(name: "G2CDevelopmentConfigurationTests", dependencies: ["G2CDevelopmentConfiguration"], path: "Tests")
])
