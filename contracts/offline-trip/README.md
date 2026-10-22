# CJ-022 offline snapshot candidate v1

Scope: isolated format/codec, private atomic file primitive and pure validity evaluator. No App factory, key provider, live cache path, wire route, offline write queue, or Memory writeback. Issue24 stays open. Source base `8deb696f8149b4f5aa70c767be6c3a263b036227`.

## Source and format

Only official `Components.Schemas.TripDetailResponse.TripRecord` from canonical c02 CJAPI is decoded. Module-internal capture validates request_id, exact response/record/document shape, duplicate keys, IDs, unique items, original UTF-8/base64, document equality and positive version. It preserves complete response bytes and exact canonical content bytes; it does not regenerate content. Proposal/null/unknown fields/malformed documents fail. This is structural validation, not proof of server acceptance: existing TripClient.detail returns a typed record without raw response bytes. The trusted accepted-response byte hook and session generation fence remain with the original Trip/API owners. No public capture/seal/open/store constructor is exposed. No public plaintext property is exposed.

Envelope v1 is JSON {metadata,ciphertext}; ciphertext is CryptoKit AES.GCM combined nonce/ciphertext/tag (random nonce per seal), 256-bit injected test key only. Sorted JSON encoding of *all* metadata is AAD: format, exact canonical source pin, account/backend/trip, formal version, syncedAt/deadline, boot/uptimeAtSync, original response/content SHA256, and expected keyID. Unknown format/source fails with no legacy fallback. Hashes are checked after authenticated decrypt. Decode never tries another key/version. Maximum response 2 MiB, envelope 4 MiB; these are local format bounds, not server contracts.

Rollback rejection requires an authoritative caller-supplied minimum formal version; a self-contained encrypted file cannot detect replay of an older valid file without an independent anchor. The evaluator requires positive minimumVersion. This module does not invent a persistent AUTH anchor or grant offline authorization.

## Files and unknown writes

The store opens every absolute path component using directory descriptors and O_NOFOLLOW; it does not resolve attacker symlinks. Callers supply an existing physical path. Test directories are new 0700 directories under realpath(NSTemporaryDirectory). It rechecks root device/inode/owner/mode before/after operations, rejects symlink/hardlink/nonregular/oversized/empty/non-0600 entries, bounds reads and detects named-file replacement and size/mtime/ctime changes. Writes use unique O_EXCL 0600 temporary files, full write+fsync, renameat and directory fsync, then exact-byte readback. Only ciphertext reaches disk. No recursive cleanup.

After an uncertain rename/fsync/readback, the same store retains original and attempted **ciphertext bytes**. New writes/clear are blocked. Reconciliation reads the fixed entry and compares with those original bytes, returning committed/originalRetained/unknown; it never reseals or restores old bytes. Process-crash durability of an unresolved operation receipt is not claimed. A same-user compromised process can race file operations; inode checks/authentication detect observable changes, not malicious-OS control. Local clear removes only this entry; it is not global logout/remote/device cleanup. iOS protected-file class and device-lock behavior remain unintegrated/unverified; no production cache is enabled.

## Validity and product gates

No TTL default. Policy absence/invalidity => unavailable. Sync time and authenticated deadline are explicit; effective deadline=min(snapshot deadline,sync+configured maximumAge). Equality with deadline is stale. Integer overflow, future sync, absent/untrusted time, wall rollback, invalid uptime, same-boot uptime rollback, absent last trusted time, wrong account/backend/trip, stale formal version or session denial => unavailable. Same-boot elapsed monotonic time can expire a snapshot even when wall time stalls. Reboot permits evaluation only with fresh host-trusted wall time and last-trusted anchor; system wall time alone is not such authority. Host must recheck current identity/session/selection after async work and immediately before display. Larger future policy cannot extend the snapshot's authenticated deadline. Results only evaluate supplied policy/clock; they do not authorize offline access. Public result carries version/syncedAt/deadline or stale/unavailable; both languages refer to the same snapshot, no regenerated translation.

Exact minimum integration inputs still needed:

- CJ007 canonical dedicated offline-snapshot key purpose (not localTripPendingV1), namespace mapping and lifecycle operations with expectedID bound to authenticated metadata; missing key is unreadable, never create/rotate/migrate/recover automatically.
- CJ007 trusted active account/backend/session generation and approved offline-session policy/clock/rollback anchor. No JWT-derived identity.
- CJ024 canonical cleanup signature/settlement and lifecycle fence for logout, account/backend switch and reconnect invalidation. Do not invent a second cleanup protocol. No cross-device immediate erase claim.
- CJ015/CJ005 accepted formal detail byte hook and trusted source identity/version; CJ006 read-only container after those interfaces are fixed.
- JT's production offline duration and remote revocation boundary; no numbers in this candidate constitute policy approval.

## Validation

Run `python3 ios/Modules/CJMessageClient/scripts/prepare_generated.py <fixed-source-repo>` then `swift test --package-path ios/Modules/CJOfflineTrip --skip-update`.

Shared prerequisite is exactly three unchanged files from CJ009 head `540da02a335e96e98917ffd3d94a395f8ca2d892`; see evidence/prep.json. Canonical export is ignored generated output at CJMessageClient/.generated/c02.../CJFoundation. All 16 inputs and original SDK lock match hashes. The initial private .prep copy is retained locally as historical preparation only, ignored and not a product dependency. No generated SDK is committed.

Author evidence: nine Swift Testing functions PASS (including multi-case boundaries); macOS module/test build PASS; iOS17 simulator-target unsigned package compile PASS with SDK27.1 (compile only, no boot/install/run). Generated upstream import warnings retained. Original two file-fixture failures and no-tests-yet build logs remain. Real accepted-trip sync, App/UI, production TTL, trusted clock persistence, real Keychain, protected-file device class, logout/CLEANUP hooks, remote revocation, physical-device offline/reopen/account switching and full I acceptance are UNRUN. Independent Review/Testing pending. No push/PR/merge/deploy.
