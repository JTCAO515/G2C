# CJ-022 accepted-source combination author evidence

Candidate base: `10e5de961abda7db92024210e934c2d0aace54b3`. Head is the commit containing this report. Existing `24221` and `10e5` histories and all failed evidence remain.

## Fixed inputs and ownership

- Canonical shared generated SDK: `c02cf08e52a0d8ffc2fefac99226654a7e01539c`, original shared owner `540da02`. Same single CJMessageClient/.generated path; no second SDK, schema, wire or generated-product commit.
- AUTH source: `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e`, existing original purpose prep retained. No additional AUTH changes.
- Trip source: `2b2991871ce4e04bd1bfb5a92f3098e01512800a`, parent `b7966a1a95ed3e9b4c701f616693cf7e13d2d313`. Exactly five differing original inputs (Package.swift plus AcceptedTripDetailSnapshot/TripClient/TripPresentation/TripTransport sources) are copied byte-for-byte and committed separately as original-owner prerequisite prep. All other Trip source inputs already match. Hashes in accepted-trip-prep.json. No edits to those bytes, original owner tree, root/shared locks, CJShell or API.
- Local CJOfflineTrip Package.swift declares the original products and existing exact OpenAPI/HTTPTypes dependencies used by the injected test transport. Existing local resolved lock remains byte-identical to 10e5; no new remote versions.

## Executed invocation chain

```
// Original event before queuing work:
request = client.prepareDetailSnapshot(id: "trip1", binding: originalBinding)
// One actual generated getTrip, intercepted in-process for this test:
accepted = await client.detailSnapshot(for: request)
client.validateDetailSnapshot(accepted) // after consumer await
cache = AcceptedDetailSnapshotCache(client: client, accepted: accepted, ...)
// constructor calls validate + withCurrentDetailSnapshot -> exact Data/record/trace/binding
// capture is pure in that read closure; namespace comes from original binding/record
receipt = cache.writeOnce()
// original source entry guard -> canonical expectedID lookup -> AES.GCM full metadata AAD
// -> original handle final source guard -> exact original-file check -> atomic ciphertext write
// -> source/session/provider and exact stored-byte check -> receipt
```

The production module imports only public Trip/CJAPI/AUTH products. It never calls detail with arbitrary caller IDs to assert acceptance and never reconstructs response bytes from a record. Tests use `@testable CJTripClient` **only** to inject its accepted existing in-process transport initializer; accepted handles and source reads themselves use the public hook. Actual canonical provider/session implementations consume only task-private in-memory persistence doubles. No SecItem, real network/account/provider, real cache path or real cleanup is invoked.

The original response deliberately contains leading/trailing whitespace and escaped Chinese Unicode. Reopened ciphertext gives exact-equal original Data and the same formal version/namespace/hash, rather than reencoded display JSON. Source sync/deadline inputs are explicit synthetic values, not production policy.

## Results

PASS: 9 new Swift Testing functions in AcceptedSourceTests (`accepted-source-final-tests.log`):

1. Exact public accepted bytes → canonical dedicated key/expectedID → private encrypted file → exact original bytes; one GET, no POST/key mutation; duplicate capture write denied.
2. Original handle retired after consumer await cannot create a cache capture.
3. Selection changes during network await produce no accepted source or cache.
4. Provider/last binding callback prepares a newer source; old capture fails before write; newer handle writes, and the old capture cannot overwrite it.
5. Provider callback changes original session operation; cache write denied.
6. Final source callback replaces file bytes; those bytes are not overwritten.
7. Unknown post-rename write blocks retry/new capture before lookup or new nonce; exact attempted bytes reconcile without modification.
8. Await between capture construction and write, then source retirement, causes zero key lookups/writes.
9. Post-rename file callback retires source; no success receipt or resend, existing ciphertext preserved rather than guessed absent/restored.

PASS: unsigned generic iOS Simulator-target module compile (`accepted-source-ios-build.log`), including actual imported Trip/AUTH/SDK dependency graph. No simulator boot/launch/install/device result. `--skip-update` deprecation warning is retained; no dependency resolution change was needed.

Prior format/clock/file-fault 9 and canonical key 9 (+2 affected old unknown-write) evidence remains valid and is reused, not rerun. Existing key fixture helpers only change file visibility for reuse; their behavior is unchanged. Initial new-test compile failure from ambiguous internal `digest` is retained (`accepted-source-initial-compile-fail.log`); qualifying CJOfflineTrip.digest fixed it. The seven-case first run is also retained separately.

## Business gates remain closed

`SnapshotCodec.appFactoryAvailable == false`. No public App cache factory or plaintext reader. Actual cache root, approved offline-session permission, production TTL, trustworthy time/rollback anchor, protected-file device behavior and CLEANUP/logout/reconnect integration remain unimplemented/unverified. Key purpose existence and local source acceptance do not supply any of these. Real accepted Trip sync, real users, Keychain, physical-device offline/reopen/account switching/remote revocation, UI, provider, deployment, independent Review/Testing and complete Issue24/I acceptance are not claimed. No push/PR/merge/deploy or Issue closure.
