#!/bin/zsh
set -euo pipefail
cd "${0:A:h}/.."
probe_root="$PWD/Probe/.build"
probe_app="$probe_root/CJ007SessionProbe.app"
mkdir -p "$probe_app"
probe_sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
xcrun swiftc -swift-version 6 -parse-as-library -target arm64-apple-ios17.0-simulator \
  -sdk "$probe_sdk" -module-cache-path /private/tmp/cj007-session-ios-cache \
  -module-name CJ007SessionProbe Sources/CJSession/*.swift Sources/CJMessageKeys/*.swift Probe/SessionProbe.swift Probe/MessageKeyProbe.swift \
  -o "$probe_app/CJ007SessionProbe"
python3 - "$probe_app/Info.plist" <<'PY'
import plistlib,sys
with open(sys.argv[1],'wb') as f:
 plistlib.dump(dict(CFBundleIdentifier='local.g2c.cj007.sessionprobe',CFBundleExecutable='CJ007SessionProbe',
 CFBundleName='CJ007SessionProbe',CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1.0',
 MinimumOSVersion='17.0',LSRequiresIPhoneOS=True,UILaunchScreen={},UIDeviceFamily=[1,2]),f)
PY
cp Probe/Proposals/MessageKeyProbeScope.plist "$probe_app/MessageKeyProbeScope.plist"
# Existing ad-hoc signing only. Entitlement proposal is NEVER applied by this script.
codesign --force --sign - "$probe_app"
echo "$probe_app"
