# CLEANUP-DEVICE@4 — provided Memory erasure and candidate journals

Frozen additive interface for the actual merged A480 and A482 consumers blocked at
[#468](https://github.com/JTCAO515/G2C/issues/468#issuecomment-6600840638) and
[#460](https://github.com/JTCAO515/G2C/issues/460#issuecomment-6602206243).
Replaces DEVICE3 for new App activation using those journals. DEVICE3 retains
the A453 consumer until A adopts this version; its requests, target set and
original-record recovery remain unchanged. DEVICE1/2 have no current new App
consumer and receive no new adapters or tests.

The six DEVICE3 paths/fields and exact original action/SHA semantics in
[DEVICE-V3.md](DEVICE-V3.md) apply with `/v4` and
`version:"CLEANUP-DEVICE@4"`:

| Method | Path | Credential |
|---|---|---|
| POST | /v4/cleanup-devices | ordinary Bearer |
| GET | /v4/cleanup-device-registrations?action_id=...&input_sha256=... | ordinary Bearer |
| POST | /v4/cleanup-device-calls | original Device |
| GET | /v4/cleanup-device-call-actions?action_id=...&input_sha256=... | original Device |
| GET | /v4/cleanup-device-calls/{invocation_id} | original Device |
| POST | /v4/cleanup-device-receipts | original Cleanup receipt capability |

Registration POST fields are `version,action_id,device_id,state_ref`; call POST
fields `version,action_id,binding_id,reason`; receipt POST fields
`version,action_id,operation_id,invocation_id,binding_id,request_digest,outcome`.
No caller-supplied owner, root, target, account operation or key selector is
accepted. Exact original action bytes/hash must be durable before dispatch;
lost ACK recovery uses only the original GET, never an inferred retry/new ID.
Wrong version/binding/purpose/hash, duplicate/extra fields or expired capability
reject. Device calls do not grant business access after account retirement.

Account cleanup and session invalidation include the unchanged nineteen
DEVICE3 targets plus exactly two indivisible paired-family targets:

| Added target | Exact provided scope |
|---|---|
| device-cache/memory-erasure-pending | M.erasure-v1 (AD CJMemoryErasurePendingV1) AND M.erasure-v1.CJMemoryErasureObservationsV1 (same AD name) |
| device-cache/memory-candidate-pending | M.candidate-v1 (AD CJMemoryCandidatePendingV1) AND M.candidate-v1.CJMemoryCandidateRejectionsV1 (same AD name) |

M is `G2CDevelopmentMemory/<environment>/<account>`. The files are
`sha256(action_id).memory`, with existing UUID.memory compatibility. Both use
the existing `localMemoryPendingV1` purpose/key UUID. A owns native resolution
and receipts: `MemoryErasurePendingStore.clearLocalFiles()` and
`MemoryCandidatePendingStore.clearLocalFiles()` each precheck and clear their
own two exact directories together, keylessly, then fsync and read back. Each
original target/intent authorizes its entire family before physical work;
neither directory can be selected alone and neither family authorizes the other.
There is no separate observations/rejections target and
no unrecorded second-target side effect. Persist the original family intent
before calling its handler; confirm it only after both directories verify
empty. Partial/uncertain work stays UNKNOWN under that same original action,
without inventing a new action or repeating an uncertain write. The primitive
does not create a key.
Before clearing `device-cache/memory-key-keychain`, prove all four added roots AND
all existing manual/lifecycle/typed/history roots empty; preserve foreign scope
and original identity fences. Only an actual authenticated own-device report
covering each target can complete that device/state group. A DEVICE3 report
cannot prove either new family target, even when the other nineteen are confirmed.

`offline_expired` retains exactly DEVICE3's three offline targets; it does not
clear unrelated Memory journals. Offline maximum remains fourteen days since
last successful sync; reconnect retirement uses the original invalidation
operation. Network/503 UNKNOWN never resets that clock or implies deletion.

Use [DEVICE-COMPLETION@2](DEVICE-COMPLETION-V2.md) to read a DEVICE4 call's
restricted original completion. CLEANUP-API@1 account interfaces are unchanged.
Original DEVICE3 credentials/operations are not upgraded or relabeled. A new
DEVICE4 registration is an explicit original action; registry drift keeps an
older frozen account operation blocked rather than silently expanding it.

Positive: a DEVICE4 original registration/call is recovered by exact action/SHA,
its real report covers all21 targets, and the same original call is queried.
Negative: old DEVICE3-only group, incomplete/unknown report, wrong key/state,
nonempty sibling or unavailable native handler remains unknown/blocked; never
report confirmed from Python metadata. Only the A480/A482 roots actually merged
and provided above are registered; future roots require their own actual evidence.
No provider/account/backup/all-device erasure claim; real evidence stays
#32/#29/#30 and backup retention remains thirty-day rolling.
