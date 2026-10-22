#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
. ./scripts/env.sh
if [ "$#" != 1 ]; then echo 'Usage: scripts/build-ios.sh SIMULATOR_UDID' >&2; exit 2; fi
# Xcode's derived lock mirrors the sole editable Swift lock.
mkdir -p ios/CJProbeApp.xcodeproj/project.xcworkspace/xcshareddata/swiftpm
cp ios/Package.resolved ios/CJProbeApp.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved
xcodebuild -project ios/CJProbeApp.xcodeproj -scheme CJProbeApp -configuration Debug \
  -destination "platform=iOS Simulator,id=$1" -derivedDataPath "$PWD/.local/DerivedData" \
  -clonedSourcePackagesDirPath "$PWD/.local/XcodePackages" -packageCachePath "$PWD/.local/XcodePackageCache" \
  -disablePackageRepositoryCache -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile \
  "CLANG_MODULE_CACHE_PATH=$PWD/.local/XcodeModuleCache" CODE_SIGNING_ALLOWED=NO build

# Package the verified PR37 derivatives into the existing unsigned simulator App.
app="$PWD/.local/DerivedData/Build/Products/Debug-iphonesimulator/CJProbeApp.app"
test -d "$app"
for icon in "$PWD"/ios/Branding/Assets/AppIcon*.png; do
  cp "$icon" "$app/"
done
