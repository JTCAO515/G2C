# CLEANUP-HOST-WORKER@1 — local original-operation recovery

This is a trusted host runner, separate from the frozen App HTTP APIs. Only the
explicit local/private PG and synthetic local invitation source are supported.
It neither provisions a key/account nor enables an external service.

Run `scripts/cleanup_worker.py` with `CJ_ENV=local`, the usual backend Python path,
explicit `--conninfo-json`, `--auth-dir`, `--cleanup-config` and retained
`--run-context` when metering is present. Configuration is the same
`CJ-LOCAL-CLEANUP@1` used by the HTTP host. No ambient PG credential is accepted
by LocalDatabase. `--once` runs a single pass; the default process repeats every
60 seconds (`--interval 1..3600`). Deployment/scheduling outside this explicit
local process is not activated by adding this file.

For each current signed local invited principal:

- If its irreversible account fence exists, reopen only that original operation.
  Recheck original task ownership and all owner usage periods **before any domain
  erasure**, including after a device report or process restart. A live worker or
  unresolved usage outcome persists an `unknown` reason on the original operation.
  No provider cancellation, financial settlement or erasure receipt is invented.
- Otherwise, run the original daily diagnostic operation. Freeze a UTC-day cutoff
  at least 90 days old. The exclusive boundary retains data exactly at cutoff.
  Repeating a day uses the same original ID/bytes; a restarted committed intent
  only reconciles its actual original result. An unresolved earlier day prevents
  new overlapping maintenance work. A backwards clock never advances the cutoff.
- Both operations use only `cj_local_cleanup`. Runtime gains no DELETE, TRUNCATE,
  elevated role or diagnostic update grant. Only diagnostic timing is cleared;
  retained answers/messages/events and usage/accounting evidence are not logs.

`Gateway.resume` is the host entry for account recovery. It accepts only a trusted
host-bound subject digest and its active original operation ID. It is not exposed
through App progress credentials or an HTTP resume route. Root progress GET remains
observational and reports the persisted task/usage reason together with the locked
progress revision. Device `confirmed` is an authenticated current-device report,
never proof about other devices or backups.

Executable examples: `account_inflight_pg.py` holds the actual original worker in
a FakeProvider while confirming, querying, reporting a device result and resuming;
it verifies no RUN/message/accounting erasure and no late publication.
`account_retention_pg.py` exercises injected cutoff clocks and real restricted-PG
maintenance. All real account/provider/cloud/backup/device validation remains in
#32/#29/#30 as applicable.
