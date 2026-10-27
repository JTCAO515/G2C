# CJ005 real loopback HTTP → AUTH/MESSAGE → isolated PostgreSQL

Product source base `312a69caf0bd97ed65679cfd8ff049972c212cef`; final test-only candidate is the commit containing this report, exact head reported after commit. Original branch/clone. Product API/domain/generated source and root dependencies remain unchanged; only `backend/cj_api/tests/**` and `scripts/**` added. Requested default gpt-6.1-sol/medium; effective UNKNOWN.

## Exact environment and first connection

New previously nonexistent `<local>/Documents/Codex/2026-10-21/cj-005-foundation/.local-cj005-pg`, parent/socket mode0700, data retained under `data`, explicit bootstrap role cj005/database postgres. PostgreSQL16.15 Homebrew, Python3.14.7, test-only psycopg3.2.10 pure Python target-installed inside this private directory; no root lock/global dependency/service config change. Blank task pgpass and explicit connection arguments; inherited PG*/DATABASE_URL/CJ_DATABASE_URL are refused, never used or printed.

Actual guard query checked data_directory, `listen_addresses=''`, private Unix socket directory and current_user before applying schema. PostgreSQL TCP is disabled; socket identifier55445 only. Real HTTP origin was `http://127.0.0.1:49864`, prebound port0 socket handed to uvicorn, proxy headers/access log disabled. No public listener or target endpoint involved.

Pinned AUTH f3c8e5074eb27de0de6fef6dd7558763cbcf4291 strict profile; MESSAGE cec92299aa77e74baafba473ecf9db7b926fbe4e; all eight runtime blobs exported/hash-checked from fixed Git objects, not moving source. Only candidate SQL from MESSAGE's exact commit applied after confirming empty public tables, SHA256 `44707ea75b7c48ebe8c6f7e51a29099a34bf66ea7ac79d0808de451ee5dd3790`. Its UNAPPLIED comment remains correct for production/shared migrations; this is one authorized task-local application only. CJ009 method/report reused, never its data/socket/venv/instance.

## Actual results

`run.txt` / `result.json`: nine PASS groups (the final group contains four generated Swift assertions, not thirteen separate tests):

1. Real verified private PG first connection and candidate-only empty schema application.
2. Missing verification-key configuration refuses API composition before HTTP bind.
3. Real HTTP POST through actual PyJWT signature/gate/Boundary/Repository: exact original bytea retained, exact duplicate returns same receipt/run, changed bytes409, exactly one receipt/delivery pair.
4. Two synthetic server-mapped subjects query distinct SQL scopes; no caller scope/owner. This is partition behavior, **not production RLS or real membership proof**.
5. Actual PostgreSQL COMMIT succeeds, then connection wrapper injects lost-ACK exception once. API503 unknown/reconcile_original; subsequent original-ID HTTP query through a new connection recovers committed original receipt, one delivery. No new-key resend or commit retry; no real packet-loss/exactly-once claim.
6. Synthetic invitation withdrawal at precommit triggers actual PG rollback (zero receipt/delivery). API conservatively preserves unknown/reconcile_original; later query null does not authorize automatic resend.
7. Synthetic return-stage withdrawal occurs after successful commit: API unknown/reconcile_original, rows persist and original query works after synthetic eligibility recovers. This is deterministic stage fault injection, **not DB-atomic authoritative revocation**.
8. Actual HTTP distinguishes input400, invalid JWT401, denied invitation403, bytes conflict409, size413, media415 and unknown503. Missing configuration has no fake principal/repository/accepted receipt. Claims saying invited do not override synthetic server policy.
9. Actual official-generated Swift CJAPI + URLSession sends original bytes twice and reads the original receipt, queries opaque `swift +/%&é` ID, reads explicit-null absence and safely rejects missing receipt. `generated-client.txt`: four assertions PASS.

The missing-field negative is explicitly a **test-only response mutation**: request first passes the real API/gate/PG query, then the harness removes receipt from that successful response and adjusts Content-Length. Swift asserts HTTP200 plus actual ClientError underlying keyNotFound(receipt), so network failure/denial cannot masquerade as this pass. This is not a new product route/header behavior, nor a naturally malformed production response. No alternative wire model: Swift reads actual generated receipt enum and checks container.value == nil for null.

RSA private key generated and retained only in Python memory; synthetic JWT/control/raw bytes passed to Swift over stdin, never arguments/files. No token/body/error-object interpolation in logs. Swift stderr is intentionally not persisted because a runtime ClientError may retain operation input; safe stdout kept. Test member/email/invite facts and issuer are explicitly synthetic, **not a real permission/provider/session source**.

## Reproduction, stop and preservation

Fresh authorized clone/environment only:

```sh
./scripts/run-loopback-pg.sh /path/to/CJ007-git-repository /path/to/CJ009-git-repository
```

Current entry first refuses any existing `.local-cj005-pg` path (including symlink), builds the generated Swift consumer, then runs the fresh-cluster harness. The actual successful run executed the same build helper immediately before the runner; afterward the wrapper only combined those already executed steps and added early reuse refusal. Syntax and existing-directory refusal were checked without restarting services; `reuse-refusal.txt` exits2. No full 9+4 rerun merely for wrapper/report edits. A fresh independent validation must use a separate authorized checkout, not remove/reuse this retained cluster.

`pg-stop.txt` records successful fast shutdown. `preservation.txt` independently verifies no owned HTTP connection accepted, no task postmaster.pid/socket, data retained. Full init/install/PG logs and candidate SQL remain in private directory; committed logs/result/hash manifest contain no key/token. No runtime failure occurred in this slice; deliberate unknown/denial/malformed/reuse failures are identified above. Prior nullable-generation failures remain in the earlier fixed candidate's evidence, not overwritten.

Data directory is excluded with one clone-local `.git/info/exclude` rule; root .gitignore and other user state unchanged. No cleanup deletion, host service stop, DNS/VPN/security/provider setting or old VP connection. hashes.json records test sources, client binary and retained raw-log/SQL hashes; run result source_head is the product source312a69c, while these new test bytes are fixed in this candidate.

Limits: local plain HTTP only, not C2 device HTTPS. Bootstrap local trust/superuser is task-only; real identity/RLS/grants, external JWKS/OAuth/SMTP, authoritative member/invite/session storage, atomic revocation/concurrency, production provisioning/retention/cleanup/backup, physical device, deployment and full acceptance remain UNRUN. Independent Review/Testing pending; no Issue closure/push/merge/deployment.
