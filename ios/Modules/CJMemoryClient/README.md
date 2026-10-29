# #228 local App candidate (L1 pending)

The explicit DEBUG iOS Simulator `localEndpoint` initializer uses only loopback,
`NoRedirectTransport`, the existing signed #226 API and the existing encrypted
manual journal. It enables manual save only; lifecycle management and ordinary
public/Release clients retain their previous gates. The host must use the same
account lifetime and explicitly selected server policy choices. No production
factory, automatic recall, lifecycle writes or real-account permission is added.
The historical read-only candidate and its earlier limitations below remain as
provenance; new local acceptance is recorded in #228, never inferred from them.

# Independent lifecycle candidate

Current follow-up adds gated pause/resume/original-action recovery on SDK20aa. See
[MEMORY-MANAGEMENT.md](MEMORY-MANAGEMENT.md) for exact pins, host limits and checks.
The accepted f87 candidate `1734971` and earlier documents below remain preserved.

# CJMemoryClient — CJ011 iOS consumer

Independent domain package for Issue #12. Own source is only this directory. The
CJShell Memory tab/account/language container remains CJ006's responsibility.

## Fixed inputs and integration

- main base: `23e12f28435ab0ddc685d544670564e3fa79db41`.
- Official API: `57336d501e5691302a3d5e9770f07666d1c57d4a`, producer
  `426d337b0647d7770f1716fad83f2e5e724d28e4`.
- CJ009 prerequisite: `d0f396ceaff5a7d51ddc3a623b35e3eef9191412`, imported unchanged
  as `bf8bf5c`. It exports the single shared CJFoundation/CJAPI package, including
  `MemoryClientConfiguration.swift`. This package points to precisely the same
  `../CJMessageClient/.generated/57336d501e5691302a3d5e9770f07666d1c57d4a/CJFoundation`
  path; no second copy or package identity.
- CJ007 prerequisite: `b24cc77c307bbb1dd9c552aeb92a148213534541`, imported unchanged
  as `d7cc48c612326ccd74a5d0fed79cab65a065ee1a`. It adds
  `MessageKeyPurpose.localMemoryPendingV1`. No Message key or token fallback.
- Review own diff from `d7cc48c612326ccd74a5d0fed79cab65a065ee1a`. Prerequisite
  commits belong to their original owners and are not this task's implementation.
  Publish must integrate their accepted equivalents before this package.

In the consumer clone, run the **CJ009-owned** fixed exporter with a repository
containing API commit 57336d5:

```sh
python3 ios/Modules/CJMessageClient/scripts/prepare_generated.py /path/to/fixed-api-repository
swift test --package-path ios/Modules/CJMemoryClient
```

No generated code is edited. `.memory` is used for every official `Client` and
accepts whole/fractional RFC3339 dates. Generated schema types supply the manual
command, receipts, groups, items and response unions. Invalid non-null fallback,
duplicate JSON keys, mismatched trace, malformed item/version/cursor and HTTP
errors are errors, never empty or successful results.

## Host composition

1. Supply a validated `MemoryEndpoint` with explicit request/response byte limits,
   a trusted async credential callback, and a synchronous `currentBinding`
   callback. The binding contains environment/account plus session generation
   and selection generation. These are **local fencing data, not server owner
   authority**. Create a new client per account/store. Call `invalidate()` and
   clear displayed read results on session/selection changes.
2. For pending storage supply an existing private directory (0700, owned by the
   process, canonical non-symlink path), explicit per-record byte/count limits,
   original expected key ID, and official `MessageEncryptionKeyProvider` with
   the exact environment/account and `localMemoryPendingV1` namespace. The store
   only performs provider lookup. It does not create, reset, rotate or clear keys.
   Missing/unknown/mismatched keys and corrupted records fail closed. Host key
   creation/reconciliation follows the existing CJ007 lifecycle and its grants.
3. The public initializer accepts only `NoRedirectTransport` for live **GET**.
   No endpoint, credential, store, storage directory, field policy, key or live
   write permission is defaulted. `save` rejects live composition before storage
   or credential access. The POST capability exists only in a package-internal
   initializer, used by `@testable` in-process transport tests. No public Boolean
   or generic transport can open it.
4. `groups`, `list(limit:after:)`, and `detail` are official GET operations.
   Listing is live item-ID keyset pagination, not a snapshot; every nonempty page
   has the final item ID as its continuation, including the last nonempty page.
   Continue until an empty/null page. Cursors are bound to this client and the
   original binding. Group selection filters loaded items by exact UTF-8 subject
   and status; a partial page is not proof of an empty group or complete count.
