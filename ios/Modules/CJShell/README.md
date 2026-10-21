# CJShell — CJ006 local candidate

Independent Swift package with adjacent CJAuth core dependency; no root package/Xcode changes or production entry point. UI@1.1 contract is in `contracts/ui/README.md` at repository root. iOS 17 and macOS 14 are experiment targets, not the agreed product minimum. macOS runs state tests; SwiftUI shell is iOS-only.

Host integration (future shared engineering owner): retain `@State private var shell = ShellState()` and present `ShellView(state: shell)`. Do not recreate the state or set `.id(language)` on the root. Optional `ShellPresentation.assistantBody` is plain native text applied with a captured UI generation; no Textual or CJ004 streaming experiment is linked.

## Local checks and display app

From repository root, run the contract and Swift tests documented in the contract README. Build a standalone arm64 simulator app without generating or changing an Xcode project:

```sh
bash ios/Modules/CJShell/scripts/build-demo.sh
```

Output is `/tmp/cj006-demo/CJShellDemo.app`, signed locally for simulator use. Requires Xcode and an executable Swift macro host; a sandbox that blocks macro subprocesses needs the normal local-build permission. No account/network configuration or permission strings are used.

On a separately allocated simulator, install the bundle and launch `local.cj006.shell.demo`. Normal launch is the real disconnected shell. Launch with `--gallery` for explicitly synthetic bilingual state, large-font and long native body examples. Gallery is demo-only, outside package targets; it never starts service calls. It uses its own `cj006.demo.gallery` preference suite. The gallery's close button is a demo control, not part of product layout.

Manual acceptance steps (runtime coverage and limits now in `evidence/RUNTIME-DELTA.md`):

1. Normal launch: only Assistant / Trips / Plugins / Memory; switch all four. Confirm plugin text says unavailable and contains no tool action.
2. Enter bilingual draft. Open Memory → Language; switch language and return. Draft and selected route must remain. Relaunch and confirm language survives; draft restoration is intentionally not offered.
3. Memory under each gallery state: account, language, help/privacy/support remain accessible. No state claims signed-in or saved.
4. Assistant: inspect top status safe area, three independent controls, history sheet, neutral avatar, disabled gift/attachment/voice/send, keyboard and last paragraph at both normal and accessibility text sizes. Use long native text sample to scroll/select text.
5. VoiceOver: inspect labels, disabled announcements, tab order, picker and back navigation. Repeat on allocated physical devices for final acceptance.

Actual local checks and exclusions are recorded in `evidence/RESULTS.md`. Do not treat app compilation as any of the above visual/runtime checks.

Account host wiring and transient-input boundaries: see `contracts/ui/ACCOUNT-HOST.md` at repository root. Default account actions remain unconfigured and offline.
