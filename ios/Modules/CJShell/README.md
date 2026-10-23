# CJShell — CJ006 local candidate

Independent Swift package with adjacent CJAuth core dependency; no root package/Xcode changes or production entry point. UI@1.1 contract is in `contracts/ui/README.md` at repository root. iOS 17 and macOS 14 are experiment targets, not the agreed product minimum. macOS runs state tests; SwiftUI shell is iOS-only.

Host integration (future shared engineering owner): retain `@State private var shell = ShellState()` and present `ShellView(state: shell)`. Do not recreate the state or set `.id(language)` on the root. Optional `ShellPresentation.assistantBody` is plain native text applied with a captured UI generation; no Textual or CJ004 streaming experiment is linked.

## Fixed f87 combination

The manifest now links the fixed f87 consumer combination, including Offline and Cleanup products. Canonical integration uses sibling modules and the single official f87 Foundation export. Linking does not configure an offline cache or create an account-cleanup action, source, UI or grant; those capabilities remain unavailable without their existing trusted inputs.

Author verification can prepare immutable Git build inputs inside this module's ignored `.deps/f87a78a9d8984c59905e385483f17dddd8144d8a` directory without changing sibling worktrees:

```sh
python3 -B ios/Modules/CJShell/scripts/prepare_fixed_dependencies.py /path/to/existing-cj-checkouts
env -u CJ_CLEANUP_ISOLATED_DEPS CJ_SHELL_ISOLATED_DEPS=1 bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-f87-demo
```

The preparation script names every exact owner commit, verifies the official SDK manifest/file hashes and refuses different existing exports or symlinks. It reads no moving worktree source and performs no network access. Repeating it verifies/reuses identical bytes. `CJ_SHELL_ISOLATED_DEPS=1` is an explicit local verification mode, not an automatic fallback or global setting. Omit it only after the canonical siblings and official SDK export have been integrated at matching fixed inputs; missing canonical modules fail visibly. The separate Cleanup module's isolated-dependency flag is deliberately unset in this composition.

See `contracts/ui/evidence/f87-combination/REPORT.md` for exact inputs, actual graph, compile/link results, selected host tests and retained initial preparation failures. Old UI/source evidence and real App/service/Keychain/device gates remain separate.

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
