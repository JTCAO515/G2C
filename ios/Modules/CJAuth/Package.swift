// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "CJAuth",
    platforms: [.iOS(.v17), .macOS(.v14)], // local experiment, not product minimum OS
    products: [.library(name: "CJAuth", targets: ["CJAuth"]),
               .library(name: "CJAuthSupabase", targets: ["CJAuthSupabase"])],
    dependencies: [.package(url: "https://github.com/supabase/supabase-swift", exact: "2.55.4")],
    targets: [
        .target(name: "CJAuth"),
        .target(name: "CJAuthSupabase", dependencies: ["CJAuth", .product(name: "Auth", package: "supabase-swift")]),
        .testTarget(name: "CJAuthTests", dependencies: ["CJAuth"]),
        .testTarget(name: "CJAuthSupabaseTests", dependencies: ["CJAuthSupabase", "CJAuth"])
    ]
)
