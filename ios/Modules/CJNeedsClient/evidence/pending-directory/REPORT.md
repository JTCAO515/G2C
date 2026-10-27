# Pending directory final fence — author repair

Base `cd33fd09ad4854f676e0dd70a11419960fbb6497`; candidate is the commit containing
this report. This business repair retains the d688 shared SDK pin and the cd33
legal-timezone repair. Only CJNeedsClient source/tests/evidence are changed.

Review source: `<local>/Documents/Codex/2026-10-21/cj-review/CJ013-client-8c28bcb/`
`review-summary.json`, `ClientCheck.swift` empty-pending case and
`independent-client.log`. Original review artifacts/probes remain untouched.

`before.txt` reproduces both empty-list variants against unchanged cd33 code:
after the read, binding callback 2 or the final callback 3 replaces the canonical
empty directory with a same-owner/key directory containing a valid original.
Old UI publishes loaded/0 while reopening the canonical path reads that original.
Two nonempty controls and unchanged-empty control pass already. Two real failed
assertions are retained; no setup/compiler failure is reported as reproduction.

The fix adds an unconditional callback-free `store.validateDirectory()` immediately
before returning pending records, after the last binding callback and any original
ciphertext checks. Empty and nonempty results now both validate the canonical
directory. Existing per-record durability validation is unchanged. Changed storage
throws and becomes explicit pending failure; no directory restoration, deletion,
new key, empty-success fallback or new POST permission exists.

PASS: `after.txt`, 2 test functions / 5 expanded cases. Four replacement cases now
report failed; unchanged empty storage still reports loaded/0. Fresh stores read
one exact original from the replacement directory. Ciphertext is unchanged, and
the retired original directory retains its original 0/1 records. Credentials and
network are not used. All before/after replacement directories and ciphertext are
retained; paths and hashes are in `manifest.json`. Nothing was automatically restored
or cleaned. These are synthetic probes, not hostile same-UID race/backup guarantees.

PASS: unsigned generic iOS Simulator SDK compile, exact full output archived
losslessly in `ios-full.txt.xz`, uncompressed hash in `manifest.json`. Command:
`xcodebuild -scheme CJNeedsClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios CODE_SIGNING_ALLOWED=NO build`.

REUSED: original POST→exact revision, 409 and reopen positives, 36/51 original
checks and cd33 5/11 timezone checks. No unrelated full suite/PG rerun. No producer,
wire, key provider, shell, Package or POST policy changes in this business repair.
Independent dual gates remain PENDING; no push/PR/merge/Issue close. Actual UI,
account, Keychain, product network, device/model, SQL and deployment remain UNRUN.
The separately requested 201156 pin follows this fixed business commit and cannot
substitute for its independent P2 gate.
