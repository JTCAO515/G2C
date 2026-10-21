# Rollback gate: no live POST activation

Delta base 6aef735ce7b2ab595cdd6071840f9bc50186d083. Fixed old authentic ciphertext can
restore an earlier staged action: AES-GCM integrity and key-ID binding do NOT establish
freshness. A synthetic encrypted replay reproduced two failing assertions in one test
before repair (evidence/rollback-before.txt); original bytes/key were valid, not corrupted.

## Minimal implemented conservative policy

Every action loaded from storage with phase staged is changed IN MEMORY to queryRequired
before activation returns. No rewrite/delete/key change is used to mask the older file.
All subsequent saves retain that conservative state. It also applies to truly unsent
staged records after reopening: the local snapshot cannot distinguish those cases.
The original ID/bytes remain intact and only query is allowed. A notObserved response
still cannot authorize a POST. There is no “retry with new ID” fallback.

This cannot detect a snapshot rolled back before the action existed, a missing entire
file, or a malicious host constructing a new action. Therefore the concrete live HTTP
composition has NO POST activation: MessageHTTPClient's liveReadTransport initializer
rejects submit before obtaining credentials or producing a submission; NoRedirectTransport
also refuses POST before URLSession sends. No configuration boolean or permissive default
opens this gate. A later fix requires separately reviewed authoritative evidence.

The explicitly named interceptedTestTransport initializer remains available ONLY for
non-network synthetic interceptors. It is not a production activation path. A host that
intentionally injects an unrelated live ClientTransport through this test seam violates
its contract; this library cannot sandbox arbitrary trusted host code. Product hosts
must use liveReadTransport and cannot treat interceptor test success as send readiness.

## Evidence needed before opening live POST

A fixed source of non-rollbackable original-action/epoch evidence bound to verified
account/environment must establish first-send authority and preservation across restart,
backup restore, credential/key lifecycle and unknown writes. It needs exact ownership,
lookup/write/unknown semantics, failures and affected recovery tests. Such an authority
is not currently provided by CJSession, message keys or encrypted snapshots; no new
ledger/schema/framework is invented here. Do not infer freshness from a new key or erase
original messages to obtain “empty” state. Actual server readback/notObserved alone does
not resolve retention/recovery uncertainty under the current wire contract.

## Results and limits

PASS: 8 transport checks + 1 actual old-ciphertext replay test on Swift6.4/macOS;
evidence/rollback-after.txt. Old persisted staged becomes queryRequired; live submit
fails before credentials, direct live transport POST fails before outflow; intercepted
original-byte path remains testable. No genuine network request/credential or Keychain.
Existing key/PG/AUTH evidence reused; no full old suite rerun. No data deletion, key
rotation or new backend authority. Independent acceptance and actual anti-rollback
storage/production POST remain outstanding. Read-only query is still separately blocked
on the known d886677 generated receipt omission until fixed CJ005 source arrives.

Query-only update: fixed CJ005 312a69ca resolves the generated receipt omission; its
query decoder/transport is now wired with actual-null validation. The LIVE POST gate
in this document is unchanged; neither a receipt query nor null is anti-rollback evidence.

Process-local strengthening: FRESH-AUTHORIZATION.md adds a non-Codable once-only permit,
pre-save reservation/consumption and denial memory across coordinator replacement. It
blocks known-action restaging after same-process clearing/replay, but cannot detect a
wholly absent action after process restart. Live gates above are unchanged and closed.
