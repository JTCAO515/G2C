# CJShell — CJ006 local candidate

Swift package linked by the G2C App target, with adjacent CJAuth and other domain modules. UI@1.1 contract is in `contracts/ui/README.md` at repository root. The accepted minimum is iOS 17 (ADR-0004); macOS 14 runs state tests; SwiftUI shell is iOS-only.

Host integration: retain `@State private var shell = ShellState()` and present `ShellView(state: shell)`. Do not recreate the state or set `.id(language)` on the root. Optional `ShellPresentation.assistantBody` is plain native text applied with a captured UI generation; no Textual or CJ004 streaming experiment is linked.

## Current App integration (PR #146)

The Xcode App target now links this package directly. Package manifests use sibling
modules and the `ios/` root package, with remote dependencies recorded in the App's
`Package.resolved`. No same-repository Git export or hash pin is needed.

Build the App with `DEVELOPER_DIR` set to the installed Xcode developer directory:

```sh
DEVELOPER_DIR="$DEVELOPER_DIR" xcodebuild -project ios/CJProbeApp.xcodeproj -scheme CJProbeApp \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath "$CJ_DERIVED_DATA" \
  ARCHS=arm64 ONLY_ACTIVE_ARCH=YES CODE_SIGNING_ALLOWED=NO build
```

The default App is a disconnected shell: sending, login, Trip confirmation and memory
services require explicit host configuration in a later P2c slice. Four tabs and a
successful build do not prove API, provider, OTP or device acceptance.

The historical `prepare_fixed_dependencies.py`, isolated-dependency flags, and demo
instructions below predate this integration. They are retained for old consumers and
historical reproduction only; they are not the current build entry. Remove them only
after remaining consumers and rollback needs have been checked. Evidence links below
refer to the `evidence-archive-2026-10-27` tag where files have left the working tree.

## Local checks and display app

From repository root, run the contract and Swift tests documented in the contract README. Build a standalone arm64 simulator app without generating or changing an Xcode project:

```sh
bash ios/Modules/CJShell/scripts/build-demo.sh
```

Output is `/tmp/cj006-demo/CJShellDemo.app`, signed locally for simulator use. Requires Xcode and an executable Swift macro host; a sandbox that blocks macro subprocesses needs the normal local-build permission. No account/network configuration or permission strings are used.

On a separately allocated simulator, install the bundle and launch `local.cj006.shell.demo`. Normal launch is the real disconnected shell. Launch with `--gallery` for explicitly synthetic bilingual state, large-font and long native body examples. Gallery is demo-only, outside package targets; it never starts service calls. It uses its own `cj006.demo.gallery` preference suite. The gallery's close button is a demo control, not part of product layout.

`--help-preview` opens the actual Help destination with no account/session resources, using the separate `cj006.demo.help` preference suite. Add `--chinese` for Chinese and `--large-text` for accessibility3 text size. This is a render entry only; initial navigation supplied by the demo does not verify link activation, scrolling, keyboard interaction or VoiceOver. It does not enable unavailable capabilities.

Manual acceptance steps (runtime coverage and limits now in `evidence/RUNTIME-DELTA.md`):

1. Normal launch: only Assistant / Trips / Plugins / Memory; switch all four. Confirm plugin text says unavailable and contains no tool action.
2. Enter bilingual draft. Open Memory → Language; switch language and return. Draft and selected route must remain. Relaunch and confirm language survives; draft restoration is intentionally not offered.
3. Memory under each gallery state: account, language, help/privacy/support remain accessible. No state claims signed-in or saved.
4. Assistant: inspect top status safe area, three independent controls, history sheet, neutral avatar, disabled gift/attachment/voice/send, keyboard and last paragraph at both normal and accessibility text sizes. Use long native text sample to scroll/select text.
5. VoiceOver: inspect labels, disabled announcements, tab order, picker and back navigation. Repeat on allocated physical devices for final acceptance.

Actual local checks and exclusions are recorded in `evidence/RESULTS.md`. Do not treat app compilation as any of the above visual/runtime checks.

Account host wiring and transient-input boundaries: see `contracts/ui/ACCOUNT-HOST.md` at repository root. Default account actions remain unconfigured and offline.

Explicit local-session UI and synthetic `--session-demo` flags are documented in `contracts/ui/SESSION-HOST.md`. Default launch never creates a session store.

Assistant recovery host and fixed generated dependency preparation: `contracts/ui/MESSAGE-HOST.md`. `--message-demo` is memory-only, visibly synthetic and never enables POST.

Server history is a separate read-only sheet using canonical CJAPI/CJMessageHTTP. Prepare the fixed 2f8 generated package before building; `build-demo.sh` compiles the actual iOS package graph and does not run a device. See `contracts/ui/SERVER-HISTORY-HOST.md` for lifecycle and dependency pins.
