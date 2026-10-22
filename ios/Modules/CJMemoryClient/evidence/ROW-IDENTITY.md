# Exact UTF-8 SwiftUI row identity repair

Parent: `ad1ddebf28dfc9480d954f9a3ce10acc00bf5604`.
Original Review/Testing found the same residual P2: accepted NFD and NFC opaque
item IDs were distinct on the wire but canonically equivalent as Swift String
ForEach identities. This report is author regression evidence, not independent
acceptance or rendered-device observation.

The only product change is in MemoryViews.swift: internal `memoryRowIdentity`
returns `Data(command.item_id.utf8)`, and MemoryItemsView's ForEach uses that exact
key path. No service ID is altered or normalized. Selection/detail still receives
`item.command.item_id` unchanged. No wire, host/container or dependencies changed.

Testing's original IndependentOpaqueViewIdentityTests probe was copied unchanged
and run on the parent: **1 FAIL**, two accepted rows but only one String identity
([before](row-identity-before.txt)). The regression now exercises the actual new
ForEach key path, requires two unique identities, verifies original UTF-8 IDs,
and confirms identity stability when rows reorder: **1 PASS**
([after](row-identity-after.txt)). Exact changed inputs:
[row-identity-sha256.json](row-identity-sha256.json).

Unsigned generic iOS Simulator SDK package compile: **PASS**
([build](row-identity-ios.txt)); full local log `/tmp/cj011-row-identity-ios.log`.
Diff whitespace/scope check: PASS. Existing ad1ddeb 29-test and four-family repair
results are reused; unrelated suites were not rerun for this view-only change.

Live POST remains disabled. No App launch, actual UI/VoiceOver rendering, network,
account, Keychain, model context, push/merge or Issue closure occurred. Await the
original Review/Testing's fixed-head gate; full App/Issue12 gates remain separate.
