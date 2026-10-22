# Durable snapshot exact-byte P2

Parent 4405be101599bcc198d1c406c0d5bf353e413f23. Input: Testing fixed
CJ-009-put-reentry-fix/ReadbackByteIdentityTests.swift and readback-byte-verified.log.
Copied original test unchanged and reproduced 1 test /2 assertions FAIL in
readback-bytes-before.txt: storage persisted generation NFC→different UTF8 NFD, but
synthesized Swift Equatable treated the snapshots equal and allowed an outbound operation.

Fix is 21 lines of explicit equality for the three existing local record types only:
- ActionRecord: messageID compares exact UTF8; originalUTF8/receipt compare Data;
  phase retains enum equality.
- DraftSaveRecord: conversationID/generation compare exact UTF8; originalUTF8 compares
  Data; expected/confirmed revision retain integer equality and editorRevision UUID equality.
- Snapshot: version retains integer equality; all dictionary indexing compares exact
  UTF8 key Data rather than String canonical equivalence, then the above value comparisons.
  Normal indices are ASCII base64; malformed injected indices cannot alias silently either.

No whole-wire textual reserialization, custom crypto, global String behavior change or
semantic-field normalization. Dictionary serialization order remains irrelevant. The
existing nested-save readback guard now sees a different exact binding, invalidates the
original lease and throws persistenceUnknown before any operation/saved result escapes.
No automatic overwrite/retry or key/data replacement; original CAS payload bytes remain.

PASS:7 checks in readback-bytes-after.txt: original mismatch repro; adjacent exact message/
conversation/generation IDs and dictionary keys, raw payload/receipt/revision changes and
order-independent same-value comparison; original2 nested-save regressions and2 unknown/
inconsistent-store checks. PASS:1 additional confirmation-path mismatch check in
readback-bytes-confirm.txt verifies no saved result and preserved original CAS bytes.
Swift6.4/macOS synthetic stores only. Prior 16+3 evidence remains scoped to its original
head; no broad suite/PG/Keychain/network rerun. Transport/read cursor94bad80/live-write
gates unchanged. Independent delta review required; original rollback/host limitations
remain and live PUT/POST are still disabled.
