# CJ-BRAND-001 resource candidate

Fixed base: `3c52f72daf1d8e2304c0c569b47e68d92a4b323e`.
Original source: PR37 `20f3eba1e1955ae1ad7ab0592ad31210a2415c62`, merge `6a89f5bf5393e4642bef9db5195b5417508c5b13`.

Run from repository root: `swift ios/Branding/generate.swift` (macOS / Xcode).
The generator checks the exact original PNG SHA-256 before rendering. All derivatives retain the full square composition. BrandAvatar is a 192px transparent PNG; system icons use a white opaque background, without cropping or redesign. The SVG contains a different bitmap and is not used. No original or personal avatar is changed.

`source-and-derived.json` records hashes, sizes and PNG color types. All four original files were byte-compared against source, merge and baseline Git objects. Author viewed the original PNG and 180px icon / 192px avatar. This is asset preparation, not App integration or display acceptance.

Current actual build entrances:
- `ios/Modules/CJShell/scripts/build-demo.sh`: Swift package + manual executable/App packaging; bundle `local.cj006.shell.demo`, existing ad-hoc signing.
- `scripts/build-ios.sh`: Xcode `CJProbeApp`; bundle `space.go2china.foundation.local`, existing signing disabled. Foundation is a probe App, not a replacement shell.

Integration pending Main's exact path ACK: CJShell AssistantShell.swift, Package.swift, scripts/build-demo.sh, new BrandAvatar.swift/resource; scripts/build-ios.sh and ios/App/Info.plist. Additionally request ios/CJProbeApp.xcodeproj/project.pbxproj resource reference/build-phase scope so ordinary Xcode builds include icons, not just wrapper-script builds. No signing, identity, entitlements or ATS change is proposed. No simulator boot/install/launch before Main coordinates an exact safe device and application lease.

Author verification: generator PASS; Git original-byte comparisons PASS; derived image inspection PASS; diff whitespace PASS. Actual App build/package/display, independent Review/Testing, device and store UNRUN. Only ios/Branding/** changed in this candidate.
