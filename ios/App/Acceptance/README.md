# Shell structure acceptance (#157)

Run on an available iOS 17.5 simulator with Xcode's native XCTest input:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
python3 -B ios/App/Acceptance/check_shell_structure.py \
  --simulator '<iOS-17.5-UDID>' --output '<new-directory-outside-repository>'
```

The script first tests the ordinary App entry and actual CJShell, then builds a
separate, visibly labelled synthetic host using the same ShellView and public
readonly MemoryClient. Both run in the isolated `space.go2china.shell.acceptance`
bundle, preserving the development App's data and keys. The synthetic server
binds only loopback, returns empty/failing memory reads, audits requests, and
rejects writes. It supplies no real account, token, cloud data or model access.

The four XCTest methods cover:

- Four tabs and their order in both languages; ordinary App language navigation,
  typed draft preservation and persisted language after relaunch.
- Account, language, help and privacy entry reachability with unconfigured,
  empty and failed memory views in both languages; account stays unverified.
- Language changes preserve synthetic business references, draft revision and
  navigation, with no extra memory requests or writes.
- Plugins show the existing unavailable description, expose no pretend tool
  buttons, make no extra requests, and show no system permission prompt.

The generated Xcode projects, results, logs and screenshots remain in the output
directory. A PASS requires both variants, all four tests, and zero failed or
skipped tests in the native result summaries. Prior output directories cannot be
overwritten. Screenshot attachments are retained inside each `.xcresult`.

`ShellFixtureApp.swift` and `ShellStructureUITests.swift` are referenced only by
these external test projects. They are absent from the repository App target and
excluded from the macOS development-configuration package. The ordinary App,
Release behavior, CJAuth and production write gates are unchanged.

This verifies UI structure and local fixture behavior. It does not approve help,
privacy or support wording (#159), prove real authentication/storage, or replace
VoiceOver/device and other state acceptance (#158 and L2/L3).
