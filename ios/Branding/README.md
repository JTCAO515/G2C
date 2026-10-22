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

## Foundation path ACK delta

Main explicitly released scripts/build-ios.sh and ios/App/Info.plist. The existing build command is unchanged except removing shell exec to allow the successful-build icon copy step. Plist comparison after removing only the two new icon dictionaries equals the original parsed plist. Shell syntax and plist lint PASS. Xcode project / CJShell remain untouched. All discovered simulators were Shutdown; no device was booted, installed or launched. Build/package/display remain UNRUN pending the coordinated target and Xcode resource-path ACK.

## Actual Foundation build/package/display

At commit dce3460e45798cb895c9220d68551c34808faaf2, `scripts/build-ios.sh C52D892F-B5EC-4414-97C4-ED34829DCD7A` succeeded with original signing-disabled command parameters. Main authorized creating the dedicated CJ-BRAND-001-20261022 iPhone 17 Pro / iOS 26.5 simulator. All six packaged icon PNGs match source derivatives; icon plist and original bundle ID checked. Installation succeeded. XcodeBuildMCP runtime snapshot showed CJ Foundation on SpringBoard (screenHash 1by7wwm), and foundation-home.jpg visibly shows the PR37 image as its system icon. Simulator shut down successfully after capture; preserved, not erased. Probe App never launched; no account, application networking or Keychain activity initiated. Dependency resolution downloaded pinned public Swift packages during build, not application service access.

Evidence: evidence/foundation-build.txt, evidence/foundation-package.txt, evidence/foundation-home.jpg. This proves the existing Foundation script's build/package/system-icon path on this simulator only. CJShell Agent avatar and direct Xcode resource integration remain pending exact file lease; full task is not complete. No push/PR/merge/store action.

## Direct Xcode resource integration (supersedes wrapper-only limitation)

After Main's explicit project-file lease, six existing icon PNGs are registered by 6 PBXFileReference + 6 PBXBuildFile objects and one PBXResourcesBuildPhase on the existing target. Parsed comparison confirms all original objects remain equal except adding these references to the group and target resource phase. All build settings, source/framework phases, package dependencies and identity are unchanged. scripts/build-ios.sh is restored byte-for-byte to fixed base 3c52f72; it no longer performs post-build copying.

Direct xcodebuild (no wrapper), generic iOS Simulator destination, separate fresh .local/DirectDerivedData, original signing disabled: PASS. Exact command is in evidence/foundation-direct-build.txt (only trailing whitespace normalized). The actual output contains all six icons and expected Info.plist icon declaration/bundle ID. Xcode CopyPNGFile optimizes PNG bytes; source/package hashes are explicitly different in foundation-direct-package.json. All six decoded RGBA pixel arrays compare equal (verify-direct-icons.swift / foundation-direct-pixels.txt). Existing system-display evidence is reused because rendered icon pixels and icon metadata are unchanged; no additional simulator boot or installation was needed. Agent avatar remains pending CJShell lease.
