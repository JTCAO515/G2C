# CJ-005 initialization plan / registry local evidence

2026-10-22 Asia/Shanghai. Source base
`015df137cfdca8e00116c8a1a751f102da909f7b`; final candidate is the commit
containing this report. Fixed accepted input tree
`3c52f72daf1d8e2304c0c569b47e68d92a4b323e`, checked against remote main at
lookup time and fetched from the local Publish clone. No push/merge/deploy.
No 015df history/HTTP/Swift test rerun. Brand paths scripts/build-ios.sh and
ios/App/Info.plist untouched and released to Main's separate brand owner.

PASS: four targeted unittest groups: fixed-source/manifests; hash/dependency/
duplicate/apply-enabled plan rejection; empty vs initialized/nonempty catalog
classification; missing config and unavailable apply CLI option rejection.
Dry-run verifies all four artifacts against immutable Git blobs, not fixtures.
This validates the listed source dependencies only; does not certify apply order.

PASS: final checker on fresh private PostgreSQL16.15, directory
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation/.local-cj005-init-pg3`.
Bootstrap role cj005i/database postgres; parent/socket0700, auth-local trust in
this private directory only, auth-host reject, listen_addresses='', Unix socket
identifier55447. Explicit identity and transaction_read_only=on observed by
checker; search_path fixed pg_catalog, no inherited connection settings.
Empty target admitted. Existing registered foundation v1 then applied only as
synthetic test seed; second check rejected initialized/nonempty target with
exit2. No MESSAGE/RUN/USAGE candidate apply. Finally stopped exact owned server;
postmaster.pid and .s.PGSQL.55447 absent. Data/logs retained, clone-local excluded.
No background process, TCP/HTTP service, real user records or secrets introduced.

Earlier first fresh `.local-cj005-init-pg` initdb attempt failed before server
start under sandbox; stderr was not retained, so exact cause UNKNOWN, not called
successful. No reuse/deletion. Escalated fresh `.local-cj005-init-pg2` test passed
before final pg_catalog tightening; final pg3 verification above supersedes it.
Both successful test instances stopped; no old .local-cj005-pg or history PG
instance started or read. No package install/driver copy required (psql used).

Registry v1.1.0: MESSAGE five tables, RUN three tables, USAGE one table; encrypted
message snapshot, session Keychain and scoped message-key Keychain registered
from fixed accepted sources. Existing session clearAndBlock and exact reconciled
key removal are recorded; invalidate is not physical deletion. No domain/file
physical-delete API invented. Retention UNDECIDED, restore fence UNIMPLEMENTED,
production not provisioned/activation blocked. Device execution UNRUN.

Composite initialization/apply BLOCKED, not local-ready completion: candidate
migration registration/rollback, namespace/provisioning, product roles/RLS/grants,
and runtime cross-domain association/fences still need owner acceptance. This
slice does not modify SQL/RLS/grants, accepted architecture or domain code.
Independent Review/Testing, actual composite apply, cloud/real-service/device and
production acceptance are UNRUN for this candidate.
