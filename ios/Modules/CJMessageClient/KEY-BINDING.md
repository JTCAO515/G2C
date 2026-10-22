# Message storage v2 + read-only official key adapter

Delta parent c3ddf31f4f8fac04879003f2d4d3af5285f25a2e. Fixed official interface
CJ007 f1ce075e4b3f26e6c65bfe4b2fa8bcec8291a552, CJ-MESSAGE-KEYS@0.1.0-rc.1.
`scripts/prepare_keys.py <CJ007 git repo>` exports that exact interface blob into ignored
.generated/CJMessageKeysInterface with a compile-only manifest; hash recorded in
key-interface-pin.json. No moving implementation, duplicated official types or Keychain
operations are consumed. Product integration must use the official CJMessageKeys product.

## Explicit format/version and incompatible old storage

New envelope bytes: ASCII `CJMKEY02` (8 bytes), canonical UUID string key ID (36 bytes),
then CryptoKit AES-GCM combined sealed box. Authenticated data is the existing exact
scope/version binding PLUS the complete 44-byte header. Key ID is public metadata, not
key material; altering it even while supplying the same AES bytes fails authentication.
Local encrypted Snapshot version1 remains inside ciphertext, unchanged.

Read parses the header, calls existing(expectedID: recorded UUID), verifies returned ID,
then authenticates/decrypts. Missing key and provider UNKNOWN/error never mean empty
history. Save first verifies any existing envelope and ciphertext; it refuses legacy,
corrupt or mismatched content before replacement. A fresh missing file only permits
lookup of an ALREADY EXISTING key; no create or inferred confirmedEmpty action exists.

Old e58dba3/c3ddf31 headerless encrypted format has no provable key ID. Load/save return
legacyStorageFormat and preserve exact old bytes. There is NO automatic migration,
header stamping, key guessing, overwrite, rotation or deletion. Earlier synthetic
process-fixture-01 is retained untouched. Any later migration needs explicit evidence
of the original key binding and a separately reviewed path; this is a breaking local
candidate storage/provider API change, not a change to network MESSAGE wire.

## Adapter and host obligations

ExistingMessageKeyAdapter directly implements CJMessageClient's storage provider using
official CJMessageKeys provider. Host must explicitly supply BOTH local StorageScope
and official MessageKeyNamespace; provider.namespace must match. It does not derive
UUIDs from strings, assume slot/account equivalence, convert session material or grant
authentication. Namespace uses official environment/account UUID + localMessageStorageV1.

The adapter performs begin(.lookup), isCurrent, existing(expectedID:), then rechecks
operation, namespace and expected key ID. It never calls create/reconcileCreation/clear/
reconcileClear, never retries unknown, and never caches returned key material. Key
material wrappers redact description/reflection. Missing returns nil only as supplied
by official existing; storage then fails keyUnavailable. No plaintext-key fallback.

Host must invalidate MessageRecovery BEFORE session clear/account change and invalidate
the key adapter/provider; clear failure keeps both inaccessible. Adapter.invalidate
permanently closes the adapter; it cannot itself discover an unrelated SessionLifecycle
failure or erase MessageRecovery plaintext. Actual host event wiring is still PENDING,
not silently claimed by this isolated bridge. No automatic key clearing on ordinary logout;
retained ciphertext still needs its original key. Network unknown preserves original
records and must not lead to create or a new ID. Key lifecycle is separate from business
eligibility and message UNKNOWN recovery.

## Checks and limits

Swift6.4/macOS: 13 tests PASS (9 storage/core regression +4 key binding/adapter cases),
evidence/key-binding-tests.txt. Tests use @testable constructors only in a synthetic
provider for the exact official interface; production adapter cannot construct official
keys/operations. Tests cover expectedID forwarding, header substitution with same AES
bytes, legacy preservation, explicit host mapping mismatch, missing/unknown, no create,
invalidation and account/environment fencing. No real key/provider implementation tested.

Fresh process-fixture-02 uses a new random externally provided synthetic key and fixed
synthetic ID: independent write/read process runs PASS in key-v2-process-*.txt. Old
process fixture/data untouched. File format changed, so process evidence was actually
rerun for v2. Initial test #require inner-try compile correction did not weaken assertions.

Real Keychain/entitlement, official implementation once-consumption behavior, full host
lifecycle wiring, key creation/cleanup, device file protection, power-loss/backup rollback,
independent review and service acceptance remain UNRUN. `isCurrent` after successful
existing must mean binding current (not merely unconsumed); implementation consumer
check will be repeated when CJ007 supplies a fixed implementation. Current fail-closed
adapter would reject a false result rather than authorizing stale keys.
