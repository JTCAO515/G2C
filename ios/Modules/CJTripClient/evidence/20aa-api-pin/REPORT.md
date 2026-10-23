# MEMORY lifecycle20aa SDK pin — subsequent candidate compatibility

Base/parent: `a5cc42005c69811ccb05754793107141fb4a9f02` (fixed f87 consumer).
Head is the commit containing this report. Changes are only CJTripClient's single
SDK path and this pin/preparation evidence folder. Sources, Tests, accepted-source
hook, consumer lock, factories, real send/save/cache/delete gates are unchanged.
Old FAIL records, f87 fixed head and its evidence are retained without amendment.
The new head is a subsequent20aa candidate, not replacement input for Main's0d1e
f87 release gate.

Exact shared input: cj-009-memory-api-pin
`cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71`.
Official decoder/export identity:
`20aa50ed5c8449e6026155a6151f22041dee7fd4` from cj-005-foundation.
Candidate path:

`../CJMessageClient/.generated/20aa50ed5c8449e6026155a6151f22041dee7fd4/CJFoundation`

## Fixed ignored preparation

The original clone's sibling remains33 and lacks20aa; peer/shared tracked paths
were not changed and no predictably failing original-tree build was attempted.
`prepare_validation.py` reuses the accepted fixed-Git-input preparation pattern
only in this module's ignored `.build/20aa-pin-validation/assembly/`. It copies
base a5 Trip/Auth files, the exact cc9 shared module and the one-path candidate
manifest. The original owner's unmodified export script produces16 exact official
20aa files. SHA, conflicts and symlinks are checked before writes; no handwritten
SDK, second type alias, replacement module or wire implementation is created.

The old `.build/f87-pin-validation/assembly/` remains separate. Its fixed consumer
manifest, Trip/Auth/shared source inputs and16 SDK files were rechecked against
its prior preparation hashes. No moving20aa file was written over those inputs.
Preparation file inventories and candidate hash are in `preparation.json`;
`provenance.json` verifies both new composition and old f87 retention.

## Actual verification

- PASS: old f87's26 paths,93 schemas,93 generated declarations and84 SDK blocks
  (28 operations across Client/Operations/convenience APIs) remain exact. SDK
  manifest/lock/date helper and Transport94 bytes are unchanged.
- PASS (fixed-input20aa composition):4 existing snapshot/getTrip codec functions
  including parameter cases for null/fallback and invalid records; exact received
  bytes, same typed record/trace/binding and closed-source behavior are retained.
- PASS (fixed-input20aa composition): unchanged public new/legacy consumer compiles;
  external snapshot/request construction still fails as expected. No probe source
  or business test was edited.
- PASS (fixed-input20aa composition): actual graph has one CJFoundation identity/path,
 20aa; unsigned generic iOS Simulator compilation passes. No launch/signing.
- PASS: actual Trip Sources/Tests/lock match a5; original sibling tracked files
  match a5. Prior f87 preparation/source/SDK is preserved. Declared accepted formal
  source identity remains the existing c02 value; no caller authority is added.
- UNRUN: original-tree graph still needs exact cc9 shared dependency/export in its
  original sibling position. Final20aa App graph remains CJ006/Main's composition,
  separate from the f87 publication. These isolated PASS results are not App/I proof.

Original current-guard/business/Transport94 evidence is reused; no full-suite,
PG, Keychain, device, actual network, real send/save/cache/delete or lifecycle action
was performed. Existing compiler warnings are retained in log excerpts; generated
source was not edited to suppress warnings. No factory/permission activation,
new product feature, live account/provider, CI, push/PR/merge/App edit/deployment or
Issue closure is claimed. New pin independent gates remain with original Review/
Testing. The cohost82f/PR109 status is supplied by Main, not retested by this pin.

Reproduce fixed-input preparation/checks:

```sh
python3 ios/Modules/CJTripClient/evidence/20aa-api-pin/prepare_validation.py \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation
swift package --package-path ios/Modules/CJTripClient/.build/20aa-pin-validation/assembly/ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-20aa-isolated-build --skip-update --force-resolved-versions \
  show-dependencies --format json > /tmp/cj015-20aa-isolated-graph.json
# Wait for successful completion, then:
python3 ios/Modules/CJTripClient/evidence/20aa-api-pin/check_pin.py \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation \
  /tmp/cj015-20aa-isolated-graph.json \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin
```

Requested Sol6.1/medium/standard/default; effective model/tier not independently verified.
