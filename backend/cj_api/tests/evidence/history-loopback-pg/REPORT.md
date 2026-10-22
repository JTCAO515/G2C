# CJ005 history/draft + AEAD real loopback/PG combination

Product source base `ad03cddd4438c477d59ac4e65f2dd5aa847ab4a8`; MESSAGE e4ca761bf1bb4f60a5d02be102fe0d5f721e478b / AUTHf3c8e507 fixed eight-blob manifest. Main reported API/context merged PR55 and adapter independent PASS, authorizing this combination. Final test-only candidate is the commit containing this report; exact head reported after commit. Product source/schema/generated/pin/locks/domain/migrations unchanged. Requested default6.1-sol/medium; effective UNKNOWN.

## New resources and offline dependency attribution

Fresh previously nonexistent task directory `/Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation/.local-cj005-history-pg`; no old database directory reused. PostgreSQL16.15, explicit local bootstrap role cj005h/database postgres, private parent/socket0700, Unix socket directory `.../.local-cj005-history-pg/s`, identifier55446, `listen_addresses=''`; actual socket path99 bytes. HTTP only prebound numeric loopback `http://127.0.0.1:52257` via port0 OS allocation, no DNS/default proxy/redirect path.

Root driver was absent and external network forbidden. Before executing, Main explicitly approved only read-only copying the already fixed psycopg3.2.10 code/distribution metadata from this owner's old driver dependency. Source whitelist is exactly `psycopg` + `psycopg-3.2.10.dist-info`; symlinks/out-of-source paths excluded, files individually hashed and verified after copy into the new private driver directory. `offline-driver.json` records source/version/aggregate hash/count; full source/copy manifest is retained privately. No old data/socket/pgpass/config/log copied/read, no old instance touched, no online installer or global dependency change. Runtime asserts imported driver file is inside the NEW task directory, version3.2.10/pure Python. Empty new pgpass + explicit Unix host/user/db/options; inherited PG*/DATABASE_URL/CJ_DATABASE_URL refused.

Only exact candidate SQL was applied after verifying actual data_directory/listen/socket/user and empty public tables. SQL SHA256 `4060541a06fdd1233b787b212917ecd69728aa272f2e9ce46b34d48d44b1107b`, new-empty-db-only. This is not a deployed migration/upgrade. No SQLite or transaction-engine double in the tested storage path.

## Actual result — nine groups, final group has four consumer assertions

`run.txt` / `result.json`: all PASS, no runtime failure in this slice.

1. Real private PostgreSQL first connection and verified empty-schema candidate application.
2. Real HTTP→actual PyJWT strict/gate→bound context→PG list pagination, authenticated-encrypted cursor and required explicit next_cursor null at end.
3. Altered ciphertext, valid synthetic B identity/another server scope, and explicit synthetic-clock expiry all409/resync without private list/body. Clock100 advanced to130 for expiry, reset100 for separate scenarios; no production clock claim.
4. Real private message-history pagination preserves exact original UTF8 JSON bytes and SHA256; second page ends with explicit null. Two normal receive calls only seed required history, not a PR49 duplicate/core test rerun.
5. Draft read required-null, empty saved bytes/revision1, exact decomposed-Unicode UTF8/revision2, stale CAS409; no message/run/delivery created by draft operations.
6. Actual PG draft COMMIT succeeds then wrapper injects one lost-ACK exception. API503 unknown/reconcile_original; a new original draft query returns current revision3 and exact bytes. We know commit occurred because of the controlled injection point, **not because equal content proves a submitter**. No blind write retry or action-journal claim.
7. Synthetic precommit invitation withdrawal causes actual PG rollback; current draft stays revision3. API conservatively remains unknown/reconcile_original, no fake successful rollback receipt.
8. Final callback authority withdrawal (sixth facts check) after real read/AEAD encoding/response materialization produces503 and withholds private list/cursor. Facts are explicitly synthetic, not real authorization-store/revocation atomicity proof.
9. Actual official-generated Swift CJAPI+URLSession over the same real HTTP/PG: list AEAD pages/required-null, private history exact bytes/cursor, draft null/object/CAS/exact bytes, and missing-key safety. `generated-client.txt`: four assertion groups. SQL independently verifies final revision4/exact Swift bytes; two receipt/delivery rows and run_count2 remain unchanged by all drafts.

For missing next_cursor/draft, a harness-only middleware first runs the genuine API/current-context/PG query and captures its successful fully checked response, then deliberately removes the required field and fixes Content-Length. Generated consumer requires HTTP200 plus actual ClientError underlying keyNotFound(exact field). This is a test response mutation, not a naturally malformed backend, alternate wire model or product test header. Null is accepted only as actual nil; absence never silently becomes null.

RSA/AES keys only generated/held in Python memory; no real issuer/account/key/JWKS used. Member/email/invitation facts and two subject→scope mappings are explicitly synthetic. JWT/controls/original bytes reach Swift only via stdin, never args/files/logs; client uses ephemeral session/direct loopback/no redirects. Safe stdout only, stderr deliberately not persisted due potential ClientError input retention. Harness failure handling records type only, never token/body/error interpolation.

## Stop, preservation and reproduction

HTTP worker joined and own socket closed; `pg_ctl -D <new data> -m fast -w stop` succeeded. `pg-stop.txt` and independent `preservation.txt` verify no own HTTP acceptance, no task postmaster.pid/socket, data retained. Old stopped PG resources unchanged. Full new init/server/driver manifest/data/candidate SQL logs remain under private directory; hashes.json binds tested source/client binary/raw-log bytes. New data is excluded only by clone-local git info rule; root .gitignore untouched.

Fresh authorized checkout only (short enough Unix socket path), using approved offline library source:

```sh
./scripts/run-history-loopback-pg.sh AUTH_GIT_REPOSITORY MESSAGE_GIT_REPOSITORY APPROVED_OFFLINE_DRIVER_DIR
```

Entry refuses existing `.local-cj005-history-pg` before build/start/copy; refusal exit2 preserved in reuse-refusal.txt. No delete/reuse/restart to rerun evidence. Syntax/scope/hash/stop checks only after success; no repeated9+4 or unrelated PR49 tests. result source_head is the tested product ad03; new harness source hashes are fixed by this candidate. Independent Review/Testing pending.

Limits: numeric plain HTTP/local PG/bootstrap trust+superuser only. No production Auth/RLS/grants/member/session source, concurrent atomic revocation/cleanup, actual wire packet loss, key lifecycle/volume/real clock, schema migration/restore, real provider/model, device/HTTPS or deployment proof. No external network, old DSN/account/data, persistent key, host service/security/permission config, push/merge/deploy or Issue closure. C2/full acceptance remains UNRUN.
