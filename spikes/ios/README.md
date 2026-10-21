# CJ-004 isolated iOS candidate

This is a disposable SDK, generated-client and rendering probe, not the product App/API. Only `spikes/ios/**` is owned by CJ-004. Base: `13905e4587feb8611ebde5e3621024f3338532ae`; branch: `cj/004-ios`. No production endpoints, secrets, real login or paid calls. The temporary `.invalid` SSE-only OpenAPI must be removed/replaced by the formal RUN/SSE source before product adoption; it must never become a second formal API.

The renderer's iOS 18 deployment target is a **probe constraint**, not a product minimum. If CJ-001 selects iOS 16/17, keep Auth/transport and replace Textual with a separately verified native renderer; do not raise the product target to accommodate this package.

Run from this directory:

```sh
export CLANG_MODULE_CACHE_PATH="$PWD/.cache/clang"
export SWIFTPM_MODULECACHE_OVERRIDE="$PWD/.cache/swift"
swift test --cache-path "$PWD/.cache/spm" --scratch-path "$PWD/.build" --jobs 4
xcodebuild -project CJIOSSpike.xcodeproj -scheme CJIOSSpike -destination 'generic/platform=iOS Simulator' -derivedDataPath DerivedData -clonedSourcePackagesDirPath .cache/xcode-packages -skipPackagePluginValidation CODE_SIGNING_ALLOWED=NO build
```

`Package.resolved` pins the entire resolution. Xcode also keeps its own resolution in the project workspace. Check both before changing dependencies. No global install or shared build directory is required.

Rendering: switch Textual/plain native text; long mixed Chinese/English, lists, links, selection, partial updates, pause, keyboard, large text and four Tabs. Dragging stops automatic following; Follow latest restores it. The growing reply has stable identity and appends each character range once. This is synthetic delivery, not an actual service stream.

All external links are intercepted with a local notice. Image and emoji loaders override Textual's **network-fetching default**, returning local placeholders for every URL. No WebView, script engine, URL preview or media fetch is installed. Native comparison deliberately shows raw Markdown; it is a baseline, not a feature-equivalent Markdown replacement.

Generated-client SSE tests use an in-memory `ClientTransport`: completion, truncated/empty stream, body transport failure and cancellation. Fixed C0 consumer tests cover formal JSON success, structured unknown/conflict, missing header/body, malformed JSON and unknown enum. Official URLSession transport and Auth sign-in method are compiled; **real URLSession networking/Auth login are UNRUN**. `[DONE]` is a disposable probe marker only, not a proposed RUN protocol. Product integration must consume formal C0/RUN errors, terminal states and recovery semantics.

See `evidence/REPORT.md` for actual outcomes, versions, device identity, limitations and remaining acceptance.

The native baseline is `CJNativeProbe.xcodeproj` / scheme `CJNativeProbe`, deployment target iOS 17. Build with its own `DerivedDataNative`. It compiles the same `ProbeView.swift` directly with `canImport(Textual) == false`; it has no third-party package dependency and is not an Auth/transport compatibility proof on iOS 17.

Local launch flags: `--large-type` requests accessibility3, `--stream` starts synthetic insertion, `--keyboard` requests focus after mounting, `--plain` selects raw native text on the Textual build. These are sample harness modes, not product configuration or interaction PASS. The default respects the system Dynamic Type size.

Reproduce formal C0 consumer validation after the package has built its generator:

```sh
python3 scripts/prepare-c0.py /absolute/path/to/cj-005-foundation
swift test --package-path .cache/c0-consumer --cache-path "$PWD/.cache/spm" --jobs 4
```

The script always reads C0 commit `db9c040f262032acaf5375db43d7169b3217e504`, verifies the runtime checkout matches this spike's committed lock, and uses the C0 consumer's committed transitive lock. It never writes the upstream repository.

Local fixture lifecycle: leaving Assistant stops and retains the partial text. Explicit Start clears it and starts a fresh generation; an old cancelled task cannot mutate the new one. See `evidence/resume/P2-LIFECYCLE.md` for the dynamic Tab-switch regression.
