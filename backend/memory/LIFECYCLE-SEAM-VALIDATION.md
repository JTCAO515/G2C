# Restricted lifecycle seam — author delta evidence 2026-10-23

Base cf6f9138147780de9cd6cd3df86642b0aec6ec5b, initial worktree clean. Read CJ019 domain/service/postgres/contract from fixed6e11d48815259bc3d879e63cd794e37e67694b86 and fixed seam request f5df2c6b4f2b8a41ffb00e3df0e4237e9f772197. No equivalent existing public action apply/query seam; save parsers cannot accept the action format. Only original backend/memory/** and contracts/memory/** edited. No root or CJ019 source changes, no external messages/chats sent.

Code: frozen LifecycleAdapter(action_id,apply,query), fixed internal version MEMORY-lifecycle-adapter.1 registered only by trusted host. Public OperationContext.apply_lifecycle/query_lifecycle reuse original guard, scope lock, transaction, one action ID/original bytes, immutable Receipt and unknown/reconcile metadata. Canonical owner does not parse CJ019 keys or copy lifecycle SQL/business checks. Same-transaction readback validates stored action receipt; adapter identity replacement/reentry/deferred return rejects. No new tables/schema/permissions or general arbitrary executor.

PASS final `backend/memory/.venv/bin/python -B backend/memory/tests/lifecycle_seam_checks.py`:12 methods,0.183s. Read-only git-show copies of exact fixed6e11 modules/schema are hashed into private fixed-manifest.json, imported with current CJ011 source. Test-only repository bridge yields CJ019's existing Transaction on the same supplied cursor/scope and never opens/commits another connection; actual fixed domain apply/query methods are called unchanged.

1. Actual pause/query/replay/resume/history using fixed CJ019; apply and original query receive the identical current tx. Original action UTF8 hash retained; changed-byte same-ID conflicts; query after resume returns original pause result.
2. Fresh precommit UNKNOWN rolls back item state and action receipt; original ID retained, commit_possible=false for this attempt.
3. Actual commit then CancelledError gives original action/reconcile metadata; independent guarded original query recovers disabled receipt.
4. Precommit cancellation remains sticky even when outer callback catches BaseException; state and receipt rolled back.
5. Repository connection close replaces adapter after actual commit; postclose guard withholds and original query recovers committed action.
6. Identity or same-scope repository replacement after encoded action projection is rejected by final guard; original committed action retained.
7. Adapter replacement after mutation but before commit rejects and rolls back.
8. Escaped context/cross-thread query rejects; captured tx cursor closed and subsequent SQL rejected after close.
9. Adapter reentry (even caught) and deferred coroutine result reject without committing action.
10. Action query invokes query only, is scope-isolated, and is subject to fresh precommit guard; no second mutation/apply.
11. Missing adapter or mismatch between apply-returned and stored receipt rejects; newly changed item/action rolls back.
12. One action identity across request; allowed same-ID apply→query, second action rejected and earlier committed action remains original reconcile; missing query does not trigger apply or add a receipt.

PASS three existing no-DB binding tests after the adapter identity condition addition. The cf6 independent13-consumption +3binding and CJ019 original14-PG/restart evidence remain reusable; no old full domain/guard/consumption suites rerun. No uv/install/cache access.

Final new private PG17: role cj011_lifecycle / DB postgres / port56117 / listen_addresses empty / UTF8; data backend/memory/.local/lifecycle-xvlkc8l5/pg; socket /tmp/cj011-lifecycle-jsuuoruu0700; explicit empty task pgpass0600, ambient PG* removed, no DSN/service/old credential inheritance. Own instance stopped in finally, data and logs retained. No previous instance restarted.

First attempt .local/lifecycle-nvy3uuun:11 methods passed, one test ERROR solely because the captured closed connection raised psycopg.OperationalError('connection is closed') while test expected InterfaceError. Cursor.closed was true; actual close behavior was safe. Preserved report/logs, stopped instance. Corrected the exact driver exception assertion (including message), then used another new empty cluster for final12PASS. No product assertion was relaxed and no old instance reused.

UNRUN: independent acceptance of new head; CJ019 production adapter module; root/API/generated client/UI consumption; real AUTH/accounts/provider; text-edit provenance/consent; shared RUN atomic publication or whole Issue17/12 acceptance. The adapter is a restricted trusted-host integration seam, not a sandbox for malicious in-process provider code.
