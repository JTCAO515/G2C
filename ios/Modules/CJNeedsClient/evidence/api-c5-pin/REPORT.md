# NEEDS c5 host-graph compatibility pin

Starting branch/head verified clean: `cj/013-needs-client`,
`25e50dbc25cc5aa9443b2d6da50c514528b2b3c6`. Requested6.1 Sol Medium/default;
effective model UNKNOWN. This is Main-authorized removal of the preview host's
actual c02/c5 SDK conflict, not a new business feature or permission.

Fixed shared input: `f4c17b59213828543cef042d127c56d8467963d8` (parent3090777),
exactly that Git tree; no later5d/9d input consumed. Official SDK identity is
`c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a`.

Preparation imports12 fixed CJMessageClient files unchanged; its full commit is
`prep_commit` in provenance.json and this pure-pin commit's parent. The prep remains
original CJ009 authorship and is excluded from the product diff. Original source
worktrees were read-only. It includes the owner's transport changes and their
historical evidence, not NEEDS-authored transport modifications or new acceptance.

**Authored diff:** one Package.swift dependency path c02→c5 plus this evidence
directory only. Sources, Tests and locks are unchanged. Active SDK path:
`../CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation`.

- PASS: one physical CJFoundation at c5 in the actual resolved package graph;
  package-graph.json. CJ006 owns full host/App graph acceptance, UNRUN here.
- PASS: all22 c02 paths and81 schemas remain identical parsed JSON definitions
  in fixed c5. SDK manifest/lock/date helper are byte-identical. All four existing
  official exports (d688,201156,c02,c5),16 files each, match exact source bytes.
- PASS: all15 NEEDS Sources/Tests/lock files match25e50 byte for byte. Imported
  shared subtree exactly matches f4c17. Hashes and pins in provenance.json.
- PASS: six existing targeted test functions / ten expanded cases, compatibility.txt:
  four-state/absence and invalid observation codec, actual generated alias detail
  and historical revision reads, four NEEDS operations with exact original bytes,
  and public construction refusing writes before credentials/storage/dispatch.
  No Sources or Tests were changed. No unrelated full suite rerun.
- PASS: unsigned generic iOS Simulator SDK build with fixed resolved versions and
  package updating disabled; command/hash/archive in ios-log.json.
- PASS: scoped diff whitespace check.

The initial SwiftPM invocation automatically refreshed dependency repositories,
and the initial Xcode build attempted automatic package updates. The latter was
stopped; its raw output is preserved losslessly as ios-initial-package-refresh.txt.xz.
Final Xcode compilation disables those updates. No locks changed. These package
manager operations are recorded separately from product HTTP; no business service,
credentials, Keychain, database or device request ran.

Prior accepted business evidence and both repairs are reused, not regraded by this
pin. Default NEEDS POST remains closed; existing HOLD/independent business gates
are unchanged. Full App, real account, Keychain, SQL, model, UI/device, CI, deployment
and Issue14 integrated acceptance remain UNRUN here. No push/PR/merge/Issue close
or new thread. Main should route this fixed pure-pin diff through original dual
review, and CJ006 should consume it in the unified c5 host graph.
