# Independent post-repair 201156 pin — author evidence

Business repair remains fixed at `5ef0d75acf7c41f400fac833ed5fa654872b82e6`, on top
of timezone repair `cd33fd09ad4854f676e0dd70a11419960fbb6497`. Both P2 independent
gates remain separate and PENDING; this dependency pin cannot waive either gate.

Preparation commit `e3f31bf1ad1d89d619718b4a9486d4fa0c2c9332` imports the exact
CJMessageClient subtree of `514e0e3a80bd9a3e34248122915d52c86ee46230`: 8 unchanged
owner-authored files, original evidence attributed to that owner. The producer
worktree was not modified. This is preparation only, not new NEEDS authorship.

The current commit's authored diff is **only CJNeedsClient/Package.swift and this
evidence directory**. One manifest path changes from the shared d688 export to:
`../CJMessageClient/.generated/201156c9bf9850f9b8e87dc1f986452ce1ae789f/CJFoundation`.
No Sources, Tests, Package.resolved, other consumers or root configuration changed.
The original README/dependency reports document the earlier d688 candidate; the
current Package.swift and this post-repair report identify the active pin.

Preparation uses the existing fixed owner's export script in this isolated clone,
reading exact API Git input `201156c9bf9850f9b8e87dc1f986452ce1ae789f` from
cj-005-foundation. No second physical SDK or handwritten generated code is added.
The earlier d688 exported directory is retained unchanged; only 201156 appears
in the actual resolved graph.

## Checks

- PASS: actual local package suite **43 functions / 67 expanded cases**, 10 suites,
  `tests.txt`. This rechecks the affected module against the changed SDK dependency,
  including original-action recovery, CAS, both P2 repairs and POST-disabled policy.
- PASS: unsigned generic iOS Simulator SDK build. Full output retained losslessly
  in `ios-full.txt.xz`; command, original size/hash in `ios-log.json`.
- PASS: graph has exactly one CJFoundation physical path, the shared 201156 path;
  `package-graph.json` and `provenance.json`. Full CJShell/App graph is UNRUN.
- PASS: all 19 previous API paths and 73 previous schemas are byte-semantically
  identical as parsed JSON objects across fixed d688→201156 inputs. Each export's
  16 official files matches its fixed source bytes and its canonical manifest.
- PASS: imported CJMessageClient subtree equals514e; all 15 NEEDS source/test/lock
  files are byte-identical to business repair5ef. Own lock and other locks unchanged.
- PASS: scoped diff whitespace check. No new business logic, backend/wire/key or
  permissions change. POST is still closed, not activated by a richer generated SDK.

Before/after P2 failures and preserved synthetic directories remain in the original
repair evidence; this pin does not rewrite them. Actual UI/device, real host account,
Keychain, product HTTP, SQL/PG, model/source extraction, CI and deployment are UNRUN.
No push/PR/merge/Issue closure. Main must route business repair and pure-pin diffs
independently to the existing Review/Testing/unique Publish roles. Publish should
consume the final pure-pin commit only with the canonical514e import available,
not silently publish this local preparation commit as NEEDS product code.
