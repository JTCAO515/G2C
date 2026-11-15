# Internal build updates (#1019)

The single content source is `ios/Modules/CJShell/Sources/CJLioUser/Resources/LioBuildUpdates.v1.json`. It contains the current build and its immediate predecessor, with the same five sections in English and Chinese. The current build, predecessor and section text are not fetched from a service. The release exporter reads this exact file; there is no second changelog copy to maintain.

`LioBuildUpdates` validates the packaged configuration at its decoding boundary. An installed build without an exact matching entry displays that build number and an explicit unavailable message, rather than substituting another build's notes. Previous entries do not grow into an archive.

`LioDemoNoticePage` owns the shared page content. The invitation sheet supplies its original agreement and back buttons, retaining the original wording, disable conditions and `agree(to:)` implementation. Those actions precede the update section, so release notes do not become an extra agreement requirement.

Signed-in users open the same page through **Internal demo information / 内部演示说明** in the existing Lio menu, below appearance. This is the smallest new route because the signed-in menu had no existing information route. Its close action only dismisses the sheet. There is no automatic upgrade popup, remembered-seen flag, account-page entry, authentication call or new network request.

The title uses the existing native readable-text measurement with the title2 serif design and dynamic type. UIKit retains its preferred font where a requested family has no serif design; this does not cap text sizes or replace content. Test audits remain unfiltered `.all`. Long release notes reuse the native selectable text reader in stable sections with individually identified rows, retaining the entire content and native text sizing as the reader scrolls. No accessibility issue type or offscreen element is manually filtered.

## Publication

Before a release, update the two entries to the exact current and previous build, and list only changes that will be merged into the archived source. Keep planning marked unavailable for acceptance until L's complete live basic eight and JT's subsequent acceptance decision. Describe independent service work separately and state whether an app update is needed.

```sh
python3 scripts/export_lio_build_updates.py --build 44 --language zh
python3 scripts/export_lio_build_updates.py --build 44 --language en
python3 scripts/export_lio_build_updates.py --build 44 --source-commit <exact-public-main-commit> --output <outside-repository-file>
```

Use the exported text for TestFlight What to Test and the corresponding #702 build notice. App bundle metadata supplies the displayed installed build. The temporary native test project sets its actual bundle build to the candidate build; it does not substitute a fake label in the view. Build products, logs and recordings stay outside the repository.
