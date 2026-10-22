# Actual-main brand combination: author validation PASS

Inputs: main 3c52f72daf1d8e2304c0c569b47e68d92a4b323e + brand 17cf5f977cdb4086ac02a2f42dc9cb57300c2a3b (already based on that main) + exact full dependency delta 3c6de6af2f30c91dee45021893a3bb36703e146e. Combined Git tree: 180f6ec312d9e994a5d54d42a070fc5b30c69f27. All seven dependency delta files were compared byte-for-byte to fixed 3c6de6af. Staged tree exists only in the detached .local/main-brand-validation worktree; no dependency product change is committed to the brand branch.

6773cb9 is excluded. Main's CJAuth Package.swift, ServerHistoryHost.swift and ServerHistoryView.swift were compared to 3c52f72, and runtime shows main's Server history (read-only) label. Brand does not depend on the unaccepted draft/cancel UI. The earlier duplicate-target failure remains historical evidence; this canonical combination resolves it.

## Executed

- Unchanged prepare_generated.py exports canonical 2f8be7c3e2dd298457488412b3a5e3b2ca59ca93 source; no key-interface export is needed by the fixed graph.
- Existing CJShell build-demo.sh executed on the isolated combination, fresh output .local/MainBrandShell and local ShellCache. Full compilation/link/package PASS. Original signing command and bundle identity local.cj006.shell.demo retained.
- Actual package: SwiftPM bundle's BrandAvatar.png and all six AppIcon PNGs equal the brand derivatives byte-for-byte. Executable SHA256 and plist icon declaration recorded in main-brand-package.json.
- Installed this newly built App onto the authorized C52D892F-B5EC-4414-97C4-ED34829DCD7A / iOS 26.5 device, normal launch with no demo/session/service configuration. Main-brand-avatar.jpg visibly shows PR37 Agent art; AX snapshot screenHash 09oq3pp retains Assistant and original controls. Main-brand-desktop.jpg shows its PR37 system icon beside the earlier Foundation App.
- Simulator shutdown succeeded after capture; device/data preserved. No other device touched; no real Auth, Keychain or application service/network operation. Build tool resolves pinned public dependencies, separate from runtime service access.

Foundation build/package/display evidence from 0275472 is reused: the canonical dependency delta affects CJMessageClient, which Foundation's root Swift package does not consume. Foundation project, sources, resource files and script are unchanged; this screenshot's Foundation installation is the previously validated artifact, not a new Foundation build claim.

Evidence files: main-brand-combination.json, main-brand-build.txt (trailing whitespace normalized only), main-brand-package.json, main-brand-runtime.json, main-brand-avatar.jpg, main-brand-desktop.jpg. The evidence-only commit does not change 17cf5f9 product files. Independent acceptance and Publish integration remain pending; no push/PR/merge/store. Prior keyboard compact-state UNKNOWN and VoiceOver/large-text UNRUN remain unchanged, outside this requested normal-avatar/system-icon check.
