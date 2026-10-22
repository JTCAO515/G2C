# Narrow preview ordinary-Host P2 repair (c5-compatible)

Independent worktree cj-009-preview-host-fix, branch cj/009-preview-host-fix,
exact parent **f4c17b59213828543cef042d127c56d8467963d8**, using official c5 export.
Original shared branch remains clean at5d85408c641a50d922cc4bddef7148a449f05381;
USAGE export and all original commits preserved, no reset/rebase or required SDK upgrade.

Input: Testing CJ-009-readonly-preview-transport/REPORT.md, its snapshot's exact
IndependentPreviewHostTests.swift and independent-host-tests.log. Copied probe is
byte-identical (SHA in preview-host-provenance.json). Reproduced original1 method/2
failed assertions in preview-host-before.txt. This proves conflicting ordinary Host
metadata reached an injected transport; it does NOT prove DNS/socket/virtual-host traffic.

Product change is one additional structural guard in NoRedirectTransport's exact
manual-preview POST branch: reject any header whose canonicalName is host. All casing,
duplicate/mixed values and even matching same-origin Host are rejected before body
collection, validation callback or underlying transport. Configured baseURL is the sole
routing authority. Existing pseudo scheme/authority nil, exact op/path, media/body/origin,
byte limits, three callbacks, cancellation, ephemeral session/timeouts/redirect rejection
remain. No body/header rewrite or broad POST permission introduced; default true writes
stay closed. Existing generic GET/HEAD behavior is not altered by this narrow correction.

PASS:11 tests on Swift6.4/macOS, preview-host-after.txt: exact original probe now passes;
new Host value/case/duplicate rejection cases; all6 original readonly-capability cases;
2 original default Message POST and draft PUT prohibition regressions. Actual generated
preview operation still passes its non-network interceptor and raw-body/callback checks.
No genuine URLSession request, DNS, socket, account, Keychain, PG or business service.
Independent Review/Testing must verify this fixed delta; P2 is not self-closed.

## Precise extraction / compatibility

Production path: ios/Modules/CJMessageClient/Sources/CJMessageHTTP/Transport.swift.
Pre-fix SHA256 (byte-identical in f4 and5d):
`6df582bee7c9575839b21ec82d54f8f0de8773c6672f3ace47d8a811fef81ca9`.
Exact post-fix SHA256 and one-file patch SHA in preview-host-provenance.json;
preview-host-runtime.patch contains ONLY the runtime hunk. Whole commit adds tests and
module evidence, never Package/SDK/export/lock changes. `git apply --check` of this runtime
patch against original5d tree PASS without applying/mutating it. Consumers can retain c5;
no9d export is needed. Apply only to matching fixed source or independently assess later
diffs, not blindly to arbitrary main.

The standalone c5 dependency was prepared in this NEW worktree; original shared c5 export
was not replaced or implicitly regenerated on its5d branch. Automatic lock resolution
change and full raw build logs retained in ignored .build/preview-host-fix-raw, tracked
source lock restored. Existing source/Package/export hashes unchanged. Current App graph,
other owners, signatures and existing69d/b868 HOLD are untouched. No push/PR/deployment.
