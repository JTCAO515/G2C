#!/bin/bash
set -euo pipefail
package_dir="$(cd "$(dirname "$0")/.." && pwd)"
output_dir="${1:-/tmp/cj006-demo}"
mkdir -p "$output_dir/CJShellDemo.app" "$output_dir/module-cache"
sdk_path="$(xcrun --sdk iphonesimulator --show-sdk-path)"
# Build the real package graph, including canonical CJAPI/CJMessageHTTP modules.
# Uses only previously prepared exact generated exports; no source generation here.
swift_args=(--disable-sandbox --package-path "$package_dir" --scratch-path "$output_dir/package-build" --cache-path "${CJ_SPM_CACHE:-/tmp/cj006-spm-cache}" --triple arm64-apple-ios17.0-simulator --sdk "$sdk_path")
env -u SDKROOT CLANG_MODULE_CACHE_PATH="$output_dir/module-cache" SWIFTPM_MODULECACHE_OVERRIDE="$output_dir/module-cache" swift build "${swift_args[@]}" --target CJShell
products="$(env -u SDKROOT CLANG_MODULE_CACHE_PATH="$output_dir/module-cache" SWIFTPM_MODULECACHE_OVERRIDE="$output_dir/module-cache" swift build "${swift_args[@]}" --show-bin-path)"
test -f "$products/CJShell.o"
SDKROOT="$sdk_path" xcrun --sdk iphonesimulator swiftc -parse-as-library -swift-version 6 -target arm64-apple-ios17.0-simulator -sdk "$sdk_path" -module-cache-path "$output_dir/module-cache" -I "$products" "$package_dir/Demo/DemoApp.swift" "$products"/*.o -o "$output_dir/CJShellDemo.app/CJShellDemo"
cat > "$output_dir/CJShellDemo.app/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.cj006.shell.demo</string>
<key>CFBundleExecutable</key><string>CJShellDemo</string>
<key>CFBundleName</key><string>CJShellDemo</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>MinimumOSVersion</key><string>17.0</string>
<key>UIDeviceFamily</key><array><integer>1</integer><integer>2</integer></array>
<key>UILaunchScreen</key><dict/>
</dict></plist>
PLIST
codesign --force --sign - "$output_dir/CJShellDemo.app"
printf '%s\n' "$output_dir/CJShellDemo.app"
