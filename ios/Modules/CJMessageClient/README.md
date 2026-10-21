# CJMessageClient — local recovery core candidate

Owner: CJ009; exclusive `ios/Modules/CJMessageClient/**`. Parent source
`9e2a7e3cfe89cccabb691c5febe9e74938c6b1ee`. No CJShell/CJAuth/root project/generated
client changes. Self-contained Swift6 package using platform Foundation/CryptoKit;
no third-party package, network, endpoint or second OpenAPI. iOS17/macOS14 manifest
platforms are engineering baselines, not a product support declaration.

## Original action and recovery

Host supplies the original UTF-8 Data and stable message ID once, before first send.
The package never builds/re-encodes server JSON, creates replacement message IDs,
changes bytes for language, or derives authority from payload. `stage` preserves exact
bytes; same ID/different bytes conflicts and the same raw body cannot be re-keyed.
ID dictionary keys encode exact UTF-8, avoiding Swift canonical-Unicode equality aliases.
The future generated transport must validate that body and ID correspond to its fixed
wire schema before staging; staging is not server schema validation or acceptance.
No semantic-equivalence inference detects a caller deliberately inventing an entirely
new body/ID; this package exposes no automatic retry/re-key workflow.

`beginSubmission` atomically persists queryRequired BEFORE returning bytes to transport.
Thus only the first staged action can produce a submission; a crash before actual send
may conservatively require query. Unknown result, commitUnknown and lost ACK stay
query-only. Query null becomes notObserved, never authority for another POST. Only a
current operation with matching original ID/digest accepts an opaque receipt. A later
transport must decode/verify the official receipt first; this package defines no wire
receipt type. Accepted records cannot be downgraded by duplicate/old callbacks.

Drafts remain separate from staged actions; edits/language changes do not modify any
original action or implicitly clear a newer draft. No automatic deletion/TTL policy.
A fresh recovery instance reloads original bytes, ID, draft and receipt/uncertainty.

## Local lifecycle boundaries

All transitions are synchronous MainActor operations with no await. Host captures an
Operation before network await and passes it back afterward. Instance UUID + local
activation generation + latest per-action operation nonce reject old instance/account/
environment/same-account-relogin and out-of-order results before display/persistence.
`invalidate` immediately removes visible state/leases, without claiming server rollback
or deleting durable original-action evidence. Local generation is NOT a server session
revision or authentication claim. Host must invoke it on logout/switch/authoritative
invalidation and hide private views when identity/eligibility is unknown.

Explicit `activate(scope)` is only a local storage operation and must be called by a
trusted verified host after its gate permits private access. It does not authenticate
an account or automatically restore a session. Session interface consumption and gaps:
[AUTH-CONSUMPTION.md](AUTH-CONSUMPTION.md). No real account mapping has been invented.

## Storage and keys

`SecureMessageStorage` is mandatory; no implicit in-memory/UserDefaults fallback.
`EncryptedFileStorage` requires external `MessageEncryptionKeyProvider`, rejects missing
or non-256-bit key, and uses CryptoKit AES-GCM with scope/version as authenticated data.
The account/environment partition also determines the hashed filename; encrypted data
cannot be swapped between scopes even if a test provider supplies the same key.
No plaintext message/draft temp files, logs, key derivation from credentials, or real
Keychain access. iOS write uses completeFileProtection; that platform branch is UNRUN.

Writes atomically replace a sealed snapshot. Any save error invalidates current visible
state and requires reopen/readback; a write may have succeeded, so no blind retry or
in-memory success. Decode/decryption/corruption/permission errors do not become empty
history. Only an actual missing file can represent no local snapshot, and even that
requires the external key to be available. No remote result is inferred from local absence.

Host supplies an app-private resolved 0700 directory and enforces one writer per scope;
files are set 0600. No multi-process locking/lease protocol is provided. Symlink targets
are rejected at checks; protection against an adversarial process racing path replacement
is not claimed. Atomic Foundation writes and the process-reopen test are not fsync/power-
loss proof. Size/retention/backups/key rotation/deletion and rollback of old valid encrypted
snapshots need the approved storage/cleanup lifecycle; this package does not supply an
anti-rollback monotonic authority or claim full cleanup. Host must bound inputs/storage.

## Tests and current result

`swift test --package-path ios/Modules/CJMessageClient` (9 Swift Testing cases). Some
sandboxes require the normal tool approval to run SwiftPM manifests; local caches were
redirected into `.build`, without globally changing configuration. Full command and
attribution are in [evidence/REPORT.md](evidence/REPORT.md).

Test-only executable `CJMessageRecoveryProbe` runs in two distinct processes with an
externally generated synthetic temporary key: write original action/draft, exit, then
reopen/recover/query-null and reject another submission. Its key-file provider lives
only under Tests, is not exported in the library, and must never be a production key
provider. All data are synthetic, with no real credentials and no network calls.

Core PASS does not prove generated transport, actual AUTH/Keychain host integration,
iOS device file protection, CJShell behavior, real service or independent acceptance.
No existing PG suite rerun. Issue10 remains open; early core is ready for fixed-head review.