5. `pending(binding:)` enumerates durable originals after reopen. Present each
   original operation and call `query(operationID:binding:)`. Receipt null means
   *not observed*, not noncommit and not resend permission. There is no resend,
   body-reconstruction, pending-delete or replacement-ID recovery API.
6. `MemoryGroupsView`, `MemoryItemsView`, `MemoryDetailView` and
   `MemorySaveStatusView` are embeddable sections with explicit unconfigured,
   loading, loaded/empty and failure states. Host owns navigation, pagination,
   current account/language settings, and clearing old account snapshots.
   `MemoryManualForm` owns one form action and is keyed by the supplied binding;
   it also checks current binding/request generation before/after async work.
   Supply permitted `MemoryManualOption` combinations and their understandable
   save-scope disclosures. Empty options remain unconfigured. No personal
   preferences, policies, occurrence times or server authority are invented. Time
   is required explicit display text; blank/whitespace is rejected before staging.
   Form submission is one-use; the original-query button preserves its original
   operation ID. Unknown results must not be presented as a fresh form retry.

## Original operation and storage contract

The manual command is encoded once using the official nine-key type. Its exact
UTF-8 bytes, original operation ID, item ID, inference classification and
SHA256 are persisted **before** async credential acquisition/network dispatch.
Sorted JSON keys do not normalize text; NFD bytes remain NFD. The official binary
POST sends the persisted bytes unchanged. A response can settle only the original
operation/item/hash, version 1, authoritative candidate/active status (inference cannot become active), and
current binding/request generation. Cancellation and errors retain the original.
Reopening never restores one-use write authority; all originals are queried again.

Each `<SHA256 of exact operation-ID UTF8>.memory` file contains a CryptoKit AES-256-GCM combined box
(nonce/ciphertext/tag), with a JSON `MemoryPending` plaintext. Associated data is
UTF-8 `CJMemoryPending|1|<environment UUID>|<account UUID>|local-memory-pending-v1|<key UUID>`.
Expected namespace/key ID come from trusted host configuration, not file metadata.
Legacy UUID-named files remain readable without rewriting; new opaque operation IDs
use a byte-exact hash filename, including distinct NFC/NFD or case variants.
Files are immutable 0600, created with `openat/O_EXCL/O_NOFOLLOW`, synced before
network use; the private directory is held by descriptor. Canonical directory
identity is checked after key and binding callbacks, after write/fsync, and with
the original encrypted record at the transport validation boundary. Displacement
fails without deleting or migrating the original ciphertext. These checks do not
claim protection against arbitrary concurrent same-UID filesystem attacks. Replacement directories,
unknown files, symlinks/hardlinks, oversized records, partial/corrupted ciphertext
and authentication failures do not become empty ledgers. No UserDefaults or
plaintext production fallback exists. The bounded record store intentionally has
no automatic pruning; reaching its explicit bound fails closed pending a separately
specified cleanup policy.

These local files **cannot prove freshness against deletion or restoration of an
older filesystem snapshot**. A missing/rolled-back ledger cannot authorize live
POST. Live write remains closed until an independently authoritative freshness
mechanism and actual write authorization are integrated by the relevant owners.
No local confirmed set, GET permission or receipt-null response removes that gate.

A saved receipt is historical. Its `active` status does not prove current effective
eligibility or that the next answer uses it; current service effective/fence logic
owns that decision. Inference is shown as candidate, never as confirmed fact.
No new wire field or local eligibility inference is introduced.

## Evidence and remaining gates

Latest row identity repair: [validation](evidence/ROW-IDENTITY.md).
Prior four-finding repair: [repair validation](evidence/REPAIR-623.md).
Historical 623 author checks: [validation](evidence/VALIDATION.md), [tests](evidence/tests.txt).
The old 20 PASS did not override the independent four failing cases.
The package's SwiftUI views compile on macOS and the generic iOS Simulator SDK.
Tests use only in-process interceptors, synthetic values and isolated temporary
private files; the official key provider uses test-only injected persistence.
There are no real account/provider calls, Keychain probes, app launches, signing
changes, backend edits, root schema/lock edits, pushes or merges.

Real HTTPS reads, actual private-platform storage lifecycle, CJShell integration,
visual/VoiceOver runtime validation, real manual save, next-answer context,
new-session/device travel use, and independent Review/Testing are **UNRUN** here.
Issue #12 remains open and is not closeable from this package evidence.
