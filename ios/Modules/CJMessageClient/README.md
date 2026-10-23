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

Transport delta: see [TRANSPORT.md](TRANSPORT.md). CJMessageHTTP now consumes exact
CJ005 d886677 CJAPI through an ignored fixed export (prepare script required). Receive
interception checks pass; generated query lacks receipt and explicitly blocks query
until CJ005 correction. This does not change the earlier core-only evidence attribution.

Storage delta: [KEY-BINDING.md](KEY-BINDING.md) defines authenticated `CJMKEY02`/key-ID
format and read-only fixed official key-interface bridge. Old headerless candidate files
are explicitly refused and preserved, without migration or key guessing. Run both prepare
scripts before a fresh build. 13 targeted checks and two separate v2 test processes pass;
real Keychain and host lifecycle remain pending.

Activation gate: [ACTIVATION-GATE.md](ACTIVATION-GATE.md) now treats every reloaded
staged action as query-only. Since entire-snapshot rollback cannot be detected locally,
live POST is explicitly unavailable; only named synthetic interceptor composition can
exercise submission. Key-ID authentication is not freshness or production activation.

Query consumption update: fixed CJ005 `312a69ca` replaces the d886677 query blocker.
[evidence/QUERY-CONSUMPTION.md](evidence/QUERY-CONSUMPTION.md) records exact generated
branches and 10+2 checks. Only explicit null is notObserved; live POST remains disabled.

Once-only local authority: [FRESH-AUTHORIZATION.md](FRESH-AUTHORIZATION.md) documents
private nonserialized first-attempt permission and same-process rollback/reentry denial.
27 affected checks plus one overlap check pass; no global rollback guarantee or live
POST activation follows. Draft and original-action state remain separate.

Local recovery enumeration: [LOCAL-PROJECTION.md](LOCAL-PROJECTION.md) exposes current
scope/Lease-bound action ID/phase and draft references only. Complete unordered local
projection, no payload or invented server sequence; six targeted checks pass. Revalidate
after await before display. It grants no new sending or server-history authority.

Read-only server projections: [HISTORY-READ-CLIENT.md](HISTORY-READ-CLIENT.md) exposes
fixed official 2f8 CJAPI conversations/history/draft GET consumption with lease-bound
results/opaque continuation. Seven new +three affected prior checks pass; no draft PUT,
no live POST activation, no actual network or host integration is claimed.

Draft PUT candidate: [DRAFT-PUT-CLIENT.md](DRAFT-PUT-CLIENT.md) provides intercepted-only
original-byte CAS saves with encrypted pending records, query-only uncertainty and
editor-revision confirmation. Nine new +three affected checks pass. Live PUT/POST remain
disabled; equal GET content or null never grants replacement PUT authority.

Formal main integration correction (base3c52f72): CJMessageKeyBridge now depends directly
on ../CJAuth's official CJMessageKeys product. Do not run prepare_keys for the main graph;
that old standalone interface-export harness is historical only and no longer a dependency.
prepare_generated remains required for the pinned official CJAPI export. See
evidence/KEY-DEPENDENCY-MAIN.md for exact interface identity and graph/consumer evidence.

Shared API export update (base main23e12f2): prepare_generated now pins official57336d50,
including required non-Generated MemoryClientConfiguration.swift. The ONE shared path is
.generated/57336d501e5691302a3d5e9770f07666d1c57d4a/CJFoundation for all consumers.
Formal CJAuth key dependency and SDK versions remain. Standalone31 checks pass; full
CJShell graph awaits CJ006's same-pin update. See evidence/MEMORY-API-PIN.md.

Next shared API candidate: official9dc67ced adds five generated Trip operations at the
single .generated/9dc67ced50a0cb7611a84b4adf97ab0b43c88bea/CJFoundation path. Prior d0/573
commit and exports stay intact for current delivery. Old interfaces/SDK versions remain;
standalone32 checks pass, while Trip activation/full App same-pin integration remain
pending. See evidence/TRIP-API-PIN.md; no other consumer should create a private CJFoundation.

Next shared NEEDS candidate: officiald688c01 adds four operations at the ONE
.generated/d688c01dc0fb18488a1e9c49414a039ce0126204/CJFoundation path. Old9dc/573 exports
and4fb remain intact. Standalone35 checks and one-package graph pass; NEEDS business
activation/full App common-pin integration remain pending. See evidence/NEEDS-API-PIN.md.

Next shared Feedback candidate: official201156c9 at the single
.generated/201156c9bf9850f9b8e87dc1f986452ce1ae789f/CJFoundation path adds generated
Feedback methods/types while preserving NEEDS and prior interfaces. Standalone38 checks
pass; old d688/9dc/573 exports remain. Current d688 App delivery and future common-pin
activation are separate. See evidence/FEEDBACK-API-PIN.md; no business POST is enabled.

Next RUN display shared candidate: officialc02cf08e at the single
.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation path. Standalone41
checks pass with exact old-interface/SDK compatibility; prior exports remain. No real
RUN request or App pin switch, and no69d/b868 HOLD resolution is implied. See
evidence/RUN-DISPLAY-API-PIN.md for limited GET/codec evidence and remaining gates.

Next readonly manual-preview export: fixedc5ffafb at the ONE
.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation path. Three new plus
three targeted old checks pass; prior full business evidence reused. Preview remains
LOCAL/UNKNOWN/not-save and generated can_save Bool needs explicit consumer rejection
of true. No POST execution or App pin switch. See evidence/MANUAL-PREVIEW-API-PIN.md.

Readonly preview transport opt-in: READONLY-PREVIEW-TRANSPORT.md defines the narrow
readOnlyManualPreview factory for the official c5 operation/path, with explicit endpoint,
timeouts and current-lifetime validator. Generic live POST/PUT remain closed; this is a
readonly computation capability, not a Trip save permission. Eight local checks pass;
CJ017 adoption and actual service remain separate.

Next USAGE status export: fixed9d0f4b4 at the ONE
.generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7/CJFoundation path. Six targeted
checks pass; exact count strings/null retained, no balance or execution authority.
Old exports stay intact, active App graph unchanged. See evidence/USAGE-STATUS-API-PIN.md.

Next original-usage association export: fixed33cec5ba at the single
.generated/33cec5ba71d74820cb0acd3c89ecbe39ba125590/CJFoundation path. Five targeted
checks pass; required association and unavailable503 never become successful null or
execution evidence. Transport94 and all old exports stay intact. See
evidence/ORIGINAL-USAGE-API-PIN.md; current App and USAGE client are not changed here.

Next current-account cleanup progress export: fixedf87a78a9 at the ONE
.generated/f87a78a9d8984c59905e385483f17dddd8144d8a/CJFoundation path. Five targeted
checks pass, old exports/Transport94 stay intact. blocked/unknown/unavailable are not
delete completion; no cleanup or postlogout capability is enabled. See
evidence/CLEANUP-PROGRESS-API-PIN.md; current App graph remains unchanged.
